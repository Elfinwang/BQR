from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch

SCRIPT_PATH = Path(__file__).resolve()
MODULE_DIR = SCRIPT_PATH.parent
REPO_ROOT = SCRIPT_PATH.parents[2]
for path in (REPO_ROOT, MODULE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from BQR.pointer_net_cut_selector.cli import decode_predictions, move_batch_to_device
from BQR.pointer_net_cut_selector.dataset import (
    JsonlCutDataset,
    TokenVocab,
    build_example_from_record,
    collate_batch,
    load_jsonl_records,
)
from BQR.pointer_net_cut_selector.model import PointerNetworkCutSelector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict SQL cut edges with a trained PointerNetworkCutSelector checkpoint.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sql-file", type=str, help="Path to a SQL file.")
    source.add_argument("--sql", type=str, help="Inline SQL text.")
    source.add_argument(
        "--input-jsonl",
        type=str,
        help="Batch mode: JSONL with sql/sql_text per line (e.g. tpch_csv_test.jsonl). Use with --output-jsonl.",
    )
    parser.add_argument("--checkpoint", type=str, required=True, help="Checkpoint from train_pointer_net.py or cli (best.pt).")
    parser.add_argument("--sample-id", type=str, default="predict_sample")
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--max-steps", type=int, default=None, help="Optional max decode length.")
    parser.add_argument("--output-json", type=str, default=None, help="Optional file to save the prediction JSON (single-query mode).")
    parser.add_argument(
        "--output-jsonl",
        type=str,
        default=None,
        help="Batch mode: write one JSON object per input line; original sql is the first field.",
    )
    return parser.parse_args()


def choose_device(user_value: str | None) -> torch.device:
    if user_value:
        return torch.device(user_value)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_sql(args: argparse.Namespace) -> str:
    if args.sql is not None:
        return args.sql
    if args.sql_file is None:
        raise ValueError("Expected --sql or --sql-file.")
    return Path(args.sql_file).expanduser().resolve().read_text(encoding="utf-8")


def _gold_targets_from_row(row: Dict[str, Any]) -> List[str]:
    raw = row.get("target_cut_edge_ids")
    if raw is None:
        raw = row.get("cut_edge_ids")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


def predict_line_payload(
    model: PointerNetworkCutSelector,
    vocab: TokenVocab,
    max_tokens_per_edge: int,
    sql_text: str,
    device: torch.device,
    max_steps: Optional[int],
) -> Dict[str, Any]:
    """Run model on one SQL string; raises if graph has no eligible edges."""
    example = build_example_from_record({"sql": sql_text.strip(), "target_cut_edge_ids": []})
    ds = JsonlCutDataset([example], vocab=vocab, max_tokens_per_edge=max_tokens_per_edge)
    batch = collate_batch([ds[0]], pad_id=vocab.pad_id)
    batch = move_batch_to_device(batch, device)

    predictions = model.predict(
        edge_token_ids=batch["edge_token_ids"],
        edge_token_mask=batch["edge_token_mask"],
        numeric_features=batch["numeric_features"],
        edge_mask=batch["edge_mask"],
        max_decode_steps=max_steps,
    )
    edge_ids: List[str] = list(batch["edge_ids"][0])
    pred_positions = predictions[0]
    predicted_edge_ids = decode_predictions(pred_positions, edge_ids)

    return {
        "num_eligible_edges": len(edge_ids),
        "predicted_cut_edge_ids": predicted_edge_ids,
        "predicted_edge_positions": list(pred_positions),
        "edge_ids": edge_ids,
    }


def load_model(checkpoint_path: str, device: torch.device) -> tuple[PointerNetworkCutSelector, TokenVocab, int]:
    ckpt = torch.load(Path(checkpoint_path).expanduser().resolve(), map_location=device)
    vocab = TokenVocab.from_state(ckpt["vocab"])
    model = PointerNetworkCutSelector(**ckpt["model_config"]).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    max_tokens = int(ckpt.get("max_tokens_per_edge", 256))
    return model, vocab, max_tokens


@torch.no_grad()
def predict(
    model: PointerNetworkCutSelector,
    vocab: TokenVocab,
    max_tokens_per_edge: int,
    sql_text: str,
    sample_id: str,
    device: torch.device,
    max_steps: int | None,
) -> Dict[str, object]:
    body = predict_line_payload(
        model=model,
        vocab=vocab,
        max_tokens_per_edge=max_tokens_per_edge,
        sql_text=sql_text,
        device=device,
        max_steps=max_steps,
    )
    out: Dict[str, object] = {"sample_id": sample_id}
    out.update(body)
    return out


def build_jsonl_output_row(
    line_index: int,
    row: Dict[str, Any],
    sql: str,
    pred: Optional[Dict[str, Any]],
    error: Optional[str],
) -> Dict[str, Any]:
    """Original sql first, then labels/metadata, then predictions (or error)."""
    out: Dict[str, Any] = {"sql": sql, "line_index": line_index}
    if "metadata" in row:
        out["metadata"] = row["metadata"]
    gold = _gold_targets_from_row(row)
    out["target_cut_edge_ids"] = gold
    if error is not None:
        out["error"] = error
        out["num_eligible_edges"] = 0
        out["predicted_cut_edge_ids"] = []
        out["predicted_edge_positions"] = []
        out["edge_ids"] = []
        return out
    assert pred is not None
    out.update(pred)
    return out


@torch.no_grad()
def predict_jsonl_file(
    model: PointerNetworkCutSelector,
    vocab: TokenVocab,
    max_tokens_per_edge: int,
    input_jsonl: Path,
    output_jsonl: Path,
    device: torch.device,
    max_steps: Optional[int],
) -> Dict[str, int]:
    records = load_jsonl_records(input_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    ok = 0
    failed = 0
    with output_jsonl.open("w", encoding="utf-8") as sink:
        for line_index, row in enumerate(records, start=1):
            sql = str(row.get("sql") or row.get("sql_text") or "").strip()
            if not sql:
                payload = build_jsonl_output_row(line_index, row, sql="", pred=None, error="empty_sql")
                failed += 1
                sink.write(json.dumps(payload, ensure_ascii=False) + "\n")
                continue
            try:
                pred = predict_line_payload(
                    model=model,
                    vocab=vocab,
                    max_tokens_per_edge=max_tokens_per_edge,
                    sql_text=sql,
                    device=device,
                    max_steps=max_steps,
                )
                payload = build_jsonl_output_row(line_index, row, sql=sql, pred=pred, error=None)
                ok += 1
            except Exception as exc:
                payload = build_jsonl_output_row(line_index, row, sql=sql, pred=None, error=f"{type(exc).__name__}: {exc}")
                failed += 1
            sink.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return {"num_lines": len(records), "num_ok": ok, "num_failed": failed}


def main() -> None:
    args = parse_args()
    if args.input_jsonl:
        if not args.output_jsonl:
            raise SystemExit("Batch mode requires --output-jsonl (path to write predictions).")
    device = choose_device(args.device)
    model, vocab, max_tokens = load_model(args.checkpoint, device)

    if args.input_jsonl:
        in_path = Path(args.input_jsonl).expanduser().resolve()
        out_path = Path(args.output_jsonl).expanduser().resolve()
        stats = predict_jsonl_file(
            model=model,
            vocab=vocab,
            max_tokens_per_edge=max_tokens,
            input_jsonl=in_path,
            output_jsonl=out_path,
            device=device,
            max_steps=args.max_steps,
        )
        print(json.dumps({"wrote": str(out_path), **stats}, ensure_ascii=False))
        return

    sql_text = load_sql(args)
    payload = predict(
        model=model,
        vocab=vocab,
        max_tokens_per_edge=max_tokens,
        sql_text=sql_text,
        sample_id=args.sample_id,
        device=device,
        max_steps=args.max_steps,
    )
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.output_json:
        out_path = Path(args.output_json).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
