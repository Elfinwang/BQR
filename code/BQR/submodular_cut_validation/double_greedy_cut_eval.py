import json
import math
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
VENDOR_DIR = REPO_ROOT / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

from sqlglot import exp, parse_one

from config import DB_CONFIG
from rename_group_alias import align_group_by_with_select
from rewriter_interface import call_rewriter
from subquery_masker import get_string_column_from_from_clause
from syntax_tree import SubqueryFixer
from utils.cost_estimator import get_cost

FLATTEN_RULES = ["FILTER_INTO_JOIN", "FILTER_CORRELATE"]
PUSHDOWN_RULES = [
    "JOIN_LEFT_UNION_TRANSPOSE",
    "JOIN_RIGHT_UNION_TRANSPOSE",
    "JOIN_PROJECT_BOTH_TRANSPOSE",
    "FILTER_INTO_JOIN",
    "FILTER_SCAN",
    "JOIN_REDUCE_EXPRESSIONS",
    "FILTER_PROJECT_TRANSPOSE",
    "FILTER_TABLE_FUNCTION_TRANSPOSE",
    "FILTER_AGGREGATE_TRANSPOSE",
    "SORT_JOIN_TRANSPOSE",
    "SEMI_JOIN_REMOVE",
]
LOCAL_RULES = [
    "AGGREGATE_VALUES",
    "JOIN_REDUCE_EXPRESSIONS",
    "AGGREGATE_EXPAND_DISTINCT_AGGREGATES",
    "AGGREGATE_PROJECT_MERGE",
    "AGGREGATE_ANY_PULL_UP_CONSTANTS",
    "AGGREGATE_UNION_AGGREGATE",
    "AGGREGATE_REMOVE",
    "FILTER_REDUCE_EXPRESSIONS",
    "PROJECT_REDUCE_EXPRESSIONS",
    "PROJECT_CALC_MERGE",
    "PROJECT_MERGE",
    "PROJECT_REMOVE",
    "PROJECT_TO_CALC",
    "SORT_PROJECT_TRANSPOSE",
    "SORT_UNION_TRANSPOSE",
    "SORT_REMOVE_CONSTANT_KEYS",
    "SORT_REMOVE",
    "SORT_FETCH_ZERO_INSTANCE",
    "CALC_MERGE",
    "CALC_REMOVE",
    "AGGREGATE_INSTANCE",
    "FILTER_INSTANCE",
    "JOIN_LEFT_INSTANCE",
    "JOIN_RIGHT_INSTANCE",
    "PROJECT_INSTANCE",
    "SORT_INSTANCE",
    "UNION_INSTANCE",
    "INTERSECT_INSTANCE",
    "MINUS_INSTANCE",
]
RULES = list(dict.fromkeys(PUSHDOWN_RULES + FLATTEN_RULES + LOCAL_RULES))
SQL_FILE = REPO_ROOT / "experiments" / "submodular_cut_validation" / "complex_tpch_query.sql"
TPCH_DB_CONFIG = dict(DB_CONFIG)
DEFAULT_DB_ID = str(DB_CONFIG.get("database", "tpch")).strip()
# Patched by double_greedy_cut_search._patch_validation_rewriter when rewrite backend is llmr2 or quite:
# run block _rewrite_block_fragment and masked-parent _safe_rewrite concurrently (per block or full pool).
_LLMR2_PARALLEL_REWRITE = False
ELIGIBLE_CUT_KINDS = {
    "scalar_subquery",
    "in_predicate",
    "exists_predicate",
    "negated_subquery_predicate",
    "binary_subquery_predicate",
    "derived_table_subquery",
}


@dataclass(frozen=True)
class NodeInfo:
    node_id: str
    sql: str
    fixed_sql: str


@dataclass(frozen=True)
class EdgeInfo:
    edge_id: str
    parent: str
    child: str
    cut_sql: str
    cut_kind: str
    # Exact SQL text used when masking this edge in its original parent context.
    # This is necessary because cut_sql alone (an expression fragment) does not carry
    # enough context to reproduce the chosen mask (e.g., a string column predicate).
    mask_sql: str


@dataclass
class BlockEval:
    root_node: str
    nodes: List[str]
    boundary_cut_edges: List[str]
    boundary_cut_kinds: List[str]
    executable: bool
    # Full-query costs are recorded once per variant (see variant dict keys);
    # per-block rows leave these null — they only carry fragment SQL for audit.
    original_cost: Optional[float]
    rewritten_cost: Optional[float]
    gain: float
    # Standalone (masked + fixed) block SQL passed to Calcite; for debugging only.
    original_sql: str
    rewritten_sql: str
    rewrite_changed: bool
    # Full query text after this block's splice step (never truncated in exports).
    merged_full_sql: str = ""
    # False if Calcite output was skipped because splice/merge failed or PG EXPLAIN rejected it.
    splice_applied: bool = False
    error: str = ""


def _normalize_sql(sql_text: str) -> str:
    return " ".join(sql_text.split()).strip().lower()


def _preview(sql_text: str, max_len: int = 220) -> str:
    """Short preview for terminal/log use only — JSON/MD exports use full SQL."""
    compact = " ".join(sql_text.split())
    return compact[:] 
    # + (" ..." if len(compact) > max_len else "")


def _md_sql_fence(lines: List[str], title: str, sql: str) -> None:
    lines.append(f"- {title}")
    lines.append("```sql")
    lines.append(sql.strip())
    lines.append("```")


def _safe_rewrite(sql_text: str) -> str:
    try:
        out = call_rewriter(DEFAULT_DB_ID, sql_text, RULES).replace("$", "").strip()
        if out and ("select" in out.lower() or out.lower().startswith("with ")):
            return out
    except Exception:
        return sql_text
    return sql_text


def _cost(sql_text: str) -> float:
    # Prefer PG EXPLAIN when available, but allow offline runs.
    # Set COST_STRATEGY=heuristic to force offline evaluation.
    strategy = os.getenv("COST_STRATEGY", "pg_explain").strip().lower()
    if strategy == "heuristic":
        return get_cost(sql_text, strategy="heuristic")
    # IMPORTANT: if PG EXPLAIN fails, treat it as non-executable for this experiment.
    # Do NOT silently fall back to heuristic, otherwise invalid rewrites look "fine".
    return get_cost(sql_text, db_config=TPCH_DB_CONFIG, strategy="pg_explain")


def _prepare_sql_for_standalone(
    sql_text: str, fixer: SubqueryFixer, context_tables: Dict[str, str]
) -> Tuple[str, Any]:
    prep = fixer.prepare_subquery_for_standalone(sql_text, context_tables)
    fixed = prep.prepared_sql
    try:
        fixed = align_group_by_with_select(fixed)
    except Exception:
        pass
    return fixed, prep


def _fix_sql_for_standalone(sql_text: str, fixer: SubqueryFixer, context_tables: Dict[str, str]) -> str:
    fixed, _ = _prepare_sql_for_standalone(sql_text, fixer, context_tables)
    return fixed


def _cut_kind(expr: exp.Expression) -> str:
    if isinstance(expr, exp.In):
        return "in_predicate"
    if isinstance(expr, exp.Exists):
        return "exists_predicate"
    if isinstance(expr, exp.Not) and isinstance(expr.this, (exp.In, exp.Exists)):
        return "negated_subquery_predicate"
    if isinstance(expr, exp.Binary) and (expr.left.find(exp.Subquery) or expr.right.find(exp.Subquery)):
        return "binary_subquery_predicate"
    if isinstance(expr, exp.Subquery):
        parent_name = type(expr.parent).__name__ if expr.parent is not None else ""
        if parent_name in {"From", "Join"}:
            return "derived_table_subquery"
        return "scalar_subquery"
    return type(expr).__name__


def _pick_cut_expr(path: Sequence[exp.Expression]) -> exp.Expression:
    fallback: Optional[exp.Expression] = None
    for expr in reversed(path):
        if isinstance(expr, exp.In):
            return expr
        if isinstance(expr, exp.Exists):
            return expr
        if isinstance(expr, exp.Not) and isinstance(expr.this, (exp.In, exp.Exists)):
            return expr
        if isinstance(expr, exp.Binary) and (expr.left.find(exp.Subquery) or expr.right.find(exp.Subquery)):
            return expr
        if fallback is None and isinstance(expr, exp.Subquery):
            fallback = expr
    if fallback is None:
        raise ValueError("Unable to locate cut expression for child SELECT.")
    return fallback


def _collect_graph(sql_text: str, fixer: SubqueryFixer) -> Tuple[str, Dict[str, NodeInfo], List[EdgeInfo]]:
    tree = parse_one(sql_text)
    context_tables = fixer.extract_outer_context_tables(sql_text)
    node_infos: Dict[str, NodeInfo] = {}
    raw_edges: List[Tuple[str, str, str, str, str]] = []
    counter = {"node": 0}
    root_id: Optional[str] = None

    def walk(
        node: exp.Expression,
        parent_select_id: Optional[str],
        path_since_parent_select: List[exp.Expression],
    ) -> None:
        nonlocal root_id
        current_parent = parent_select_id
        current_path = path_since_parent_select
        if isinstance(node, exp.Select):
            node_id = f"N{counter['node']}"
            counter["node"] += 1
            raw_sql = node.sql()
            fixed_sql = _fix_sql_for_standalone(raw_sql, fixer, context_tables)
            node_infos[node_id] = NodeInfo(node_id=node_id, sql=raw_sql, fixed_sql=fixed_sql)
            if parent_select_id is None and root_id is None:
                root_id = node_id
            if parent_select_id is not None:
                cut_expr = _pick_cut_expr(current_path)
                edge_id = f"E{len(raw_edges)}"
                try:
                    mask_sql = _make_mask_expr(cut_expr, edge_id=edge_id).sql()
                except Exception:
                    # Keep edge-id specific marker in fallback as well.
                    mask_sql = f"'__CUT_{edge_id}__'"
                raw_edges.append((parent_select_id, node_id, cut_expr.sql(), _cut_kind(cut_expr), mask_sql))
            current_parent = node_id
            current_path = []

        for child in node.args.values():
            if isinstance(child, list):
                for item in child:
                    if isinstance(item, exp.Expression):
                        walk(item, current_parent, current_path + [item])
            elif isinstance(child, exp.Expression):
                walk(child, current_parent, current_path + [child])

    walk(tree, None, [])
    if root_id is None:
        raise ValueError("No SELECT node found in SQL.")

    edges = [
        EdgeInfo(
            edge_id=f"E{i}",
            parent=parent,
            child=child,
            cut_sql=cut_sql,
            cut_kind=cut_kind,
            mask_sql=mask_sql,
        )
        for i, (parent, child, cut_sql, cut_kind, mask_sql) in enumerate(raw_edges)
    ]
    return root_id, node_infos, edges


def _make_mask_expr(expr: exp.Expression, edge_id: Optional[str] = None) -> exp.Expression:
    """
    Build a mask expression for a cut edge.

    IMPORTANT:
    - Placeholder is edge-specific: __CUT_E0__, __CUT_E1__, ...
    - Avoid "__CUT__ = __CUT__" tautologies because Calcite can fold/eliminate them.
    """
    placeholder = f"__CUT_{edge_id}__" if edge_id else "__CUT__"

    def has_subquery(node: exp.Expression) -> bool:
        return isinstance(node, (exp.Subquery, exp.Exists)) or any(
            has_subquery(v)
            for v in node.args.values()
            if isinstance(v, exp.Expression)
        ) or any(
            has_subquery(item)
            for v in node.args.values()
            if isinstance(v, list)
            for item in v
            if isinstance(item, exp.Expression)
        )

    def first_column(node: exp.Expression) -> Optional[str]:
        if isinstance(node, exp.Column):
            return node.sql()
        for v in node.args.values():
            if isinstance(v, exp.Expression):
                found = first_column(v)
                if found:
                    return found
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, exp.Expression):
                        found = first_column(item)
                        if found:
                            return found
        return None

    if isinstance(expr, exp.Not) and isinstance(expr.this, exp.Expression):
        return _make_mask_expr(expr.this, edge_id=edge_id)
    if isinstance(expr, exp.Binary):
        for side in (expr.left, expr.right):
            if isinstance(side, exp.Expression) and not has_subquery(side):
                colname = first_column(side)
                if colname:
                    return parse_one(f"{colname} = '{placeholder}'")
    if isinstance(expr, exp.In):
        colname = first_column(expr.this)
        if colname:
            return parse_one(f"{colname} = '{placeholder}'")
    if isinstance(expr, exp.Exists):
        colname = first_column(expr)
        if colname:
            return parse_one(f"{colname} = '{placeholder}'")
    if isinstance(expr, (exp.In, exp.Exists, exp.Not, exp.Binary)):
        colname = get_string_column_from_from_clause(expr, TPCH_DB_CONFIG)
        if colname:
            return parse_one(f"{colname} = '{placeholder}'")
        return parse_one(f"CAST(CURRENT_DATE AS VARCHAR) = '{placeholder}'")
    if isinstance(expr, exp.Subquery):
        parent_name = type(expr.parent).__name__ if expr.parent is not None else ""
        if parent_name in {"From", "Join"}:
            raise ValueError("Derived-table subqueries inside FROM/JOIN cannot be masked as __CUT__.")
        return parse_one(f"CAST(CURRENT_DATE AS VARCHAR) = '{placeholder}'")
    return parse_one(f"CAST(CURRENT_DATE AS VARCHAR) = '{placeholder}'")


def _mask_selected_cut_exprs(
    sql_text: str,
    target_cut_sqls: Set[str],
    cut_sql_to_edge_id: Optional[Dict[str, str]] = None,
    cut_sql_to_mask_sql: Optional[Dict[str, str]] = None,
) -> str:
    if not target_cut_sqls:
        return sql_text
    normalized_targets = {_normalize_sql(x) for x in target_cut_sqls}
    normalized_edge_id_map: Dict[str, str] = {}
    if cut_sql_to_edge_id:
        normalized_edge_id_map = {
            _normalize_sql(cut_sql): str(edge_id)
            for cut_sql, edge_id in cut_sql_to_edge_id.items()
        }
    normalized_mask_sql_map: Dict[str, str] = {}
    if cut_sql_to_mask_sql:
        normalized_mask_sql_map = {
            _normalize_sql(cut_sql): str(mask_sql)
            for cut_sql, mask_sql in cut_sql_to_mask_sql.items()
            if str(mask_sql or "").strip()
        }
    tree = parse_one(sql_text)

    def visit(expr: exp.Expression) -> exp.Expression:
        normalized_expr = _normalize_sql(expr.sql())
        if normalized_expr in normalized_targets:
            # Highest priority: use the exact edge-recorded mask SQL so trace
            # placeholders match parent_cut_placeholders.mask_sql exactly.
            mask_sql = normalized_mask_sql_map.get(normalized_expr)
            if mask_sql:
                return parse_one(mask_sql)
            edge_id = normalized_edge_id_map.get(normalized_expr)
            return _make_mask_expr(expr, edge_id=edge_id)
        for key, value in expr.args.items():
            if isinstance(value, exp.Expression):
                expr.set(key, visit(value))
            elif isinstance(value, list):
                expr.set(key, [visit(item) if isinstance(item, exp.Expression) else item for item in value])
        return expr

    return visit(tree).sql()


def _strip_cross_joins_for_aliases(
    sql_text: str, aliases: Set[str], context_tables: Dict[str, str]
) -> str:
    """
    Remove CROSS JOINs added by SubqueryFixer for standalone execution so the
    fragment can be merged back into the full query (outer scope already has those tables).
    """
    out = sql_text
    for alias in aliases:
        if alias not in context_tables:
            continue
        table = context_tables[alias]
        pats = [
            rf"\s+CROSS\s+JOIN\s+{re.escape(table)}\s+AS\s+{re.escape(alias)}\b",
            rf"\s+CROSS\s+JOIN\s+{re.escape(table)}\s+{re.escape(alias)}\b",
        ]
        for pat in pats:
            out = re.sub(pat, " ", out, flags=re.IGNORECASE)
    return " ".join(out.split())


def _restore_boundary_mask_sql(rewritten_sql: str, boundary_edges: List[EdgeInfo]) -> str:
    """
    Replace boundary mask expressions with the original cut SQL so the merged fragment
    matches the semantics of the uncut query (subqueries / predicates restored).
    """
    t = rewritten_sql
    for edge in boundary_edges:
        orig = edge.cut_sql.strip()
        mask_sql = (edge.mask_sql or "").strip()
        if not mask_sql:
            continue

        # Try exact match first.
        if mask_sql in t:
            t = t.replace(mask_sql, orig, 1)
            continue

        # Calcite may drop qualifiers (e.g., "partsupp.ps_comment" -> "ps_comment").
        unqualified_mask = re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\.", "", mask_sql)
        if unqualified_mask != mask_sql and unqualified_mask in t:
            t = t.replace(unqualified_mask, orig, 1)
            continue

        tn = " ".join(t.split())
        mn = " ".join(mask_sql.split())
        if mn in tn:
            t = tn.replace(mn, " ".join(orig.split()), 1)
            continue
        umn = " ".join(unqualified_mask.split())
        if umn != mn and umn in tn:
            t = tn.replace(umn, " ".join(orig.split()), 1)
    # Restore edge-specific scalar placeholders if they are still present as literals.
    for edge in boundary_edges:
        if edge.cut_kind != "scalar_subquery":
            continue
        quoted_placeholder = f"'__CUT_{edge.edge_id}__'"
        if quoted_placeholder in t:
            t = t.replace(quoted_placeholder, f"({edge.cut_sql.strip()})", 1)

    # Backward compatibility for old unnumbered placeholder.
    if "'__CUT__'" in t:
        for edge in boundary_edges:
            if edge.cut_kind == "scalar_subquery":
                t = t.replace("'__CUT__'", f"({edge.cut_sql.strip()})", 1)
                break
    return t


def _replace_mask_once(sql_text: str, mask_sql: str, replacement_sql: str) -> str:
    """Replace one mask occurrence with robust fallbacks."""
    t = sql_text or ""
    m = (mask_sql or "").strip()
    r = (replacement_sql or "").strip()
    if not t or not m or not r:
        return t
    if m in t:
        return t.replace(m, r, 1)

    tn = " ".join(t.split())
    mn = " ".join(m.split())
    rn = " ".join(r.split())
    if mn in tn:
        return tn.replace(mn, rn, 1)

    # Safe fallback: replace "<optional_alias>.<col> = '__CUT_Ex__'" as a whole condition.
    m_col = re.match(
        r"\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'(__CUT_E\d+__|__CUT__)'\s*$",
        m,
        flags=re.IGNORECASE,
    )
    if not m_col:
        m_col = re.match(
            r"\s*'(__CUT_E\d+__|__CUT__)'\s*=\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*$",
            m,
            flags=re.IGNORECASE,
        )
    if m_col:
        if m_col.group(1).startswith("__CUT"):
            placeholder = m_col.group(1)
            col = m_col.group(2)
        else:
            col = m_col.group(1)
            placeholder = m_col.group(2)
        patterns = [
            rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?{re.escape(col)}\s*=\s*'{re.escape(placeholder)}'",
            rf"'{re.escape(placeholder)}'\s*=\s*\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?{re.escape(col)}\b",
        ]
        for pat in patterns:
            new_t, n = re.subn(pat, r, t, count=1, flags=re.IGNORECASE)
            if n > 0:
                return new_t

    placeholder_match = re.search(r"'(__CUT_E\d+__|__CUT__)'", m)
    if placeholder_match:
        quoted_placeholder = f"'{placeholder_match.group(1)}'"
        generic_patterns = [
            rf"CAST\s*\(\s*CURRENT_DATE\s+AS\s+(?:TEXT|VARCHAR)\s*\)\s*=\s*{re.escape(quoted_placeholder)}",
            rf"CAST\s*\(\s*CURRENT_TIMESTAMP\s+AS\s+(?:TEXT|VARCHAR)\s*\)\s*=\s*{re.escape(quoted_placeholder)}",
            rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*{re.escape(quoted_placeholder)}",
            rf"{re.escape(quoted_placeholder)}\s*=\s*\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*\b",
        ]
        for pat in generic_patterns:
            new_t, n = re.subn(pat, r, t, count=1, flags=re.IGNORECASE)
            if n > 0:
                return new_t
        if quoted_placeholder in t:
            return t.replace(quoted_placeholder, f"({r})", 1)
    return t


def _extract_placeholder_alias(mask_sql: str, edge_id: str) -> Optional[str]:
    """
    Extract table alias from mask predicate like:
      t4.c_email_address = '__CUT_E2__'
    """
    try:
        tree = parse_one(mask_sql)
    except Exception:
        return None

    placeholder = f"__CUT_{edge_id}__"
    alias_holder: List[Optional[str]] = [None]

    def visit(node: exp.Expression) -> None:
        if alias_holder[0] is not None:
            return
        if isinstance(node, exp.EQ):
            left, right = node.left, node.right
            if isinstance(left, exp.Column) and isinstance(right, exp.Literal) and str(right.this) == placeholder:
                alias_holder[0] = left.table
                return
            if isinstance(right, exp.Column) and isinstance(left, exp.Literal) and str(left.this) == placeholder:
                alias_holder[0] = right.table
                return
        for v in node.args.values():
            if isinstance(v, exp.Expression):
                visit(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, exp.Expression):
                        visit(item)

    visit(tree)
    return alias_holder[0]


def _extract_placeholder_alias_from_parent_sql(
    parent_sql: str,
    mask_sql: str,
    edge_id: str,
) -> Optional[str]:
    """
    Extract alias from parent rewritten SQL by locating the placeholder condition.
    Example in parent SQL: t4.c_preferred_cust_flag = '__CUT_E2__' -> t4
    """
    placeholder = f"__CUT_{edge_id}__"
    m_col = re.match(
        r"\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'(__CUT_E\d+__|__CUT__)'\s*$",
        (mask_sql or "").strip(),
        flags=re.IGNORECASE,
    )
    if not m_col:
        return None
    col = m_col.group(1)
    pat = (
        rf"\b([A-Za-z_][A-Za-z0-9_]*)\.{re.escape(col)}\s*=\s*'{re.escape(placeholder)}'"
    )
    found = re.search(pat, parent_sql or "", flags=re.IGNORECASE)
    if found:
        return found.group(1)
    if re.search(rf"\b{re.escape(col)}\s*=\s*'{re.escape(placeholder)}'", parent_sql or "", flags=re.IGNORECASE):
        return ""
    return None


def _retarget_column_aliases(sql_text: str, from_alias: Optional[str], to_alias: Optional[str]) -> str:
    """Retarget qualified columns from one alias to another via AST."""
    src = str(from_alias or "").strip()
    dst = str(to_alias or "").strip()
    if not src or not dst or src == dst:
        return sql_text
    try:
        tree = parse_one(sql_text)
    except Exception:
        return sql_text

    def visit(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Column) and node.table == src:
            node.set("table", exp.to_identifier(dst))
        for key, value in node.args.items():
            if isinstance(value, exp.Expression):
                node.set(key, visit(value))
            elif isinstance(value, list):
                node.set(key, [visit(item) if isinstance(item, exp.Expression) else item for item in value])
        return node

    return visit(tree).sql()


def _infer_child_alias_for_parent_mapping(cut_expr_sql: str, parent_alias: Optional[str]) -> Optional[str]:
    """
    Infer child-side alias from a correlated predicate in cut expression.
    Example: c.col = t4.col with parent_alias=t4 -> return c.
    """
    p_alias = str(parent_alias or "").strip()
    if not p_alias:
        return None
    try:
        tree = parse_one(cut_expr_sql)
    except Exception:
        return None

    def visit(node: exp.Expression) -> Optional[str]:
        if isinstance(node, exp.EQ):
            left, right = node.left, node.right
            if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                if left.table == p_alias and right.table and right.table != p_alias:
                    return right.table
                if right.table == p_alias and left.table and left.table != p_alias:
                    return left.table
        for v in node.args.values():
            if isinstance(v, exp.Expression):
                out = visit(v)
                if out:
                    return out
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, exp.Expression):
                        out = visit(item)
                        if out:
                            return out
        return None

    return visit(tree)


def _find_placeholder_condition_in_sql(parent_sql: str, edge_id: str) -> Optional[str]:
    """
    Find the full placeholder condition (e.g. ``alias.col = '__CUT_Ex__'``) in
    *parent_sql* by searching for the placeholder text directly.

    This handles cases where Calcite renamed the table alias or column name so
    that searching by the original mask column fails.  Returns the matched
    condition string, or *None* if the placeholder is not present.
    """
    placeholder = f"__CUT_{edge_id}__"
    pat = rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*'{re.escape(placeholder)}'"
    found = re.search(pat, parent_sql or "", flags=re.IGNORECASE)
    if found:
        return found.group(0)
    pat2 = rf"'{re.escape(placeholder)}'\s*=\s*\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*"
    found2 = re.search(pat2, parent_sql or "", flags=re.IGNORECASE)
    if found2:
        return found2.group(0)
    return None


def _extract_alias_from_condition(condition_sql: str, edge_id: str) -> Optional[str]:
    """
    Extract the table alias from a placeholder condition such as
    ``alias.col = '__CUT_Ex__'``.  Returns the alias string (may be empty when
    the column is unqualified), or *None* if the pattern is not recognised.
    """
    placeholder = f"__CUT_{edge_id}__"
    pat = rf"^\s*([A-Za-z_][A-Za-z0-9_]*)\.(?:[A-Za-z_][A-Za-z0-9_]*)\s*=\s*'{re.escape(placeholder)}'"
    m = re.match(pat, (condition_sql or "").strip(), flags=re.IGNORECASE)
    if m:
        return m.group(1)
    pat2 = rf"^\s*'{re.escape(placeholder)}'\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\.(?:[A-Za-z_][A-Za-z0-9_]*)"
    m2 = re.match(pat2, (condition_sql or "").strip(), flags=re.IGNORECASE)
    if m2:
        return m2.group(1)
    return None


def _replace_edge_placeholder_expr_once(parent_sql: str, edge_id: str, replacement_expr_sql: str) -> Tuple[str, Optional[str]]:
    """
    Replace expression containing '__CUT_<edge_id>__' with replacement expression.
    Returns (new_sql, detected_parent_alias_for_placeholder).
    """
    placeholder = f"__CUT_{edge_id}__"
    try:
        tree = parse_one(parent_sql)
        replacement_expr = parse_one(replacement_expr_sql)
    except Exception:
        return parent_sql, None

    detected_alias: List[Optional[str]] = [None]
    replaced = False

    def expr_has_placeholder(node: exp.Expression) -> bool:
        if isinstance(node, exp.Literal) and str(node.this) == placeholder:
            return True
        return any(
            expr_has_placeholder(v)
            for v in node.args.values()
            if isinstance(v, exp.Expression)
        ) or any(
            expr_has_placeholder(item)
            for v in node.args.values()
            if isinstance(v, list)
            for item in v
            if isinstance(item, exp.Expression)
        )

    def extract_alias_from_expr(node: exp.Expression) -> Optional[str]:
        if isinstance(node, exp.EQ):
            left, right = node.left, node.right
            if isinstance(left, exp.Column):
                return left.table
            if isinstance(right, exp.Column):
                return right.table
        for v in node.args.values():
            if isinstance(v, exp.Expression):
                alias = extract_alias_from_expr(v)
                if alias:
                    return alias
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, exp.Expression):
                        alias = extract_alias_from_expr(item)
                        if alias:
                            return alias
        return None

    def visit(node: exp.Expression) -> exp.Expression:
        nonlocal replaced
        if not replaced and expr_has_placeholder(node):
            detected_alias[0] = extract_alias_from_expr(node)
            replaced = True
            return replacement_expr.copy()
        for key, value in node.args.items():
            if isinstance(value, exp.Expression):
                node.set(key, visit(value))
            elif isinstance(value, list):
                node.set(key, [visit(item) if isinstance(item, exp.Expression) else item for item in value])
        return node

    out = visit(tree)
    return out.sql(), detected_alias[0]


def _cut_expr_with_rewritten_child(edge: EdgeInfo, rewritten_child_sql: str) -> str:
    """
    Rebuild edge.cut_sql by replacing its first Subquery with rewritten child SQL.
    """

    raw_child = ""
    try:
        raw_child = parse_one(edge.cut_sql).find(exp.Select).sql()  # first SELECT under edge.cut_sql
    except Exception:
        raw_child = ""
    if raw_child and raw_child in edge.cut_sql:
        return edge.cut_sql.replace(raw_child, rewritten_child_sql, 1)

    cut_expr = parse_one(edge.cut_sql)
    rewritten_child = parse_one(rewritten_child_sql)
    rewritten_subquery = exp.Subquery(this=rewritten_child)
    replaced = False

    def visit(node: exp.Expression) -> exp.Expression:
        nonlocal replaced
        if not replaced and isinstance(node, exp.Exists):
            # EXISTS usually contains a Select directly (not exp.Subquery).
            node.set("this", rewritten_child.copy())
            replaced = True
            return node
        if not replaced and isinstance(node, exp.Subquery):
            replaced = True
            return rewritten_subquery
        for key, value in node.args.items():
            if isinstance(value, exp.Expression):
                node.set(key, visit(value))
            elif isinstance(value, list):
                node.set(key, [visit(item) if isinstance(item, exp.Expression) else item for item in value])
        return node

    out = visit(cut_expr)
    # Scalar-subquery fallback when cut_expr itself is just a subquery text.
    if not replaced and edge.cut_kind == "scalar_subquery":
        return f"({rewritten_child_sql})"
    return out.sql()


def _merge_block_into_full_query(
    full_sql: str,
    block_root: str,
    raw_fragment_sql: str,
    merged_fragment_sql: str,
) -> Optional[str]:
    """
    Replace the block root SELECT subtree in the full query with the merged fragment.
    Tries exact substring replace first, then preorder index-based replace (same Select
    ordering as _collect_graph).
    """
    if raw_fragment_sql in full_sql:
        return full_sql.replace(raw_fragment_sql, merged_fragment_sql, 1)

    target_i = int(block_root[1:])
    counter = [0]
    tree_holder: List[exp.Expression] = [parse_one(full_sql)]
    merged_expr = parse_one(merged_fragment_sql)

    def walk(parent: Optional[exp.Expression], key: Optional[str], idx: Optional[int], node: exp.Expression) -> bool:
        if isinstance(node, exp.Select):
            i = counter[0]
            counter[0] += 1
            if i == target_i:
                if parent is None:
                    tree_holder[0] = merged_expr
                elif idx is not None and key is not None:
                    lst = parent.args[key]
                    assert isinstance(lst, list)
                    lst[idx] = merged_expr  # type: ignore[index]
                elif key is not None:
                    parent.set(key, merged_expr)  # type: ignore[arg-type]
                return True
        for k, v in list(node.args.items()):
            if isinstance(v, exp.Expression):
                if walk(node, k, None, v):
                    return True
            elif isinstance(v, list):
                for j, item in enumerate(v):
                    if isinstance(item, exp.Expression) and walk(node, k, j, item):
                        return True
        return False

    counter[0] = 0
    if not walk(None, None, None, tree_holder[0]):
        return None
    return tree_holder[0].sql()


def _get_select_sql_at_index(full_sql: str, target_i: int) -> Optional[str]:
    """
    Return the SQL text of the target_i-th SELECT in preorder (same ordering as _collect_graph / _merge).
    Used after child blocks are rewritten so we splice using the live subtree text, not the stale original.
    """
    tree = parse_one(full_sql)
    counter = [0]

    def walk(node: exp.Expression) -> Optional[str]:
        if isinstance(node, exp.Select):
            i = counter[0]
            counter[0] += 1
            if i == target_i:
                return node.sql()
        for v in node.args.values():
            if isinstance(v, exp.Expression):
                got = walk(v)
                if got is not None:
                    return got
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, exp.Expression):
                        got = walk(item)
                        if got is not None:
                            return got
        return None

    return walk(tree)


def _build_parent_map(edges: Sequence[EdgeInfo]) -> Dict[str, str]:
    return {edge.child: edge.parent for edge in edges}


def _block_roots(root: str, cuts: Set[str], edge_map: Dict[str, EdgeInfo]) -> Set[str]:
    roots = {root}
    roots.update(edge_map[eid].child for eid in cuts)
    return roots


def _assign_block_root(node_id: str, roots: Set[str], parent_map: Dict[str, str]) -> str:
    cur = node_id
    while cur not in roots and cur in parent_map:
        cur = parent_map[cur]
    return cur


def _split_blocks(
    root: str,
    node_infos: Dict[str, NodeInfo],
    edge_map: Dict[str, EdgeInfo],
    cuts: Set[str],
) -> Tuple[Dict[str, List[str]], Dict[str, List[EdgeInfo]]]:
    parent_map = _build_parent_map(edge_map.values())
    roots = _block_roots(root, cuts, edge_map)
    blocks: Dict[str, List[str]] = {rid: [] for rid in roots}
    for node_id in node_infos:
        block_root = _assign_block_root(node_id, roots, parent_map)
        blocks.setdefault(block_root, []).append(node_id)
    for rid in blocks:
        blocks[rid] = sorted(blocks[rid], key=lambda x: int(x[1:]))

    boundary_edges: Dict[str, List[EdgeInfo]] = {rid: [] for rid in roots}
    for eid in cuts:
        edge = edge_map[eid]
        parent_block = _assign_block_root(edge.parent, roots, parent_map)
        boundary_edges.setdefault(parent_block, []).append(edge)
    for rid in boundary_edges:
        boundary_edges[rid] = sorted(boundary_edges[rid], key=lambda x: int(x.edge_id[1:]))
    return blocks, boundary_edges


def _derived_table_parent_nodes(cuts: Set[str], edge_map: Dict[str, EdgeInfo]) -> Set[str]:
    """
    Parent SELECTs of selected FROM/JOIN derived-table cuts.

    For these cuts we rewrite the detached derived-table SELECT itself, then splice
    that SELECT back into the live full query. The containing parent query must not
    be sent through the rewrite backend, otherwise the FROM/JOIN context can be
    reshaped while the child is being stitched back.
    """
    return {
        edge_map[eid].parent
        for eid in cuts
        if eid in edge_map and edge_map[eid].cut_kind == "derived_table_subquery"
    }


def _evaluate_block(
    full_sql: str,
    full_cost_before: float,
    block_root: str,
    block_nodes: List[str],
    boundary_edges: List[EdgeInfo],
    node_infos: Dict[str, NodeInfo],
    fixer: SubqueryFixer,
    context_tables: Dict[str, str],
    cache: Dict[Tuple[str, Tuple[str, ...]], BlockEval],
) -> BlockEval:
    cache_key = (block_root, tuple(edge.edge_id for edge in boundary_edges))
    if cache_key in cache:
        return BlockEval(**asdict(cache[cache_key]))

    raw_sql = node_infos[block_root].sql
    # Do not mask boundary cuts inside this fragment (see module docstring).
    masked_sql = _mask_selected_cut_exprs(raw_sql, set())
    fixed_sql, standalone_prep = _prepare_sql_for_standalone(masked_sql, fixer, context_tables)
    rewritten_sql = _safe_rewrite(fixed_sql)
    rewrite_changed = _normalize_sql(fixed_sql) != _normalize_sql(rewritten_sql)

    merged_fragment = fixer.restore_subquery_from_standalone(rewritten_sql, standalone_prep)
    merged_fragment = _restore_boundary_mask_sql(merged_fragment, [])
    merged_full = _merge_block_into_full_query(full_sql, block_root, raw_sql, merged_fragment)
    merged_snap = merged_full or ""

    try:
        if merged_full is None:
            raise RuntimeError("Could not splice rewritten block back into full SQL")
        full_cost_after = _cost(merged_full)
        if not math.isfinite(full_cost_before) or not math.isfinite(full_cost_after):
            raise RuntimeError("Non-finite EXPLAIN cost on full query")
        result = BlockEval(
            root_node=block_root,
            nodes=block_nodes,
            boundary_cut_edges=[edge.edge_id for edge in boundary_edges],
            boundary_cut_kinds=[edge.cut_kind for edge in boundary_edges],
            executable=True,
            original_cost=full_cost_before,
            rewritten_cost=full_cost_after,
            gain=full_cost_before - full_cost_after,
            original_sql=fixed_sql,
            rewritten_sql=rewritten_sql,
            rewrite_changed=rewrite_changed,
            merged_full_sql=merged_snap,
            splice_applied=True,
        )
    except Exception as exc:
        result = BlockEval(
            root_node=block_root,
            nodes=block_nodes,
            boundary_cut_edges=[edge.edge_id for edge in boundary_edges],
            boundary_cut_kinds=[edge.cut_kind for edge in boundary_edges],
            executable=False,
            original_cost=None,
            rewritten_cost=None,
            gain=0.0,
            original_sql=fixed_sql,
            rewritten_sql=rewritten_sql,
            rewrite_changed=rewrite_changed,
            merged_full_sql=merged_snap,
            splice_applied=False,
            error=str(exc),
        )
    cache[cache_key] = result
    return BlockEval(**asdict(result))


def _rewrite_block_fragment(
    block_root: str,
    block_nodes: List[str],
    boundary_edges: List[EdgeInfo],
    node_infos: Dict[str, NodeInfo],
    fixer: SubqueryFixer,
    context_tables: Dict[str, str],
    fragment_cache: Dict[Tuple[str, Tuple[str, ...], str], Dict[str, Any]],
    raw_sql_override: Optional[str] = None,
    parent_mask_debug: Optional[Dict[str, Any]] = None,
    collect_rewrite_trace: bool = False,
) -> Tuple[str, str, str, str, bool, Optional[Dict[str, Any]]]:
 
    raw_sql = raw_sql_override if raw_sql_override is not None else node_infos[block_root].sql
    raw_sig = _normalize_sql(raw_sql)
    cache_key = (block_root, tuple(edge.edge_id for edge in boundary_edges), raw_sig)
    if cache_key in fragment_cache:
        c = fragment_cache[cache_key]
        tp = c.get("trace_payload")
        return (
            c["raw"],
            c["fixed"],
            c["rewritten"],
            c["merged"],
            c["changed"] == "1",
            dict(tp) if collect_rewrite_trace and tp is not None else None,
        )

    # Live fragment is complete after bottom-up splices; do not strip nested cuts here.
    masked_sql = _mask_selected_cut_exprs(raw_sql, set())
    fixed_sql, standalone_prep = _prepare_sql_for_standalone(masked_sql, fixer, context_tables)
    rewritten_sql = _safe_rewrite(fixed_sql)
    rewrite_changed = _normalize_sql(fixed_sql) != _normalize_sql(rewritten_sql)

    merged_fragment = fixer.restore_subquery_from_standalone(rewritten_sql, standalone_prep)
    merged_fragment = _restore_boundary_mask_sql(merged_fragment, [])

    trace_payload: Dict[str, Any] = {
        "block_root": block_root,
        "block_nodes": list(block_nodes),
        "boundary_edges": [_edge_to_dict(e) for e in boundary_edges],
        "raw_fragment_sql": raw_sql,
        "masked_sql": (
            str(parent_mask_debug.get("masked_parent_sql", ""))
            if parent_mask_debug is not None
            else ""
        ),
        "parent_sql_before_mask": (
            str(parent_mask_debug.get("parent_sql_before_mask", ""))
            if parent_mask_debug is not None
            else ""
        ),
        "parent_cut_placeholders": (
            list(parent_mask_debug.get("parent_cut_placeholders", []))
            if parent_mask_debug is not None
            else []
        ),
        "fixed_for_standalone_sql": fixed_sql,
        "calcite_rewritten_fragment_sql": rewritten_sql,
        "merged_fragment_sql_after_restore": merged_fragment,
        "standalone_placeholder_context_alias": standalone_prep.placeholder_context_alias,
        "standalone_placeholder_replacements": [
            {
                "original_sql": rep.original_sql,
                "outer_alias": rep.outer_alias,
                "table_name": rep.table_name,
                "column_name": rep.column_name,
                "placeholder_column": rep.placeholder_column,
                "placeholder_literal_sql": rep.placeholder_literal_sql,
            }
            for rep in standalone_prep.replacements
        ],
        "from_cache": False,
    }

    fragment_cache[cache_key] = {
        "raw": raw_sql,
        "fixed": fixed_sql,
        "rewritten": rewritten_sql,
        "merged": merged_fragment,
        "changed": "1" if rewrite_changed else "0",
        "trace_payload": trace_payload,
    }
    trace = trace_payload if collect_rewrite_trace else None
    return raw_sql, fixed_sql, rewritten_sql, merged_fragment, rewrite_changed, trace


def _evaluate_cut_set(
    full_sql: str,
    base_cost: float,
    root: str,
    cuts: Set[str],
    node_infos: Dict[str, NodeInfo],
    edge_map: Dict[str, EdgeInfo],
    fixer: SubqueryFixer,
    context_tables: Dict[str, str],
    cache: Dict[Tuple[str, Tuple[str, ...]], BlockEval],
    collect_rewrite_trace: bool = False,
    all_rewrites_parallel: bool = False,
) -> Dict:
    blocks, boundary_edges = _split_blocks(root, node_infos, edge_map, cuts)
    block_roots = sorted(blocks.keys(), key=lambda x: int(x[1:]))
    current_full_sql = full_sql
    fragment_cache: Dict[Tuple[str, Tuple[str, ...], str], Dict[str, Any]] = {}
    block_results: List[BlockEval] = []
    fatal_error: Optional[str] = None
    rewrite_trace: List[Dict[str, Any]] = []
    skip_rewrite_roots = _derived_table_parent_nodes(cuts, edge_map)

    rewrite_roots = sorted(
        [rid for rid in block_roots if rid != root],
        key=lambda x: -int(x[1:]),
    )
    precomputed_rewrites: Dict[str, Dict[str, Any]] = {}
    precompute_executor: Optional[ThreadPoolExecutor] = None
    if all_rewrites_parallel and rewrite_roots:
        max_workers = max(1, len(rewrite_roots) * 2)
        precompute_executor = ThreadPoolExecutor(max_workers=max_workers)
        for rid in rewrite_roots:
            b_edges = boundary_edges.get(rid, [])
            target_i = int(rid[1:])
            live_raw = _get_select_sql_at_index(full_sql, target_i)
            if live_raw is None:
                continue
            incoming_cut_edges = sorted(
                [edge_map[eid] for eid in cuts if edge_map[eid].child == rid],
                key=lambda e: int(e.edge_id[1:]),
            )
            incoming_edges_are_derived_tables = bool(incoming_cut_edges) and all(
                e.cut_kind == "derived_table_subquery" for e in incoming_cut_edges
            )
            parent_mask_debug: Optional[Dict[str, Any]] = None
            if incoming_cut_edges and not incoming_edges_are_derived_tables:
                parent_id = incoming_cut_edges[0].parent
                parent_sql_live = _get_select_sql_at_index(full_sql, int(parent_id[1:])) or ""
                if parent_sql_live:
                    cut_sql_to_edge_id = {e.cut_sql: e.edge_id for e in incoming_cut_edges}
                    cut_sql_to_mask_sql = {e.cut_sql: e.mask_sql for e in incoming_cut_edges}
                    masked_parent_sql = _mask_selected_cut_exprs(
                        parent_sql_live,
                        set(cut_sql_to_edge_id.keys()),
                        cut_sql_to_edge_id=cut_sql_to_edge_id,
                        cut_sql_to_mask_sql=cut_sql_to_mask_sql,
                    )
                    parent_mask_debug = {
                        "parent_node": parent_id,
                        "parent_sql_before_mask": parent_sql_live,
                        "masked_parent_sql": masked_parent_sql,
                        "parent_cut_placeholders": [
                            {
                                "edge_id": e.edge_id,
                                "cut_sql": e.cut_sql,
                                "mask_sql": e.mask_sql,
                            }
                            for e in incoming_cut_edges
                        ],
                    }

            parent_rewrite_state: Optional[Dict[str, Any]] = None
            parent_future: Optional[Any] = None
            if parent_mask_debug is not None and not incoming_edges_are_derived_tables:
                parent_masked_sql = str(parent_mask_debug.get("masked_parent_sql", "") or "")
                parent_fixed_sql, parent_standalone_prep = _prepare_sql_for_standalone(
                    parent_masked_sql, fixer, context_tables
                )
                parent_rewrite_state = {
                    "parent_id": str(parent_mask_debug.get("parent_node", "") or ""),
                    "parent_raw_sql": str(parent_mask_debug.get("parent_sql_before_mask", "") or ""),
                    "parent_masked_sql": parent_masked_sql,
                    "parent_cut_placeholders": list(parent_mask_debug.get("parent_cut_placeholders", []) or []),
                    "parent_fixed_sql": parent_fixed_sql,
                    "parent_standalone_prep": parent_standalone_prep,
                    "parent_rewritten_sql": None,
                }
                parent_future = precompute_executor.submit(_safe_rewrite, parent_fixed_sql)

            block_future = None
            if rid not in skip_rewrite_roots:
                block_future = precompute_executor.submit(
                    _rewrite_block_fragment,
                    block_root=rid,
                    block_nodes=blocks[rid],
                    boundary_edges=b_edges,
                    node_infos=node_infos,
                    fixer=fixer,
                    context_tables=context_tables,
                    fragment_cache=fragment_cache,
                    raw_sql_override=live_raw,
                    parent_mask_debug=parent_mask_debug,
                    collect_rewrite_trace=collect_rewrite_trace,
                )
            precomputed_rewrites[rid] = {
                "live_raw": live_raw,
                "incoming_cut_edges": incoming_cut_edges,
                "incoming_edges_are_derived_tables": incoming_edges_are_derived_tables,
                "parent_mask_debug": parent_mask_debug,
                "parent_rewrite_state": parent_rewrite_state,
                "block_future": block_future,
                "parent_future": parent_future,
            }
    for rid in rewrite_roots:
        b_edges = boundary_edges.get(rid, [])
        target_i = int(rid[1:])
        try:
            precomputed = precomputed_rewrites.get(rid)
            live_raw = (
                str(precomputed["live_raw"])
                if precomputed is not None
                else _get_select_sql_at_index(current_full_sql, target_i)
            )
            if live_raw is None:
                raise RuntimeError(f"Could not locate SELECT index {target_i} in current full SQL for {rid}")

            if rid in skip_rewrite_roots:
                fixed_sql, _ = _prepare_sql_for_standalone(live_raw, fixer, context_tables)
                if collect_rewrite_trace:
                    rewrite_trace.append(
                        {
                            "block_root": rid,
                            "block_nodes": list(blocks[rid]),
                            "boundary_edges": [_edge_to_dict(e) for e in b_edges],
                            "raw_fragment_sql": live_raw,
                            "fixed_for_standalone_sql": fixed_sql,
                            "rewrite_skipped": True,
                            "skip_reason": "parent_of_selected_derived_table_cut",
                            "merged_full_sql_after_splice": current_full_sql,
                            "splice_ok": True,
                        }
                    )
                block_results.append(
                    BlockEval(
                        root_node=rid,
                        nodes=blocks[rid],
                        boundary_cut_edges=[edge.edge_id for edge in b_edges],
                        boundary_cut_kinds=[edge.cut_kind for edge in b_edges],
                        executable=True,
                        original_cost=None,
                        rewritten_cost=None,
                        gain=0.0,
                        original_sql=fixed_sql,
                        rewritten_sql=fixed_sql,
                        rewrite_changed=False,
                        merged_full_sql=current_full_sql,
                        splice_applied=False,
                        error="Skipped rewrite: parent of selected FROM/JOIN derived-table cut.",
                    )
                )
                continue

            # Build parent-side masked SQL for trace/debug:
            # replace the cut expression(s) in parent query with edge-specific
            # placeholders so parent rewrite can be reasoned about and later
            # stitched back by placeholder position.
            if precomputed is not None:
                incoming_cut_edges = list(precomputed["incoming_cut_edges"])
                incoming_edges_are_derived_tables = bool(precomputed["incoming_edges_are_derived_tables"])
                parent_mask_debug = precomputed.get("parent_mask_debug")
            else:
                incoming_cut_edges = sorted(
                    [edge_map[eid] for eid in cuts if edge_map[eid].child == rid],
                    key=lambda e: int(e.edge_id[1:]),
                )
                parent_mask_debug: Optional[Dict[str, Any]] = None
                incoming_edges_are_derived_tables = bool(incoming_cut_edges) and all(
                    e.cut_kind == "derived_table_subquery" for e in incoming_cut_edges
                )
            if precomputed is None and incoming_cut_edges and not incoming_edges_are_derived_tables:
                parent_id = incoming_cut_edges[0].parent
                parent_sql_live = _get_select_sql_at_index(current_full_sql, int(parent_id[1:])) or ""
                if parent_sql_live:
                    # Always enforce edge-specific placeholders so multiple cuts
                    # in one parent never collide (__CUT_E0__, __CUT_E1__, ...).
                    cut_sql_to_edge_id = {e.cut_sql: e.edge_id for e in incoming_cut_edges}
                    cut_sql_to_mask_sql = {e.cut_sql: e.mask_sql for e in incoming_cut_edges}
                    masked_parent_sql = _mask_selected_cut_exprs(
                        parent_sql_live,
                        set(cut_sql_to_edge_id.keys()),
                        cut_sql_to_edge_id=cut_sql_to_edge_id,
                        cut_sql_to_mask_sql=cut_sql_to_mask_sql,
                    )
                    parent_mask_debug = {
                        "parent_node": parent_id,
                        "parent_sql_before_mask": parent_sql_live,
                        "masked_parent_sql": masked_parent_sql,
                        "parent_cut_placeholders": [
                            {
                                "edge_id": e.edge_id,
                                "cut_sql": e.cut_sql,
                                "mask_sql": e.mask_sql,
                            }
                            for e in incoming_cut_edges
                        ],
                    }

            parent_rewrite_state: Optional[Dict[str, Any]]
            if precomputed is not None:
                parent_rewrite_state = precomputed.get("parent_rewrite_state")
            else:
                parent_rewrite_state = None
            if precomputed is None and parent_mask_debug is not None and not incoming_edges_are_derived_tables:
                parent_masked_sql = str(parent_mask_debug.get("masked_parent_sql", "") or "")
                parent_fixed_sql, parent_standalone_prep = _prepare_sql_for_standalone(
                    parent_masked_sql, fixer, context_tables
                )
                parent_rewrite_state = {
                    "parent_id": str(parent_mask_debug.get("parent_node", "") or ""),
                    "parent_raw_sql": str(parent_mask_debug.get("parent_sql_before_mask", "") or ""),
                    "parent_masked_sql": parent_masked_sql,
                    "parent_cut_placeholders": list(parent_mask_debug.get("parent_cut_placeholders", []) or []),
                    "parent_fixed_sql": parent_fixed_sql,
                    "parent_standalone_prep": parent_standalone_prep,
                    "parent_rewritten_sql": None,
                }

            if precomputed is not None and precomputed.get("block_future") is not None:
                (
                    raw_fragment_sql,
                    fixed_sql,
                    calcite_rewritten_sql,
                    merged_fragment_sql,
                    rewrite_changed,
                    block_trace,
                ) = precomputed["block_future"].result()
                if parent_rewrite_state is not None and precomputed.get("parent_future") is not None:
                    parent_rewrite_state["parent_rewritten_sql"] = precomputed["parent_future"].result()
            elif _LLMR2_PARALLEL_REWRITE and parent_rewrite_state is not None:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    block_future = executor.submit(
                        _rewrite_block_fragment,
                        block_root=rid,
                        block_nodes=blocks[rid],
                        boundary_edges=b_edges,
                        node_infos=node_infos,
                        fixer=fixer,
                        context_tables=context_tables,
                        fragment_cache=fragment_cache,
                        raw_sql_override=live_raw,
                        parent_mask_debug=parent_mask_debug,
                        collect_rewrite_trace=collect_rewrite_trace,
                    )
                    parent_future = executor.submit(_safe_rewrite, str(parent_rewrite_state["parent_fixed_sql"]))
                    (
                        raw_fragment_sql,
                        fixed_sql,
                        calcite_rewritten_sql,
                        merged_fragment_sql,
                        rewrite_changed,
                        block_trace,
                    ) = block_future.result()
                    parent_rewrite_state["parent_rewritten_sql"] = parent_future.result()
            else:
                raw_fragment_sql, fixed_sql, calcite_rewritten_sql, merged_fragment_sql, rewrite_changed, block_trace = (
                    _rewrite_block_fragment(
                        block_root=rid,
                        block_nodes=blocks[rid],
                        boundary_edges=b_edges,
                        node_infos=node_infos,
                        fixer=fixer,
                        context_tables=context_tables,
                        fragment_cache=fragment_cache,
                        raw_sql_override=live_raw,
                        parent_mask_debug=parent_mask_debug,
                        collect_rewrite_trace=collect_rewrite_trace,
                    )
                )

            # New pipeline for cut edges:
            # 1) rewrite masked parent SQL
            # 2) splice rewritten child back by mask placeholder
            # 3) splice rewritten parent into current full SQL
            merged_full: Optional[str]
            if incoming_edges_are_derived_tables:
                if collect_rewrite_trace and block_trace is not None:
                    block_trace["parent_rewrite_skipped"] = True
                    block_trace["parent_rewrite_skip_reason"] = "selected_cut_is_from_or_join_derived_table"
                merged_full = _merge_block_into_full_query(
                    current_full_sql, rid, raw_fragment_sql, merged_fragment_sql
                )
            elif parent_rewrite_state is not None:
                parent_id = str(parent_rewrite_state["parent_id"])
                parent_raw_sql = str(parent_rewrite_state["parent_raw_sql"])
                parent_masked_sql = str(parent_rewrite_state["parent_masked_sql"])
                parent_cut_placeholders = list(parent_rewrite_state["parent_cut_placeholders"])
                cut_by_edge_id = {
                    str(item.get("edge_id", "")): str(item.get("cut_sql", ""))
                    for item in parent_cut_placeholders
                    if str(item.get("edge_id", "")).strip()
                }

                parent_fixed_sql = str(parent_rewrite_state["parent_fixed_sql"])
                parent_standalone_prep = parent_rewrite_state["parent_standalone_prep"]
                parent_rewritten_sql = parent_rewrite_state.get("parent_rewritten_sql")
                if parent_rewritten_sql is None:
                    parent_rewritten_sql = _safe_rewrite(parent_fixed_sql)
                parent_rewritten_sql_stitched = parent_rewritten_sql
                rewritten_edges_debug: List[Dict[str, str]] = []
                parent_rewrite_fallback_reason = ""

                # Replace mask placeholders with rewritten child expression.
                for e in incoming_cut_edges:
                    cut_sql_for_parent = cut_by_edge_id.get(e.edge_id, e.cut_sql)
                    edge_for_parent = EdgeInfo(
                        edge_id=e.edge_id,
                        parent=e.parent,
                        child=e.child,
                        cut_sql=cut_sql_for_parent,
                        cut_kind=e.cut_kind,
                        mask_sql=e.mask_sql,
                    )
                    rewritten_edge_sql = _cut_expr_with_rewritten_child(edge_for_parent, merged_fragment_sql)

                    original_parent_alias = _extract_placeholder_alias(e.mask_sql, e.edge_id)

                    parent_alias = _extract_placeholder_alias_from_parent_sql(
                        parent_rewritten_sql_stitched,
                        e.mask_sql,
                        e.edge_id,
                    )

                    effective_mask_sql = e.mask_sql

                    if parent_alias is None:
                        actual_condition = _find_placeholder_condition_in_sql(
                            parent_rewritten_sql_stitched, e.edge_id
                        )
                        if actual_condition:
                            effective_mask_sql = actual_condition
                            parent_alias = _extract_alias_from_condition(actual_condition, e.edge_id)
                  
                    if original_parent_alias and parent_alias and original_parent_alias != parent_alias:
                        rewritten_edge_for_parent = _retarget_column_aliases(
                            rewritten_edge_sql,
                            from_alias=original_parent_alias,
                            to_alias=parent_alias,
                        )
                    else:
                        rewritten_edge_for_parent = rewritten_edge_sql

                    parent_rewritten_sql_stitched = _replace_mask_once(
                        parent_rewritten_sql_stitched,
                        effective_mask_sql,
                        rewritten_edge_for_parent,
                    )
                    rewritten_edges_debug.append(
                        {
                            "edge_id": e.edge_id,
                            "parent_alias": str(parent_alias or ""),
                            "child_alias": str(original_parent_alias or ""),
                            "rewritten_edge": rewritten_edge_for_parent,
                        }
                    )

                parent_merged_sql = fixer.restore_subquery_from_standalone(
                    parent_rewritten_sql_stitched,
                    parent_standalone_prep,
                )

                if collect_rewrite_trace and block_trace is not None:
                    block_trace["parent_masked_sql_for_rewrite"] = parent_masked_sql
                    block_trace["parent_fixed_for_standalone_sql"] = parent_fixed_sql
                    block_trace["parent_calcite_rewritten_sql"] = parent_rewritten_sql
                    block_trace["parent_calcite_rewritten_sql_after_stitch"] = parent_rewritten_sql_stitched
                    block_trace["rewritten_edges"] = rewritten_edges_debug
                    block_trace["parent_merged_sql_after_child_stitch"] = parent_merged_sql
                    if parent_rewrite_fallback_reason:
                        block_trace["parent_rewrite_fallback_reason"] = parent_rewrite_fallback_reason

                merged_full = _merge_block_into_full_query(
                    current_full_sql,
                    parent_id,
                    parent_raw_sql,
                    parent_merged_sql,
                )
            else:
                merged_full = _merge_block_into_full_query(
                    current_full_sql, rid, raw_fragment_sql, merged_fragment_sql
                )
            if merged_full is None:
                raise RuntimeError("Could not splice rewritten block back into full SQL")

            step_cost = _cost(merged_full)
            if not math.isfinite(step_cost):
                if collect_rewrite_trace and block_trace is not None:
                    bt = dict(block_trace)
                    bt["merged_full_sql_after_splice"] = merged_full
                    bt["pg_explain_cost_after_splice"] = None
                    bt["splice_ok"] = False
                    bt["splice_error_note"] = "PostgreSQL EXPLAIN returned non-finite cost after splice"
                    rewrite_trace.append(bt)
                block_results.append(
                    BlockEval(
                        root_node=rid,
                        nodes=blocks[rid],
                        boundary_cut_edges=[edge.edge_id for edge in b_edges],
                        boundary_cut_kinds=[edge.cut_kind for edge in b_edges],
                        executable=True,
                        original_cost=None,
                        rewritten_cost=None,
                        gain=0.0,
                        original_sql=fixed_sql,
                        rewritten_sql=calcite_rewritten_sql,
                        rewrite_changed=rewrite_changed,
                        merged_full_sql=current_full_sql,
                        splice_applied=False,
                        error=(
                            "Rewritten splice rejected by PostgreSQL EXPLAIN (query would not execute "
                            "or planner error); left previous full SQL unchanged for this block."
                        ),
                    )
                )
                continue

            if collect_rewrite_trace and block_trace is not None:
                bt = dict(block_trace)
                bt["merged_full_sql_after_splice"] = merged_full
                bt["pg_explain_cost_after_splice"] = float(step_cost)
                bt["splice_ok"] = True
                rewrite_trace.append(bt)

            current_full_sql = merged_full
            block_results.append(
                BlockEval(
                    root_node=rid,
                    nodes=blocks[rid],
                    boundary_cut_edges=[edge.edge_id for edge in b_edges],
                    boundary_cut_kinds=[edge.cut_kind for edge in b_edges],
                    executable=True,
                    original_cost=None,
                    rewritten_cost=None,
                    gain=0.0,
                    original_sql=fixed_sql,
                    rewritten_sql=calcite_rewritten_sql,
                    rewrite_changed=rewrite_changed,
                    merged_full_sql=current_full_sql,
                    splice_applied=True,
                )
            )
        except Exception as exc:
            fatal_error = str(exc)
            if collect_rewrite_trace:
                rewrite_trace.append(
                    {
                        "block_root": rid,
                        "block_nodes": list(blocks[rid]),
                        "boundary_edges": [_edge_to_dict(e) for e in b_edges],
                        "fatal_exception": str(exc),
                    }
                )
            block_results.append(
                BlockEval(
                    root_node=rid,
                    nodes=blocks[rid],
                    boundary_cut_edges=[edge.edge_id for edge in b_edges],
                    boundary_cut_kinds=[edge.cut_kind for edge in b_edges],
                    executable=False,
                    original_cost=None,
                    rewritten_cost=None,
                    gain=0.0,
                    original_sql=node_infos[rid].fixed_sql,
                    rewritten_sql=node_infos[rid].fixed_sql,
                    rewrite_changed=False,
                    merged_full_sql=current_full_sql,
                    splice_applied=False,
                    error=str(exc),
                )
            )
            break

    if precompute_executor is not None:
        precompute_executor.shutdown(wait=True)

    full_cost_after: Optional[float] = None
    if fatal_error is None:
        try:
            full_cost_after = _cost(current_full_sql)
        except Exception:
            full_cost_after = None

    all_executable = fatal_error is None and full_cost_after is not None and math.isfinite(full_cost_after)
    objective = (base_cost - full_cost_after) if (all_executable and full_cost_after is not None) else 0.0
    out: Dict[str, Any] = {
        "cut_edge_ids": sorted(cuts, key=lambda x: int(x[1:])),
        "block_roots": block_roots,
        "original_full_sql": full_sql,
        "all_blocks_executable": all_executable,
        "objective": objective,
        "full_query_cost_baseline": base_cost,
        "full_query_cost_rewritten": full_cost_after,
        "rewritten_full_sql": current_full_sql,
        "variant_fatal_error": fatal_error or "",
        "blocks": [asdict(block) for block in block_results],
    }
    if collect_rewrite_trace:
        out["rewrite_trace"] = rewrite_trace
    return out


def _edge_to_dict(edge: EdgeInfo) -> Dict[str, str]:
    return {
        "edge_id": edge.edge_id,
        "parent": edge.parent,
        "child": edge.child,
        "cut_kind": edge.cut_kind,
        "eligible_for_cut": edge.cut_kind in ELIGIBLE_CUT_KINDS,
        "cut_sql": edge.cut_sql.strip(),
        "mask_sql": (edge.mask_sql or "").strip(),
    }


def _node_to_dict(node_id: str, info: NodeInfo) -> Dict[str, str]:
    return {
        "node_id": node_id,
        "select_sql": info.sql,
        "fixed_sql": info.fixed_sql,
    }


def _search_chain_cases(
    root: str,
    node_infos: Dict[str, NodeInfo],
    edges: List[EdgeInfo],
    fixer: SubqueryFixer,
    context_tables: Dict[str, str],
) -> Tuple[List[Dict], Optional[Dict]]:
    eligible_edges = [edge for edge in edges if edge.cut_kind in ELIGIBLE_CUT_KINDS]
    edge_map = {edge.edge_id: edge for edge in edges}
    children_by_parent: Dict[str, List[EdgeInfo]] = {}
    for edge in eligible_edges:
        children_by_parent.setdefault(edge.parent, []).append(edge)
    cache: Dict[Tuple[str, Tuple[str, ...]], BlockEval] = {}
    full_sql = node_infos[root].sql
    base_cost = _cost(full_sql)

    all_cases: List[Dict] = []
    case_id = 1
    for e1 in eligible_edges:
        for e2 in children_by_parent.get(e1.child, []):
            for e3 in children_by_parent.get(e2.child, []):
                s = {e1.edge_id}
                t = {e1.edge_id, e2.edge_id}
                extra = e3.edge_id
                variants = {
                    "S": _evaluate_cut_set(full_sql, base_cost, root, s, node_infos, edge_map, fixer, context_tables, cache),
                    "S_plus_e": _evaluate_cut_set(
                        full_sql, base_cost, root, s | {extra}, node_infos, edge_map, fixer, context_tables, cache
                    ),
                    "T": _evaluate_cut_set(full_sql, base_cost, root, t, node_infos, edge_map, fixer, context_tables, cache),
                    "T_plus_e": _evaluate_cut_set(
                        full_sql, base_cost, root, t | {extra}, node_infos, edge_map, fixer, context_tables, cache
                    ),
                }
                all_executable = all(v["all_blocks_executable"] for v in variants.values())
                delta_small = variants["S_plus_e"]["objective"] - variants["S"]["objective"]
                delta_large = variants["T_plus_e"]["objective"] - variants["T"]["objective"]
                holds = delta_small >= delta_large
                strict_holds = delta_small > delta_large
                all_cases.append(
                    {
                        "case_id": case_id,
                        "chain_edge_ids": [e1.edge_id, e2.edge_id, e3.edge_id],
                        "S_edge_ids": sorted(s, key=lambda x: int(x[1:])),
                        "T_edge_ids": sorted(t, key=lambda x: int(x[1:])),
                        "e_edge_id": extra,
                        "S_edges": [_edge_to_dict(edge_map[eid]) for eid in sorted(s, key=lambda x: int(x[1:]))],
                        "T_edges": [_edge_to_dict(edge_map[eid]) for eid in sorted(t, key=lambda x: int(x[1:]))],
                        "e_edge": _edge_to_dict(edge_map[extra]),
                        "constraints": {
                            "S_subset_T_strict": True,
                            "same_extra_edge": True,
                        },
                        "all_blocks_executable": all_executable,
                        "variants": variants,
                        "delta_small": delta_small,
                        "delta_large": delta_large,
                        "diminishing_returns_holds": holds,
                        "strict_diminishing_returns": strict_holds,
                    }
                )
                case_id += 1

    def rank_key(case: Dict) -> Tuple[int, int, float, float]:
        return (
            1 if case["all_blocks_executable"] else 0,
            1 if case["strict_diminishing_returns"] else 0,
            case["delta_small"] - case["delta_large"],
            case["delta_small"],
        )

    all_cases.sort(key=rank_key, reverse=True)
    chosen = None
    for case in all_cases:
        if case["all_blocks_executable"] and case["strict_diminishing_returns"]:
            chosen = case
            break
    if chosen is None:
        for case in all_cases:
            if case["all_blocks_executable"] and case["diminishing_returns_holds"]:
                chosen = case
                break
    return all_cases, chosen


def _search_fork_cases(
    root: str,
    node_infos: Dict[str, NodeInfo],
    edges: List[EdgeInfo],
    fixer: SubqueryFixer,
    context_tables: Dict[str, str],
) -> Tuple[List[Dict], Optional[Dict]]:
    """
    Search "fork" patterns that match the user's requested experiment:

      S = {e0}
      T = {e0, e1}  (so S ⊂ T, both are valid cut sets)
      e = extra cut edge that shares the same parent SELECT as e1 (i.e., sibling edge)

    This covers common nested-subquery cases where a block root (e0.child) contains
    multiple eligible cut edges (siblings), so "add the same e" can be compared
    under different prior cut sets.
    """
    eligible_edges = [edge for edge in edges if edge.cut_kind in ELIGIBLE_CUT_KINDS]
    edge_map = {edge.edge_id: edge for edge in edges}

    children_by_parent: Dict[str, List[EdgeInfo]] = {}
    for edge in eligible_edges:
        children_by_parent.setdefault(edge.parent, []).append(edge)

    cache: Dict[Tuple[str, Tuple[str, ...]], BlockEval] = {}
    full_sql = node_infos[root].sql
    base_cost = _cost(full_sql)

    all_cases: List[Dict] = []
    case_id = 1
    for e0 in eligible_edges:
        for e1 in children_by_parent.get(e0.child, []):
            for extra in children_by_parent.get(e1.parent, []):
                if extra.edge_id == e1.edge_id:
                    continue
                s = {e0.edge_id}
                t = {e0.edge_id, e1.edge_id}
                variants = {
                    "S": _evaluate_cut_set(full_sql, base_cost, root, s, node_infos, edge_map, fixer, context_tables, cache),
                    "S_plus_e": _evaluate_cut_set(
                        full_sql, base_cost, root, s | {extra.edge_id}, node_infos, edge_map, fixer, context_tables, cache
                    ),
                    "T": _evaluate_cut_set(full_sql, base_cost, root, t, node_infos, edge_map, fixer, context_tables, cache),
                    "T_plus_e": _evaluate_cut_set(
                        full_sql, base_cost, root, t | {extra.edge_id}, node_infos, edge_map, fixer, context_tables, cache
                    ),
                }
                all_executable = all(v["all_blocks_executable"] for v in variants.values())
                delta_small = variants["S_plus_e"]["objective"] - variants["S"]["objective"]
                delta_large = variants["T_plus_e"]["objective"] - variants["T"]["objective"]
                holds = delta_small >= delta_large
                strict_holds = delta_small > delta_large
                all_cases.append(
                    {
                        "case_id": case_id,
                        "pattern": "fork",
                        "triple_edge_ids": [e0.edge_id, e1.edge_id, extra.edge_id],
                        "S_edge_ids": sorted(s, key=lambda x: int(x[1:])),
                        "T_edge_ids": sorted(t, key=lambda x: int(x[1:])),
                        "e_edge_id": extra.edge_id,
                        "S_edges": [_edge_to_dict(edge_map[eid]) for eid in sorted(s, key=lambda x: int(x[1:]))],
                        "T_edges": [_edge_to_dict(edge_map[eid]) for eid in sorted(t, key=lambda x: int(x[1:]))],
                        "e_edge": _edge_to_dict(edge_map[extra.edge_id]),
                        "constraints": {
                            "S_subset_T_strict": True,
                            "same_extra_edge": True,
                            "extra_is_sibling_of_e1": True,
                        },
                        "all_blocks_executable": all_executable,
                        "variants": variants,
                        "delta_small": delta_small,
                        "delta_large": delta_large,
                        "diminishing_returns_holds": holds,
                        "strict_diminishing_returns": strict_holds,
                    }
                )
                case_id += 1

    def rank_key(case: Dict) -> Tuple[int, int, float, float]:
        return (
            1 if case["all_blocks_executable"] else 0,
            1 if case["strict_diminishing_returns"] else 0,
            case["delta_small"] - case["delta_large"],
            case["delta_small"],
        )

    all_cases.sort(key=rank_key, reverse=True)
    chosen = None
    for case in all_cases:
        if case["all_blocks_executable"] and case["strict_diminishing_returns"]:
            chosen = case
            break
    if chosen is None:
        for case in all_cases:
            if case["all_blocks_executable"] and case["diminishing_returns_holds"]:
                chosen = case
                break
    return all_cases, chosen


def _build_md_report(result: Dict) -> str:
    lines: List[str] = []
    lines.append("# Cut-Based Diminishing-Returns Validation")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- Query file: `{result['query_file']}`")
    if result.get("input_sql_full"):
        _md_sql_fence(lines, "Input SQL (full file contents)", result["input_sql_full"])
    if result.get("original_full_sql"):
        _md_sql_fence(
            lines,
            "Root SELECT / original full SQL used for the experiment (same as graph root text)",
            result["original_full_sql"],
        )
    lines.append(f"- DB used for EXPLAIN: `{result['db_config']['database']}`")
    lines.append(f"- Total SELECT nodes: {result['graph']['num_select_nodes']}")
    lines.append(f"- Total parent-child edges: {result['graph']['num_edges']}")
    lines.append(f"- Eligible cut edges: {result['graph']['num_eligible_cut_edges']}")
    lines.append(f"- Rules used for rewrite: {len(result['rules'])}")
    lines.append(f"- Cut penalty: `{result['cut_penalty']}`")
    lines.append("")
    lines.append("## Graph Edges")
    for edge in result["graph"]["edges"]:
        lines.append(
            f"- `{edge['edge_id']}`: {edge['parent']} -> {edge['child']} | kind=`{edge['cut_kind']}` | eligible=`{edge['eligible_for_cut']}`"
        )
        _md_sql_fence(lines, "cut expression (full)", edge["cut_sql"])
    lines.append("")
    lines.append("## Search Summary")
    lines.append(f"- Chain cases tested: {result['summary']['num_chain_cases']}")
    if "num_fork_cases" in result["summary"]:
        lines.append(f"- Fork cases tested: {result['summary']['num_fork_cases']}")
        lines.append(f"- Total cases tested: {result['summary']['num_total_cases']}")
    lines.append(f"- All-blocks-executable cases: {result['summary']['all_executable_cases']}")
    lines.append(f"- Holds count: {result['summary']['holds_count']}")
    lines.append(f"- Strict holds count: {result['summary']['strict_holds_count']}")
    lines.append("")

    def _emit_case(case: Dict, note: str = "") -> None:
        lines.append("## Chosen Concrete Example")
        if note:
            lines.append(f"- {note}")
        lines.append(f"- `S = {case['S_edge_ids']}`")
        lines.append(f"- `T = {case['T_edge_ids']}`")
        lines.append(f"- `e = {case['e_edge_id']}`")
        lines.append(f"- All blocks executable: `{case['all_blocks_executable']}`")
        lines.append(
            f"- Diminishing returns: Δ_small={case['delta_small']:.4f}, Δ_large={case['delta_large']:.4f}, strict={case['strict_diminishing_returns']}"
        )
        lines.append("")
        for variant_name in ["S", "S_plus_e", "T", "T_plus_e"]:
            variant = case["variants"][variant_name]
            lines.append(
                f"### {variant_name}: cuts={variant['cut_edge_ids']} | objective={variant['objective']:.4f} | all executable=`{variant['all_blocks_executable']}`"
            )
            fb = variant.get("full_query_cost_baseline")
            if fb is not None:
                lines.append(f"- Full-query EXPLAIN baseline: `{fb:.4f}`")
            fa = variant.get("full_query_cost_rewritten")
            if fa is not None:
                lines.append(f"- Full-query EXPLAIN rewritten: `{fa:.4f}`")
            if variant.get("original_full_sql"):
                _md_sql_fence(lines, "Original full SQL (baseline text for this variant)", variant["original_full_sql"])
            if variant.get("rewritten_full_sql"):
                _md_sql_fence(lines, "Rewritten full SQL (after all splices for this cut set)", variant["rewritten_full_sql"])
            if variant.get("variant_fatal_error"):
                lines.append(f"- Variant stopped early: `{variant['variant_fatal_error']}`")
            for block in variant["blocks"]:
                lines.append(
                    f"- Block `{block['root_node']}` nodes={block['nodes']} executable=`{block['executable']}` "
                    f"splice_applied=`{block.get('splice_applied', False)}` boundary={block['boundary_cut_edges']}"
                )
                if block.get("merged_full_sql"):
                    _md_sql_fence(lines, f"  Full SQL after block `{block['root_node']}`", block["merged_full_sql"])
                _md_sql_fence(lines, f"  Block `{block['root_node']}` standalone (Calcite input)", block["original_sql"])
                _md_sql_fence(lines, f"  Block `{block['root_node']}` standalone (Calcite output)", block["rewritten_sql"])
                if block.get("error"):
                    lines.append(f"  - note/error: `{block['error']}`")
            lines.append("")

    chosen = result.get("chosen_case")
    if chosen:
        _emit_case(chosen)
    else:
        top_cases = result.get("top_cases") or []
        if top_cases:
            _emit_case(top_cases[0], "No case satisfying the requested strict constraints was found; showing best-ranked available case.")
        else:
            lines.append("## Chosen Concrete Example")
            lines.append("- No case was found to display.")
            lines.append("")

    lines.append("## Top Cases")
    for case in result["top_cases"]:
        lines.append(
            f"- Case {case['case_id']}: S={case['S_edge_ids']}, T={case['T_edge_ids']}, e={case['e_edge_id']}, all_executable={case['all_blocks_executable']}, Δ_small={case['delta_small']:.4f}, Δ_large={case['delta_large']:.4f}, strict={case['strict_diminishing_returns']}"
        )
    return "\n".join(lines)


def main() -> None:
    sql_text = SQL_FILE.read_text(encoding="utf-8")

    fixer = SubqueryFixer()
    context_tables = fixer.extract_outer_context_tables(sql_text)
    root, node_infos, edges = _collect_graph(sql_text, fixer)
    full_sql = node_infos[root].sql
    base_cost = _cost(full_sql)
    chain_cases, chain_chosen = _search_chain_cases(root, node_infos, edges, fixer, context_tables)
    fork_cases, fork_chosen = _search_fork_cases(root, node_infos, edges, fixer, context_tables)
    all_cases = chain_cases + fork_cases
    chosen = fork_chosen or chain_chosen

    result = {
        "query_file": str(SQL_FILE),
        "input_sql_full": sql_text,
        "original_full_sql": full_sql,
        "db_config": TPCH_DB_CONFIG,
        "rules": RULES,
        "cut_penalty": 0.0,
        "base_query_cost": base_cost,
        "graph": {
            "root_node": root,
            "num_select_nodes": len(node_infos),
            "num_edges": len(edges),
            "num_eligible_cut_edges": sum(1 for edge in edges if edge.cut_kind in ELIGIBLE_CUT_KINDS),
            "edges": [_edge_to_dict(edge) for edge in edges],
        },
        "chosen_case": chosen,
        "top_cases": all_cases[:8],
        "summary": {
            "num_chain_cases": len(chain_cases),
            "num_fork_cases": len(fork_cases),
            "num_total_cases": len(all_cases),
            "all_executable_cases": sum(1 for case in all_cases if case["all_blocks_executable"]),
            "holds_count": sum(1 for case in all_cases if case["all_blocks_executable"] and case["diminishing_returns_holds"]),
            "strict_holds_count": sum(
                1 for case in all_cases if case["all_blocks_executable"] and case["strict_diminishing_returns"]
            ),
        },
        "method_note": (
            "Blocks are rewritten bottom-up (deepest Select first). Each step uses the live SELECT text extracted "
            "from the current full SQL (not the stale text from the initial graph), then masks boundary cuts, "
            "replaces correlated outer-column inputs with a reversible single-row placeholder context for "
            "standalone rewriting, calls Calcite, restores the original correlated columns and cut SQL at "
            "boundaries, and splices back. After each splice, PostgreSQL EXPLAIN validates the whole query; "
            "if EXPLAIN fails (e.g. LATERAL / correlation mismatch), that block’s rewrite is skipped and the "
            "previous full SQL is kept. Objective f(C) = EXPLAIN(original) - EXPLAIN(final after accepted splices). "
            "Exports store full SQL strings (no truncation)."
        ),
    }

    out_json = REPO_ROOT / "experiments" / "submodular_cut_validation" / "complexvalidation_result_whole.json"
    out_md = REPO_ROOT / "experiments" / "submodular_cut_validation" / "complex_validation_result_whole.md"
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md.write_text(_build_md_report(result), encoding="utf-8")

    summary = {
        "num_chain_cases": result["summary"]["num_chain_cases"],
        "num_fork_cases": result["summary"]["num_fork_cases"],
        "num_total_cases": result["summary"]["num_total_cases"],
        "all_executable_cases": result["summary"]["all_executable_cases"],
        "strict_holds_count": result["summary"]["strict_holds_count"],
        "chosen_case": None
        if chosen is None
        else {
            "S": chosen["S_edge_ids"],
            "T": chosen["T_edge_ids"],
            "e": chosen["e_edge_id"],
            "delta_small": chosen["delta_small"],
            "delta_large": chosen["delta_large"],
            "strict": chosen["strict_diminishing_returns"],
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Saved: {out_json}")
    print(f"Saved: {out_md}")


if __name__ == "__main__":
    raise SystemExit(
        "Exit"
    )
