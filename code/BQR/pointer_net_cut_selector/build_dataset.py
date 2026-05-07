#!/usr/bin/env python3
"""
Build pointer-network train/test JSONL from TPCH CSV (column: original_sql).

Each line is compatible with dataset.build_example_from_record:
  {"sql": "...", "target_cut_edge_ids": [...], "metadata": {...}}

Labels are heuristic weak supervision (for pipeline testing). For oracle labels,
run double-greedy separately and merge target_cut_edge_ids.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from BQR.pointer_net_cut_selector.graph_adapter import build_graph_example


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _match_keyword(text: str, i: int, keyword: str) -> Optional[int]:
    j = _skip_ws(text, i)
    end = j + len(keyword)
    if text[j:end].lower() != keyword.lower():
        return None
    if end < len(text) and (text[end].isalnum() or text[end] == "_"):
        return None
    return end


def _read_identifier(text: str, i: int) -> Tuple[Optional[str], int]:
    i = _skip_ws(text, i)
    if i >= len(text):
        return None, i

    if text[i] == '"':
        j = i + 1
        while j < len(text):
            if text[j] == '"':
                if j + 1 < len(text) and text[j + 1] == '"':
                    j += 2
                    continue
                return text[i : j + 1], j + 1
            j += 1
        return None, i

    if not (text[i].isalpha() or text[i] == "_"):
        return None, i

    j = i + 1
    while j < len(text) and (text[j].isalnum() or text[j] == "_"):
        j += 1
    return text[i:j], j


def _read_parenthesized(text: str, i: int) -> Tuple[Optional[str], int]:
    i = _skip_ws(text, i)
    if i >= len(text) or text[i] != "(":
        return None, i

    depth = 0
    j = i
    in_single = False
    in_double = False
    while j < len(text):
        ch = text[j]
        nxt = text[j + 1] if j + 1 < len(text) else ""

        if not in_double and ch == "'" and not in_single:
            in_single = True
        elif in_single and ch == "'" and nxt == "'":
            j += 2
            continue
        elif in_single and ch == "'":
            in_single = False
        elif not in_single and ch == '"' and not in_double:
            in_double = True
        elif in_double and ch == '"':
            in_double = False
        elif not in_single and not in_double:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return text[i + 1 : j], j + 1
        j += 1
    return None, i


def parse_top_level_ctes(sql: str) -> Tuple[Dict[str, str], str]:
    ctes: Dict[str, str] = {}
    i = _skip_ws(sql, 0)
    end = _match_keyword(sql, i, "with")
    if end is None:
        return ctes, sql.strip()
    i = end
    end_recursive = _match_keyword(sql, i, "recursive")
    if end_recursive is not None:
        i = end_recursive

    while True:
        cte_name, i2 = _read_identifier(sql, i)
        if cte_name is None:
            return {}, sql.strip()
        i = i2

        i = _skip_ws(sql, i)
        if i < len(sql) and sql[i] == "(":
            _, i = _read_parenthesized(sql, i)
            if _ is None:
                return {}, sql.strip()

        as_end = _match_keyword(sql, i, "as")
        if as_end is None:
            return {}, sql.strip()
        i = as_end

        body, i = _read_parenthesized(sql, i)
        if body is None:
            return {}, sql.strip()

        ctes[cte_name.strip('"').lower()] = body.strip()

        i = _skip_ws(sql, i)
        if i < len(sql) and sql[i] == ",":
            i += 1
            continue
        break

    return ctes, sql[i:].strip()


FROM_JOIN_PATTERN = re.compile(
    r"(?P<prefix>\b(?:from|join)\s+)"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*|\"(?:[^\"]|\"\")+\")"
    r"(?P<suffix>\s*(?:as\s+)?[A-Za-z_][A-Za-z0-9_]*)?",
    flags=re.IGNORECASE,
)


def inline_ctes_in_query(sql: str) -> str:
    """
    If the query has a top-level WITH clause, inline each CTE as a parenthesized subquery in FROM/JOIN.
    Same behavior as the standalone SQLStorm inliner (regex + hand-rolled WITH parse).
    """
    ctes, body = parse_top_level_ctes(sql)
    if not ctes:
        return " ".join(sql.strip().split())

    cache: Dict[str, str] = {}
    visiting = set()

    def inline_cte(cte_name: str) -> str:
        key = cte_name.lower()
        if key in cache:
            return cache[key]
        if key in visiting:
            return ctes[key]
        visiting.add(key)
        resolved = inline_refs(ctes[key])
        visiting.remove(key)
        cache[key] = resolved
        return resolved

    def replace_ref(match: re.Match) -> str:
        prefix = match.group("prefix")
        raw_name = match.group("name")
        suffix = match.group("suffix") or ""

        table_name = raw_name.strip('"').lower()
        if table_name not in ctes:
            return match.group(0)

        inlined = inline_cte(table_name)
        alias = suffix.strip()
        if not alias:
            alias = f"as {raw_name}"
        return f"{prefix}({inlined}) {alias}"

    def inline_refs(text: str) -> str:
        return FROM_JOIN_PATTERN.sub(replace_ref, text)

    return " ".join(inline_refs(body).strip().split())


def heuristic_targets(edge_ids: Sequence[str], variant: int) -> List[str]:
    if not edge_ids:
        return []
    n = len(edge_ids)
    v = variant % 6
    if v == 0:
        return []
    if v == 1:
        return [edge_ids[0]]
    if v == 2:
        return list(edge_ids[: min(2, n)])
    if v == 3:
        return list(edge_ids[: min(3, n)])
    if v == 4:
        return [edge_ids[-1]]
    return [edge_ids[n // 2]]


def load_csv_rows(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    if "original_sql" not in df.columns:
        raise ValueError(f"CSV must contain column 'original_sql'; got: {list(df.columns)}")
    return df


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build TPCH CSV -> pointer-net train/test JSONL.")
    p.add_argument(
        "--csv",
        type=str,
        default=str(REPO_ROOT / "data" / "queries" / "TPCH" / "queries_tpch_test.csv"),
        help="Path to queries_tpch_test.csv (must have original_sql).",
    )
    p.add_argument(
        "--output-train",
        type=str,
        default=str(REPO_ROOT / "data" / "pointer_net" / "tpch_csv_train.jsonl"),
    )
    p.add_argument(
        "--output-test",
        type=str,
        default=str(REPO_ROOT / "data" / "pointer_net" / "tpch_csv_test.jsonl"),
    )
    p.add_argument("--train-ratio", type=float, default=0.9, help="Fraction of usable rows for training.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-rows", type=int, default=None, help="Optional cap for debugging.")
    return p.parse_args()


def _source_id(ser: pd.Series, idx: int) -> str:
    """First non-(db_id, original_sql) column is usually the query id column."""
    for key in ser.index:
        if key in ("original_sql", "db_id"):
            continue
        val = ser.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return str(idx + 1)


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv).expanduser().resolve()
    random.seed(args.seed)

    df = load_csv_rows(csv_path)
    rows: List[Dict[str, Any]] = []
    stats = {"total_csv_rows": len(df), "skipped_empty_sql": 0, "skipped_graph_error": 0, "skipped_no_edges": 0, "usable": 0}

    for idx, (_, ser) in enumerate(df.iterrows()):
        if args.max_rows is not None and idx >= args.max_rows:
            break
        sql = str(ser.get("original_sql", "") or "").strip()
        if not sql:
            stats["skipped_empty_sql"] += 1
            continue
        sql = inline_ctes_in_query(sql)
        try:
            graph = build_graph_example(sql)
        except Exception:
            stats["skipped_graph_error"] += 1
            continue
        variant = stats["usable"]
        if not graph.eligible_edge_ids:
            stats["skipped_no_edges"] += 1
            targets = []
            label_heuristic = "no_edges"
        else:
            targets = heuristic_targets(graph.eligible_edge_ids, variant)
            label_heuristic = f"v{variant % 6}"
        rows.append(
            {
                "sql": sql,
                "target_cut_edge_ids": targets,
                "metadata": {
                    "csv_row_index": int(idx),
                    "source_id": _source_id(ser, idx),
                    "db_id": str(ser.get("db_id", "") or "tpch"),
                    "eligible_edge_ids": graph.eligible_edge_ids,
                    "label_heuristic": label_heuristic,
                },
            }
        )
        stats["usable"] += 1

    if len(rows) < 2:
        raise SystemExit(
            f"Need at least 2 usable rows; got {len(rows)}. Stats: {json.dumps(stats)}"
        )

    random.shuffle(rows)
    n_train = max(1, int(len(rows) * args.train_ratio))
    if n_train >= len(rows):
        n_train = len(rows) - 1
    train_rows = rows[:n_train]
    test_rows = rows[n_train:]

    out_train = Path(args.output_train).expanduser().resolve()
    out_test = Path(args.output_test).expanduser().resolve()
    out_train.parent.mkdir(parents=True, exist_ok=True)
    out_test.parent.mkdir(parents=True, exist_ok=True)

    for path, part in [(out_train, train_rows), (out_test, test_rows)]:
        with path.open("w", encoding="utf-8") as f:
            for rec in part:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    summary = {
        "csv": str(csv_path),
        "train": str(out_train),
        "test": str(out_test),
        "num_train": len(train_rows),
        "num_test": len(test_rows),
        "stats": stats,
        "train_ratio": args.train_ratio,
        "seed": args.seed,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
