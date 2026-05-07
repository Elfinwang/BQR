from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import torch
from torch.utils.data import DataLoader, random_split

SCRIPT_PATH = Path(__file__).resolve()
MODULE_DIR = SCRIPT_PATH.parent
REPO_ROOT = SCRIPT_PATH.parents[2]
for path in (REPO_ROOT, MODULE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from BQR.pointer_net_cut_selector.cli import (
    compute_loss,
    evaluate_model,
    move_batch_to_device,
    save_checkpoint,
)
from BQR.pointer_net_cut_selector.dataset import (
    ExampleRecord,
    JsonlCutDataset,
    build_example_from_record,
    build_vocab_from_examples,
    collate_batch,
    load_jsonl_records,
)
from BQR.pointer_net_cut_selector.model import PointerNetworkCutSelector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train PointerNetworkCutSelector on JSONL with 'sql' (or 'sql_text') and "
            "target cut edge ids (e.g. target_cut_edge_ids / cut_edge_ids)."
        )
    )
    parser.add_argument("--train-jsonl", type=str, required=True, help="Training JSONL (see dataset.build_example_from_record).")
    parser.add_argument("--valid-jsonl", type=str, default=None, help="Optional validation JSONL.")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory for checkpoints (best.pt, last.pt).")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--train-split", type=float, default=0.9, help="Used when --valid-jsonl is omitted.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", type=str, default=None, help="e.g. cuda, cuda:0, cpu")
    parser.add_argument("--token-embed-dim", type=int, default=128)
    parser.add_argument("--hidden-dim", type=int, default=256, help="Edge hidden dim (BiLSTM + decoder).")
    parser.add_argument("--encoder-layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--max-tokens-per-edge", type=int, default=256)
    parser.add_argument("--min-vocab-freq", type=int, default=1)
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def choose_device(user_value: Optional[str]) -> torch.device:
    if user_value:
        return torch.device(user_value)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_train_examples(path: str) -> List[ExampleRecord]:
    """Load either dataset-style JSONL (sql + targets) or SQLCutSample lines from build_pointer_dataset."""
    file_path = Path(path).expanduser().resolve()
    raw_records = load_jsonl_records(file_path)
    if not raw_records:
        raise ValueError(f"No JSON lines in: {file_path}")

    first = raw_records[0]
    if "edge_texts" in first and "sql_text" in first:
        examples: List[ExampleRecord] = []
        for row in raw_records:
            sql_text = str(row.get("sql_text") or "").strip()
            if not sql_text:
                continue
            targets = row.get("target_edge_ids") or []
            if not isinstance(targets, list):
                raise TypeError("target_edge_ids must be a list when using SQLCutSample JSONL.")
            record = {"sql": sql_text, "target_cut_edge_ids": targets}
            examples.append(build_example_from_record(record))
        if not examples:
            raise ValueError(f"No usable SQLCutSample rows in: {file_path}")
        return examples

    return [build_example_from_record(row) for row in raw_records]


def build_dataloaders(
    args: argparse.Namespace,
    vocab: Any,
    train_examples: List[ExampleRecord],
) -> tuple[DataLoader, DataLoader, DataLoader]:
    if args.valid_jsonl:
        valid_examples = load_train_examples(args.valid_jsonl)
        train_ds = JsonlCutDataset(train_examples, vocab=vocab, max_tokens_per_edge=args.max_tokens_per_edge)
        valid_ds = JsonlCutDataset(valid_examples, vocab=vocab, max_tokens_per_edge=args.max_tokens_per_edge)
    else:
        dataset = JsonlCutDataset(train_examples, vocab=vocab, max_tokens_per_edge=args.max_tokens_per_edge)
        train_size = max(1, int(len(dataset) * args.train_split))
        valid_size = len(dataset) - train_size
        if valid_size == 0 and len(dataset) > 1:
            train_size = len(dataset) - 1
            valid_size = 1
        if valid_size == 0:
            train_ds = valid_ds = dataset
        else:
            train_ds, valid_ds = random_split(
                dataset,
                [train_size, valid_size],
                generator=torch.Generator().manual_seed(args.seed),
            )

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=lambda batch: collate_batch(batch, pad_id=vocab.pad_id),
    )
    train_eval_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=lambda batch: collate_batch(batch, pad_id=vocab.pad_id),
    )
    valid_loader = DataLoader(
        valid_ds,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=lambda batch: collate_batch(batch, pad_id=vocab.pad_id),
    )
    return train_loader, train_eval_loader, valid_loader


def main() -> None:
    args = parse_args()
    set_seed(args.seed)
    device = choose_device(args.device)

    train_examples = load_train_examples(args.train_jsonl)
    vocab = build_vocab_from_examples(train_examples, min_freq=args.min_vocab_freq)
    train_loader, train_eval_loader, valid_loader = build_dataloaders(args, vocab, train_examples)

    model = PointerNetworkCutSelector(
        vocab_size=len(vocab),
        numeric_feature_dim=5,
        token_embed_dim=args.token_embed_dim,
        edge_hidden_dim=args.hidden_dim,
        encoder_layers=args.encoder_layers,
        dropout=args.dropout,
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    best_metric = float("-inf")
    history: List[Dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        seen = 0
        for batch in train_loader:
            batch = move_batch_to_device(batch, device)
            optimizer.zero_grad(set_to_none=True)
            loss = compute_loss(model, batch)
            loss.backward()
            optimizer.step()
            batch_size = batch["edge_token_ids"].size(0)
            running_loss += float(loss.item()) * batch_size
            seen += batch_size

        train_loss = running_loss / max(seen, 1)
        train_metrics = evaluate_model(model, train_eval_loader, device)
        dev_metrics = evaluate_model(model, valid_loader, device)
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_eval_loss": train_metrics["loss"],
            "train_sequence_exact_match": train_metrics["sequence_exact_match"],
            "train_set_exact_match": train_metrics["set_exact_match"],
            "train_avg_f1": train_metrics["avg_f1"],
            "train_token_accuracy": train_metrics["token_accuracy"],
            "valid_loss": dev_metrics["loss"],
            "valid_sequence_exact": dev_metrics["sequence_exact_match"],
            "valid_set_exact": dev_metrics["set_exact_match"],
            "valid_avg_f1": dev_metrics["avg_f1"],
            "valid_token_accuracy": dev_metrics["token_accuracy"],
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False))

        score = dev_metrics["sequence_exact_match"]
        if score > best_metric:
            best_metric = score
            save_checkpoint(
                path=output_dir / "best.pt",
                model=model,
                vocab=vocab,
                max_tokens_per_edge=args.max_tokens_per_edge,
                train_args=vars(args),
            )

        save_checkpoint(
            path=output_dir / "last.pt",
            model=model,
            vocab=vocab,
            max_tokens_per_edge=args.max_tokens_per_edge,
            train_args=vars(args),
        )

    (output_dir / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"saved_dir": str(output_dir), "best_valid_seq_exact": best_metric}, ensure_ascii=False))


if __name__ == "__main__":
    main()
