from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from BQR.submodular_cut_validation.run_validation_cut_experiment import (  # noqa: E402
    ELIGIBLE_CUT_KINDS,
    EdgeInfo,
    NodeInfo,
    _collect_graph,
)
from syntax_tree import SubqueryFixer  # noqa: E402


def _edge_sort_key(edge_id: str) -> int:
    if edge_id.startswith("E") and edge_id[1:].isdigit():
        return int(edge_id[1:])
    if edge_id.isdigit():
        return int(edge_id)
    return 10**9


@dataclass(frozen=True)
class GraphExample:
    sql: str
    root_node: str
    node_infos: Dict[str, NodeInfo]
    edges: List[EdgeInfo]
    eligible_edges: List[EdgeInfo]

    @property
    def eligible_edge_ids(self) -> List[str]:
        return [edge.edge_id for edge in self.eligible_edges]

    @property
    def edge_by_id(self) -> Dict[str, EdgeInfo]:
        return {edge.edge_id: edge for edge in self.edges}


def build_graph_example(sql: str) -> GraphExample:
    fixer = SubqueryFixer()
    root_node, node_infos, edges = _collect_graph(sql, fixer)
    eligible_edges = sorted(
        [edge for edge in edges if edge.cut_kind in ELIGIBLE_CUT_KINDS],
        key=lambda edge: _edge_sort_key(edge.edge_id),
    )
    return GraphExample(
        sql=sql,
        root_node=root_node,
        node_infos=node_infos,
        edges=edges,
        eligible_edges=eligible_edges,
    )
