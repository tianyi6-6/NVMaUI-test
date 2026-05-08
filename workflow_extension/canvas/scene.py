"""工作流画布场景

提供工作流画布的场景管理，包括节点、连线的添加、删除、移动等操作。
支持撤销/重做系统、节点连接、画布网格绘制等功能。
"""

import logging
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsScene

from workflow_extension.canvas.items.edge_item import WorkflowEdgeItem
from workflow_extension.canvas.items.node_item import WorkflowNodeItem
from workflow_extension.models import WorkflowEdgeModel, WorkflowGraphModel, WorkflowNodeModel
from workflow_extension.node_registry import NodeSpec
from workflow_extension.undo_system import WorkflowUndoStack, AddNodeCommand, DeleteNodesCommand, AddEdgeCommand, RemoveEdgeCommand, MoveNodesCommand


class WorkflowScene(QGraphicsScene):
    """工作流画布场景
    
    管理工作流画布中的所有节点和连线，提供以下功能：
    - 节点的添加、删除、移动
    - 连线的创建、删除、重连
    - 撤销/重做系统
    - 端口兼容性检查
    - 画布网格绘制
    
    Signals:
        node_selected (object): 节点被选中时发出
        graph_changed (): 图结构改变时发出
    """

    node_selected = Signal(object)
    graph_changed = Signal()

    def __init__(self, parent=None, enable_extended_node_ui=False):
        """初始化工作流场景
        
        Args:
            parent: 父对象
            enable_extended_node_ui: 是否启用扩展的节点UI（支持调整大小、编辑标题等）
        """
        super().__init__(parent)
        self.enable_extended_node_ui = bool(enable_extended_node_ui)
        # 设置背景颜色
        self.setBackgroundBrush(QColor("#22252b"))
        # 禁用索引以提高性能
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        # 节点字典：node_id -> WorkflowNodeItem
        self.node_items = {}
        # 连线列表：[(from_id, from_port, to_id, to_port, edge_item), ...]
        self.edges = []
        # 节点规范解析器函数
        self.spec_resolver = None
        # 参数变化回调函数
        self.on_node_param_changed = None
        # 连线拖拽状态
        self._drag_from = None  # (src_item, src_port)
        self._drag_edge = None  # 临时连线项
        self._armed_link_source = None  # 待连接的源节点
        # 线段拖拽相关状态（用于重连已有连线）
        self._dragging_existing_edge = False
        self._dragged_edge_info = None  # (edge_item, src_item, src_port, dst_item, dst_port, is_dragging_from_src)
        # 撤销/重做系统
        self.undo_stack = WorkflowUndoStack()
        self._node_move_start_positions = {}  # 节点移动开始位置：node_id -> (x, y)
        self._is_moving_nodes = False
        # 下拉菜单展开状态标志
        self._combo_box_opened = False
        self._active_combo_box = None
        # 移除场景矩形限制以启用无限画布
        # self.setSceneRect(-2000, -2000, 4000, 4000)

    def set_spec_resolver(self, resolver):
        """设置节点规范解析器
        
        Args:
            resolver: 根据节点类型返回NodeSpec的函数
        """
        self.spec_resolver = resolver

    def eventFilter(self, obj, event):
        """
        事件过滤器，用于检测QComboBox弹出列表的显示和隐藏
        """
        from PySide6.QtCore import QEvent
        # 检测QComboBox弹出列表的显示和隐藏
        if event.type() == QEvent.Show:
            class_name = obj.metaObject().className()
            # QComboBox的弹出列表通常是QListView
            if "QListView" in class_name or "QComboBox" in class_name:
                self._combo_box_opened = True
        elif event.type() == QEvent.Hide:
            class_name = obj.metaObject().className()
            if "QListView" in class_name or "QComboBox" in class_name:
                self._combo_box_opened = False
        return super().eventFilter(obj, event)

    def drawBackground(self, painter, rect):
        """绘制背景网格
        
        绘制浅色网格以辅助节点对齐和布局。
        小网格间距20px，大网格间距100px。
        
        Args:
            painter: 绘图器
            rect: 需要绘制的矩形区域
        """
        super().drawBackground(painter, rect)

        minor_step = 20  # 小网格间距
        major_step = 100  # 大网格间距

        # 计算网格线的起始位置
        left = int(rect.left()) - (int(rect.left()) % minor_step)
        top = int(rect.top()) - (int(rect.top()) % minor_step)

        minor_lines = []
        major_lines = []

        # 计算垂直线
        x = left
        while x < int(rect.right()):
            if x % major_step == 0:
                major_lines.append((x, int(rect.top()), x, int(rect.bottom())))
            else:
                minor_lines.append((x, int(rect.top()), x, int(rect.bottom())))
            x += minor_step

        # 计算水平线
        y = top
        while y < int(rect.bottom()):
            if y % major_step == 0:
                major_lines.append((int(rect.left()), y, int(rect.right()), y))
            else:
                minor_lines.append((int(rect.left()), y, int(rect.right()), y))
            y += minor_step

        # 绘制小网格线
        painter.save()
        painter.setPen(QPen(QColor("#2d323b"), 1))
        for x1, y1, x2, y2 in minor_lines:
            painter.drawLine(x1, y1, x2, y2)

        # 绘制大网格线
        painter.setPen(QPen(QColor("#39404d"), 1))
        for x1, y1, x2, y2 in major_lines:
            painter.drawLine(x1, y1, x2, y2)
        painter.restore()

    def add_node_with_undo(self, node_type, title, pos, params=None, node_id=None):
        """通过撤销系统添加节点
        
        Args:
            node_type: 节点类型
            title: 节点标题
            pos: 节点位置 (QPointF)
            params: 节点参数字典
            node_id: 节点ID，如果为None则自动生成
        
        Returns:
            创建的节点项
        """
        command = AddNodeCommand(node_type, title, pos, params, node_id)
        self.undo_stack.push_command(command, self)
        return command.created_node
    
    def add_node(self, node_type, title, pos, params=None, node_id=None):
        """添加节点到画布
        
        Args:
            node_type: 节点类型
            title: 节点标题
            pos: 节点位置 (QPointF)
            params: 节点参数字典
            node_id: 节点ID，如果为None则自动生成
        
        Returns:
            创建的节点项
        """
        node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"
        model = WorkflowNodeModel(
            node_id=node_id,
            node_type=node_type,
            title=title,
            position=(pos.x(), pos.y()),
            params=params or {},
        )
        spec = self.spec_resolver(node_type) if self.spec_resolver else NodeSpec(node_type=node_type, title=title, category="默认")
        item = WorkflowNodeItem(
            model,
            spec=spec,
            on_param_changed=self.on_node_param_changed,
            enable_extended_node_ui=self.enable_extended_node_ui,
        )
        self.addItem(item)
        self.node_items[node_id] = item
        self.graph_changed.emit()
        return item

    def mousePressEvent(self, event):
        """鼠标按下事件处理
        
        处理以下操作：
        1. 完成待连接的节点连线
        2. 开始拖拽已有连线的端点进行重连
        3. 从输出端口拖拽创建新连线
        4. 开始移动节点
        """
        if event.button() == Qt.LeftButton and self._armed_link_source is not None:
            # 完成待连接的节点连线
            target = self._find_port_hit(event.scenePos(), require_output=False)
            if target:
                dst_item, dst_port = target
                src_item, src_port = self._armed_link_source
                if src_item is not dst_item and self._is_port_compatible(src_item, src_port, dst_item, dst_port):
                    self._add_edge_with_undo(src_item, src_port, dst_item, dst_port)
            self._armed_link_source = None
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            # 首先检查是否点击了已存在线段的端点
            edge_info = self._find_edge_endpoint_hit(event.scenePos())
            if edge_info:
                self._start_drag_existing_edge(edge_info, event.scenePos())
                event.accept()
                return
            # 然后检查是否点击了输出端口（创建新连接）
            hit = self._find_port_hit(event.scenePos(), require_output=True)
            if hit:
                src_item, src_port = hit
                self._drag_from = (src_item, src_port)
                self._drag_edge = WorkflowEdgeItem(src_item, src_port, src_item, src_port, temporary=True)
                self.addItem(self._drag_edge)
                self._drag_edge.set_temp_target(event.scenePos())
                event.accept()
                return
            # 检查是否开始移动节点
            selected_items = [item for item in self.selectedItems() if isinstance(item, WorkflowNodeItem)]
            if selected_items:
                self._is_moving_nodes = True
                self._node_move_start_positions = {}
                for item in selected_items:
                    self._node_move_start_positions[item.model.node_id] = (item.pos().x(), item.pos().y())
        super().mousePressEvent(event)
        selected = self.selectedItems()
        if selected and isinstance(selected[0], WorkflowNodeItem):
            self.node_selected.emit(selected[0].model)

    def mouseMoveEvent(self, event):
        """鼠标移动事件处理
        
        在拖拽连线时更新临时连线的终点位置。
        """
        if self._drag_edge is not None:
            self._drag_edge.set_temp_target(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件处理
        
        完成以下操作：
        1. 完成连线拖拽并创建连接
        2. 完成已有连线的重连或删除
        3. 记录节点移动的撤销操作
        """
        if self._drag_edge is not None:
            if self._dragging_existing_edge and self._dragged_edge_info:
                # 处理已存在线段的拖拽释放
                self._finish_drag_existing_edge(event.scenePos())
                event.accept()
                return
            elif self._drag_from is not None:
                # 处理新创建线段的释放
                src_item, src_port = self._drag_from
                self.removeItem(self._drag_edge)
                self._drag_edge = None
                target = self._find_port_hit(event.scenePos(), require_output=False)
                self._drag_from = None
                if target:
                    dst_item, dst_port = target
                    if src_item is not dst_item and self._is_port_compatible(src_item, src_port, dst_item, dst_port):
                        self._add_edge_with_undo(src_item, src_port, dst_item, dst_port)
                event.accept()
                return
        
        # 处理节点移动的撤销
        if self._is_moving_nodes and self._node_move_start_positions:
            selected_items = [item for item in self.selectedItems() if isinstance(item, WorkflowNodeItem)]
            if selected_items:
                node_moves = []
                for item in selected_items:
                    node_id = item.model.node_id
                    if node_id in self._node_move_start_positions:
                        old_pos = self._node_move_start_positions[node_id]
                        new_pos = (item.pos().x(), item.pos().y())
                        # 只有位置真正改变时才记录
                        if old_pos != new_pos:
                            node_moves.append((node_id, old_pos, new_pos))
                
                if node_moves:
                    command = MoveNodesCommand(node_moves)
                    self.undo_stack.push_command(command, command)
        
        # 清理移动状态
        self._is_moving_nodes = False
        self._node_move_start_positions.clear()
        
        super().mouseReleaseEvent(event)

    def _find_port_hit(self, pos, require_output=None):
        """查找指定位置的端口
        
        Args:
            pos: 场景坐标位置
            require_output: 是否要求输出端口（None表示任意）
        
        Returns:
            (node_item, port_name) 或 None
        """
        for item in self.node_items.values():
            hit = item.port_at_scene_pos(pos, require_output=require_output)
            if hit:
                is_output, name = hit
                if require_output is None or require_output == is_output:
                    return item, name
        return None

    def _find_edge_endpoint_hit(self, scene_pos):
        """检查点击位置是否命中了已存在线段的端点
        
        Args:
            scene_pos: 场景坐标位置
        
        Returns:
            (edge_item, src_item, src_port, dst_item, dst_port, is_dragging_from_src) 或 None
            is_dragging_from_src 为 True 表示从输出端拖拽，False 表示从输入端拖拽
        """
        port_radius = 8  # 端点检测半径
        
        for edge_info in self.edges:
            from_id, from_port, to_id, to_port, edge_item = edge_info
            src_item = self.node_items.get(from_id)
            dst_item = self.node_items.get(to_id)
            
            if not src_item or not dst_item:
                continue
                
            # 检查输出端点
            src_anchor = src_item.anchor(from_port, is_output=True)
            if (scene_pos - src_anchor).manhattanLength() < port_radius:
                return (edge_item, src_item, from_port, dst_item, to_port, True)  # True表示从输出端拖拽
                
            # 检查输入端点
            dst_anchor = dst_item.anchor(to_port, is_output=False)
            if (scene_pos - dst_anchor).manhattanLength() < port_radius:
                return (edge_item, src_item, from_port, dst_item, to_port, False)  # False表示从输入端拖拽
                
        return None

    def _start_drag_existing_edge(self, edge_info, scene_pos):
        """开始拖拽已存在的线段
        
        Args:
            edge_info: 线段信息元组
            scene_pos: 鼠标场景坐标
        """
        edge_item, src_item, src_port, dst_item, dst_port, is_dragging_from_src = edge_info
        
        # 保存原始线段信息
        self._dragged_edge_info = edge_info
        self._dragging_existing_edge = True
        
        # 创建临时拖拽线段
        if is_dragging_from_src:
            # 从输出端拖拽，保持输入端不变
            self._drag_from = (dst_item, dst_port)  # 反向连接，输入作为源
            self._drag_edge = WorkflowEdgeItem(dst_item, dst_port, dst_item, dst_port, temporary=True)
        else:
            # 从输入端拖拽，保持输出端不变
            self._drag_from = (src_item, src_port)
            self._drag_edge = WorkflowEdgeItem(src_item, src_port, src_item, src_port, temporary=True)
            
        self.addItem(self._drag_edge)
        self._drag_edge.set_temp_target(scene_pos)
        
        # 隐藏原始线段（但不删除，以便可能恢复）
        edge_item.setVisible(False)
        
        logging.debug("[WorkflowCanvas] start dragging existing edge from %s", 
                     "output" if is_dragging_from_src else "input")

    def _finish_drag_existing_edge(self, scene_pos):
        """完成线段拖拽
        
        根据拖拽终点决定是重连连线、恢复原连线还是删除连线。
        
        Args:
            scene_pos: 鼠标释放时的场景坐标
        """
        if not self._dragged_edge_info:
            return
            
        edge_item, src_item, src_port, dst_item, dst_port, is_dragging_from_src = self._dragged_edge_info
        
        # 移除临时拖拽线段
        if self._drag_edge:
            self.removeItem(self._drag_edge)
            self._drag_edge = None
        self._drag_from = None
        
        # 检查新的连接目标
        new_target = None
        if is_dragging_from_src:
            # 从输出端拖拽，寻找新的输入端
            new_target = self._find_port_hit(scene_pos, require_output=False)
        else:
            # 从输入端拖拽，寻找新的输出端
            new_target = self._find_port_hit(scene_pos, require_output=True)
            
        if new_target:
            new_item, new_port = new_target
            
            # 检查兼容性和有效性
            if is_dragging_from_src:
                # 从输出端拖拽到新输入端
                if (new_item is not src_item and 
                    self._is_port_compatible(src_item, src_port, new_item, new_port)):
                    # 删除旧连接，创建新连接
                    self._remove_edge_with_undo(edge_item)
                    self._add_edge_with_undo(src_item, src_port, new_item, new_port)
                    logging.debug("[WorkflowCanvas] edge reconnected: %s.%s -> %s.%s", 
                                 src_item.model.node_id, src_port, new_item.model.node_id, new_port)
                else:
                    # 连接无效，恢复原始线段
                    edge_item.setVisible(True)
                    logging.debug("[WorkflowCanvas] edge reconnect cancelled, restored original")
            else:
                # 从输入端拖拽到新输出端
                if (new_item is not dst_item and 
                    self._is_port_compatible(new_item, new_port, dst_item, dst_port)):
                    # 删除旧连接，创建新连接
                    self._remove_edge_with_undo(edge_item)
                    self._add_edge_with_undo(new_item, new_port, dst_item, dst_port)
                    logging.debug("[WorkflowCanvas] edge reconnected: %s.%s -> %s.%s", 
                                 new_item.model.node_id, new_port, dst_item.model.node_id, dst_port)
                else:
                    # 连接无效，恢复原始线段
                    edge_item.setVisible(True)
                    logging.debug("[WorkflowCanvas] edge reconnect cancelled, restored original")
        else:
            # 没有连接到新端口，删除线段
            self._remove_edge_with_undo(edge_item)
            logging.debug("[WorkflowCanvas] edge deleted after drag with no connection")
            
        # 清理状态
        self._dragging_existing_edge = False
        self._dragged_edge_info = None

    def _remove_edge_with_undo(self, edge_item):
        """通过撤销系统删除连接
        
        Args:
            edge_item: 要删除的连线项
        """
        for edge_info in list(self.edges):
            if edge_info[4] == edge_item:
                from_id, from_port, to_id, to_port, _ = edge_info
                command = RemoveEdgeCommand(edge_info)
                self.undo_stack.push_command(command, self)
                src_item = self.node_items.get(from_id)
                dst_item = self.node_items.get(to_id)
                if src_item and dst_item:
                    logging.info("[Workflow] 已断开连接: %s.%s -> %s.%s", 
                                src_item.model.title, from_port, dst_item.model.title, to_port)
                break
    
    def _remove_edge(self, edge_item):
        """移除指定的线段（不使用撤销系统）
        
        Args:
            edge_item: 要移除的连线项
        """
        for edge_info in list(self.edges):
            if edge_info[4] == edge_item:
                self.edges.remove(edge_info)
                self.removeItem(edge_item)
                self.graph_changed.emit()
                break

    def find_node_at(self, pos):
        """查找指定位置的节点
        
        Args:
            pos: 场景坐标位置
        
        Returns:
            WorkflowNodeItem 或 None
        """
        for item in self.items(pos):
            if isinstance(item, WorkflowNodeItem):
                return item
        return None

    def is_interactive_hit(self, pos):
        """检查指定位置是否命中了可交互元素
        
        可交互元素包括：节点、端口、连线端点
        
        Args:
            pos: 场景坐标位置
        
        Returns:
            bool: 是否命中可交互元素
        """
        if self.find_node_at(pos) is not None:
            return True
        if self._find_port_hit(pos, require_output=None) is not None:
            return True
        if self._find_edge_endpoint_hit(pos) is not None:
            return True
        return False

    def begin_link_from_node(self, node_item):
        """从指定节点开始连线（用于键盘快捷键）
        
        Args:
            node_item: 源节点项
        
        Returns:
            bool: 是否成功启动连线
        """
        if not isinstance(node_item, WorkflowNodeItem):
            return False
        if not node_item.spec.output_ports:
            return False
        self._armed_link_source = (node_item, node_item.spec.output_ports[0].name)
        return True

    def has_active_drag_link(self):
        """检查是否有正在拖拽的连线
        
        Returns:
            bool: 是否有正在拖拽的连线
        """
        return self._drag_edge is not None and self._drag_from is not None

    def begin_drag_link_at(self, scene_pos):
        """在指定位置开始拖拽连线
        
        Args:
            scene_pos: 场景坐标位置
        
        Returns:
            bool: 是否成功开始拖拽
        """
        hit = self._find_port_hit(scene_pos, require_output=True)
        if not hit:
            return False
        src_item, src_port = hit
        logging.debug(
            "[WorkflowCanvas] begin drag: %s.%s", src_item.model.node_id, src_port
        )
        self._drag_from = (src_item, src_port)
        self._drag_edge = WorkflowEdgeItem(src_item, src_port, src_item, src_port, temporary=True)
        self.addItem(self._drag_edge)
        self._drag_edge.set_temp_target(scene_pos)
        return True

    def update_drag_link_to(self, scene_pos):
        """更新拖拽连线的终点位置
        
        Args:
            scene_pos: 新的场景坐标位置
        """
        if self._drag_edge is not None:
            self._drag_edge.set_temp_target(scene_pos)

    def finish_drag_link_at(self, scene_pos):
        """在指定位置完成拖拽连线
        
        Args:
            scene_pos: 场景坐标位置
        
        Returns:
            bool: 是否成功创建连接
        """
        if self._drag_edge is None or self._drag_from is None:
            return False
        src_item, src_port = self._drag_from
        self.removeItem(self._drag_edge)
        self._drag_edge = None
        self._drag_from = None
        target = self._find_port_hit(scene_pos, require_output=False)
        if not target:
            logging.debug("[WorkflowCanvas] finish drag cancelled: no input port hit")
            return False
        dst_item, dst_port = target
        if src_item is dst_item:
            logging.debug("[WorkflowCanvas] finish drag cancelled: same node")
            return False
        if not self._is_port_compatible(src_item, src_port, dst_item, dst_port):
            logging.debug(
                "[WorkflowCanvas] finish drag cancelled: incompatible %s.%s -> %s.%s",
                src_item.model.node_id,
                src_port,
                dst_item.model.node_id,
                dst_port,
            )
            return False
        self._add_edge(src_item, src_port, dst_item, dst_port)
        logging.info(
            "[Workflow] 已连接节点: %s.%s -> %s.%s",
            src_item.model.title,
            src_port,
            dst_item.model.title,
            dst_port,
        )
        return True

    @staticmethod
    def _port_type(spec: NodeSpec, port_name: str, output=True):
        """获取指定端口的数据类型
        
        Args:
            spec: 节点规范
            port_name: 端口名称
            output: 是否为输出端口
        
        Returns:
            str: 端口数据类型
        """
        ports = spec.output_ports if output else spec.input_ports
        for p in ports:
            if p.name == port_name:
                return p.data_type
        return "any"

    def _is_port_compatible(self, src_item, src_port, dst_item, dst_port):
        """检查两个端口是否兼容
        
        端口兼容性规则：
        - 相同数据类型可以连接
        - any 类型可以与任何类型连接
        
        Args:
            src_item: 源节点项
            src_port: 源端口名称
            dst_item: 目标节点项
            dst_port: 目标端口名称
        
        Returns:
            bool: 端口是否兼容
        """
        src_t = self._port_type(src_item.spec, src_port, output=True)
        dst_t = self._port_type(dst_item.spec, dst_port, output=False)
        return src_t == "any" or dst_t == "any" or src_t == dst_t

    def _add_edge_with_undo(self, src_item, src_port, dst_item, dst_port):
        """通过撤销系统添加连接
        
        Args:
            src_item: 源节点项
            src_port: 源端口名称
            dst_item: 目标节点项
            dst_port: 目标端口名称
        """
        command = AddEdgeCommand(src_item.model.node_id, src_port, dst_item.model.node_id, dst_port)
        self.undo_stack.push_command(command, self)
        logging.info("[Workflow] 已连接节点: %s.%s -> %s.%s", 
                    src_item.model.title, src_port, dst_item.model.title, dst_port)
    
    def _add_edge(self, src_item, src_port, dst_item, dst_port):
        """添加连接（不使用撤销系统）
        
        如果目标端口已有连接，会先删除旧连接。
        
        Args:
            src_item: 源节点项
            src_port: 源端口名称
            dst_item: 目标节点项
            dst_port: 目标端口名称
        """
        for edge in list(self.edges):
            if edge[2] == dst_item.model.node_id and edge[3] == dst_port:
                self.removeItem(edge[4])
                self.edges.remove(edge)
        edge_item = WorkflowEdgeItem(src_item, src_port, dst_item, dst_port)
        self.addItem(edge_item)
        self.edges.append((src_item.model.node_id, src_port, dst_item.model.node_id, dst_port, edge_item))
        self.graph_changed.emit()

    def update_edges_for_node(self, node_id):
        """更新指定节点相关的所有连线
        
        当节点移动时，需要刷新连接到该节点的所有连线路径。
        
        Args:
            node_id: 节点ID
        """
        for from_id, _, to_id, _, edge_item in self.edges:
            if from_id == node_id or to_id == node_id:
                edge_item.refresh_path()

    def delete_selected_with_undo(self):
        """通过撤销系统删除选中节点"""
        selected_items = [item for item in self.selectedItems() if isinstance(item, WorkflowNodeItem)]
        if selected_items:
            node_ids = [item.model.node_id for item in selected_items]
            node_titles = [item.model.title for item in selected_items]
            command = DeleteNodesCommand(node_ids)
            self.undo_stack.push_command(command, self)
            logging.info("[Workflow] 已删除节点: %s", ", ".join(node_titles))
    
    def delete_selected(self):
        """删除选中节点（不使用撤销系统）"""
        for it in self.selectedItems():
            if isinstance(it, WorkflowNodeItem):
                node_id = it.model.node_id
                for edge in list(self.edges):
                    if edge[0] == node_id or edge[2] == node_id:
                        self.removeItem(edge[4])
                        self.edges.remove(edge)
                self.removeItem(it)
                self.node_items.pop(node_id, None)
        self.graph_changed.emit()

    def clear_all(self):
        """清空画布中的所有节点和连线"""
        self.clear()
        self.node_items = {}
        self.edges = []
        self._drag_from = None
        self._drag_edge = None
        self._armed_link_source = None
        # 清除线段拖拽相关状态
        self._dragging_existing_edge = False
        self._dragged_edge_info = None
        self.graph_changed.emit()

    def build_graph(self):
        """构建工作流图模型
        
        将当前画布中的节点和连线序列化为 WorkflowGraphModel。
        
        Returns:
            WorkflowGraphModel: 工作流图模型
        """
        graph = WorkflowGraphModel()
        for item in self.node_items.values():
            item.model.position = (item.pos().x(), item.pos().y())
            graph.nodes.append(item.model)
        for from_id, from_port, to_id, to_port, _ in self.edges:
            graph.edges.append(
                WorkflowEdgeModel(from_node=from_id, to_node=to_id, from_port=from_port, to_port=to_port)
            )
        return graph

    def load_graph(self, graph: WorkflowGraphModel):
        """加载工作流图模型到画布
        
        从 WorkflowGraphModel 反序列化并创建节点和连线。
        
        Args:
            graph: 工作流图模型
        """
        self.clear_all()
        for node in graph.nodes:
            self.add_node(
                node_type=node.node_type,
                title=node.title,
                pos=QPointF(node.position[0], node.position[1]),
                params=dict(node.params),
                node_id=node.node_id,
            )
        for edge in graph.edges:
            src = self.node_items.get(edge.from_node)
            dst = self.node_items.get(edge.to_node)
            if not src or not dst:
                continue
            edge_item = WorkflowEdgeItem(src, edge.from_port, dst, edge.to_port)
            self.addItem(edge_item)
            self.edges.append((edge.from_node, edge.from_port, edge.to_node, edge.to_port, edge_item))
        self.graph_changed.emit()


