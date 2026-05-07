from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem

from workflow_extension.canvas.items.node_item import WorkflowNodeItem


class WorkflowEdgeItem(QGraphicsPathItem):
    def __init__(self, src: WorkflowNodeItem, src_port: str, dst: WorkflowNodeItem, dst_port: str, temporary=False):
        super().__init__()
        self.src = src
        self.src_port = src_port
        self.dst = dst
        self.dst_port = dst_port
        self.temporary = temporary
        self._temp_dst = self.src.anchor(self.src_port, is_output=True) if temporary else None
        self.setZValue(-1)
        self.setPen(QPen(QColor("#4f92de"), 2, Qt.DashLine if temporary else Qt.SolidLine))
        self.refresh_path()

    def set_temp_target(self, point: QPointF):
        self._temp_dst = point
        self.refresh_path()

    def refresh_path(self):
        p1 = self.src.anchor(self.src_port, is_output=True)
        p2 = self._temp_dst if self.temporary else self.dst.anchor(self.dst_port, is_output=False)
        if p2 is None:
            p2 = p1
        dx = max(60.0, abs(p2.x() - p1.x()) * 0.45)
        c1 = QPointF(p1.x() + dx, p1.y())
        c2 = QPointF(p2.x() - dx, p2.y())
        path = QPainterPath(p1)
        path.cubicTo(c1, c2, p2)
        self.setPath(path)
        self.update()


