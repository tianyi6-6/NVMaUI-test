import base64
import json
from dataclasses import asdict
from pathlib import Path

from workflow_extension.models import WorkflowEdgeModel, WorkflowGraphModel, WorkflowNodeModel


_KEY = b"NVMAG_WORKFLOW_KEY"


def _xor_crypt(data: bytes) -> bytes:
    return bytes([b ^ _KEY[i % len(_KEY)] for i, b in enumerate(data)])


def save_workflow(graph: WorkflowGraphModel, file_path: str):
    raw = json.dumps(asdict(graph), ensure_ascii=False, indent=2).encode("utf-8")
    encrypted = base64.b64encode(_xor_crypt(raw))
    Path(file_path).write_bytes(encrypted)


def load_workflow(file_path: str) -> WorkflowGraphModel:
    encrypted = Path(file_path).read_bytes()
    raw = _xor_crypt(base64.b64decode(encrypted))
    payload = json.loads(raw.decode("utf-8"))
    graph = WorkflowGraphModel(version=payload.get("version", "1.0"), name=payload.get("name", "Untitled"))
    for n in payload.get("nodes", []):
        graph.nodes.append(
            WorkflowNodeModel(
                node_id=n["node_id"],
                node_type=n["node_type"],
                title=n["title"],
                position=tuple(n["position"]),
                params=n.get("params", {}),
            )
        )
    for e in payload.get("edges", []):
        graph.edges.append(
            WorkflowEdgeModel(
                from_node=e["from_node"],
                to_node=e["to_node"],
                from_port=e.get("from_port", "out"),
                to_port=e.get("to_port", "in"),
            )
        )
    return graph


def export_json(graph: WorkflowGraphModel, file_path: str):
    Path(file_path).write_text(json.dumps(asdict(graph), ensure_ascii=False, indent=2), encoding="utf-8")


def export_python(graph: WorkflowGraphModel, file_path: str):
    lines = [
        "# Auto-generated NVMagUI workflow script",
        "from pprint import pprint",
        "",
        "NODES = [",
    ]
    for node in graph.nodes:
        lines.append(
            f"    dict(id='{node.node_id}', type='{node.node_type}', title='{node.title}', params={repr(node.params)}),"
        )
    lines.extend(["]", "", "EDGES = ["])
    for edge in graph.edges:
        lines.append(f"    ('{edge.from_node}', '{edge.to_node}'),")
    lines.extend(["]", "", "print('Nodes:')", "pprint(NODES)", "print('Edges:')", "pprint(EDGES)"])
    Path(file_path).write_text("\n".join(lines), encoding="utf-8")
