#!/usr/bin/env python3
"""Evaluate a trained checkpoint on a JSONL test set (sql + target_cut_edge_ids)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import torch

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from BQR.pointer_net_cut_selector.cli import decode_predictions, move_batch_to_device
from BQR.pointer_net_cut_selector.dataset import JsonlCutDataset, TokenVocab, build_example_from_record, collate_batch
from BQR.pointer_net_cut_selector.model import PointerNetworkCutSelector


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate pointer-net checkpoint on JSONL test file.")
    p.add_argument("--checkpoint", type=str, required=True, help="Path to best.pt or last.pt")
    p.add_argument("--test-jsonl", type=str, required=True, help="JSONL with sql and target_cut_edge_ids")
    p.add_argument("--device", type=str, default=None)
    p.add_argument("--max-steps", type=int, default=None)
    p.add_argument("--output-report", type=str, default=None, help="Optional JSON report path")
    return p.parse_args()


def load_ckpt(path: str, device: torch.device) -> tuple[PointerNetworkCutSelector, TokenVocab, int]:
    ckpt = torch.load(Path(path).expanduser().resolve(), map_location=device)
    vocab = TokenVocab.from_state(ckpt["vocab"])
    model = PointerNetworkCutSelector(**ckpt["model_config"]).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    return model, vocab, int(ckpt.get("max_tokens_per_edge", 256))


@torch.no_grad()
def main() -> None:
    args = parse_args()
    device = torch.device(args.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model, vocab, max_tokens = load_ckpt(args.checkpoint, device)

    test_path = Path(args.test_jsonl).expanduser().resolve()
    lines: List[Dict[str, Any]] = []
    with test_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lines.append(json.loads(line))

    seq_exact = 0
    set_exact = 0
    n = 0
    failures: List[Dict[str, Any]] = []

    for row in lines:
        sql = (row.get("sql") or row.get("sql_text") or "").strip()
        gold = row.get("target_cut_edge_ids") or row.get("cut_edge_ids") or []
        if not isinstance(gold, list):
            gold = []
        gold = [str(x) for x in gold]
        if not sql:
            continue
        try:
            example = build_example_from_record({"sql": sql, "target_cut_edge_ids": []})
        except Exception as exc:
            failures.append({"error": str(exc), "sql_preview": sql[:200]})
            continue

        ds = JsonlCutDataset([example], vocab=vocab, max_tokens_per_edge=max_tokens)
        batch = collate_batch([ds[0]], pad_id=vocab.pad_id)
        batch = move_batch_to_device(batch, device)
        preds_pos = model.predict(
            edge_token_ids=batch["edge_token_ids"],
            edge_token_mask=batch["edge_token_mask"],
            numeric_features=batch["numeric_features"],
            edge_mask=batch["edge_mask"],
            max_decode_steps=args.max_steps,
        )[0]
        edge_ids = list(batch["edge_ids"][0])
        pred_ids = decode_predictions(preds_pos, edge_ids)

        n += 1
        if pred_ids == gold:
            seq_exact += 1
        if set(pred_ids) == set(gold):
            set_exact += 1

    out = {
        "checkpoint": str(Path(args.checkpoint).resolve()),
        "test_jsonl": str(test_path),
        "num_evaluated": n,
        "num_parse_failures": len(failures),
        "sequence_exact_match": seq_exact / n if n else 0.0,
        "set_exact_match": set_exact / n if n else 0.0,
    }
    if failures:
        out["failures_sample"] = failures[:5]

    text = json.dumps(out, indent=2, ensure_ascii=False)
    print(text)
    if args.output_report:
        Path(args.output_report).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_report).expanduser().resolve().write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
