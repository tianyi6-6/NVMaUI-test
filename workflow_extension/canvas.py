import uuid
import logging

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QTimer, QEvent, QObject
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsProxyWidget,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QLineEdit,
    QSpinBox,
    QWidget,
    QLabel,
    QStyle,
)

from workflow_extension.models import WorkflowEdgeModel, WorkflowGraphModel, WorkflowNodeModel
from workflow_extension.node_registry import NodeSpec
from workflow_extension.undo_system import WorkflowUndoStack, AddNodeCommand, DeleteNodesCommand, AddEdgeCommand, RemoveEdgeCommand, MoveNodesCommand


class TitleEditEventFilter(QObject):
    """标题编辑框的事件过滤器"""
    def __init__(self, edit_widget, node_item):
        super().__init__()
        self._edit_widget = edit_widget
        self._node_item = node_item
    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                # Enter键：完成编辑
                self._node_item._finish_edit_title()
                return True
            elif event.key() == Qt.Key_Escape:
                # Escape键：取消编辑
                self._node_item._cancel_edit_title()
                return True
            # 其他键（包括Backspace、Delete、方向键等）让QLineEdit正常处理
            # 不拦截，返回False让默认处理器处理
        
        return super().eventFilter(obj, event)


class WorkflowNodeItem(QGraphicsRectItem):
    def __init__(self, model: WorkflowNodeModel, spec: NodeSpec, on_param_changed=None):
        super().__init__(0, 0, 280, 180)
        self.model = model
        self.spec = spec
        self._on_param_changed = on_param_changed
        self.setPos(QPointF(model.position[0], model.position[1]))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setPen(QPen(QColor("#9a9a9a"), 1.2))
        self._header_h = 34
        self._port_radius = 5
        self._port_hit_padding = 8
        self._input_ports = {}
        self._output_ports = {}
        self._proxy = None
        # 新增：标题编辑相关
        self._title_edit_proxy = None
        self._title_edit_widget = None
        self._is_editing_title = False
        self._edit_event_filter = None  # 事件过滤器
        self._build_param_widget()
        self._rebuild_ports()

    def _build_param_widget(self):
        if self._proxy is not None:
            self.scene().removeItem(self._proxy)
            self._proxy = None
        card = QWidget()
        form = QFormLayout(card)
        form.setContentsMargins(8, 4, 8, 4)
        form.setSpacing(4)
        specs = self.spec.param_specs if self.spec else []
        for p in specs[:4]:
            current = self.model.params.get(p.key, "")
            if p.editor == "int":
                editor = QSpinBox()
                editor.setRange(int(p.minimum), int(p.maximum))
                editor.setSingleStep(int(max(1, p.step)))
                editor.setValue(int(current))
                editor.valueChanged.connect(lambda v, key=p.key: self._set_param_value(key, v))
            elif p.editor == "float":
                editor = QDoubleSpinBox()
                editor.setDecimals(6)
                editor.setRange(float(p.minimum), float(p.maximum))
                editor.setSingleStep(float(p.step))
                editor.setValue(float(current))
                editor.valueChanged.connect(lambda v, key=p.key: self._set_param_value(key, v))
            elif p.editor == "select":
                editor = QComboBox()
                editor.addItems([str(x) for x in p.options])
                idx = editor.findText(str(current))
                editor.setCurrentIndex(max(idx, 0))
                editor.currentTextChanged.connect(lambda v, key=p.key: self._set_param_value(key, v))
            elif p.editor == "bool":
                editor = QCheckBox()
                editor.setChecked(bool(current))
                editor.toggled.connect(lambda v, key=p.key: self._set_param_value(key, v))
            else:
                editor = QLineEdit(str(current))
                editor.editingFinished.connect(
                    lambda e=editor, key=p.key: self._set_param_value(key, e.text().strip())
                )
            form.addRow(p.label, editor)
        self._proxy = QGraphicsProxyWidget(self)
        self._proxy.setWidget(card)
        self._proxy.setPos(6, self._header_h + 26)
        self._proxy.setZValue(2)
        target_h = max(130, self._header_h + 36 + card.sizeHint().height())
        self.setRect(0, 0, 280, target_h)

    def _set_param_value(self, key, value):
        self.model.params[key] = value
        if self._on_param_changed:
            self._on_param_changed(self.model)

    def _status_color(self):
        brush = self.brush()
        if brush.style() != Qt.NoBrush:
            return brush.color()
        return QColor("#de6d1f")

    def _rebuild_ports(self):
        self._input_ports = {}
        self._output_ports = {}
        left_base = self._header_h + 16
        right_base = self._header_h + 16
        for i, p in enumerate(self.spec.input_ports):
            self._input_ports[p.name] = QPointF(6, left_base + i * 22)
        for i, p in enumerate(self.spec.output_ports):
            self._output_ports[p.name] = QPointF(self.rect().width() - 6, right_base + i * 22)

    def anchor(self, port_name, is_output):
        port_map = self._output_ports if is_output else self._input_ports
        pos = port_map.get(port_name)
        if pos is None:
            pos = (
                QPointF(self.rect().width() - 6, self._header_h + 18)
                if is_output
                else QPointF(6, self._header_h + 18)
            )
        return self.mapToScene(pos)

    def port_at_scene_pos(self, scene_pos, require_output=None):
        local = self.mapFromScene(scene_pos)
        check = []
        if require_output is None or require_output is False:
            check.extend([(False, name, pos) for name, pos in self._input_ports.items()])
        if require_output is None or require_output is True:
            check.extend([(True, name, pos) for name, pos in self._output_ports.items()])
        for is_output, name, pos in check:
            area = QRectF(
                pos.x() - self._port_radius - self._port_hit_padding,
                pos.y() - self._port_radius - self._port_hit_padding,
                (self._port_radius + self._port_hit_padding) * 2,
                (self._port_radius + self._port_hit_padding) * 2,
            )
            if area.contains(local):
                return is_output, name
        return None

    def mouseDoubleClickEvent(self, event):
        """双击事件：开始编辑节点标题"""
        if event.button() == Qt.LeftButton:
            # 检查是否点击在标题区域
            header_rect = self.rect().adjusted(0, 0, 0, -(self.rect().height() - self._header_h))
            if header_rect.contains(event.pos()):
                self._start_edit_title()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)
    
    def _start_edit_title(self):
        """开始编辑节点标题"""
        if self._is_editing_title:
            return
        
        self._is_editing_title = True
        
        # 创建编辑框
        self._title_edit_widget = QLineEdit(self.model.title)
        self._title_edit_widget.setStyleSheet("""
            QLineEdit {
                background-color: #f0f0f0;
                border: 2px solid #4A90E2;
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 12px;
                font-weight: bold;
            }
        """)
        
        # 创建事件过滤器来处理键盘事件
        self._edit_event_filter = TitleEditEventFilter(self._title_edit_widget, self)
        self._title_edit_widget.installEventFilter(self._edit_event_filter)
        
        # 创建代理组件
        self._title_edit_proxy = QGraphicsProxyWidget(self)
        self._title_edit_proxy.setWidget(self._title_edit_widget)
        
        # 设置位置和大小
        header_rect = self.rect().adjusted(0, 0, 0, -(self.rect().height() - self._header_h))
        edit_rect = header_rect.adjusted(28, 6, -16, -6)
        self._title_edit_proxy.setPos(edit_rect.topLeft())
        self._title_edit_proxy.resize(edit_rect.width(), edit_rect.height())
        self._title_edit_proxy.setZValue(10)  # 确保在最上层
        
        # 设置焦点和选中
        QTimer.singleShot(0, self._set_edit_focus)
        
        self.update()
    
    def _set_edit_focus(self):
        """设置编辑框焦点和选中"""
        if self._title_edit_widget:
            self._title_edit_widget.setFocus()
            self._title_edit_widget.selectAll()
    
    def _finish_edit_title(self):
        """完成编辑节点标题"""
        if not self._is_editing_title or not self._title_edit_widget:
            return
        
        new_title = self._title_edit_widget.text().strip()
        if new_title and new_title != self.model.title:
            old_title = self.model.title
            self.model.title = new_title
            
            # 通知参数变化
            if self._on_param_changed:
                self._on_param_changed(self.model)
            
            # 如果有场景，通知场景图发生变化
            if self.scene():
                self.scene().graph_changed.emit()
        
        # 清理编辑组件
        self._cleanup_title_edit()
        
        self.update()
    
    def _cancel_edit_title(self):
        """取消编辑节点标题"""
        if not self._is_editing_title:
            return
        
        # 清理编辑组件，不保存更改
        self._cleanup_title_edit()
        
        self.update()
    
    def _cleanup_title_edit(self):
        """清理标题编辑组件"""
        self._is_editing_title = False
        
        if self._title_edit_proxy:
            # 移除事件过滤器
            if self._edit_event_filter:
                self._title_edit_widget.removeEventFilter(self._edit_event_filter)
                self._edit_event_filter = None
            
            if self.scene():
                self.scene().removeItem(self._title_edit_proxy)
            self._title_edit_proxy = None
            self._title_edit_widget = None
    
    def keyPressEvent(self, event):
        """处理键盘事件：Escape取消"""
        if self._is_editing_title and self._title_edit_widget:
            if event.key() == Qt.Key_Escape:
                self._cancel_edit_title()
                event.accept()
                return
        
        super().keyPressEvent(event)
    
    def focusOutEvent(self, event):
        """失去焦点时自动完成编辑"""
        if self._is_editing_title:
            # 立即处理，避免延迟导致的问题
            self._finish_edit_title()
        super().focusOutEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().update_edges_for_node(self.model.node_id)
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        body_rect = self.rect()
        header_rect = body_rect.adjusted(0, 0, 0, -(body_rect.height() - self._header_h))
        radius = 10

        # ComfyUI风格：选中时绘制高亮边框
        if option.state & QStyle.State_Selected:
            # 绘制选中高亮边框（蓝色，稍微粗一点）
            highlight_pen = QPen(QColor("#4A90E2"), 3.0)
            highlight_pen.setCosmetic(True)  # 确保线宽不受缩放影响
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(body_rect.adjusted(-1, -1, 1, 1), radius, radius)

        painter.setPen(QPen(QColor("#7c7c7c"), 1.0))
        painter.setBrush(QBrush(QColor("#f2f2f2")))
        painter.drawRoundedRect(body_rect, radius, radius)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#e8d4c2")))
        painter.drawRoundedRect(header_rect, radius, radius)
        painter.drawRect(0, self._header_h - radius, body_rect.width(), radius)

        painter.setPen(QPen(QColor("#303030")))
        # 如果正在编辑标题，不显示静态标题
        if not self._is_editing_title:
            painter.drawText(header_rect.adjusted(28, 8, -12, -8), Qt.AlignLeft | Qt.AlignVCenter, self.model.title)

        painter.setPen(QPen(QColor("#9e9e9e")))
        painter.drawLine(12, self._header_h + 20, body_rect.width() - 12, self._header_h + 20)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._status_color()))
        painter.drawEllipse(QPointF(14, 17), 5, 5)
        painter.setBrush(QBrush(QColor("#17b34a")))
        painter.drawEllipse(QPointF(body_rect.width() - 14, 17), 4, 4)

        # 移除英文node_type显示，只保留中文标题
        # painter.setPen(QPen(QColor("#6f6f6f")))
        # painter.drawText(body_rect.adjusted(10, self._header_h + 2, -10, -10), Qt.AlignLeft | Qt.AlignTop, self.model.node_type)

        painter.setPen(QPen(QColor("#8f8f8f")))
        painter.setBrush(QBrush(QColor("#4d8fdf")))
        for name, pos in self._input_ports.items():
            painter.drawEllipse(pos, self._port_radius, self._port_radius)
            # 移除英文端口名称显示
            # painter.drawText(pos + QPointF(8, 4), name)
        for name, pos in self._output_ports.items():
            painter.drawEllipse(pos, self._port_radius, self._port_radius)
            # 移除英文端口名称显示
            # txt_w = min(90, painter.fontMetrics().horizontalAdvance(name))
            # painter.drawText(pos + QPointF(-(txt_w + 10), 4), name)


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


class WorkflowScene(QGraphicsScene):
    node_selected = Signal(object)
    graph_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
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
        # Remove scene rect limitation to enable infinite canvas
# self.setSceneRect(-2000, -2000, 4000, 4000)

    def set_spec_resolver(self, resolver):
        self.spec_resolver = resolver

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
        item = WorkflowNodeItem(model, spec=spec, on_param_changed=self.on_node_param_changed)
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
            logging.debug("[WorkflowCanvas] begin_drag_link_at miss output port at (%.1f, %.1f)", scene_pos.x(), scene_pos.y())
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
        logging.debug(
            "[WorkflowCanvas] finish drag success: %s.%s -> %s.%s",
            src_item.model.node_id,
            src_port,
            dst_item.model.node_id,
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
            command = DeleteNodesCommand(node_ids)
            self.undo_stack.push_command(command, self)
    
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


class WorkflowCanvasView(QGraphicsView):
    def __init__(self, scene: WorkflowScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        # Avoid ghosting/trails when many paths and proxy widgets update together.
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheNone)
        self.setOptimizationFlag(QGraphicsView.DontSavePainterState, False)
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, False)
        self._is_panning = False
        self._pan_start = None
        self.setCursor(Qt.ArrowCursor)
        self._overlay = QLabel(self.viewport())
        self._overlay.setStyleSheet(
            "QLabel { background: rgba(32, 36, 45, 180); color: #d8deea; padding: 3px 8px; border-radius: 8px; }"
        )
        self._overlay.move(10, 10)
        self._overlay.hide()
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.timeout.connect(self._overlay.hide)
        
        # Enable infinite canvas functionality
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        
        # Set initial large scene rect that will expand dynamically
        scene.setSceneRect(-10000, -10000, 20000, 20000)
        
        # 启用键盘快捷键
        self.setFocusPolicy(Qt.StrongFocus)

    def _update_overlay(self, view_pos=None, force_show=False):
        if view_pos is None:
            view_pos = self.viewport().mapFromGlobal(self.cursor().pos())
        scene_pos = self.mapToScene(view_pos)
        scale_pct = int(round(self.transform().m11() * 100))
        self._overlay.setText(f"+ ({scene_pos.x():.1f}, {scene_pos.y():.1f})   {scale_pct}%")
        self._overlay.adjustSize()
        if force_show or self._is_panning:
            self._overlay.show()

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        over_interactive = self.scene().is_interactive_hit(scene_pos) if hasattr(self.scene(), "is_interactive_hit") else False
        if event.button() == Qt.LeftButton and hasattr(self.scene(), "begin_drag_link_at"):
            if self.scene().begin_drag_link_at(scene_pos):
                self.setCursor(Qt.CrossCursor)
                event.accept()
                return
        if event.button() == Qt.LeftButton and (self.itemAt(event.pos()) is None) and not over_interactive:
            self._is_panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            self._overlay_timer.stop()
            self._update_overlay(event.pos(), force_show=True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self.scene(), "has_active_drag_link") and self.scene().has_active_drag_link():
            self.scene().update_drag_link_to(self.mapToScene(event.pos()))
            event.accept()
            return
        if self._is_panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            
            # Expand scene rect if needed for infinite scrolling
            self._ensure_infinite_canvas()
            
            self._update_overlay(event.pos(), force_show=True)
            event.accept()
            return
        if self._overlay.isVisible():
            self._update_overlay(event.pos(), force_show=True)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and hasattr(self.scene(), "has_active_drag_link") and self.scene().has_active_drag_link():
            self.scene().finish_drag_link_at(self.mapToScene(event.pos()))
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._is_panning:
            self._is_panning = False
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            self._overlay.hide()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _ensure_infinite_canvas(self):
        """Dynamically expand scene rect to enable infinite scrolling"""
        if not self.scene():
            return
            
        # Get current visible area in scene coordinates
        viewport_rect = self.viewport().rect()
        visible_scene_rect = self.mapToScene(viewport_rect).boundingRect()
        
        # Get current scene rect
        current_rect = self.scene().sceneRect()
        
        # Expansion margin (how much to expand beyond visible area)
        margin = 2000
        
        # Calculate needed expansion
        new_rect = current_rect
        
        if visible_scene_rect.left() < current_rect.left() + margin:
            new_rect.setLeft(visible_scene_rect.left() - margin)
        if visible_scene_rect.right() > current_rect.right() - margin:
            new_rect.setRight(visible_scene_rect.right() + margin)
        if visible_scene_rect.top() < current_rect.top() + margin:
            new_rect.setTop(visible_scene_rect.top() - margin)
        if visible_scene_rect.bottom() > current_rect.bottom() - margin:
            new_rect.setBottom(visible_scene_rect.bottom() + margin)
        
        # Apply expansion if needed
        if new_rect != current_rect:
            self.scene().setSceneRect(new_rect)

    def keyPressEvent(self, event):
        """处理键盘快捷键"""
        # 检查是否有节点正在编辑标题
        is_any_node_editing = False
        for item in self.scene().selectedItems():
            if isinstance(item, WorkflowNodeItem) and hasattr(item, '_is_editing_title') and item._is_editing_title:
                is_any_node_editing = True
                break
        
        # 如果有节点正在编辑，不处理删除键
        if is_any_node_editing and (event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace):
            # 让编辑框处理这些键
            super().keyPressEvent(event)
            return
        
        # 撤销/重做快捷键
        if event.key() == Qt.Key_Z and event.modifiers() == Qt.ControlModifier:
            # Ctrl+Z - 撤销
            if self.scene().undo_stack.can_undo():
                self.scene().undo_stack.undo(self.scene())
            event.accept()
            return
        elif (event.key() == Qt.Key_Z and 
              event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)):
            # Ctrl+Shift+Z - 重做
            if self.scene().undo_stack.can_redo():
                self.scene().undo_stack.redo(self.scene())
            event.accept()
            return
        elif event.key() == Qt.Key_Y and event.modifiers() == Qt.ControlModifier:
            # Ctrl+Y - 重做（另一种常见快捷键）
            if self.scene().undo_stack.can_redo():
                self.scene().undo_stack.redo(self.scene())
            event.accept()
            return
        elif event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            # Delete/Backspace - 删除选中节点（仅在非编辑状态下）
            if self.scene().selectedItems():
                self.scene().delete_selected_with_undo()
                event.accept()
            return
        
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        self.scale(factor, factor)
        self._update_overlay(event.position().toPoint(), force_show=True)
        self._overlay_timer.start(900)
        
        # Ensure canvas can expand during zoom
        self._ensure_infinite_canvas()
