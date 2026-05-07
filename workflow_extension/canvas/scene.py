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
    node_selected = Signal(object)
    graph_changed = Signal()

    def __init__(self, parent=None, enable_extended_node_ui=False):
        super().__init__(parent)
        self.enable_extended_node_ui = bool(enable_extended_node_ui)
        self.setBackgroundBrush(QColor("#22252b"))
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.node_items = {}
        self.edges = []
        self.spec_resolver = None
        self.on_node_param_changed = None
        self._drag_from = None
        self._drag_edge = None
        self._armed_link_source = None
        # 新增：线段拖拽相关状态
        self._dragging_existing_edge = False
        self._dragged_edge_info = None  # (edge_item, src_item, src_port, dst_item, dst_port, is_dragging_from_src)
        # 新增：撤销/重做系统
        self.undo_stack = WorkflowUndoStack()
        self._node_move_start_positions = {}  # 节点移动开始位置
        self._is_moving_nodes = False
        # 新增：下拉菜单展开状态标志
        self._combo_box_opened = False
        self._active_combo_box = None
        # Remove scene rect limitation to enable infinite canvas
# self.setSceneRect(-2000, -2000, 4000, 4000)

    def set_spec_resolver(self, resolver):
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
        super().drawBackground(painter, rect)

        minor_step = 20
        major_step = 100

        left = int(rect.left()) - (int(rect.left()) % minor_step)
        top = int(rect.top()) - (int(rect.top()) % minor_step)

        minor_lines = []
        major_lines = []

        x = left
        while x < int(rect.right()):
            if x % major_step == 0:
                major_lines.append((x, int(rect.top()), x, int(rect.bottom())))
            else:
                minor_lines.append((x, int(rect.top()), x, int(rect.bottom())))
            x += minor_step

        y = top
        while y < int(rect.bottom()):
            if y % major_step == 0:
                major_lines.append((int(rect.left()), y, int(rect.right()), y))
            else:
                minor_lines.append((int(rect.left()), y, int(rect.right()), y))
            y += minor_step

        painter.save()
        painter.setPen(QPen(QColor("#2d323b"), 1))
        for x1, y1, x2, y2 in minor_lines:
            painter.drawLine(x1, y1, x2, y2)

        painter.setPen(QPen(QColor("#39404d"), 1))
        for x1, y1, x2, y2 in major_lines:
            painter.drawLine(x1, y1, x2, y2)
        painter.restore()

    def add_node_with_undo(self, node_type, title, pos, params=None, node_id=None):
        """通过撤销系统添加节点"""
        command = AddNodeCommand(node_type, title, pos, params, node_id)
        self.undo_stack.push_command(command, self)
        return command.created_node
    
    def add_node(self, node_type, title, pos, params=None, node_id=None):
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
        if event.button() == Qt.LeftButton and self._armed_link_source is not None:
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
        if self._drag_edge is not None:
            self._drag_edge.set_temp_target(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
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
                    self.undo_stack.push_command(command, self)
        
        # 清理移动状态
        self._is_moving_nodes = False
        self._node_move_start_positions.clear()
        
        super().mouseReleaseEvent(event)

    def _find_port_hit(self, pos, require_output=None):
        for item in self.node_items.values():
            hit = item.port_at_scene_pos(pos, require_output=require_output)
            if hit:
                is_output, name = hit
                if require_output is None or require_output == is_output:
                    return item, name
        return None

    def _find_edge_endpoint_hit(self, scene_pos):
        """检查点击位置是否命中了已存在线段的端点"""
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
        """开始拖拽已存在的线段"""
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
        """完成线段拖拽"""
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
        """通过撤销系统删除连接"""
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
        """移除指定的线段"""
        for edge_info in list(self.edges):
            if edge_info[4] == edge_item:
                self.edges.remove(edge_info)
                self.removeItem(edge_item)
                self.graph_changed.emit()
                break

    def find_node_at(self, pos):
        for item in self.items(pos):
            if isinstance(item, WorkflowNodeItem):
                return item
        return None

    def is_interactive_hit(self, pos):
        if self.find_node_at(pos) is not None:
            return True
        if self._find_port_hit(pos, require_output=None) is not None:
            return True
        if self._find_edge_endpoint_hit(pos) is not None:
            return True
        return False

    def begin_link_from_node(self, node_item):
        if not isinstance(node_item, WorkflowNodeItem):
            return False
        if not node_item.spec.output_ports:
            return False
        self._armed_link_source = (node_item, node_item.spec.output_ports[0].name)
        return True

    def has_active_drag_link(self):
        return self._drag_edge is not None and self._drag_from is not None

    def begin_drag_link_at(self, scene_pos):
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
        if self._drag_edge is not None:
            self._drag_edge.set_temp_target(scene_pos)

    def finish_drag_link_at(self, scene_pos):
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
        ports = spec.output_ports if output else spec.input_ports
        for p in ports:
            if p.name == port_name:
                return p.data_type
        return "any"

    def _is_port_compatible(self, src_item, src_port, dst_item, dst_port):
        src_t = self._port_type(src_item.spec, src_port, output=True)
        dst_t = self._port_type(dst_item.spec, dst_port, output=False)
        return src_t == "any" or dst_t == "any" or src_t == dst_t

    def _add_edge_with_undo(self, src_item, src_port, dst_item, dst_port):
        """通过撤销系统添加连接"""
        command = AddEdgeCommand(src_item.model.node_id, src_port, dst_item.model.node_id, dst_port)
        self.undo_stack.push_command(command, self)
        logging.info("[Workflow] 已连接节点: %s.%s -> %s.%s", 
                    src_item.model.title, src_port, dst_item.model.title, dst_port)
    
    def _add_edge(self, src_item, src_port, dst_item, dst_port):
        for edge in list(self.edges):
            if edge[2] == dst_item.model.node_id and edge[3] == dst_port:
                self.removeItem(edge[4])
                self.edges.remove(edge)
        edge_item = WorkflowEdgeItem(src_item, src_port, dst_item, dst_port)
        self.addItem(edge_item)
        self.edges.append((src_item.model.node_id, src_port, dst_item.model.node_id, dst_port, edge_item))
        self.graph_changed.emit()

    def update_edges_for_node(self, node_id):
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


