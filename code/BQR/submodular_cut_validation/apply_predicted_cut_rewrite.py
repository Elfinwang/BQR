"""
Apply a fixed set of cut edges to a SQL query and run the same rewrite pipeline
as double_greedy_cut_search (via CutSetEvaluator).

Input modes:
  1) JSONL: each line like pointer_net predictions (uses predicted_cut_edge_ids by default;
     target_cut_edge_ids is only for reference in the sample file).
  2) Single .sql file + a JSON list of edge ids (e.g. '["E3"]').

Output: JSONL with original / rewritten SQL and planner costs (same cost backend as cut eval).

JSONL throughput: use `--jsonl-workers N` or env `BQR_JSONL_WORKERS` to rewrite multiple lines in
parallel (intended for `quite` / `calcite_rules`). With `--rewrite-backend quite` and no flag/env,
defaults to min(4, CPU count). Not used with `--llmr2-trace-csv`; `llmr2` forces workers=1.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

SCRIPT_PATH = Path(__file__).resolve()
BASE_DIR = SCRIPT_PATH.parent
REPO_ROOT = SCRIPT_PATH.parents[2]
for p in (str(REPO_ROOT), str(BASE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from BQR.submodular_cut_validation import double_greedy_cut_search as dg_search  # noqa: E402
from config import DB_CONFIG  # noqa: E402

CSV_LLM_R2_TRACE_COLUMNS = (
    "db_id",
    "original_sql",
    "source_jsonl_line",
    "cut_edge_id",
    "step_type",
)


def _should_use_full_parallel_rewrite(enable: bool = True) -> bool:
    """
    Fixed-cut mode can pre-split all selected edges, so expensive backends (llmr2, quite)
    can rewrite every cut block (and masked-parent rewrites) in one ThreadPool wave.

    Keep this behavior scoped to apply_predicted_cut_rewrite.py. double_greedy_cut_search.py
    still evaluates incrementally because cut edges are selected step-by-step.
    """
    if not enable:
        return False
    backend = getattr(dg_search, "_ACTIVE_REWRITE_BACKEND", None)
    return bool(backend is not None and backend.name in ("llmr2", "quite"))


def _parse_cuts_json(text: str) -> List[str]:
    data = json.loads(text)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("--cuts-json must be a JSON array of edge id strings")
    out: List[str] = []
    for x in data:
        if not isinstance(x, str):
            raise ValueError("Each cut edge id must be a string (e.g. 'E0')")
        out.append(x)
    return out


def _validate_cuts_against_graph(
    cuts: Sequence[str], evaluator: dg_search.CutSetEvaluator
) -> Optional[str]:
    missing = [eid for eid in cuts if eid not in evaluator.edge_map]
    if missing:
        return f"Cut edge id(s) not in this query graph: {missing}; known: {list(evaluator.edge_map.keys())}"
    return None


def _rewrite_one(
    sql_text: str,
    cut_edge_ids: Sequence[str],
    db_id: str,
    enable_full_parallel_rewrite: bool = True,
) -> Tuple[Dict[str, Any], dg_search.CutSetEvaluator]:
    evaluator = dg_search.CutSetEvaluator(sql_text.strip(), collect_rewrite_trace=False)
    cuts_set: Set[str] = set(cut_edge_ids)

    # Empty-cut fallback: apply the configured rewrite backend to the full query.
    # This mirrors the "empty_cut_fallback" behavior used in double_greedy_cut_search,
    # but is scoped to this fixed-cut application script.
    if not cuts_set:
        backend = getattr(dg_search, "_ACTIVE_REWRITE_BACKEND", None)
        if backend is None:
            payload = {
                "original_sql": sql_text,
                "rewritten_sql": sql_text,
                "applied_cut_edge_ids": [],
                "original_query_cost": float(evaluator.base_cost),
                "rewritten_query_cost": float(evaluator.base_cost),
                "all_blocks_executable": True,
                "variant_fatal_error": "",
                "objective": 0.0,
            }
            return payload, evaluator

        VALIDATION = dg_search._validation()
        db_id = str(db_id or (DB_CONFIG.get("database") or "tpch")).strip() or "tpch"
        try:
            fb_ctx: Dict[str, Any] = dict(getattr(dg_search, "_REWRITE_EXTRA_CONTEXT", None) or {})
            fb_ctx["phase"] = "empty_cut_fallback"
            rr = backend.rewrite(
                sql_text=evaluator.full_sql,
                db_id=db_id,
                context=fb_ctx,
            )
            candidate = (rr.rewritten_sql or "").strip() or evaluator.full_sql
        except Exception as exc:
            payload = {
                "original_sql": sql_text,
                "rewritten_sql": sql_text,
                "applied_cut_edge_ids": [],
                "original_query_cost": float(evaluator.base_cost),
                "rewritten_query_cost": None,
                "all_blocks_executable": False,
                "variant_fatal_error": f"empty_cut_fallback_exception:{type(exc).__name__}: {exc}",
                "objective": 0.0,
            }
            return payload, evaluator

        rewritten_cost: Optional[float] = None
        cost_raw: Optional[str] = None
        try:
            c = float(VALIDATION._cost(candidate))
            if math.isfinite(c):
                rewritten_cost = c
            else:
                cost_raw = str(c)
        except Exception as exc:
            cost_raw = f"{type(exc).__name__}: {exc}"

        if rewritten_cost is None:
            payload = {
                "original_sql": sql_text,
                "rewritten_sql": sql_text,
                "applied_cut_edge_ids": [],
                "original_query_cost": float(evaluator.base_cost),
                "rewritten_query_cost": None,
                "all_blocks_executable": False,
                "variant_fatal_error": f"empty_cut_fallback_failed:{cost_raw or 'non_finite_cost'}",
                "objective": 0.0,
            }
            return payload, evaluator

        payload = {
            "original_sql": sql_text,
            "rewritten_sql": candidate,
            "applied_cut_edge_ids": [],
            "original_query_cost": float(evaluator.base_cost),
            "rewritten_query_cost": float(rewritten_cost),
            "all_blocks_executable": True,
            "variant_fatal_error": "",
            "objective": float(evaluator.base_cost - rewritten_cost),
        }
        return payload, evaluator

    err = _validate_cuts_against_graph(sorted(cuts_set), evaluator)
    if err is not None:
        payload = {
            "original_sql": sql_text,
            "rewritten_sql": "",
            "applied_cut_edge_ids": dg_search._sorted_edge_ids(list(cuts_set)),
            "original_query_cost": float(evaluator.base_cost),
            "rewritten_query_cost": None,
            "all_blocks_executable": False,
            "variant_fatal_error": err,
        }
        return payload, evaluator

    rec = evaluator.evaluate(
        cuts_set,
        all_rewrites_parallel=_should_use_full_parallel_rewrite(enable_full_parallel_rewrite),
    )
    rew_cost = rec.full_query_cost_rewritten
    if rew_cost is not None and not math.isfinite(rew_cost):
        rew_cost = None

    payload = {
        "original_sql": sql_text,
        "rewritten_sql": rec.rewritten_full_sql,
        "applied_cut_edge_ids": rec.cut_edge_ids,
        "original_query_cost": float(evaluator.base_cost),
        "rewritten_query_cost": rew_cost,
        "all_blocks_executable": rec.all_blocks_executable,
        "variant_fatal_error": rec.variant_fatal_error or "",
        "objective": rec.objective,
    }
    return payload, evaluator


def _emit_record(base: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    row = dict(base)
    if extra:
        row.update(extra)
    return row


def _db_id_from_jsonl_obj(obj: Dict[str, Any], default_db_id: str) -> str:
    meta = obj.get("metadata")
    if isinstance(meta, dict) and meta.get("db_id") is not None:
        return str(meta["db_id"]).strip()
    if obj.get("db_id") is not None:
        return str(obj.get("db_id")).strip()
    return default_db_id


def try_evaluate_with_rewrite_trace(
    sql_text: str,
    cut_ids: List[str],
    enable_full_parallel_rewrite: bool = True,
) -> Optional[dg_search.EvalRecord]:
    """Build graph, validate cuts, evaluate with `rewrite_trace` in `debug` (or None on failure)."""
    try:
        evaluator = dg_search.CutSetEvaluator(sql_text.strip(), collect_rewrite_trace=True)
        err = _validate_cuts_against_graph(sorted(set(cut_ids)), evaluator)
        if err is not None:
            return None
        return evaluator.evaluate(
            set(cut_ids),
            all_rewrites_parallel=_should_use_full_parallel_rewrite(enable_full_parallel_rewrite),
        )
    except Exception:
        return None


def _canonical_edge_id(edge_id: str) -> str:
    """Normalize to E0, E1, ... for trace CSV cut_edge_id column."""
    s = str(edge_id).strip()
    if not s:
        return s
    if re.fullmatch(r"\d+", s):
        return f"E{s}"
    m = re.fullmatch(r"[Ee](\d+)", s)
    if m:
        return f"E{m.group(1)}"
    return s


def _format_traced_cut_edge_ids(edge_ids: Optional[Sequence[str]]) -> str:
    if not edge_ids:
        return ""
    return ",".join(_canonical_edge_id(e) for e in dg_search._sorted_edge_ids(list(edge_ids)))


def _boundary_edge_ids_csv_explicit(trace_entry: Dict[str, Any]) -> str:
    b = trace_entry.get("boundary_edges") or []
    eids: List[str] = []
    for e in b:
        if isinstance(e, dict) and e.get("edge_id") is not None:
            eids.append(_canonical_edge_id(str(e["edge_id"])))
    return ",".join(eids)


def build_llmr2_trace_csv_rows(
    *,
    full_original_sql: str,
    rec: Optional[dg_search.EvalRecord],
    source_jsonl_line: int,
    db_id: str,
    traced_cut_edge_ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    """
    One query → CSV rows: full_query, then per rewrite step subquery/parent_query pairs.
    cut_edge_id uses canonical E0,E1,... (comma-separated).
    """
    rows: List[Dict[str, str]] = []

    def _row(text: str, cut_id: str, step_type: str) -> None:
        rows.append(
            {
                "db_id": db_id,
                "original_sql": text,
                "source_jsonl_line": str(int(source_jsonl_line)),
                "cut_edge_id": cut_id,
                "step_type": step_type,
            }
        )

    if traced_cut_edge_ids is not None:
        cuts_label = _format_traced_cut_edge_ids(traced_cut_edge_ids)
    elif rec is not None and rec.cut_edge_ids:
        cuts_label = _format_traced_cut_edge_ids(rec.cut_edge_ids)
    else:
        cuts_label = ""

    _row(full_original_sql.strip(), cuts_label, "full_query")
    if rec is None or not rec.debug:
        return rows
    trace: List[Dict[str, Any]] = list((rec.debug).get("rewrite_trace") or [])
    for step_i, ent in enumerate(trace, start=1):
        eids = _boundary_edge_ids_csv_explicit(ent)
        if "fatal_exception" in ent:
            _row(str(ent.get("fatal_exception", "")), eids, f"block_error_{step_i}")
            break
        sub = (ent.get("fixed_for_standalone_sql") or ent.get("raw_fragment_sql") or "").strip()
        par = (ent.get("merged_full_sql_after_splice") or "").strip()
        _row(sub, eids, f"subquery_{step_i}")
        _row(par, eids, f"parent_query_{step_i}")
    return rows


def write_llmr2_trace_csv_rows(output_csv: Path, rows: Sequence[Dict[str, str]]) -> None:
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(CSV_LLM_R2_TRACE_COLUMNS),
            quoting=csv.QUOTE_MINIMAL,
        )
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_LLM_R2_TRACE_COLUMNS})


def export_llmr2_trace_csv_for_jsonl(
    input_path: Path,
    output_csv: Path,
    *,
    cuts_field: str = "predicted_cut_edge_ids",
    default_db_id: Optional[str] = None,
    enable_full_parallel_rewrite: bool = True,
) -> None:
    """Read JSONL with sql + cut ids; write one consolidated LLMR2 trace CSV."""
    base_db = str((default_db_id or DB_CONFIG.get("database") or "tpch")).strip() or "tpch"
    all_rows: List[Dict[str, str]] = []
    with input_path.open("r", encoding="utf-8") as fin:
        for line_no, line in enumerate(fin, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            sql_text = obj.get("sql") or obj.get("original_sql")
            if not sql_text:
                raise ValueError(f"{input_path}:{line_no}: missing 'sql' / 'original_sql'")
            if cuts_field not in obj:
                raise ValueError(f"{input_path}:{line_no}: missing field {cuts_field!r}")
            raw_cuts = obj[cuts_field]
            if raw_cuts is None:
                cut_ids: List[str] = []
            elif isinstance(raw_cuts, list):
                cut_ids = [str(x) for x in raw_cuts]
            else:
                raise ValueError(f"{input_path}:{line_no}: {cuts_field} must be a list or null")
            db_id = _db_id_from_jsonl_obj(obj, base_db)
            rec = try_evaluate_with_rewrite_trace(
                sql_text,
                cut_ids,
                enable_full_parallel_rewrite=enable_full_parallel_rewrite,
            )
            all_rows.extend(
                build_llmr2_trace_csv_rows(
                    full_original_sql=sql_text,
                    rec=rec,
                    source_jsonl_line=line_no,
                    db_id=db_id,
                    traced_cut_edge_ids=cut_ids,
                )
            )
    write_llmr2_trace_csv_rows(output_csv, all_rows)


def _jsonl_line_to_output(
    *,
    input_path: Path,
    line_no: int,
    obj: Dict[str, Any],
    cuts_field: str,
    base_db: str,
    enable_full_parallel_rewrite: bool,
) -> Dict[str, Any]:
    """Build one output JSON object for a parsed JSONL record (used sequential + parallel)."""
    sql_text = obj.get("sql") or obj.get("original_sql")
    if not sql_text:
        raise ValueError(f"{input_path}:{line_no}: missing 'sql' field")
    if cuts_field not in obj:
        raise ValueError(f"{input_path}:{line_no}: missing field {cuts_field!r}")
    raw_cuts = obj[cuts_field]
    if raw_cuts is None:
        cut_ids: List[str] = []
    elif isinstance(raw_cuts, list):
        cut_ids = [str(x) for x in raw_cuts]
    else:
        raise ValueError(f"{input_path}:{line_no}: {cuts_field} must be a list or null")

    row_start = time.perf_counter()
    db_id = _db_id_from_jsonl_obj(obj, base_db)
    try:
        payload, _ = _rewrite_one(
            sql_text,
            cut_ids,
            db_id=db_id,
            enable_full_parallel_rewrite=enable_full_parallel_rewrite,
        )
    except Exception as exc:
        payload = {
            "original_sql": sql_text,
            "rewritten_sql": sql_text,
            "applied_cut_edge_ids": dg_search._sorted_edge_ids(cut_ids),
            "original_query_cost": None,
            "rewritten_query_cost": None,
            "all_blocks_executable": False,
            "variant_fatal_error": f"rewrite_exception: {type(exc).__name__}: {exc}",
        }
    return {
        "original_sql": payload.get("original_sql", ""),
        "rewritten_sql": payload.get("rewritten_sql", ""),
        "applied_cut_edge_ids": payload.get("applied_cut_edge_ids", []),
        "original_query_cost": payload.get("original_query_cost"),
        "rewritten_query_cost": payload.get("rewritten_query_cost"),
        "variant_fatal_error": payload.get("variant_fatal_error", ""),
        "line_index": obj.get("line_index", line_no),
        "inference_time_sec": round(time.perf_counter() - row_start, 6),
    }


def run_jsonl(
    input_path: Path,
    output_path: Path,
    cuts_field: str,
    llmr2_trace_csv: Optional[Path] = None,
    default_db_id: Optional[str] = None,
    enable_full_parallel_rewrite: bool = True,
    jsonl_workers: int = 1,
) -> None:
    base_db = str(
        (default_db_id or DB_CONFIG.get("database") or "tpch")
    ).strip() or "tpch"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trace_f = None
    trace_writer: Optional[csv.DictWriter] = None
    if llmr2_trace_csv is not None:
        llmr2_trace_csv.parent.mkdir(parents=True, exist_ok=True)
        trace_f = llmr2_trace_csv.open("w", encoding="utf-8", newline="")
        trace_writer = csv.DictWriter(
            trace_f,
            fieldnames=list(CSV_LLM_R2_TRACE_COLUMNS),
            quoting=csv.QUOTE_MINIMAL,
        )
        trace_writer.writeheader()

    workers = max(1, int(jsonl_workers))
    if trace_writer is not None and workers > 1:
        print(
            "[apply_predicted_cut_rewrite] --llmr2-trace-csv is set: using jsonl-workers=1 (trace must be sequential)."
        )
        workers = 1

    if workers <= 1:
        with input_path.open("r", encoding="utf-8") as fin, output_path.open("w", encoding="utf-8") as fout:
            for line_no, line in enumerate(fin, 1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                sql_text = obj.get("sql") or obj.get("original_sql")
                if not sql_text:
                    raise ValueError(f"{input_path}:{line_no}: missing 'sql' field")
                if cuts_field not in obj:
                    raise ValueError(f"{input_path}:{line_no}: missing field {cuts_field!r}")
                raw_cuts = obj[cuts_field]
                if raw_cuts is None:
                    cut_ids: List[str] = []
                elif isinstance(raw_cuts, list):
                    cut_ids = [str(x) for x in raw_cuts]
                else:
                    raise ValueError(f"{input_path}:{line_no}: {cuts_field} must be a list or null")

                if trace_writer is not None:
                    rec = try_evaluate_with_rewrite_trace(
                        sql_text,
                        cut_ids,
                        enable_full_parallel_rewrite=enable_full_parallel_rewrite,
                    )
                    db_id = _db_id_from_jsonl_obj(obj, base_db)
                    for r in build_llmr2_trace_csv_rows(
                        full_original_sql=sql_text,
                        rec=rec,
                        source_jsonl_line=line_no,
                        db_id=db_id,
                        traced_cut_edge_ids=cut_ids,
                    ):
                        trace_writer.writerow(r)

                out = _jsonl_line_to_output(
                    input_path=input_path,
                    line_no=line_no,
                    obj=obj,
                    cuts_field=cuts_field,
                    base_db=base_db,
                    enable_full_parallel_rewrite=enable_full_parallel_rewrite,
                )
                fout.write(json.dumps(out, ensure_ascii=False) + "\n")
    else:
        records: List[Tuple[int, Dict[str, Any]]] = []
        with input_path.open("r", encoding="utf-8") as fin:
            for line_no, line in enumerate(fin, 1):
                line = line.strip()
                if not line:
                    continue
                records.append((line_no, json.loads(line)))

        def _task(item: Tuple[int, Dict[str, Any]]) -> Tuple[int, Dict[str, Any]]:
            line_no, obj = item
            out = _jsonl_line_to_output(
                input_path=input_path,
                line_no=line_no,
                obj=obj,
                cuts_field=cuts_field,
                base_db=base_db,
                enable_full_parallel_rewrite=enable_full_parallel_rewrite,
            )
            return line_no, out

        print(
            f"[apply_predicted_cut_rewrite] JSONL parallel: {len(records)} lines, jsonl-workers={workers}",
            flush=True,
        )
        print(
            f"[apply_predicted_cut_rewrite] Streaming output (same order as input): {output_path.resolve()}",
            flush=True,
        )
        # Write in input order as soon as each prefix of lines is ready (QUITE can take a long time per row).
        line_order = [ln for ln, _ in records]
        completed: Dict[int, Dict[str, Any]] = {}
        emit_ptr = 0

        def _try_flush(fout: Any) -> None:
            nonlocal emit_ptr
            while emit_ptr < len(line_order):
                need = line_order[emit_ptr]
                if need not in completed:
                    break
                row = completed.pop(need)
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                fout.flush()
                emit_ptr += 1

        with output_path.open("w", encoding="utf-8") as fout:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futs = [pool.submit(_task, rec) for rec in records]
                for fut in concurrent.futures.as_completed(futs):
                    line_no, out = fut.result()
                    completed[line_no] = out
                    _try_flush(fout)
            _try_flush(fout)
    if trace_f is not None:
        trace_f.close()


def run_sql_file(
    sql_path: Path,
    cuts: Sequence[str],
    output_path: Path,
    llmr2_trace_csv: Optional[Path] = None,
    default_db_id: Optional[str] = None,
    enable_full_parallel_rewrite: bool = True,
) -> None:
    base_db = str(
        (default_db_id or DB_CONFIG.get("database") or "tpch")
    ).strip() or "tpch"
    sql_text = sql_path.read_text(encoding="utf-8")
    cut_list = [str(c) for c in cuts]
    if llmr2_trace_csv is not None:
        llmr2_trace_csv.parent.mkdir(parents=True, exist_ok=True)
        rec = try_evaluate_with_rewrite_trace(
            sql_text,
            cut_list,
            enable_full_parallel_rewrite=enable_full_parallel_rewrite,
        )
        with llmr2_trace_csv.open("w", encoding="utf-8", newline="") as tf:
            tw = csv.DictWriter(
                tf,
                fieldnames=list(CSV_LLM_R2_TRACE_COLUMNS),
                quoting=csv.QUOTE_MINIMAL,
            )
            tw.writeheader()
            for r in build_llmr2_trace_csv_rows(
                full_original_sql=sql_text,
                rec=rec,
                source_jsonl_line=1,
                db_id=base_db,
                traced_cut_edge_ids=cut_list,
            ):
                tw.writerow(r)
    row_start = time.perf_counter()
    payload, _ = _rewrite_one(
        sql_text,
        cut_list,
        db_id=base_db,
        enable_full_parallel_rewrite=enable_full_parallel_rewrite,
    )
    out = {
        "original_sql": payload.get("original_sql", ""),
        "rewritten_sql": payload.get("rewritten_sql", ""),
        "applied_cut_edge_ids": payload.get("applied_cut_edge_ids", []),
        "original_query_cost": payload.get("original_query_cost"),
        "rewritten_query_cost": payload.get("rewritten_query_cost"),
        "variant_fatal_error": payload.get("variant_fatal_error", ""),
        "sql_path": str(sql_path.resolve()),
        "inference_time_sec": round(time.perf_counter() - row_start, 6),
    }
    output_path.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Rewrite SQL using a fixed predicted cut set.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--jsonl", type=Path, help="Input JSONL (e.g. pointer_net predictions).")
    g.add_argument("--sql", type=Path, help="Single SQL file to rewrite.")
    ap.add_argument(
        "--cuts-field",
        default="predicted_cut_edge_ids",
        help="JSONL field to read cut ids from (default: predicted_cut_edge_ids).",
    )
    ap.add_argument(
        "--cuts-json",
        default=None,
        help='JSON array of edge ids, required with --sql (e.g. \'["E0","E1"]\').',
    )
    ap.add_argument(
        "--cuts-json-file",
        type=Path,
        default=None,
        help="Path to a JSON file containing an array of edge ids (alternative to --cuts-json).",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output JSONL path (one line for --sql, many for --jsonl). "
            "When using --jsonl and omitted, defaults to <jsonl_stem>_rewritten_sql<suffix>."
        ),
    )
    ap.add_argument(
        "--llmr2-trace-csv",
        type=Path,
        default=None,
        help="Also write LLMR2-oriented cut step rows to this CSV (db_id, original_sql, source_jsonl_line, cut_edge_id, step_type).",
    )
    ap.add_argument(
        "--llmr2-trace-csv-only",
        action="store_true",
        help="Only write --llmr2-trace-csv (requires --jsonl); skips --output JSONL.",
    )
    ap.add_argument(
        "--default-db-id",
        type=str,
        default=None,
        help="db_id for the trace CSV if a JSONL line has no metadata.db_id (default: config database).",
    )
    ap.add_argument(
        "--rewrite-backend",
        type=str,
        default="calcite_rules",
        help="Rewrite backend: calcite_rules (default), llmr2, or quite.",
    )
    ap.add_argument(
        "--quite-schema-file",
        type=Path,
        default=None,
        help=(
            "Schema .sql path passed to the quite backend (context quite_schema_file). "
            "If omitted, quite still uses env QUITE_SCHEMA_FILE when set."
        ),
    )
    ap.add_argument(
        "--disable-full-parallel-rewrite",
        action="store_true",
        help=(
            "Disable fixed-cut full parallel rewrite (llmr2 / quite). "
            "By default this script rewrites all selected cut blocks in parallel for those backends."
        ),
    )
    ap.add_argument(
        "--jsonl-workers",
        type=int,
        default=None,
        help=(
            "Process --jsonl lines in parallel with this many threads (default: env BQR_JSONL_WORKERS, "
            "else 1 except quite→min(4, CPUs)). Disabled when --llmr2-trace-csv is set; llmr2 backend uses 1."
        ),
    )
    args = ap.parse_args()

    # Keep the same backend wiring as double_greedy_cut_search.py.
    dg_search._ACTIVE_REWRITE_BACKEND = dg_search.create_rewrite_backend(args.rewrite_backend, REPO_ROOT)
    dg_search._VALIDATION = None
    if args.quite_schema_file is not None:
        qp = args.quite_schema_file.expanduser().resolve()
        if not qp.is_file():
            ap.error(f"--quite-schema-file not a file: {qp}")
        dg_search._REWRITE_EXTRA_CONTEXT = {"quite_schema_file": str(qp)}
    else:
        dg_search._REWRITE_EXTRA_CONTEXT = None

    enable_full_parallel_rewrite = not bool(args.disable_full_parallel_rewrite)

    def _resolve_jsonl_workers() -> int:
        if args.llmr2_trace_csv is not None:
            return 1
        if args.jsonl_workers is not None:
            return max(1, int(args.jsonl_workers))
        env_raw = (os.getenv("BQR_JSONL_WORKERS") or "").strip()
        if env_raw:
            try:
                return max(1, int(env_raw, 10))
            except ValueError:
                pass
        backend_name = (args.rewrite_backend or "").strip().lower()
        if backend_name in {"quite", "quite_rewriter"}:
            cpu = os.cpu_count() or 4
            return min(4, max(2, cpu))
        return 1

    jsonl_workers_effective = _resolve_jsonl_workers()
    _be = dg_search._ACTIVE_REWRITE_BACKEND
    if jsonl_workers_effective > 1 and _be is not None and _be.name == "llmr2":
        print(
            "[apply_predicted_cut_rewrite] llmr2 backend is not thread-safe across JSONL rows; using jsonl-workers=1.",
            flush=True,
        )
        jsonl_workers_effective = 1

    if args.llmr2_trace_csv_only:
        if args.jsonl is None or args.llmr2_trace_csv is None:
            ap.error("--llmr2-trace-csv-only requires --jsonl and --llmr2-trace-csv")
        if args.output is not None:
            ap.error("--llmr2-trace-csv-only cannot be used with --output")
        export_llmr2_trace_csv_for_jsonl(
            args.jsonl,
            args.llmr2_trace_csv,
            cuts_field=args.cuts_field,
            default_db_id=args.default_db_id,
            enable_full_parallel_rewrite=enable_full_parallel_rewrite,
        )
        return

    if args.output is None:
        if args.jsonl is not None:
            in_path = args.jsonl
            in_suffix = in_path.suffix or ".jsonl"
            args.output = in_path.with_name(f"{in_path.stem}_rewritten_sql{in_suffix}")
        else:
            ap.error("--output is required with --sql (unless using --llmr2-trace-csv-only)")

    if args.sql is not None:
        if args.cuts_json_file is not None:
            cuts = _parse_cuts_json(args.cuts_json_file.read_text(encoding="utf-8"))
        elif args.cuts_json is not None:
            cuts = _parse_cuts_json(args.cuts_json)
        else:
            ap.error("--sql requires --cuts-json or --cuts-json-file")
        run_sql_file(
            args.sql,
            cuts,
            args.output,
            llmr2_trace_csv=args.llmr2_trace_csv,
            default_db_id=args.default_db_id,
            enable_full_parallel_rewrite=enable_full_parallel_rewrite,
        )
    else:
        run_jsonl(
            args.jsonl,
            args.output,
            args.cuts_field,
            llmr2_trace_csv=args.llmr2_trace_csv,
            default_db_id=args.default_db_id,
            enable_full_parallel_rewrite=enable_full_parallel_rewrite,
            jsonl_workers=jsonl_workers_effective,
        )


if __name__ == "__main__":
    main()
