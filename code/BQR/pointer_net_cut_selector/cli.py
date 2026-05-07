from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random
import sys
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

import torch
from torch import nn
from torch.utils.data import DataLoader


if __package__ in {None, ""}:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

if TYPE_CHECKING:
    from BQR.pointer_net_cut_selector.dataset import TokenVocab
    from BQR.pointer_net_cut_selector.model import PointerNetworkCutSelector


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def resolve_device(device_arg: str) -> torch.device:
    if device_arg == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device_arg)


def read_sql(sql: Optional[str], sql_file: Optional[str]) -> str:
    if sql is not None:
        return sql
    if sql_file is None:
        raise ValueError("Either --sql or --sql-file is required.")
    return Path(sql_file).expanduser().resolve().read_text(encoding="utf-8")


def build_dataloader(
    examples: Sequence[Any],
    vocab: "TokenVocab",
    batch_size: int,
    shuffle: bool,
    max_tokens_per_edge: int,
) -> DataLoader:
    from BQR.pointer_net_cut_selector.dataset import JsonlCutDataset, collate_batch

    dataset = JsonlCutDataset(examples=examples, vocab=vocab, max_tokens_per_edge=max_tokens_per_edge)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        collate_fn=lambda batch: collate_batch(batch, pad_id=vocab.pad_id),
    )


def move_batch_to_device(batch: Dict[str, Any], device: torch.device) -> Dict[str, Any]:
    moved = dict(batch)
    for key in ("edge_token_ids", "edge_token_mask", "numeric_features", "edge_mask", "target_positions"):
        moved[key] = batch[key].to(device)
    return moved


def compute_loss(model: "PointerNetworkCutSelector", batch: Dict[str, Any]) -> torch.Tensor:
    output = model(
        edge_token_ids=batch["edge_token_ids"],
        edge_token_mask=batch["edge_token_mask"],
        numeric_features=batch["numeric_features"],
        edge_mask=batch["edge_mask"],
        target_positions=batch["target_positions"],
    )
    logits = output.logits
    targets = batch["target_positions"][:, : logits.size(1)]
    loss = nn.functional.cross_entropy(
        logits.reshape(-1, logits.size(-1)),
        targets.reshape(-1),
        ignore_index=-100,
    )
    return loss


def compute_batch_token_accuracy(logits: torch.Tensor, targets: torch.Tensor, ignore_index: int = -100) -> tuple[int, int]:
    """Per-step argmax vs gold; returns (num_correct, num_valid_tokens)."""
    preds = logits.argmax(dim=-1)
    valid = targets != ignore_index
    correct = int(((preds == targets) & valid).sum().item())
    total = int(valid.sum().item())
    return correct, total


def decode_predictions(predicted_positions: Sequence[int], edge_ids: Sequence[str]) -> List[str]:
    return [edge_ids[pos] for pos in predicted_positions if 0 <= pos < len(edge_ids)]


def _set_metrics(predicted: Sequence[str], target: Sequence[str]) -> Dict[str, float]:
    predicted_set = set(predicted)
    target_set = set(target)
    tp = len(predicted_set & target_set)
    precision = tp / len(predicted_set) if predicted_set else (1.0 if not target_set else 0.0)
    recall = tp / len(target_set) if target_set else (1.0 if not predicted_set else 0.0)
    if precision + recall == 0.0:
        f1 = 0.0
    else:
        f1 = 2.0 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


@torch.no_grad()
def evaluate_model(
    model: "PointerNetworkCutSelector",
    dataloader: DataLoader,
    device: torch.device,
) -> Dict[str, Any]:
    model.eval()
    total_loss = 0.0
    total_examples = 0
    sequence_exact = 0
    set_exact = 0
    precision_sum = 0.0
    recall_sum = 0.0
    f1_sum = 0.0
    token_correct = 0
    token_total = 0

    for batch in dataloader:
        batch = move_batch_to_device(batch, device)
        output = model(
            edge_token_ids=batch["edge_token_ids"],
            edge_token_mask=batch["edge_token_mask"],
            numeric_features=batch["numeric_features"],
            edge_mask=batch["edge_mask"],
            target_positions=batch["target_positions"],
        )
        logits = output.logits
        targets = batch["target_positions"][:, : logits.size(1)]
        loss = nn.functional.cross_entropy(
            logits.reshape(-1, logits.size(-1)),
            targets.reshape(-1),
            ignore_index=-100,
        )
        bc, tt = compute_batch_token_accuracy(logits, targets)
        token_correct += bc
        token_total += tt

        predictions = model.predict(
            edge_token_ids=batch["edge_token_ids"],
            edge_token_mask=batch["edge_token_mask"],
            numeric_features=batch["numeric_features"],
            edge_mask=batch["edge_mask"],
        )
        total_loss += float(loss.item()) * len(predictions)
        total_examples += len(predictions)
        for idx, pred_positions in enumerate(predictions):
            predicted_ids = decode_predictions(pred_positions, batch["edge_ids"][idx])
            target_ids = batch["target_edge_ids"][idx]
            if predicted_ids == target_ids:
                sequence_exact += 1
            if set(predicted_ids) == set(target_ids):
                set_exact += 1
            metrics = _set_metrics(predicted_ids, target_ids)
            precision_sum += metrics["precision"]
            recall_sum += metrics["recall"]
            f1_sum += metrics["f1"]

    if total_examples == 0:
        return {
            "loss": 0.0,
            "sequence_exact_match": 0.0,
            "set_exact_match": 0.0,
            "avg_precision": 0.0,
            "avg_recall": 0.0,
            "avg_f1": 0.0,
            "token_accuracy": 0.0,
        }
    return {
        "loss": total_loss / total_examples,
        "sequence_exact_match": sequence_exact / total_examples,
        "set_exact_match": set_exact / total_examples,
        "avg_precision": precision_sum / total_examples,
        "avg_recall": recall_sum / total_examples,
        "avg_f1": f1_sum / total_examples,
        "token_accuracy": token_correct / max(token_total, 1),
    }


def save_checkpoint(
    path: Path,
    model: "PointerNetworkCutSelector",
    vocab: "TokenVocab",
    max_tokens_per_edge: int,
    train_args: Dict[str, Any],
) -> None:
    payload = {
        "model_state_dict": model.state_dict(),
        "model_config": model.get_config(),
        "vocab": vocab.to_state(),
        "max_tokens_per_edge": max_tokens_per_edge,
        "train_args": train_args,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)


def load_checkpoint(path: str | Path, device: torch.device) -> Tuple["PointerNetworkCutSelector", "TokenVocab", Dict[str, Any]]:
    from BQR.pointer_net_cut_selector.dataset import TokenVocab
    from BQR.pointer_net_cut_selector.model import PointerNetworkCutSelector

    ckpt_path = Path(path).expanduser().resolve()
    payload = torch.load(ckpt_path, map_location=device)
    vocab = TokenVocab.from_state(payload["vocab"])
    model = PointerNetworkCutSelector(**payload["model_config"])
    model.load_state_dict(payload["model_state_dict"])
    model.to(device)
    model.eval()
    return model, vocab, payload


def train_command(args: argparse.Namespace) -> None:
    from BQR.pointer_net_cut_selector.dataset import build_examples_from_jsonl, build_vocab_from_examples
    from BQR.pointer_net_cut_selector.model import PointerNetworkCutSelector

    set_seed(args.seed)
    device = resolve_device(args.device)

    train_examples = build_examples_from_jsonl(args.train_jsonl)
    if not train_examples:
        raise ValueError("Training JSONL produced no usable examples.")
    vocab = build_vocab_from_examples(train_examples, min_freq=args.min_vocab_freq)
    train_loader = build_dataloader(
        train_examples,
        vocab=vocab,
        batch_size=args.batch_size,
        shuffle=True,
        max_tokens_per_edge=args.max_tokens_per_edge,
    )
    train_eval_loader = build_dataloader(
        train_examples,
        vocab=vocab,
        batch_size=args.batch_size,
        shuffle=False,
        max_tokens_per_edge=args.max_tokens_per_edge,
    )

    dev_loader = None
    dev_examples = []
    if args.dev_jsonl:
        dev_examples = build_examples_from_jsonl(args.dev_jsonl)
        dev_loader = build_dataloader(
            dev_examples,
            vocab=vocab,
            batch_size=args.batch_size,
            shuffle=False,
            max_tokens_per_edge=args.max_tokens_per_edge,
        )

    model = PointerNetworkCutSelector(
        vocab_size=len(vocab),
        numeric_feature_dim=5,
        token_embed_dim=args.token_embed_dim,
        edge_hidden_dim=args.hidden_dim,
        encoder_layers=args.encoder_layers,
        dropout=args.dropout,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    best_metric = float("-inf")
    history: List[Dict[str, Any]] = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        seen_examples = 0
        for batch in train_loader:
            batch = move_batch_to_device(batch, device)
            optimizer.zero_grad(set_to_none=True)
            loss = compute_loss(model, batch)
            loss.backward()
            if args.grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            optimizer.step()
            batch_size = batch["edge_token_ids"].size(0)
            running_loss += float(loss.item()) * batch_size
            seen_examples += batch_size

        train_loss = running_loss / max(seen_examples, 1)
        train_metrics = evaluate_model(model, train_eval_loader, device)
        epoch_record: Dict[str, Any] = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_eval_loss": train_metrics["loss"],
            "train_sequence_exact_match": train_metrics["sequence_exact_match"],
            "train_set_exact_match": train_metrics["set_exact_match"],
            "train_avg_f1": train_metrics["avg_f1"],
            "train_token_accuracy": train_metrics["token_accuracy"],
        }

        score = -train_loss
        if dev_loader is not None:
            dev_metrics = evaluate_model(model, dev_loader, device)
            epoch_record["dev"] = dev_metrics
            score = dev_metrics["sequence_exact_match"]
        history.append(epoch_record)
        print(json.dumps(epoch_record, ensure_ascii=False))

        if score > best_metric:
            best_metric = score
            save_checkpoint(
                path=Path(args.output_checkpoint).expanduser().resolve(),
                model=model,
                vocab=vocab,
                max_tokens_per_edge=args.max_tokens_per_edge,
                train_args=vars(args),
            )

    summary = {
        "output_checkpoint": str(Path(args.output_checkpoint).expanduser().resolve()),
        "num_train_examples": len(train_examples),
        "num_dev_examples": len(dev_examples),
        "vocab_size": len(vocab),
        "best_model_selection_metric": best_metric,
        "history": history,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def maybe_evaluate_cut_set(sql: str, predicted_edge_ids: Sequence[str]) -> Optional[Dict[str, Any]]:
    from BQR.submodular_cut_validation.double_greedy_cut_search import CutSetEvaluator

    evaluator = CutSetEvaluator(sql)
    result = evaluator.evaluate(set(predicted_edge_ids))
    return asdict(result)


def predict_command(args: argparse.Namespace) -> None:
    from BQR.pointer_net_cut_selector.dataset import JsonlCutDataset, build_example_from_record, collate_batch
    from BQR.pointer_net_cut_selector.graph_adapter import build_graph_example

    device = resolve_device(args.device)
    model, vocab, checkpoint = load_checkpoint(args.checkpoint, device)
    sql = read_sql(args.sql, args.sql_file)
    graph = build_graph_example(sql)

    if not graph.eligible_edges:
        output = {
            "predicted_cut_edge_ids": [],
            "num_eligible_edges": 0,
            "eligible_edges": [],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    example = build_example_from_record({"sql": sql, "target_cut_edge_ids": []})
    dataset = JsonlCutDataset(
        examples=[example],
        vocab=vocab,
        max_tokens_per_edge=int(checkpoint.get("max_tokens_per_edge", 256)),
    )
    batch = collate_batch([dataset[0]], pad_id=vocab.pad_id)
    batch = move_batch_to_device(batch, device)
    predictions = model.predict(
        edge_token_ids=batch["edge_token_ids"],
        edge_token_mask=batch["edge_token_mask"],
        numeric_features=batch["numeric_features"],
        edge_mask=batch["edge_mask"],
        max_decode_steps=args.max_decode_steps,
    )
    predicted_edge_ids = decode_predictions(predictions[0], batch["edge_ids"][0])
    output: Dict[str, Any] = {
        "predicted_cut_edge_ids": predicted_edge_ids,
        "num_eligible_edges": len(graph.eligible_edges),
        "eligible_edges": [
            {
                "edge_id": edge.edge_id,
                "parent": edge.parent,
                "child": edge.child,
                "cut_kind": edge.cut_kind,
                "cut_sql": edge.cut_sql,
            }
            for edge in graph.eligible_edges
        ],
    }
    if args.evaluate:
        output["evaluation"] = maybe_evaluate_cut_set(sql, predicted_edge_ids)
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train and run a pointer network for SQL cut-edge selection.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train", help="Train from JSONL data.")
    train_parser.add_argument("--train-jsonl", required=True, help="JSONL with sql and target cut edge ids/sequence.")
    train_parser.add_argument("--dev-jsonl", default=None, help="Optional dev JSONL for model selection.")
    train_parser.add_argument("--output-checkpoint", required=True, help="Where to save the best checkpoint.")
    train_parser.add_argument("--epochs", type=int, default=10)
    train_parser.add_argument("--batch-size", type=int, default=8)
    train_parser.add_argument("--lr", type=float, default=1e-3)
    train_parser.add_argument("--weight-decay", type=float, default=1e-5)
    train_parser.add_argument("--dropout", type=float, default=0.1)
    train_parser.add_argument("--token-embed-dim", type=int, default=128)
    train_parser.add_argument("--hidden-dim", type=int, default=256)
    train_parser.add_argument("--encoder-layers", type=int, default=1)
    train_parser.add_argument("--grad-clip", type=float, default=1.0)
    train_parser.add_argument("--min-vocab-freq", type=int, default=1)
    train_parser.add_argument("--max-tokens-per-edge", type=int, default=256)
    train_parser.add_argument("--seed", type=int, default=0)
    train_parser.add_argument("--device", default="auto")
    train_parser.set_defaults(func=train_command)

    predict_parser = subparsers.add_parser("predict", help="Predict cut edges for one SQL query.")
    source_group = predict_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--sql", default=None, help="Inline SQL string.")
    source_group.add_argument("--sql-file", default=None, help="Path to a SQL file.")
    predict_parser.add_argument("--checkpoint", required=True, help="Trained checkpoint.")
    predict_parser.add_argument("--evaluate", action="store_true", help="Evaluate the predicted cut set with CutSetEvaluator.")
    predict_parser.add_argument("--max-decode-steps", type=int, default=None)
    predict_parser.add_argument("--output-json", default=None)
    predict_parser.add_argument("--device", default="auto")
    predict_parser.set_defaults(func=predict_command)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
