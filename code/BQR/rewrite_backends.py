from __future__ import annotations

import ast
import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from rewriter_interface import call_rewriter


_DEFAULT_RULES: List[str] = [
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
    "FILTER_CORRELATE",
    "AGGREGATE_VALUES",
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


def _clean_rewrite_sql(sql_text: str) -> str:
    out = (sql_text or "").replace("$", "").strip()
    return out


@dataclass
class RewriteResult:
    backend: str
    input_sql: str
    rewritten_sql: str
    changed: bool
    metadata: Dict[str, Any]


class RewriteBackend:
    name: str = "base"

    def rewrite(self, sql_text: str, db_id: str, context: Optional[Dict[str, Any]] = None) -> RewriteResult:
        raise NotImplementedError


class CalciteRuleBackend(RewriteBackend):
    name = "calcite_rules"

    def __init__(self, rules: Optional[Sequence[str]] = None) -> None:
        self.rules = list(rules or _DEFAULT_RULES)

    def rewrite(self, sql_text: str, db_id: str, context: Optional[Dict[str, Any]] = None) -> RewriteResult:
        original = (sql_text or "").strip()
        try:
            rewritten = _clean_rewrite_sql(call_rewriter(db_id, original, self.rules))
            if not rewritten:
                rewritten = original
        except Exception as exc:
            return RewriteResult(
                backend=self.name,
                input_sql=original,
                rewritten_sql=original,
                changed=False,
                metadata={"error": f"{type(exc).__name__}: {exc}", "rules_count": len(self.rules)},
            )
        return RewriteResult(
            backend=self.name,
            input_sql=original,
            rewritten_sql=rewritten,
            changed=(rewritten.lower() != original.lower()),
            metadata={"rules_count": len(self.rules)},
        )


def _load_llmr2_helpers(llmr2_py_path: Path) -> Dict[str, Any]:
    """
    Reuse pure helper pieces from LLM-R2/src/LLM_R2.py without importing it directly.
    Direct import is avoided because that file executes heavy model/bootstrap code.
    """
    source = llmr2_py_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    keep_assigns = {
        "agge_rewrite_rules",
        "filt_rewrite_rules",
        "join_rewrite_rules",
        "sort_rewrite_rules",
        "union_rewrite_rules",
    }
    keep_funcs = {"generate_turbo_prompt_light", "filter_gpt_output"}
    selected_nodes: List[ast.AST] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id in keep_assigns for t in node.targets):
                selected_nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in keep_funcs:
            selected_nodes.append(node)

    module = ast.Module(body=selected_nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    ns: Dict[str, Any] = {}
    exec(compile(module, str(llmr2_py_path), "exec"), ns, ns)
    return ns


class LLMR2Backend(RewriteBackend):
    name = "llmr2"

    def __init__(self, repo_root: Path, fallback_rules: Optional[Sequence[str]] = None) -> None:
        self.repo_root = repo_root
        self.fallback_rules = list(fallback_rules or _DEFAULT_RULES)
        self._helpers: Optional[Dict[str, Any]] = None
        self._client: Optional[Any] = None
        self._embedder: Optional[Any] = None
        self._init_error: Optional[str] = None
        self._model = os.getenv("LLMR2_MODEL", "gpt-4o").strip() or "gpt-4o"
        # self._model = os.getenv("LLMR2_MODEL", "gpt-3.5-turbo").strip() or "gpt-3.5-turbo"
        self._num_promos = max(0, int(os.getenv("LLMR2_NUM_PROMOS", "1") or "1"))
        self._pool_cache: Dict[str, List[tuple[str, List[str]]]] = {}
        self._pool_source_cache: Dict[str, List[str]] = {}

    def _lazy_init(self) -> None:
        if self._helpers is not None or self._init_error is not None:
            return
        llmr2_py = self.repo_root / "LLM-R2" / "src" / "LLM_R2.py"
        if not llmr2_py.exists():
            self._init_error = f"missing_file:{llmr2_py}"
            return
        try:
            self._helpers = _load_llmr2_helpers(llmr2_py)
        except Exception as exc:
            self._init_error = f"load_helpers_failed:{type(exc).__name__}: {exc}"
            return

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            self._init_error = "missing_env:OPENAI_API_KEY"
        else:
            try:
                from openai import OpenAI  # type: ignore

                self._client = OpenAI(api_key=api_key)
            except Exception as exc:
                self._init_error = f"openai_client_failed:{type(exc).__name__}: {exc}"

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:
            self._init_error = (
                f"{self._init_error};sentbert_init_failed:{type(exc).__name__}: {exc}"
                if self._init_error
                else f"sentbert_init_failed:{type(exc).__name__}: {exc}"
            )

    @staticmethod
    def _parse_rules(raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        s = str(raw).strip()
        if not s or s.upper() == "NA":
            return []
        try:
            v = ast.literal_eval(s)
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
        except Exception:
            pass
        return []

    def _resolve_pool_files(self, db_id: str) -> List[Path]:
        pools_dir = self.repo_root / "LLM-R2" / "data" / "data_llmr2" / "pools"
        candidates = [
            pools_dir / f"pos_pool_{db_id}_updated.csv",
            pools_dir / f"neg_pool_{db_id}_updated.csv",
        ]
        return [p for p in candidates if p.exists()]

    def _load_demo_pool(self, db_id: str) -> List[tuple[str, List[str]]]:
        if db_id in self._pool_cache:
            return self._pool_cache[db_id]
        rows: List[tuple[str, List[str]]] = []
        sources: List[str] = []
        for path in self._resolve_pool_files(db_id):
            source = "neg" if path.name.startswith("neg_pool_") else "pos"
            try:
                df = pd.read_csv(path).fillna("NA")
            except Exception:
                continue
            sql_col = "original_sql" if "original_sql" in df.columns else None
            if sql_col is None:
                continue
            if "activated_rules" in df.columns:
                rule_col = "activated_rules"
            elif "activated_rules_gpt" in df.columns:
                rule_col = "activated_rules_gpt"
            else:
                continue
            for _, row in df.iterrows():
                q = str(row.get(sql_col, "") or "").strip()
                rules = self._parse_rules(row.get(rule_col))
                if q:
                    rows.append((q, rules))
                    sources.append(source)
        self._pool_cache[db_id] = rows
        self._pool_source_cache[db_id] = sources
        return rows

    def _retrieve_promotions(self, db_id: str, query: str) -> List[tuple[Dict[str, Any], str, str, List[str], str]]:
        if self._num_promos <= 0 or self._embedder is None:
            return []
        pool = self._load_demo_pool(db_id)
        if not pool:
            return []
        sources = self._pool_source_cache.get(db_id, ["unknown"] * len(pool))
        corpus = [x[0] for x in pool]
        try:
            q_emb = self._embedder.encode([query], normalize_embeddings=True)
            c_emb = self._embedder.encode(corpus, normalize_embeddings=True)
            sims = np.dot(c_emb, q_emb[0])
            topk = np.argsort(-sims)[: self._num_promos]
        except Exception:
            return []
        promos: List[tuple[Dict[str, Any], str, str, List[str], str]] = []
        for idx in topk:
            demo_q, demo_rules = pool[int(idx)]
            promos.append(({}, demo_q, "", list(demo_rules), sources[int(idx)]))
        return promos

    def _pick_rules(self, sql_text: str, db_id: str) -> tuple[List[str], Dict[str, Any]]:
        self._lazy_init()
        meta: Dict[str, Any] = {"model": self._model, "retrieval": "sentbert", "db_id": db_id}
        print(f"[LLMR2] processing query: {sql_text}")
        print(f"[LLMR2] model: {self._model}")
        if self._helpers is None:
            meta["llmr2_init_error"] = self._init_error or "helpers_not_initialized"
            return list(self.fallback_rules), meta
        assert self._helpers is not None

        gen_prompt: Callable[..., Any] = self._helpers["generate_turbo_prompt_light"]
        parse_rules: Callable[[str], List[str]] = self._helpers["filter_gpt_output"]
        promotions = self._retrieve_promotions(db_id=db_id, query=sql_text)
        meta["num_promotions"] = len(promotions)
        if promotions:
            selected_demo_sql = promotions[0][1]
            selected_demo_rules = promotions[0][3]
            selected_demo_source = promotions[0][4]
        else:
            selected_demo_sql = ""
            selected_demo_rules = []
            selected_demo_source = "none"
        meta["selected_demo_sql"] = selected_demo_sql
        meta["selected_demo_rules"] = selected_demo_rules
        meta["selected_demo_source"] = selected_demo_source
       
        if not selected_demo_rules:
            meta["selected_demo_empty_rules"] = True
        
        prompt_promotions = [(a, b, c, d) for (a, b, c, d, _) in promotions]
        prompt = gen_prompt(schema={}, query=sql_text, logical_plan="", promotions=prompt_promotions)
        if self._client is None:
            meta["llmr2_init_error"] = self._init_error or "openai_client_not_initialized"
            return list(self.fallback_rules), meta
        try:
            resp = self._client.chat.completions.create(messages=prompt, model=self._model, temperature=0)
            content = (resp.choices[0].message.content or "").strip()
            rules = parse_rules(content)
            meta["llm_output_raw"] = content
            if rules:
                meta["selected_rules_count"] = len(rules)
                return rules, meta
            meta["llm_empty_rules"] = True
            return list(self.fallback_rules), meta
        except Exception as exc:
            meta["llm_inference_error"] = f"{type(exc).__name__}: {exc}"
            return list(self.fallback_rules), meta

    def rewrite(self, sql_text: str, db_id: str, context: Optional[Dict[str, Any]] = None) -> RewriteResult:
        original = (sql_text or "").strip()
        rules, meta = self._pick_rules(original, db_id=db_id)
        try:
            rewritten = _clean_rewrite_sql(call_rewriter(db_id, original, rules))
            if not rewritten:
                rewritten = original
        except Exception as exc:
            meta["rewriter_error"] = f"{type(exc).__name__}: {exc}"
            rewritten = original
        return RewriteResult(
            backend=self.name,
            input_sql=original,
            rewritten_sql=rewritten,
            changed=(rewritten.lower() != original.lower()),
            metadata={**meta, "rules_count": len(rules)},
        )


def _quite_log_enabled() -> bool:
    return (os.getenv("QUITE_QUIET", "") or "").strip().lower() not in {"1", "true", "yes"}


def _quite_preview(text: str, max_len: int = 240) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


class QuiteBackend(RewriteBackend):
    """
    QUITE LLM query rewriter (external repo). Mirrors run.py's QueryRewriter flow without CSV batching.

    Configuration:
    - QUITE_ROOT: absolute path to the QUITE project (default: ../QUITE).
    - QUITE_SCHEMA_FILE: default schema .sql path for Equivalence_Check_Tool / agents.
    - QUITE_MAX_ITERATIONS: FSM max loops (default: 2).
    - QUITE_QUIET: if 1/true/yes, suppress [QUITE] progress prints (QUITE internals may still print).

    Inside QUITE (single-query FSM), optional env in QUITE's config_file/.env:
    - PARALLEL_REASONING_THREADS (default 2), LLM_MAX_CONCURRENT (default 3) — see finite_state_machine.py.

    Per-call overrides via context:
    - quite_schema_file or schema_file: path string to the schema file.
    """

    name = "quite"

    def __init__(self, repo_root: Path, quite_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root
        root_env = (os.getenv("QUITE_ROOT") or "").strip()
        self.quite_root = (
            Path(quite_root).expanduser().resolve()
            if quite_root is not None
            else Path(root_env or "../QUITE").expanduser().resolve()
        )
        try:
            self._max_iterations = max(1, int(os.getenv("QUITE_MAX_ITERATIONS", "2") or "2"))
        except ValueError:
            self._max_iterations = 2

    def _resolve_schema_file(self, context: Optional[Dict[str, Any]]) -> Optional[str]:
        ctx = context or {}
        for key in ("quite_schema_file", "schema_file"):
            raw = ctx.get(key)
            if raw is None:
                continue
            p = Path(str(raw).strip()).expanduser()
            if p.is_file():
                return str(p.resolve())
        env_schema = (os.getenv("QUITE_SCHEMA_FILE") or "").strip()
        if env_schema:
            p = Path(env_schema).expanduser()
            if p.is_file():
                return str(p.resolve())
        return None

    def _prepare_quite_env(self) -> Optional[str]:
        root = str(self.quite_root)
        if not self.quite_root.is_dir():
            return f"missing_quite_root:{root}"
        if not (self.quite_root / "run.py").exists():
            return f"missing_quite_run_py:{self.quite_root / 'run.py'}"
        os.environ["PROJECT_ROOT"] = root
        if root not in sys.path:
            sys.path.insert(0, root)
        return None

    async def _rewrite_once_async(self, sql_text: str, schema_file: str) -> tuple[str, Dict[str, Any]]:
        from src.utils.path_config import load_project_env, setup_python_path
        from src.utils.data_distribution import get_available_databases, get_statistics_list
        from src.utils.get_data_statistics import get_data_statistics
        from src.Rewrite_Middleware.middleware import DBMS
        from src.utils.agent_template import MessageQueue
        from src.Query_Rewriter.finite_state_machine import QueryRewriter

        setup_python_path()
        load_project_env()

        mq = MessageQueue(window_size=8)
        dbms = DBMS()
        db_name = dbms.db_name
        if db_name in get_available_databases():
            data_statistics = get_statistics_list(db_name)
        else:
            data_statistics = get_data_statistics()

        rewriter = QueryRewriter(mq, dbms, data_statistics, schema_file, self._max_iterations)
        rewriter.initial_sql = sql_text
        try:
            if _quite_log_enabled():
                print(
                    f"[QUITE] QueryRewriter.run() starting "
                    f"(sql_len={len(sql_text)}, max_iterations={self._max_iterations}, db={db_name!r})"
                )
            rewritten = await rewriter.run()
            if _quite_log_enabled():
                print("[QUITE] QueryRewriter.run() finished")
            out = (rewritten or "").strip() or sql_text
            meta: Dict[str, Any] = {
                "quite_root": str(self.quite_root),
                "schema_file": schema_file,
                "max_iterations": self._max_iterations,
                "optimization_advice": rewriter.optimization_advice,
            }
            return out, meta
        finally:
            await rewriter.clear()

    def rewrite(self, sql_text: str, db_id: str, context: Optional[Dict[str, Any]] = None) -> RewriteResult:
        original = (sql_text or "").strip()
        meta: Dict[str, Any] = {"db_id": db_id}
        ctx = context or {}
        phase = str(ctx.get("phase", "") or "unspecified")
        schema_path = self._resolve_schema_file(context)
        if not schema_path:
            meta["error"] = (
                "missing_schema: set env QUITE_SCHEMA_FILE or pass context['quite_schema_file'] "
                "with a valid schema .sql path (same role as run.py --schema_file)."
            )
            if _quite_log_enabled():
                print(f"[QUITE] skip rewrite (missing schema) phase={phase!r} db_id={db_id!r} sql_len={len(original)}")
            return RewriteResult(
                backend=self.name,
                input_sql=original,
                rewritten_sql=original,
                changed=False,
                metadata=meta,
            )

        prep_err = self._prepare_quite_env()
        if prep_err:
            meta["error"] = prep_err
            if _quite_log_enabled():
                print(f"[QUITE] skip rewrite ({prep_err}) phase={phase!r} db_id={db_id!r}")
            return RewriteResult(
                backend=self.name,
                input_sql=original,
                rewritten_sql=original,
                changed=False,
                metadata=meta,
            )

        if _quite_log_enabled():
            print(
                f"[QUITE] rewrite start phase={phase!r} db_id={db_id!r} "
                f"quite_root={self.quite_root} schema={schema_path} "
                f"max_iterations={self._max_iterations} input_len={len(original)}"
            )
            print(f"[QUITE] input SQL preview: {_quite_preview(original)}")
        t0 = time.perf_counter()
        rewritten = original
        try:
            rewritten, run_meta = asyncio.run(self._rewrite_once_async(original, schema_path))
            meta.update(run_meta)
        except RuntimeError as exc:
            meta["asyncio_error"] = f"{type(exc).__name__}: {exc}"
            rewritten = original
            if _quite_log_enabled():
                print(f"[QUITE] rewrite failed (asyncio): {meta['asyncio_error']}")
        except Exception as exc:
            meta["quite_error"] = f"{type(exc).__name__}: {exc}"
            rewritten = original
            if _quite_log_enabled():
                print(f"[QUITE] rewrite failed: {meta['quite_error']}")

        rewritten = _clean_rewrite_sql(rewritten)
        if not rewritten:
            rewritten = original

        elapsed = time.perf_counter() - t0
        meta["quite_wall_time_sec"] = round(elapsed, 4)
        changed = rewritten.lower() != original.lower()
        if _quite_log_enabled():
            print(
                f"[QUITE] rewrite done phase={phase!r} elapsed_s={elapsed:.3f} "
                f"changed={changed} output_len={len(rewritten)}"
            )
            print(f"[QUITE] output SQL preview: {_quite_preview(rewritten)}")
            adv = meta.get("optimization_advice")
            if adv is not None and str(adv).strip():
                print(f"[QUITE] optimization_advice: {_quite_preview(str(adv), max_len=400)}")

        return RewriteResult(
            backend=self.name,
            input_sql=original,
            rewritten_sql=rewritten,
            changed=changed,
            metadata=meta,
        )


def create_rewrite_backend(name: str, repo_root: Path, rules: Optional[Sequence[str]] = None) -> RewriteBackend:
    key = (name or "calcite_rules").strip().lower()
    if key in {"calcite", "calcite_rules", "default"}:
        return CalciteRuleBackend(rules=rules)
    if key in {"llmr2", "llm-r2"}:
        return LLMR2Backend(repo_root=repo_root, fallback_rules=rules)
    if key in {"quite", "quite_rewriter"}:
        return QuiteBackend(repo_root=repo_root)
    raise ValueError(f"Unsupported rewrite backend: {name}")
