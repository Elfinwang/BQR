from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import torch
from torch.utils.data import Dataset


SCRIPT_PATH = Path(__file__).resolve()
MODULE_DIR = SCRIPT_PATH.parent
REPO_ROOT = SCRIPT_PATH.parents[2]
VALIDATION_MODULE_PATH = REPO_ROOT / "BQR" / "submodular_cut_validation" / "run_validation_cut_experiment.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_VALIDATION: Optional[Any] = None


def _load_validation_module() -> Any:
    spec = importlib.util.spec_from_file_location("submodular_cut_validation_module", VALIDATION_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load validation module from: {VALIDATION_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validation() -> Any:
    global _VALIDATION
    if _VALIDATION is None:
        _VALIDATION = _load_validation_module()
    return _VALIDATION


def _node_sort_key(node_id: str) -> int:
    try:
        return int(node_id[1:]) if node_id.startswith("N") else int(node_id)
    except Exception:
        return 10**9


def _edge_sort_key(edge_id: str) -> int:
    try:
        return int(edge_id[1:]) if edge_id.startswith("E") else int(edge_id)
    except Exception:
        return 10**9


@dataclass
class SQLCutSample:
    sample_id: str
    sql_text: str
    node_ids: List[str]
    node_texts: List[str]
    edge_ids: List[str]
    edge_indices: List[Tuple[int, int]]
    edge_texts: List[str]
    edge_cut_kinds: List[str]
    target_edge_ids: List[str]
    has_target: bool


def build_sample_from_sql(
    sql_text: str,
    sample_id: str,
    target_edge_ids: Optional[Sequence[str]] = None,
) -> SQLCutSample:
    validation = _validation()
    fixer = validation.SubqueryFixer()
    root, node_infos, edges = validation._collect_graph(sql_text, fixer)
    eligible_edges = sorted(
        [edge for edge in edges if edge.cut_kind in validation.ELIGIBLE_CUT_KINDS],
        key=lambda edge: _edge_sort_key(edge.edge_id),
    )
    sorted_nodes = sorted(node_infos.values(), key=lambda node: _node_sort_key(node.node_id))
    node_id_to_index = {node.node_id: idx for idx, node in enumerate(sorted_nodes)}

    node_texts: List[str] = []
    for node in sorted_nodes:
        node_texts.append(
            "\n".join(
                [
                    f"node_id: {node.node_id}",
                    f"is_root: {str(node.node_id == root).lower()}",
                    "sql:",
                    node.sql.strip(),
                ]
            )
        )

    edge_ids: List[str] = []
    edge_indices: List[Tuple[int, int]] = []
    edge_texts: List[str] = []
    edge_cut_kinds: List[str] = []
    for edge in eligible_edges:
        edge_ids.append(edge.edge_id)
        edge_indices.append((node_id_to_index[edge.parent], node_id_to_index[edge.child]))
        edge_cut_kinds.append(edge.cut_kind)
        edge_texts.append(
            "\n".join(
                [
                    f"edge_id: {edge.edge_id}",
                    f"parent_node: {edge.parent}",
                    f"child_node: {edge.child}",
                    f"cut_kind: {edge.cut_kind}",
                    "cut_sql:",
                    edge.cut_sql.strip(),
                ]
            )
        )

    has_target = target_edge_ids is not None
    requested_targets = list(target_edge_ids or [])
    missing_targets = [edge_id for edge_id in requested_targets if edge_id not in set(edge_ids)]
    if missing_targets:
        raise ValueError(f"Sample {sample_id} contains unknown or ineligible target_edge_ids: {missing_targets}")

    return SQLCutSample(
        sample_id=sample_id,
        sql_text=sql_text,
        node_ids=[node.node_id for node in sorted_nodes],
        node_texts=node_texts,
        edge_ids=edge_ids,
        edge_indices=edge_indices,
        edge_texts=edge_texts,
        edge_cut_kinds=edge_cut_kinds,
        target_edge_ids=requested_targets,
        has_target=has_target,
    )


def save_samples_to_jsonl(samples: Iterable[SQLCutSample], output_path: str | Path) -> None:
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")


def load_samples_from_jsonl(path: str | Path) -> List[SQLCutSample]:
    out: List[SQLCutSample] = []
    with Path(path).expanduser().resolve().open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            payload = line.strip()
            if not payload:
                continue
            row = json.loads(payload)
            out.append(
                SQLCutSample(
                    sample_id=row["sample_id"],
                    sql_text=row["sql_text"],
                    node_ids=list(row["node_ids"]),
                    node_texts=list(row["node_texts"]),
                    edge_ids=list(row["edge_ids"]),
                    edge_indices=[tuple(pair) for pair in row["edge_indices"]],
                    edge_texts=list(row["edge_texts"]),
                    edge_cut_kinds=list(row["edge_cut_kinds"]),
                    target_edge_ids=list(row.get("target_edge_ids", [])),
                    has_target=bool(row.get("has_target", "target_edge_ids" in row)),
                )
            )
    if not out:
        raise ValueError(f"No samples found in: {path}")
    return out


class SQLCutDataset(Dataset[SQLCutSample]):
    def __init__(self, samples: Sequence[SQLCutSample]) -> None:
        self.samples = list(samples)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> SQLCutSample:
        return self.samples[idx]


def collate_sql_cut_samples(samples: Sequence[SQLCutSample]) -> Dict[str, Any]:
    if not samples:
        raise ValueError("Cannot collate an empty sample list.")

    max_edges = max(len(sample.edge_ids) for sample in samples)
    edge_mask = torch.zeros(len(samples), max_edges, dtype=torch.bool)
    target_sequence: Optional[torch.Tensor] = None

    has_targets = any(sample.has_target for sample in samples)
    if has_targets:
        max_target_len = max(len(sample.target_edge_ids) for sample in samples) + 1
        target_sequence = torch.full((len(samples), max_target_len), fill_value=-1, dtype=torch.long)

    batch_edge_id_to_pos: List[Dict[str, int]] = []
    for batch_idx, sample in enumerate(samples):
        edge_mask[batch_idx, : len(sample.edge_ids)] = True
        edge_to_pos = {edge_id: pos for pos, edge_id in enumerate(sample.edge_ids)}
        batch_edge_id_to_pos.append(edge_to_pos)
        if target_sequence is None or not sample.has_target:
            continue
        seq = [edge_to_pos[edge_id] for edge_id in sample.target_edge_ids]
        seq.append(max_edges)
        target_sequence[batch_idx, : len(seq)] = torch.tensor(seq, dtype=torch.long)

    return {
        "sample_ids": [sample.sample_id for sample in samples],
        "sql_texts": [sample.sql_text for sample in samples],
        "node_ids": [sample.node_ids for sample in samples],
        "node_texts": [sample.node_texts for sample in samples],
        "edge_ids": [sample.edge_ids for sample in samples],
        "edge_indices": [sample.edge_indices for sample in samples],
        "edge_texts": [sample.edge_texts for sample in samples],
        "edge_cut_kinds": [sample.edge_cut_kinds for sample in samples],
        "edge_mask": edge_mask,
        "target_sequence": target_sequence,
        "max_edges": max_edges,
        "edge_id_to_pos": batch_edge_id_to_pos,
    }
