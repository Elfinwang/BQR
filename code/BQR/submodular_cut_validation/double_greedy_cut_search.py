from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

SCRIPT_PATH = Path(__file__).resolve()
BASE_DIR = SCRIPT_PATH.parent
REPO_ROOT = SCRIPT_PATH.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from BQR.rewrite_backends import RewriteBackend, create_rewrite_backend
from BQR.submodular_cut_validation.double_greedy_reporting import (
    build_evaluations_payload,
    build_md_report,
    resolve_md_output_path,
    save_best_sql_and_recheck,
)
from config import DB_CONFIG

def _edge_sort_key(edge_id: str) -> int:
    try:
        if edge_id.startswith("E"):
            return int(edge_id[1:])
        return int(edge_id)
    except Exception:
        return 10**9

def _sorted_edge_ids(edge_ids: Sequence[str]) -> List[str]:
    return sorted(edge_ids, key=_edge_sort_key)


def _sanitize_json_values(value: Any) -> Any:
    """Recursively convert non-finite floats to None for strict JSON output."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize_json_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_values(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize_json_values(v) for v in value]
    return value

def _load_validation_module() -> Any:
    module_path = BASE_DIR / "double_greedy_cut_eval.py"
    spec = importlib.util.spec_from_file_location("double_greedy_cut_eval", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module spec from: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Unify DB config source: always use project-level config.py
    if hasattr(module, "TPCH_DB_CONFIG"):
        module.TPCH_DB_CONFIG = dict(DB_CONFIG)
    return module

_VALIDATION: Optional[Any] = None
_ACTIVE_REWRITE_BACKEND: Optional[RewriteBackend] = None
_REWRITE_EXTRA_CONTEXT: Optional[Dict[str, Any]] = None


def _patch_validation_mask_restore(module: Any) -> None:
    """
    Patch parent-side cut-mask restoration in the validation module.

    The mask must stay attached to the parent side of the cut expression, e.g.
    `ctr1.ctr_state = '__CUT_E1__'`. After Calcite renames that alias, the
    restoration step uses the placeholder condition to retarget rewritten edges.
    """

    def _make_mask_expr(expr: Any, edge_id: Optional[str] = None) -> Any:
        placeholder = f"__CUT_{edge_id}__" if edge_id else "__CUT__"
        exp_mod = getattr(module, "exp")
        parse_one = getattr(module, "parse_one")

        def has_subquery(node: Any) -> bool:
            return isinstance(node, (exp_mod.Subquery, exp_mod.Exists)) or any(
                has_subquery(v)
                for v in node.args.values()
                if isinstance(v, exp_mod.Expression)
            ) or any(
                has_subquery(item)
                for v in node.args.values()
                if isinstance(v, list)
                for item in v
                if isinstance(item, exp_mod.Expression)
            )

        def first_column(node: Any) -> Optional[str]:
            if isinstance(node, exp_mod.Column):
                return node.sql()
            for v in node.args.values():
                if isinstance(v, exp_mod.Expression):
                    found = first_column(v)
                    if found:
                        return found
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, exp_mod.Expression):
                            found = first_column(item)
                            if found:
                                return found
            return None

        def first_column_with_alias(node: Any, alias: str) -> Optional[str]:
            if isinstance(node, exp_mod.Column) and node.table == alias:
                return node.sql()
            for v in node.args.values():
                if isinstance(v, exp_mod.Expression):
                    found = first_column_with_alias(v, alias)
                    if found:
                        return found
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, exp_mod.Expression):
                            found = first_column_with_alias(item, alias)
                            if found:
                                return found
            return None

        def correlated_outer_column(expr_node: Any, outer_alias: str) -> Optional[str]:
            # Prefer correlation keys like `ctr1.ctr_state = ctr2.ctr_state`,
            # which are stable under Calcite rewrite, over aggregated value cols.
            if isinstance(expr_node, exp_mod.EQ):
                left = expr_node.left
                right = expr_node.right
                if isinstance(left, exp_mod.Column) and isinstance(right, exp_mod.Column):
                    if left.table == outer_alias and right.table and right.table != outer_alias:
                        return left.sql()
                    if right.table == outer_alias and left.table and left.table != outer_alias:
                        return right.sql()
                    # Fallback: both sides still bind to outer alias (some rewrites
                    # can collapse inner alias), keep outer-key style column.
                    if left.table == outer_alias:
                        return left.sql()
                    if right.table == outer_alias:
                        return right.sql()
            for v in expr_node.args.values():
                if isinstance(v, exp_mod.Expression):
                    found = correlated_outer_column(v, outer_alias)
                    if found:
                        return found
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, exp_mod.Expression):
                            found = correlated_outer_column(item, outer_alias)
                            if found:
                                return found
            return None

        if isinstance(expr, exp_mod.Not) and isinstance(expr.this, exp_mod.Expression):
            return _make_mask_expr(expr.this, edge_id=edge_id)
        if isinstance(expr, exp_mod.Binary):
            for side in (expr.left, expr.right):
                if isinstance(side, exp_mod.Expression) and not has_subquery(side):
                    # 1) Find the outer alias from non-subquery side.
                    outer_col = first_column(side)
                    if not outer_col:
                        continue
                    outer_alias = outer_col.split(".", 1)[0] if "." in outer_col else ""
                    # 2) Prefer correlated key column (e.g., ctr1.ctr_state).
                    if outer_alias:
                        corr_col = correlated_outer_column(expr, outer_alias)
                        if corr_col:
                            return parse_one(f"{corr_col} = '{placeholder}'")
                    # 3) Fallback to first column with same outer alias.
                    if outer_alias:
                        same_alias_col = first_column_with_alias(expr, outer_alias)
                        if same_alias_col:
                            return parse_one(f"{same_alias_col} = '{placeholder}'")
                    # 4) Last fallback: original non-subquery side column.
                    return parse_one(f"{outer_col} = '{placeholder}'")
        if isinstance(expr, exp_mod.In):
            colname = first_column(expr.this)
            if colname:
                return parse_one(f"{colname} = '{placeholder}'")
        if isinstance(expr, exp_mod.Exists):
            colname = first_column(expr)
            if colname:
                return parse_one(f"{colname} = '{placeholder}'")
        if isinstance(expr, exp_mod.Subquery):
            parent_name = type(expr.parent).__name__ if expr.parent is not None else ""
            if parent_name in {"From", "Join"}:
                raise ValueError("Derived-table subqueries inside FROM/JOIN cannot be masked as __CUT__.")
            return parse_one(f"CAST(CURRENT_DATE AS VARCHAR) = '{placeholder}'")
        return parse_one(f"CAST(CURRENT_DATE AS VARCHAR) = '{placeholder}'")

    def _replace_mask_once(sql_text: str, mask_sql: str, replacement_sql: str) -> str:
        t = sql_text or ""
        m = (mask_sql or "").strip()
        r = (replacement_sql or "").strip()
        if not t or not m or not r:
            return t

        if m in t:
            return t.replace(m, r, 1)

        compact_t = " ".join(t.split())
        compact_m = " ".join(m.split())
        compact_r = " ".join(r.split())
        if compact_m and compact_m in compact_t:
            return compact_t.replace(compact_m, compact_r, 1)

        placeholder_match = re.search(r"'(__CUT_E\d+__|__CUT__)'", m)
        if not placeholder_match:
            placeholder_match = re.search(r"(__CUT_E\d+__|__CUT__)", m)
        if not placeholder_match:
            return t

        placeholder = placeholder_match.group(1)
        quoted_placeholder = f"'{placeholder}'"

        # If mask_sql was `alias.col = '__CUT_Ex__'`, keep only the column name.
        # Calcite may rename or remove the alias, but the placeholder itself is
        # edge-specific, so replacing the first matching condition is safe.
        col_match = re.search(
            rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            rf"{re.escape(quoted_placeholder)}",
            m,
            flags=re.IGNORECASE,
        )
        if not col_match:
            col_match = re.search(
                rf"{re.escape(quoted_placeholder)}\s*=\s*"
                rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\b",
                m,
                flags=re.IGNORECASE,
            )

        if col_match:
            col = col_match.group(1)
            patterns = [
                rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?{re.escape(col)}\s*=\s*{re.escape(quoted_placeholder)}",
                rf"{re.escape(quoted_placeholder)}\s*=\s*\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?{re.escape(col)}\b",
            ]
            for pat in patterns:
                new_t, n = re.subn(pat, r, t, count=1, flags=re.IGNORECASE)
                if n:
                    return new_t

        # Fallbacks for older mask expressions and simple placeholder predicates.
        generic_patterns = [
            rf"CAST\s*\(\s*CURRENT_TIMESTAMP\s+AS\s+VARCHAR\s*\)\s*=\s*{re.escape(quoted_placeholder)}",
            rf"CAST\s*\(\s*CURRENT_TIMESTAMP\s*\(\s*\)\s+AS\s+VARCHAR\s*\)\s*=\s*{re.escape(quoted_placeholder)}",
            rf"CAST\s*\(\s*CURRENT_DATE\s+AS\s+VARCHAR\s*\)\s*=\s*{re.escape(quoted_placeholder)}",
            rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*{re.escape(quoted_placeholder)}",
            rf"{re.escape(quoted_placeholder)}\s*=\s*\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*\b",
        ]
        for pat in generic_patterns:
            new_t, n = re.subn(pat, r, t, count=1, flags=re.IGNORECASE)
            if n:
                return new_t

        # Scalar subquery masks can survive as a bare string literal.
        if quoted_placeholder in t:
            return t.replace(quoted_placeholder, f"({r})", 1)

        return t

    module._make_mask_expr = _make_mask_expr
    module._replace_mask_once = _replace_mask_once

    def _extract_placeholder_alias_from_parent_sql(
        parent_sql: str,
        mask_sql: str,
        edge_id: str,
    ) -> Optional[str]:
        sql = parent_sql or ""
        placeholder = f"__CUT_{edge_id}__"
        m_col = re.match(
            r"\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'(__CUT_E\d+__|__CUT__)'\s*$",
            (mask_sql or "").strip(),
            flags=re.IGNORECASE,
        )
        if not m_col:
            return None
        col = m_col.group(1)

        patterns = [
            rf"\b([A-Za-z_][A-Za-z0-9_]*)\.{re.escape(col)}\s*=\s*'{re.escape(placeholder)}'",
            rf"'{re.escape(placeholder)}'\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\.{re.escape(col)}\b",
            rf"CAST\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\.{re.escape(col)}\s+AS\s+[^)]*\)\s*=\s*CAST\s*\(\s*'{re.escape(placeholder)}'\s+AS\s+[^)]*\)",
            rf"CAST\s*\(\s*'{re.escape(placeholder)}'\s+AS\s+[^)]*\)\s*=\s*CAST\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\.{re.escape(col)}\s+AS\s+[^)]*\)",
        ]
        for pat in patterns:
            found = re.search(pat, sql, flags=re.IGNORECASE)
            if found:
                return found.group(1)

        if re.search(rf"\b{re.escape(col)}\s*=\s*'{re.escape(placeholder)}'", sql, flags=re.IGNORECASE):
            return ""
        if re.search(
            rf"CAST\s*\(\s*{re.escape(col)}\s+AS\s+[^)]*\)\s*=\s*CAST\s*\(\s*'{re.escape(placeholder)}'\s+AS\s+[^)]*\)",
            sql,
            flags=re.IGNORECASE,
        ):
            return ""
        return None

    module._extract_placeholder_alias_from_parent_sql = _extract_placeholder_alias_from_parent_sql


def _patch_validation_rewriter(module: Any) -> None:
    _patch_validation_mask_restore(module)

    backend = _ACTIVE_REWRITE_BACKEND
    if backend is None:
        return
    module._LLMR2_PARALLEL_REWRITE = backend.name in ("llmr2", "quite")
    default_db_id = str(DB_CONFIG.get("database", "tpch")).strip()

    def _rewrite_with_backend(sql_text: str, trace_ctx: Optional[Dict[str, Any]] = None) -> str:
        try:
            ctx: Dict[str, Any] = dict(_REWRITE_EXTRA_CONTEXT or {})
            ctx["phase"] = "cut_block"
            if trace_ctx:
                ctx.update(trace_ctx)
            rr = backend.rewrite(sql_text=sql_text, db_id=default_db_id, context=ctx)
            out = (rr.rewritten_sql or "").strip()
            if out and ("select" in out.lower() or out.lower().startswith("with ")):
                # Keep backend rewrite output directly; executability is validated
                # later on the merged full SQL by the evaluation pipeline.
                return out
        except Exception:
            pass
        return sql_text

    module._safe_rewrite = _rewrite_with_backend

def _validation() -> Any:
    """
    Lazy-load the validation module.

    This keeps --help and imports working even when optional dependencies
    (e.g., sqlglot) are not installed, as long as we don't run the evaluation.
    """
    global _VALIDATION
    if _VALIDATION is None:
        _VALIDATION = _load_validation_module()
        _patch_validation_rewriter(_VALIDATION)
    return _VALIDATION

@dataclass
class EvalRecord:
    cut_edge_ids: List[str]
    objective: float
    f_value: float
    all_blocks_executable: bool
    full_query_cost_rewritten: Optional[float]
    full_query_cost_rewritten_raw: Optional[str]
    rewritten_full_sql: str
    variant_fatal_error: str
    debug: Optional[Dict[str, Any]] = None

@dataclass
class SearchResult:
    strategy: str
    best: EvalRecord
    details: Dict[str, Any]

class CutSetEvaluator:
    def __init__(self, sql_text: str, collect_rewrite_trace: bool = False) -> None:
        VALIDATION = _validation()
        self.sql_text = sql_text
        self.collect_rewrite_trace = collect_rewrite_trace
        self.fixer = VALIDATION.SubqueryFixer()
        self.context_tables = self.fixer.extract_outer_context_tables(sql_text)
        self.root, self.node_infos, self.edges = VALIDATION._collect_graph(sql_text, self.fixer)
        self.edge_map = {edge.edge_id: edge for edge in self.edges}
        self.eligible_edges = _sorted_edge_ids(
            [edge.edge_id for edge in self.edges if edge.cut_kind in VALIDATION.ELIGIBLE_CUT_KINDS]
        )
        self.full_sql = self.node_infos[self.root].sql
        self.base_cost = float(VALIDATION._cost(self.full_sql))
        if not math.isfinite(self.base_cost):
            raise RuntimeError(f"Baseline cost is not finite: {self.base_cost}")

        self.block_eval_cache: Dict[Tuple[str, Tuple[str, ...]], Any] = {}
        self.objective_cache: Dict[FrozenSet[str], EvalRecord] = {}
        self.variant_cache: Dict[FrozenSet[str], Dict[str, Any]] = {}

        self.eval_call_count = 0
        self.cache_hit_count = 0

    def graph_payload(self) -> Dict[str, Any]:
        """Same shape as double_greedy_cut_eval graph summary (nodes + edges)."""
        VALIDATION = _validation()
        return {
            "root_node": self.root,
            "num_select_nodes": len(self.node_infos),
            "num_edges": len(self.edges),
            "num_eligible_cut_edges": len(self.eligible_edges),
            "nodes": [
                VALIDATION._node_to_dict(nid, self.node_infos[nid])
                for nid in sorted(
                    self.node_infos.keys(),
                    key=lambda x: int(x[1:]) if x.startswith("N") else 10**9,
                )
            ],
            "edges": [VALIDATION._edge_to_dict(edge) for edge in self.edges],
        }

    def _equivalence_guard_ok(self, rewritten_full_sql: str) -> Tuple[bool, str]:
        """
        Best-effort equivalence guard.

        If any cut placeholder '__CUT_<edge_id>__' (or legacy '__CUT__') remains in the final
        SQL, semantics are almost certainly wrong even if PostgreSQL EXPLAIN succeeds. (The
        validation pipeline avoids masking inside detached child fragments; leftover tokens
        would indicate a bug or stale splice.)
        """
        sql = rewritten_full_sql or ""
        if "__CUT__" in sql:
            return False, "Equivalence guard failed: '__CUT__' placeholder remains in rewritten SQL."
        if re.search(r"__CUT_E\d+__", sql):
            return (
                False,
                "Equivalence guard failed: per-edge '__CUT_E*__' placeholder remains in rewritten SQL.",
            )
        return True, ""

    def evaluate(self, cuts: Set[str], all_rewrites_parallel: bool = False) -> EvalRecord:
        VALIDATION = _validation()
        key = frozenset(cuts)
        self.eval_call_count += 1
        cached = None if all_rewrites_parallel else self.objective_cache.get(key)
        if cached is not None:
            self.cache_hit_count += 1
            return cached

        variant = VALIDATION._evaluate_cut_set(
            full_sql=self.full_sql,
            base_cost=self.base_cost,
            root=self.root,
            cuts=set(key),
            node_infos=self.node_infos,
            edge_map=self.edge_map,
            fixer=self.fixer,
            context_tables=self.context_tables,
            cache=self.block_eval_cache,
            collect_rewrite_trace=self.collect_rewrite_trace,
            all_rewrites_parallel=all_rewrites_parallel,
        )
        self.variant_cache[key] = dict(variant or {})

        debug: Optional[Dict[str, Any]] = None
        if self.collect_rewrite_trace:
            debug = {
                "cut_edge_ids": _sorted_edge_ids(list(key)),
                "rewrite_trace": list((variant or {}).get("rewrite_trace") or []),
            }

        objective = float(variant.get("objective", 0.0) or 0.0)
        f_value = objective

        raw_cost = variant.get("full_query_cost_rewritten")
        cost_clean: Optional[float]
        cost_raw_str: Optional[str] = None
        try:
            if raw_cost is None:
                cost_clean = None
            else:
                cost_val = float(raw_cost)
                if math.isfinite(cost_val):
                    cost_clean = cost_val
                else:
                    cost_clean = None
                    cost_raw_str = str(raw_cost)
        except Exception:
            cost_clean = None
            cost_raw_str = str(raw_cost)
        result = EvalRecord(
            cut_edge_ids=_sorted_edge_ids(variant.get("cut_edge_ids", list(key))),
            objective=objective,
            f_value=f_value,
            all_blocks_executable=bool(variant.get("all_blocks_executable", False)),
            full_query_cost_rewritten=cost_clean,
            full_query_cost_rewritten_raw=cost_raw_str,
            rewritten_full_sql=variant.get("rewritten_full_sql", ""),
            variant_fatal_error=variant.get("variant_fatal_error", ""),
            debug=debug,
        )

        ok, guard_err = self._equivalence_guard_ok(result.rewritten_full_sql)
        if not ok:
            result = EvalRecord(
                cut_edge_ids=result.cut_edge_ids,
                objective=0.0,
                f_value=0.0,
                all_blocks_executable=False,
                full_query_cost_rewritten=None,
                full_query_cost_rewritten_raw=None,
                rewritten_full_sql=result.rewritten_full_sql,
                variant_fatal_error=(result.variant_fatal_error + " | " + guard_err).strip(" |"),
                debug=debug,
            )

        if not all_rewrites_parallel:
            self.objective_cache[key] = result
        return result

    @property
    def cache_size(self) -> int:
        return len(self.objective_cache)

def _effective_rewritten_cost(rec: EvalRecord) -> Optional[float]:
    """
    Return comparable rewritten cost for decision making.

    We only treat the cost as valid when the variant is executable and the
    rewritten cost is finite.
    """
    if not rec.all_blocks_executable:
        return None
    c = rec.full_query_cost_rewritten
    if c is None:
        return None
    if not math.isfinite(c):
        return None
    return float(c)


def _marginal_gain_by_cost(before: EvalRecord, after: EvalRecord) -> float:
    """
    Gain is defined as cost(before) - cost(after).

    Positive gain means `after` has lower rewritten cost and is preferred.
    """
    before_cost = _effective_rewritten_cost(before)
    after_cost = _effective_rewritten_cost(after)
    if before_cost is not None and after_cost is not None:
        return before_cost - after_cost
    if before_cost is None and after_cost is not None:
        return float("inf")
    if before_cost is not None and after_cost is None:
        return float("-inf")
    return 0.0


def _better(lhs: EvalRecord, rhs: EvalRecord) -> bool:
    lhs_cost = _effective_rewritten_cost(lhs)
    rhs_cost = _effective_rewritten_cost(rhs)
    if lhs_cost is not None and rhs_cost is not None and lhs_cost != rhs_cost:
        return lhs_cost < rhs_cost
    if lhs_cost is not None and rhs_cost is None:
        return True
    if lhs_cost is None and rhs_cost is not None:
        return False
    if lhs.f_value != rhs.f_value:
        return lhs.f_value > rhs.f_value
    return lhs.objective > rhs.objective

def run_double_greedy(
    evaluator: CutSetEvaluator,
    restarts: int,
    seed: int,
    attach_decision_rewrite_traces: bool = False,
) -> SearchResult:
    rng = random.Random(seed)
    all_edges = list(evaluator.eligible_edges)
    if not all_edges:
        base_eval = evaluator.evaluate(set())
        return SearchResult(
            strategy="double_greedy",
            best=base_eval,
            details={"restarts": 0, "runs": []},
        )

    runs: List[Dict[str, Any]] = []
    best_overall: Optional[EvalRecord] = None
    baseline_eval = evaluator.evaluate(set())

    for run_idx in range(restarts):
        order = list(all_edges)
        rng.shuffle(order)

        a_set: Set[str] = set()
        b_set: Set[str] = set(all_edges)
        a_eval = evaluator.evaluate(a_set)
        b_eval = evaluator.evaluate(b_set)

        decisions: List[Dict[str, Any]] = []
        for edge_id in order:
            # Cache keys for the two oracle calls in this double-greedy step (before mutating A/B).
            a_probe_cuts = frozenset(a_set | {edge_id})
            b_probe_cuts = frozenset(b_set - {edge_id})
            a_plus = evaluator.evaluate(a_set | {edge_id})
            b_minus = evaluator.evaluate(b_set - {edge_id})

            # Explicitly compare rewritten costs for the current context:
            # alpha: cost(A) vs cost(A U {e})
            # beta:  cost(B) vs cost(B \\ {e})
            alpha = _marginal_gain_by_cost(a_eval, a_plus)
            beta = _marginal_gain_by_cost(b_eval, b_minus)
            if alpha >= beta:
                a_set.add(edge_id)
                a_eval = a_plus
                decision = "add_to_A"
            else:
                b_set.remove(edge_id)
                b_eval = b_minus
                decision = "remove_from_B"

            step: Dict[str, Any] = {
                "edge_id": edge_id,
                "alpha": alpha,
                "beta": beta,
                "decision": decision,
                "A_size": len(a_set),
                "B_size": len(b_set),
            }
            if attach_decision_rewrite_traces and evaluator.collect_rewrite_trace:
                step["probe_for_alpha"] = {
                    "cut_edge_ids": _sorted_edge_ids(list(a_probe_cuts)),
                    "rewrite_trace": (evaluator.variant_cache.get(a_probe_cuts) or {}).get("rewrite_trace"),
                }
                step["probe_for_beta"] = {
                    "cut_edge_ids": _sorted_edge_ids(list(b_probe_cuts)),
                    "rewrite_trace": (evaluator.variant_cache.get(b_probe_cuts) or {}).get("rewrite_trace"),
                }
            decisions.append(step)

        final_eval = a_eval if _better(a_eval, b_eval) else b_eval
        run_record = {
            "run_idx": run_idx,
            "order": order,
            "final_from": "A" if final_eval.cut_edge_ids == a_eval.cut_edge_ids else "B",
            "final": asdict(final_eval),
            "decisions": decisions,
        }
        runs.append(run_record)

        if best_overall is None or _better(final_eval, best_overall):
            best_overall = final_eval

    assert best_overall is not None
    # Never return a solution worse than baseline.
    if _better(baseline_eval, best_overall):
        best_overall = baseline_eval
    return SearchResult(
        strategy="double_greedy",
        best=best_overall,
        details={"restarts": restarts, "runs": runs, "baseline": asdict(baseline_eval)},
    )

def run_greedy_cardinality(evaluator: CutSetEvaluator, max_cuts: Optional[int]) -> SearchResult:
    selected: Set[str] = set()
    current = evaluator.evaluate(selected)
    trajectory: List[Dict[str, Any]] = [{"step": 0, "selected": [], "eval": asdict(current), "gain": 0.0}]
    remaining = set(evaluator.eligible_edges)

    step = 1
    while remaining and (max_cuts is None or len(selected) < max_cuts):
        best_edge: Optional[str] = None
        best_gain = float("-inf")
        best_eval: Optional[EvalRecord] = None

        for edge_id in _sorted_edge_ids(list(remaining)):
            candidate = evaluator.evaluate(selected | {edge_id})
            # Decide whether to add edge_id by direct cost comparison:
            # cost(current selected cuts) vs cost(current + edge_id).
            gain = _marginal_gain_by_cost(current, candidate)
            if gain > best_gain:
                best_gain = gain
                best_edge = edge_id
                best_eval = candidate

        if best_edge is None or best_eval is None or best_gain <= 0.0:
            break

        selected.add(best_edge)
        remaining.remove(best_edge)
        current = best_eval
        trajectory.append(
            {
                "step": step,
                "selected": _sorted_edge_ids(list(selected)),
                "picked_edge": best_edge,
                "gain": best_gain,
                "eval": asdict(current),
            }
        )
        step += 1

    return SearchResult(
        strategy="greedy_cardinality",
        best=current,
        details={"max_cuts": max_cuts, "trajectory": trajectory},
    )

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search cut-edge sets for query rewrite using global objective "
            "f(S)=C(base)-C(rewritten_with_S) (can be negative)."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sql-file", type=str, help="Path to SQL file.")
    source.add_argument("--sql", type=str, help="Inline SQL string.")
    source.add_argument("--jsonl-file", type=str, help="Path to JSONL input file.")
    parser.add_argument(
        "--jsonl-sql-field",
        type=str,
        default="sql",
        help="Field name for SQL text when using --jsonl-file (default: sql).",
    )
    parser.add_argument(
        "--output-jsonl",
        type=str,
        default=None,
        help="Output JSONL path for --jsonl-file mode. Each line includes original_sql and rewritten_sql.",
    )

    parser.add_argument(
        "--strategy",
        type=str,
        default="double_greedy",
        help=(
            "Search strategy or strategies. "
            "Supported: double_greedy, greedy_cardinality, all, or a comma-separated list "
            "(e.g., 'double_greedy,greedy_cardinality')."
        ),
    )
    parser.add_argument("--restarts", type=int, default=10, help="Number of random restarts for double greedy.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for double greedy.")
    parser.add_argument("--max-cuts", type=int, default=None, help="Max selected cuts for greedy_cardinality.")
    parser.add_argument("--output-json", type=str, default=None, help="Optional output JSON path.")
    parser.add_argument(
        "--output-md",
        type=str,
        default=None,
        help="Optional output MD path. If omitted and --output-json is set, defaults to <output-json>.md.",
    )
    parser.add_argument(
        "--save-best-sql",
        type=str,
        default=None,
        help="Optional path to save best rewritten SQL as a .sql file.",
    )
    parser.add_argument(
        "--dump-evaluations",
        action="store_true",
        help=(
            "Include all evaluated cut sets (oracle payloads) in the output JSON. "
            "Useful for debugging why some cut sets explode in cost."
        ),
    )
    parser.add_argument(
        "--dump-evaluations-with-sql",
        action="store_true",
        help="When dumping evaluations, include full SQL texts (can make JSON very large).",
    )
    parser.add_argument(
        "--rewrite-trace",
        action="store_true",
        help=(
            "Record per-block rewrite traces (mask placeholders, Calcite I/O, restore, splice) for each "
            "evaluated cut set, and attach alpha/beta probe traces to double-greedy decision steps. "
            "Makes JSON large."
        ),
    )
    parser.add_argument(
        "--rewrite-backend",
        type=str,
        default="calcite_rules",
        help="Rewrite backend: calcite_rules (default), llmr2, or quite.",
    )
    parser.add_argument(
        "--quite-schema-file",
        type=Path,
        default=None,
        help=(
            "When using --rewrite-backend quite: schema .sql path passed as context quite_schema_file "
            "(same as QUITE run.py --schema_file). If omitted, quite uses env QUITE_SCHEMA_FILE when set."
        ),
    )
    return parser.parse_args()

def _parse_strategy_list(raw: str) -> List[str]:
    supported = {"double_greedy", "greedy_cardinality"}
    token = (raw or "").strip().lower()
    if token in {"all", "*"}:
        return sorted(supported)
    parts = [p.strip().lower() for p in token.split(",") if p.strip()]
    if not parts:
        return ["double_greedy"]
    unknown = [p for p in parts if p not in supported]
    if unknown:
        raise ValueError(f"Unknown strategy(s): {unknown}. Supported: {sorted(supported)}")
    # Preserve user order but dedupe.
    out: List[str] = []
    for p in parts:
        if p not in out:
            out.append(p)
    return out

def _load_sql_text(args: argparse.Namespace) -> str:
    if args.sql is not None:
        return args.sql
    path = Path(args.sql_file).expanduser().resolve()
    return path.read_text(encoding="utf-8")


def _run_search_for_sql(sql_text: str, args: argparse.Namespace) -> Dict[str, Any]:
    VALIDATION = _validation()
    t0 = time.time()
    evaluator = CutSetEvaluator(sql_text, collect_rewrite_trace=bool(args.rewrite_trace))
    baseline_eval = evaluator.evaluate(set())

    strategies = _parse_strategy_list(args.strategy)
    per_strategy: List[SearchResult] = []
    best_overall = SearchResult(strategy="baseline", best=baseline_eval, details={"baseline": asdict(baseline_eval)})
    for strat in strategies:
        if strat == "double_greedy":
            sr = run_double_greedy(
                evaluator=evaluator,
                restarts=max(1, args.restarts),
                seed=args.seed,
                attach_decision_rewrite_traces=bool(args.rewrite_trace),
            )
        elif strat == "greedy_cardinality":
            sr = run_greedy_cardinality(evaluator=evaluator, max_cuts=args.max_cuts)
        else:
            raise RuntimeError(f"Unhandled strategy: {strat}")

        # Guardrail: never keep a solution worse than baseline.
        if _better(baseline_eval, sr.best):
            sr = SearchResult(
                strategy=sr.strategy,
                best=baseline_eval,
                details={**(sr.details or {}), "baseline_overrode_result": True, "baseline": asdict(baseline_eval)},
            )

        per_strategy.append(sr)
        if _better(sr.best, best_overall.best):
            best_overall = sr

    fallback_info: Dict[str, Any] = {}
    if len(best_overall.best.cut_edge_ids) == 0 and _ACTIVE_REWRITE_BACKEND is not None:
        db_id = str(DB_CONFIG.get("database", "tpch")).strip()
        fb_ctx: Dict[str, Any] = dict(_REWRITE_EXTRA_CONTEXT or {})
        fb_ctx["phase"] = "empty_cut_fallback"
        full_rewrite = _ACTIVE_REWRITE_BACKEND.rewrite(
            sql_text=evaluator.full_sql,
            db_id=db_id,
            context=fb_ctx,
        )
        candidate_rewritten_full_sql = (full_rewrite.rewritten_sql or "").strip() or evaluator.full_sql
        full_cost_after: Optional[float] = None
        cost_raw_str: Optional[str] = None
        rewritten_full_sql = evaluator.full_sql
        try:
            c = float(VALIDATION._cost(candidate_rewritten_full_sql))
            if math.isfinite(c):
                full_cost_after = c
                rewritten_full_sql = candidate_rewritten_full_sql
            else:
                cost_raw_str = str(c)
        except Exception as exc:
            cost_raw_str = f"{type(exc).__name__}: {exc}"

        executable = full_cost_after is not None
        objective = (evaluator.base_cost - full_cost_after) if executable else 0.0
        best_overall = SearchResult(
            strategy=f"{best_overall.strategy}_empty_cut_fallback",
            best=EvalRecord(
                cut_edge_ids=[],
                objective=objective,
                f_value=objective,
                all_blocks_executable=executable,
                full_query_cost_rewritten=full_cost_after,
                full_query_cost_rewritten_raw=cost_raw_str,
                rewritten_full_sql=rewritten_full_sql,
                variant_fatal_error="" if executable else f"empty_cut_fallback_failed:{cost_raw_str}",
                debug=None,
            ),
            details={
                **(best_overall.details or {}),
                "empty_cut_fallback_applied": True,
                "empty_cut_fallback_backend": _ACTIVE_REWRITE_BACKEND.name,
                "empty_cut_fallback_metadata": full_rewrite.metadata,
            },
        )
        fallback_info = {
            "applied": True,
            "backend": _ACTIVE_REWRITE_BACKEND.name,
            "changed": full_rewrite.changed,
            "metadata": full_rewrite.metadata,
        }

    elapsed_sec = time.time() - t0
    output = {
        "strategy": best_overall.strategy,
        "strategies_run": strategies,
        "per_strategy": [{"strategy": r.strategy, "best": asdict(r.best), "details": r.details} for r in per_strategy],
        "objective_definition": "f(S)=C(base)-C(rewritten_with_S) (can be negative)",
        "cost_strategy": (os.getenv("COST_STRATEGY", "pg_explain").strip().lower()),
        "base_cost": evaluator.base_cost,
        "root_node": evaluator.root,
        "num_select_nodes": len(evaluator.node_infos),
        "num_edges": len(evaluator.edges),
        "num_eligible_edges": len(evaluator.eligible_edges),
        "eligible_edge_ids": evaluator.eligible_edges,
        "graph": evaluator.graph_payload(),
        "rewrite_trace_enabled": bool(args.rewrite_trace),
        "rewrite_backend": _ACTIVE_REWRITE_BACKEND.name if _ACTIVE_REWRITE_BACKEND is not None else "calcite_rules",
        "baseline": asdict(baseline_eval),
        "best": asdict(best_overall.best),
        "search_details": best_overall.details,
        "empty_cut_fallback": fallback_info,
        "eval_stats": {
            "eval_call_count": evaluator.eval_call_count,
            "cache_hit_count": evaluator.cache_hit_count,
            "cache_size": evaluator.cache_size,
            "cache_hit_rate": (
                evaluator.cache_hit_count / evaluator.eval_call_count if evaluator.eval_call_count > 0 else 0.0
            ),
        },
        "runtime_sec": elapsed_sec,
    }
    if args.dump_evaluations:
        output["evaluated_cut_sets"] = build_evaluations_payload(
            variant_cache=evaluator.variant_cache,
            include_sql=bool(args.dump_evaluations_with_sql),
            sorted_edge_ids_fn=_sorted_edge_ids,
            edge_sort_key_fn=_edge_sort_key,
        )
    return output


def _run_jsonl_mode(args: argparse.Namespace) -> None:
    if not args.output_jsonl:
        raise ValueError("--jsonl-file requires --output-jsonl")
    input_path = Path(args.jsonl_file).expanduser().resolve()
    output_path = Path(args.output_jsonl).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sql_field = args.jsonl_sql_field

    total = 0
    succeeded = 0
    with input_path.open("r", encoding="utf-8") as fin, output_path.open("w", encoding="utf-8") as fout:
        for line_no, line in enumerate(fin, 1):
            row_start = time.perf_counter()
            text = line.strip()
            if not text:
                continue
            total += 1
            obj = json.loads(text)
            if not isinstance(obj, dict):
                raise ValueError(f"{input_path}:{line_no}: each line must be a JSON object")
            sql_text = str(obj.get(sql_field, "") or "").strip()
            if not sql_text:
                out_row = {
                    "original_sql": "",
                    "rewritten_sql": "",
                    "variant_fatal_error": f"missing_sql_field:{sql_field}",
                    "line_index": line_no,
                    "inference_time_sec": round(time.perf_counter() - row_start, 6),
                }
                fout.write(json.dumps(out_row, ensure_ascii=False) + "\n")
                continue

            try:
                result = _run_search_for_sql(sql_text, args)
                best = result["best"]
                out_row = {
                    "original_sql": sql_text,
                    "rewritten_sql": best.get("rewritten_full_sql", ""),
                    "applied_cut_edge_ids": best.get("cut_edge_ids", []),
                    "variant_fatal_error": best.get("variant_fatal_error", ""),
                    "original_query_cost": result.get("base_cost"),
                    "rewritten_query_cost": best.get("full_query_cost_rewritten"),
                    "line_index": obj.get("line_index", line_no),
                    "inference_time_sec": round(time.perf_counter() - row_start, 6),
                }
                succeeded += 1
            except Exception as exc:
                out_row = {
                    "original_sql": sql_text,
                    "rewritten_sql": sql_text,
                    "applied_cut_edge_ids": [],
                    "variant_fatal_error": f"search_exception:{type(exc).__name__}: {exc}",
                    "original_query_cost": None,
                    "rewritten_query_cost": None,
                    "line_index": obj.get("line_index", line_no),
                    "inference_time_sec": round(time.perf_counter() - row_start, 6),
                }

            if "metadata" in obj:
                out_row["metadata"] = obj.get("metadata")
            fout.write(json.dumps(out_row, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "mode": "jsonl",
                "input_jsonl": str(input_path),
                "output_jsonl": str(output_path),
                "total_rows": total,
                "succeeded": succeeded,
                "failed_or_fallback": total - succeeded,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

def main() -> None:
    global _ACTIVE_REWRITE_BACKEND, _VALIDATION, _REWRITE_EXTRA_CONTEXT
    args = _parse_args()
    _ACTIVE_REWRITE_BACKEND = create_rewrite_backend(args.rewrite_backend, REPO_ROOT)
    _VALIDATION = None
    if args.quite_schema_file is not None:
        qp = args.quite_schema_file.expanduser().resolve()
        if not qp.is_file():
            raise SystemExit(f"--quite-schema-file is not a file: {qp}")
        _REWRITE_EXTRA_CONTEXT = {"quite_schema_file": str(qp)}
    else:
        _REWRITE_EXTRA_CONTEXT = None
    if args.jsonl_file is not None:
        _run_jsonl_mode(args)
        return

    sql_text = _load_sql_text(args)
    output = _run_search_for_sql(sql_text, args)
    output["sql_source"] = {"sql_file": args.sql_file, "inline_sql": args.sql is not None}

    print(
        json.dumps(
            {
                "strategy": output["strategy"],
                "base_cost": output["base_cost"],
                "best_cut_edge_ids": output["best"]["cut_edge_ids"],
                "best_f_value": output["best"]["f_value"],
                "best_objective": output["best"]["objective"],
                "best_rewritten_cost": output["best"]["full_query_cost_rewritten"],
                "eval_calls": output["eval_stats"]["eval_call_count"],
                "cache_hit_rate": output["eval_stats"]["cache_hit_rate"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    saved_paths: List[str] = []
    if args.save_best_sql:
        VALIDATION = _validation()
        save_result = save_best_sql_and_recheck(
            best_sql=str(output.get("best", {}).get("rewritten_full_sql", "") or ""),
            save_best_sql_path=args.save_best_sql,
            cost_fn=VALIDATION._cost,
        )
        saved_paths.append(save_result["saved_path"])
        output["best_sql_path"] = save_result["best_sql_path"]
        output["best_rewritten_cost_rechecked"] = save_result["best_rewritten_cost_rechecked"]

    if args.output_json:
        out_path = Path(args.output_json).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Strict JSON: forbid NaN/Infinity, so we must sanitize all floats beforehand.
        output_for_json = _sanitize_json_values(output)
        out_path.write_text(json.dumps(output_for_json, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        saved_paths.append(str(out_path))

        md_path = resolve_md_output_path(out_path, args.output_md)
        md_path.write_text(build_md_report(output), encoding="utf-8")
        saved_paths.append(str(md_path))

    for p in saved_paths:
        print(f"Saved: {p}")

if __name__ == "__main__":
    main()