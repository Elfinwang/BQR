#!/usr/bin/env python3
"""Build Pointer Network train/validation JSONL using BQR(HEU) cut-edge labels.

Read labels from the input CSV or match a BQR(HEU) result JSONL by original SQL.
Missing labels are errors; an explicit empty list is a valid no-cut target.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LABEL_FIELDS = ("target_cut_edge_ids", "applied_cut_edge_ids", "cut_edge_ids")


def extract_labels(record: Dict[str, Any], location: str) -> List[str]:
    """Require explicit JSON arrays and reject conflicting label fields."""
    candidates: List[List[str]] = []
    for field in LABEL_FIELDS:
        if field not in record:
            continue
        value = record[field]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{location}: {field} must be a JSON array, e.g. [\"E0\"] or [].") from exc
        if not isinstance(value, list) or any(not isinstance(edge, str) or not edge.strip() for edge in value):
            raise ValueError(f"{location}: {field} must be an array of non-empty edge ID strings.")
        if len(set(value)) != len(value):
            raise ValueError(f"{location}: {field} contains duplicate edge IDs.")
        candidates.append(value)
    if not candidates:
        raise ValueError(f"{location}: missing BQR(HEU) cut-edge labels; provide --labels-jsonl or a CSV label column.")
    if any(set(value) != set(candidates[0]) for value in candidates[1:]):
        raise ValueError(f"{location}: conflicting cut-edge label fields.")
    return candidates[0]


def check_search_status(record: Dict[str, Any], location: str) -> None:
    error = record.get("variant_fatal_error")
    if error:
        raise ValueError(f"{location}: failed BQR(HEU) result cannot be used as a label: {error}")


def load_label_index(path: Path) -> Dict[str, List[str]]:
    labels: Dict[str, List[str]] = {}
    with path.open(encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            location = f"{path}:{line_no}"
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{location}: expected a JSON object.")
            check_search_status(record, location)
            sql = str(record.get("original_sql") or record.get("sql") or "").strip()
            if not sql:
                raise ValueError(f"{location}: missing original_sql/sql.")
            targets = extract_labels(record, location)
            if sql in labels and set(labels[sql]) != set(targets):
                raise ValueError(f"{location}: conflicting labels for the same SQL; select one BQR(HEU) result per query.")
            labels[sql] = targets
    if not labels:
        raise ValueError(f"{path}: no labeled queries found.")
    return labels


def load_csv_rows(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    if "original_sql" not in df.columns:
        raise ValueError(f"CSV must contain column 'original_sql'; got: {list(df.columns)}")
    return df


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=str, required=True, help="CSV containing original_sql and optional BQR(HEU) label columns.")
    parser.add_argument("--labels-jsonl", type=str, help="BQR(HEU) batch results matched by exact original SQL (outer whitespace ignored).")
    parser.add_argument("--output-train", type=str, default=str(REPO_ROOT / "data/pointer_net/tpch_csv_train.jsonl"))
    parser.add_argument("--output-test", type=str, default=str(REPO_ROOT / "data/pointer_net/tpch_csv_test.jsonl"), help="Held-out validation JSONL.")
    parser.add_argument("--train-ratio", type=float, default=0.9, help="Fraction of distinct SQL queries assigned to training.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-rows", type=int, default=None, help="Optional input row limit for debugging.")
    args = parser.parse_args(argv)
    if not 0 < args.train_ratio < 1:
        parser.error("--train-ratio must be strictly between 0 and 1")
    if args.max_rows is not None and args.max_rows < 1:
        parser.error("--max-rows must be positive")
    return args


def build_rows(df: pd.DataFrame, label_index: Optional[Dict[str, List[str]]], graph_builder: Any,
               max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for idx, (_, series) in enumerate(df.iterrows()):
        if max_rows is not None and idx >= max_rows:
            break
        location = f"CSV data row {idx + 1}"
        sql = str(series.get("original_sql", "")).strip()
        if not sql:
            raise ValueError(f"{location}: original_sql is empty.")
        record = series.to_dict()
        check_search_status(record, location)
        if label_index is None:
            targets = extract_labels(record, location)
        else:
            if sql not in label_index:
                raise ValueError(f"{location}: no matching BQR(HEU) label; use the same SQL text as the search input.")
            targets = label_index[sql]
            if any(field in record for field in LABEL_FIELDS):
                csv_targets = extract_labels(record, location)
                if set(csv_targets) != set(targets):
                    raise ValueError(f"{location}: CSV labels disagree with --labels-jsonl.")
        try:
            graph = graph_builder(sql)
        except Exception as exc:
            raise ValueError(f"{location}: could not construct SQL graph: {exc}") from exc
        eligible = graph.eligible_edge_ids
        unknown = set(targets) - set(eligible)
        if unknown:
            raise ValueError(f"{location}: labels contain ineligible edges {sorted(unknown)}; candidates: {eligible}")
        # Search labels describe a set; use graph order for a stable training sequence.
        target_set = set(targets)
        rows.append({
            "sql": sql,
            "target_cut_edge_ids": [edge for edge in eligible if edge in target_set],
            "metadata": {
                "csv_row_index": idx,
                "db_id": str(series.get("db_id", "") or "tpch"),
                "eligible_edge_ids": eligible,
                "label_source": "bqr_heu",
            },
        })
    return rows


def split_rows(rows: List[Dict[str, Any]], train_ratio: float, seed: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        group = groups.setdefault(row["sql"], [])
        if group and group[0]["target_cut_edge_ids"] != row["target_cut_edge_ids"]:
            raise ValueError("Conflicting labels for duplicate SQL rows.")
        group.append(row)
    if len(groups) < 2:
        raise ValueError("Need at least two distinct labeled SQL queries for training and validation.")
    queries = list(groups)
    random.Random(seed).shuffle(queries)
    n_train = max(1, min(len(queries) - 1, int(len(queries) * train_ratio)))
    train = [row for sql in queries[:n_train] for row in groups[sql]]
    valid = [row for sql in queries[n_train:] for row in groups[sql]]
    return train, valid


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv).expanduser().resolve()
    label_path = Path(args.labels_jsonl).expanduser().resolve() if args.labels_jsonl else None
    out_train = Path(args.output_train).expanduser().resolve()
    out_test = Path(args.output_test).expanduser().resolve()
    inputs = {csv_path, label_path}
    if out_train == out_test or out_train in inputs or out_test in inputs:
        raise ValueError("Output paths must be distinct and must not overwrite input files.")
    df = load_csv_rows(csv_path)
    label_index = load_label_index(label_path) if label_path else None
    if label_index is None and not any(field in df.columns for field in LABEL_FIELDS):
        raise ValueError("Missing BQR(HEU) cut-edge labels: provide --labels-jsonl or a CSV label column.")
    from BQR.pointer_net_cut_selector.graph_adapter import build_graph_example

    rows = build_rows(df, label_index, build_graph_example, args.max_rows)
    train_rows, valid_rows = split_rows(rows, args.train_ratio, args.seed)
    for path, records in ((out_train, train_rows), (out_test, valid_rows)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({
        "csv": str(csv_path), "labels_jsonl": str(label_path) if label_path else None,
        "train": str(out_train), "validation": str(out_test),
        "num_train": len(train_rows), "num_validation": len(valid_rows),
        "label_source": "bqr_heu", "train_ratio": args.train_ratio, "seed": args.seed,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
