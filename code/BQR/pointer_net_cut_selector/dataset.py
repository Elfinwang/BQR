from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

import torch
from torch.utils.data import Dataset

from BQR.pointer_net_cut_selector.graph_adapter import GraphExample, build_graph_example


TOKEN_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*|\d+|!=|<=|>=|<>|==|:=|::|[-+*/%=<>()\[\]{},.;]"
)
SPECIAL_TOKENS = ["<pad>", "<unk>"]


def _edge_sort_key(edge_id: str) -> int:
    if edge_id.startswith("E") and edge_id[1:].isdigit():
        return int(edge_id[1:])
    if edge_id.isdigit():
        return int(edge_id)
    return 10**9


def tokenize_sqlish(text: str) -> List[str]:
    return TOKEN_PATTERN.findall((text or "").lower())


@dataclass
class TokenVocab:
    stoi: Dict[str, int]
    itos: List[str]

    @classmethod
    def build(cls, texts: Iterable[str], min_freq: int = 1) -> "TokenVocab":
        counter: Counter[str] = Counter()
        for text in texts:
            counter.update(tokenize_sqlish(text))
        itos = list(SPECIAL_TOKENS)
        for token, freq in sorted(counter.items()):
            if freq >= min_freq:
                itos.append(token)
        stoi = {token: idx for idx, token in enumerate(itos)}
        return cls(stoi=stoi, itos=itos)

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "TokenVocab":
        return cls(stoi=dict(state["stoi"]), itos=list(state["itos"]))

    def to_state(self) -> Dict[str, Any]:
        return {"stoi": self.stoi, "itos": self.itos}

    @property
    def pad_id(self) -> int:
        return self.stoi["<pad>"]

    @property
    def unk_id(self) -> int:
        return self.stoi["<unk>"]

    def encode(self, text: str) -> List[int]:
        return [self.stoi.get(token, self.unk_id) for token in tokenize_sqlish(text)]

    def __len__(self) -> int:
        return len(self.itos)


def build_edge_text(graph: GraphExample, edge_index: int) -> str:
    edge = graph.eligible_edges[edge_index]
    parent_sql = graph.node_infos[edge.parent].sql
    child_sql = graph.node_infos[edge.child].sql
    return " ".join(
        [
            f"kind {edge.cut_kind}",
            f"cut {edge.cut_sql}",
            f"mask {edge.mask_sql}",
            f"parent {parent_sql}",
            f"child {child_sql}",
        ]
    )


def build_numeric_features(graph: GraphExample, edge_index: int) -> List[float]:
    edge = graph.eligible_edges[edge_index]
    num_nodes = max(len(graph.node_infos), 1)
    num_edges = max(len(graph.eligible_edges), 1)
    parent_idx = int(edge.parent[1:]) if edge.parent.startswith("N") and edge.parent[1:].isdigit() else 0
    child_idx = int(edge.child[1:]) if edge.child.startswith("N") and edge.child[1:].isdigit() else 0
    edge_idx = int(edge.edge_id[1:]) if edge.edge_id.startswith("E") and edge.edge_id[1:].isdigit() else edge_index
    return [
        edge_index / num_edges,
        edge_idx / max(num_edges, 1),
        parent_idx / num_nodes,
        child_idx / num_nodes,
        1.0 if edge.parent == graph.root_node else 0.0,
    ]


def _coerce_target_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return [part for part in parts if part]
    return None


def extract_target_edge_sequence(record: Dict[str, Any], eligible_edge_ids: Sequence[str]) -> List[str]:
    for key in (
        "target_cut_edge_sequence",
        "target_cut_edges_sequence",
        "target_cut_edge_ids",
        "target_cut_edges",
        "cut_edge_ids",
        "labels",
    ):
        values = _coerce_target_list(record.get(key))
        if values is None:
            continue
        seen = set()
        sequence = []
        for edge_id in values:
            if edge_id not in eligible_edge_ids:
                raise ValueError(f"Target edge id '{edge_id}' is not eligible for this SQL graph.")
            if edge_id not in seen:
                sequence.append(edge_id)
                seen.add(edge_id)
        return sequence
    raise ValueError("Record must contain one of target_cut_edge_sequence / target_cut_edge_ids / cut_edge_ids.")


@dataclass
class ExampleRecord:
    sql: str
    graph: GraphExample
    edge_texts: List[str]
    numeric_features: List[List[float]]
    target_edge_ids: List[str]
    target_positions: List[int]
    metadata: Dict[str, Any]


def build_example_from_record(record: Dict[str, Any]) -> ExampleRecord:
    sql = str(record.get("sql") or record.get("sql_text") or "").strip()
    if not sql:
        raise ValueError("Each record must contain a non-empty 'sql' or 'sql_text' field.")
    graph = build_graph_example(sql)
    edge_texts = [build_edge_text(graph, idx) for idx in range(len(graph.eligible_edges))]
    numeric_features = [build_numeric_features(graph, idx) for idx in range(len(graph.eligible_edges))]
    target_edge_ids = extract_target_edge_sequence(record, graph.eligible_edge_ids)
    position_by_id = {edge_id: idx for idx, edge_id in enumerate(graph.eligible_edge_ids)}
    target_positions = [position_by_id[edge_id] for edge_id in target_edge_ids]
    metadata = {key: value for key, value in record.items() if key != "sql"}
    return ExampleRecord(
        sql=sql,
        graph=graph,
        edge_texts=edge_texts,
        numeric_features=numeric_features,
        target_edge_ids=target_edge_ids,
        target_positions=target_positions,
        metadata=metadata,
    )


def load_jsonl_records(path: str | Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    input_path = Path(path).expanduser().resolve()
    with input_path.open("r", encoding="utf-8") as handle:
        for line_idx, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_idx} of {input_path}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Line {line_idx} of {input_path} is not a JSON object.")
            records.append(record)
    return records


def build_examples_from_jsonl(path: str | Path) -> List[ExampleRecord]:
    return [build_example_from_record(record) for record in load_jsonl_records(path)]


class JsonlCutDataset(Dataset[ExampleRecord]):
    def __init__(self, examples: Sequence[ExampleRecord], vocab: TokenVocab, max_tokens_per_edge: int = 256) -> None:
        self.examples = list(examples)
        self.vocab = vocab
        self.max_tokens_per_edge = max_tokens_per_edge

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        example = self.examples[idx]
        edge_token_ids = []
        for text in example.edge_texts:
            token_ids = self.vocab.encode(text)[: self.max_tokens_per_edge]
            if not token_ids:
                token_ids = [self.vocab.unk_id]
            edge_token_ids.append(token_ids)
        return {
            "sql": example.sql,
            "graph": example.graph,
            "edge_ids": example.graph.eligible_edge_ids,
            "edge_token_ids": edge_token_ids,
            "numeric_features": example.numeric_features,
            "target_positions": list(example.target_positions),
            "target_edge_ids": list(example.target_edge_ids),
            "metadata": dict(example.metadata),
        }


def build_vocab_from_examples(examples: Sequence[ExampleRecord], min_freq: int = 1) -> TokenVocab:
    texts = [text for example in examples for text in example.edge_texts]
    return TokenVocab.build(texts, min_freq=min_freq)


def collate_batch(batch: Sequence[Dict[str, Any]], pad_id: int) -> Dict[str, Any]:
    batch_size = len(batch)
    max_edges = max(1, max(len(item["edge_token_ids"]) for item in batch))
    max_tokens = max(
        1,
        max(
            (len(tokens) for item in batch for tokens in item["edge_token_ids"]),
            default=0,
        ),
    )
    max_target_len = max(len(item["target_positions"]) for item in batch) + 1
    eos_index = max_edges
    feature_dim = max(
        (len(features[0]) for features in (item["numeric_features"] for item in batch) if features),
        default=5,
    )

    edge_token_ids = torch.full((batch_size, max_edges, max_tokens), pad_id, dtype=torch.long)
    edge_token_mask = torch.zeros((batch_size, max_edges, max_tokens), dtype=torch.bool)
    numeric_features = torch.zeros((batch_size, max_edges, feature_dim), dtype=torch.float32)
    edge_mask = torch.zeros((batch_size, max_edges), dtype=torch.bool)
    target_positions = torch.full((batch_size, max_target_len), -100, dtype=torch.long)

    sql_list: List[str] = []
    graph_list: List[GraphExample] = []
    edge_id_list: List[List[str]] = []
    target_edge_id_list: List[List[str]] = []
    metadata_list: List[Dict[str, Any]] = []

    for batch_idx, item in enumerate(batch):
        sql_list.append(item["sql"])
        graph_list.append(item["graph"])
        edge_id_list.append(list(item["edge_ids"]))
        target_edge_id_list.append(list(item["target_edge_ids"]))
        metadata_list.append(dict(item["metadata"]))
        valid_edge_count = len(item["edge_token_ids"])
        edge_mask[batch_idx, :valid_edge_count] = True
        for edge_idx, token_ids in enumerate(item["edge_token_ids"]):
            edge_token_ids[batch_idx, edge_idx, : len(token_ids)] = torch.tensor(token_ids, dtype=torch.long)
            edge_token_mask[batch_idx, edge_idx, : len(token_ids)] = True
            numeric_features[batch_idx, edge_idx] = torch.tensor(item["numeric_features"][edge_idx], dtype=torch.float32)
        label_seq = list(item["target_positions"]) + [eos_index]
        target_positions[batch_idx, : len(label_seq)] = torch.tensor(label_seq, dtype=torch.long)

    return {
        "sql": sql_list,
        "graphs": graph_list,
        "edge_ids": edge_id_list,
        "edge_token_ids": edge_token_ids,
        "edge_token_mask": edge_token_mask,
        "numeric_features": numeric_features,
        "edge_mask": edge_mask,
        "target_positions": target_positions,
        "target_edge_ids": target_edge_id_list,
        "metadata": metadata_list,
        "eos_index": eos_index,
    }


def sort_edge_ids(edge_ids: Sequence[str]) -> List[str]:
    return sorted(edge_ids, key=_edge_sort_key)
