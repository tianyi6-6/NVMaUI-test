from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class WorkflowNodeModel:
    node_id: str
    node_type: str
    title: str
    position: Tuple[float, float]
    params: Dict[str, object] = field(default_factory=dict)


@dataclass
class WorkflowEdgeModel:
    from_node: str
    to_node: str
    from_port: str = "out"
    to_port: str = "in"


@dataclass
class WorkflowGraphModel:
    version: str = "1.0"
    name: str = "Untitled"
    nodes: List[WorkflowNodeModel] = field(default_factory=list)
    edges: List[WorkflowEdgeModel] = field(default_factory=list)
