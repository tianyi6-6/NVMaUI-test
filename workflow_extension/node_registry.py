from dataclasses import dataclass, field
from typing import Callable, Dict, List


@dataclass
class NodePortSpec:
    name: str
    data_type: str = "any"


@dataclass
class NodeParamSpec:
    key: str
    label: str
    editor: str = "text"  # text|int|float|select|bool
    options: List[str] = field(default_factory=list)
    minimum: float = 0.0
    maximum: float = 999999.0
    step: float = 1.0


@dataclass
class NodeSpec:
    node_type: str
    title: str
    category: str
    default_params: Dict[str, object] = field(default_factory=dict)
    input_ports: List[NodePortSpec] = field(default_factory=lambda: [NodePortSpec("in", "any")])
    output_ports: List[NodePortSpec] = field(default_factory=lambda: [NodePortSpec("out", "any")])
    param_specs: List[NodeParamSpec] = field(default_factory=list)
    executor: Callable = None


class NodeRegistry:
    def __init__(self):
        self._specs: Dict[str, NodeSpec] = {}

    def register(self, spec: NodeSpec):
        self._specs[spec.node_type] = spec

    def get(self, node_type: str) -> NodeSpec:
        return self._specs[node_type]

    def all_specs(self):
        return list(self._specs.values())

    def grouped(self):
        groups = {}
        for spec in self._specs.values():
            groups.setdefault(spec.category, []).append(spec)
        return groups
