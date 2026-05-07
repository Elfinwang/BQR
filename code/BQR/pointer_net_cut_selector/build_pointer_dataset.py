# 对于单个sql

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SCRIPT_PATH = Path(__file__).resolve()
MODULE_DIR = SCRIPT_PATH.parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from BQR.pointer_net_cut_selector.sql_graph_dataset import SQLCutSample, build_sample_from_sql, save_samples_to_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build pointer-network training samples from a manifest. "
            "Each manifest line should contain sql_file or sql_text, and optionally "
            "target_edge_ids or search_result_json."
        )
    )
    parser.add_argument("--manifest-jsonl", type=str, default=None, help="Input manifest JSONL.")
    parser.add_argument("--output-jsonl", type=str, default=None, help="Output dataset JSONL.")
    parser.add_argument(
        "--write-example-manifest",
        type=str,
        default=None,
        help=(
            "If set, write a single-line example manifest to this path and exit. "
            "Use repo-relative paths; edit search_result_json to your double-greedy JSON."
        ),
    )
    return parser.parse_args()


def _load_target_edge_ids(row: Dict[str, Any]) -> List[str]:
    if "target_edge_ids" in row and row["target_edge_ids"] is not None:
        return list(row["target_edge_ids"])

    search_json = row.get("search_result_json")
    if search_json:
        payload = json.loads(Path(search_json).expanduser().resolve().read_text(encoding="utf-8"))
        best = payload.get("best") or {}
        return list(best.get("cut_edge_ids") or [])
    return []


def _load_sql(row: Dict[str, Any]) -> str:
    if row.get("sql_text") is not None:
        return str(row["sql_text"])
    sql_file = row.get("sql_file")
    if not sql_file:
        raise ValueError("Each manifest row must provide sql_file or sql_text.")
    return Path(sql_file).expanduser().resolve().read_text(encoding="utf-8")


def _sample_id(row: Dict[str, Any], line_no: int) -> str:
    explicit = row.get("sample_id")
    if explicit:
        return str(explicit)
    if row.get("sql_file"):
        return Path(row["sql_file"]).stem
    return f"sample_{line_no}"


def main() -> None:
    args = parse_args()
    if args.write_example_manifest:
        example_path = Path(args.write_example_manifest).expanduser().resolve()
        example_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "sample_id": "complex_tpch_example",
            "sql_file": "experiments/submodular_cut_validation/complex_tpch_query.sql",
            "search_result_json": "experiments/double_greedy/complex_tpch_sql_double_greedy0416.json",
        }
        example_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote example manifest to {example_path}")
        return

    if not args.manifest_jsonl or not args.output_jsonl:
        raise SystemExit("--manifest-jsonl and --output-jsonl are required unless --write-example-manifest is set.")

    samples: List[SQLCutSample] = []
    manifest_path = Path(args.manifest_jsonl).expanduser().resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Manifest not found: {manifest_path}\n"
            "Create a JSONL file with one object per line, e.g.:\n"
            '  {"sql_file": "path/to/query.sql", "search_result_json": "path/to/double_greedy_output.json"}\n'
            "Or generate a starter file:\n"
            "  python BQR/pointer_net_cut_selector/build_pointer_dataset.py "
            "--manifest-jsonl dummy.jsonl --output-jsonl out.jsonl "
            "--write-example-manifest data/pointer_net/train_manifest.jsonl\n"
            "Then edit paths inside the manifest and re-run without --write-example-manifest."
        )
    with manifest_path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            row = json.loads(raw)
            sample = build_sample_from_sql(
                sql_text=_load_sql(row),
                sample_id=_sample_id(row, line_no),
                target_edge_ids=_load_target_edge_ids(row),
            )
            samples.append(sample)

    if not samples:
        raise ValueError(f"No valid rows found in: {manifest_path}")
    save_samples_to_jsonl(samples, args.output_jsonl)
    print(f"Built {len(samples)} samples -> {Path(args.output_jsonl).expanduser().resolve()}")


if __name__ == "__main__":
    main()
