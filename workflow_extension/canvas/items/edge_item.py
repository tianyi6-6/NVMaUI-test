"""工作流连线项

用于在工作流画布中表示节点之间的连接关系。
支持临时连线（拖拽时）和永久连线两种模式。
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem

from workflow_extension.canvas.items.node_item import WorkflowNodeItem


class WorkflowEdgeItem(QGraphicsPathItem):
    """工作流连线项
    
    在画布上绘制连接两个节点的贝塞尔曲线。
    临时连线使用虚线，永久连线使用实线。
    
    Attributes:
        src (WorkflowNodeItem): 源节点
        src_port (str): 源端口名称
        dst (WorkflowNodeItem): 目标节点
        dst_port (str): 目标端口名称
        temporary (bool): 是否为临时连线（拖拽中）
    """
    def __init__(self, src: WorkflowNodeItem, src_port: str, dst: WorkflowNodeItem, dst_port: str, temporary=False):
        """初始化连线项
        
        Args:
            src: 源节点
            src_port: 源端口名称
            dst: 目标节点
            dst_port: 目标端口名称
            temporary: 是否为临时连线（拖拽时使用虚线）
        """
        super().__init__()
        self.src = src
        self.src_port = src_port
        self.dst = dst
        self.dst_port = dst_port
        self.temporary = temporary
        # 临时连线的目标点为鼠标当前位置
        self._temp_dst = self.src.anchor(self.src_port, is_output=True) if temporary else None
        # 设置Z值为-1，确保连线在节点下方
        self.setZValue(-1)
        # 临时连线使用虚线，永久连线使用实线
        self.setPen(QPen(QColor("#4f92de"), 2, Qt.DashLine if temporary else Qt.SolidLine))
        self.refresh_path()

    def set_temp_target(self, point: QPointF):
        """设置临时连线的目标点
        
        用于拖拽过程中实时更新连线终点位置。
        
        Args:
            point: 鼠标在场景中的位置
        """
        self._temp_dst = point
        self.refresh_path()

    def refresh_path(self):
        """刷新连线路径
        
        使用三次贝塞尔曲线绘制平滑的连接线。
        控制点根据两点距离动态计算，确保曲线美观。
        """
        # 获取起点（源节点端口位置）
        p1 = self.src.anchor(self.src_port, is_output=True)
        # 获取终点（临时连线使用鼠标位置，永久连线使用目标端口位置）
        p2 = self._temp_dst if self.temporary else self.dst.anchor(self.dst_port, is_output=False)
        if p2 is None:
            p2 = p1
        # 计算贝塞尔曲线控制点，确保曲线平滑
        dx = max(60.0, abs(p2.x() - p1.x()) * 0.45)
        c1 = QPointF(p1.x() + dx, p1.y())  # 第一个控制点
        c2 = QPointF(p2.x() - dx, p2.y())  # 第二个控制点
        # 构建贝塞尔曲线路径
        path = QPainterPath(p1)
        path.cubicTo(c1, c2, p2)
        self.setPath(path)
        self.update()


