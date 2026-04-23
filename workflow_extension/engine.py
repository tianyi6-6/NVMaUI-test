from collections import defaultdict, deque
from typing import Dict, List

from PySide6.QtCore import QCoreApplication, QObject, Signal


class WorkflowExecutor(QObject):
    node_started = Signal(str)
    node_finished = Signal(str, object)
    node_failed = Signal(str, str)
    run_finished = Signal()

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self, graph, context):
        self._stop_requested = False
        order = self._topological_order(graph)
        outputs: Dict[str, object] = {}
        incoming: Dict[str, List[str]] = defaultdict(list)
        for edge in graph.edges:
            incoming[edge.to_node].append(edge.from_node)

        for node in order:
            QCoreApplication.processEvents()
            if self._stop_requested:
                break
            self.node_started.emit(node.node_id)
            QCoreApplication.processEvents()
            try:
                spec = self.registry.get(node.node_type)
                node_inputs = [outputs[nid] for nid in incoming.get(node.node_id, []) if nid in outputs]
                result = spec.executor(context, node, node_inputs) if spec.executor else {}
                outputs[node.node_id] = result
                self.node_finished.emit(node.node_id, result)
                QCoreApplication.processEvents()
            except Exception as exc:
                self.node_failed.emit(node.node_id, str(exc))
                break
        self.run_finished.emit()

    @staticmethod
    def _topological_order(graph):
        indegree = defaultdict(int)
        edges = defaultdict(list)
        nodes_by_id = {node.node_id: node for node in graph.nodes}
        for edge in graph.edges:
            edges[edge.from_node].append(edge.to_node)
            indegree[edge.to_node] += 1
            indegree.setdefault(edge.from_node, 0)

        q = deque([nid for nid in nodes_by_id if indegree[nid] == 0])
        ordered = []
        while q:
            nid = q.popleft()
            ordered.append(nodes_by_id[nid])
            for nxt in edges[nid]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    q.append(nxt)

        if len(ordered) != len(graph.nodes):
            raise ValueError("工作流存在环路，无法执行。")
        return ordered
