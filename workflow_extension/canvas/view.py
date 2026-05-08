"""工作流画布视图

提供工作流画布的视图控件，支持无限画布、缩放、平移等交互功能。
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsView, QLabel

from workflow_extension.canvas.items.node_item import WorkflowNodeItem
from workflow_extension.canvas.scene import WorkflowScene


class WorkflowCanvasView(QGraphicsView):
    """工作流画布视图
    
    提供工作流画布的视图控件，支持以下功能：
    - 无限画布滚动
    - 鼠标拖拽平移
    - 滚轮缩放
    - 键盘快捷键（撤销、重做、删除）
    - 坐标和缩放比例显示
    """
    def __init__(self, scene: WorkflowScene, parent=None):
        """初始化画布视图
        
        Args:
            scene: 工作流场景对象
            parent: 父控件
        """
        super().__init__(scene, parent)
        # 启用抗锯齿渲染
        self.setRenderHint(QPainter.Antialiasing)
        # 设置拖拽模式为矩形选择
        self.setDragMode(QGraphicsView.RubberBandDrag)
        # 避免多个路径和代理控件更新时出现重影/拖尾
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheNone)
        self.setOptimizationFlag(QGraphicsView.DontSavePainterState, False)
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, False)
        # 平移相关状态
        self._is_panning = False
        self._pan_start = None
        self.setCursor(Qt.ArrowCursor)
        # 坐标和缩放比例显示标签
        self._overlay = QLabel(self.viewport())
        self._overlay.setStyleSheet(
            "QLabel { background: rgba(32, 36, 45, 180); color: #d8deea; padding: 3px 8px; border-radius: 8px; }"
        )
        self._overlay.move(10, 10)
        self._overlay.hide()
        # 自动隐藏显示标签的定时器
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.timeout.connect(self._overlay.hide)
        
        # 启用无限画布功能
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        
        # 设置初始大场景矩形，后续动态扩展
        scene.setSceneRect(-10000, -10000, 20000, 20000)
        
        # 启用键盘快捷键
        self.setFocusPolicy(Qt.StrongFocus)

    def _update_overlay(self, view_pos=None, force_show=False):
        """更新坐标和缩放比例显示标签
        
        Args:
            view_pos: 视图坐标，如果为None则使用当前鼠标位置
            force_show: 是否强制显示
        """
        if view_pos is None:
            view_pos = self.viewport().mapFromGlobal(self.cursor().pos())
        scene_pos = self.mapToScene(view_pos)
        scale_pct = int(round(self.transform().m11() * 100))
        self._overlay.setText(f"+ ({scene_pos.x():.1f}, {scene_pos.y():.1f})   {scale_pct}%")
        self._overlay.adjustSize()
        if force_show or self._is_panning:
            self._overlay.show()

    def mousePressEvent(self, event):
        """鼠标按下事件处理
        
        在空白区域按下左键时启动平移模式。
        """
        scene_pos = self.mapToScene(event.pos())
        over_interactive = self.scene().is_interactive_hit(scene_pos) if hasattr(self.scene(), "is_interactive_hit") else False
        # 在空白区域且未命中交互元素时启动平移
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
        """鼠标移动事件处理
        
        在平移模式下更新画布位置，否则更新坐标显示。
        """
        if self._is_panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            # 移动滚动条实现平移
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            
            # 根据需要扩展场景矩形以支持无限滚动
            self._ensure_infinite_canvas()
            
            self._update_overlay(event.pos(), force_show=True)
            event.accept()
            return
        if self._overlay.isVisible():
            self._update_overlay(event.pos(), force_show=True)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件处理
        
        结束平移模式并恢复光标。
        """
        if event.button() == Qt.LeftButton and self._is_panning:
            self._is_panning = False
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            self._overlay.hide()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _ensure_infinite_canvas(self):
        """动态扩展场景矩形以支持无限滚动
        
        当视口接近场景边界时，自动扩展场景矩形，
        确保用户可以无限滚动画布。
        """
        if not self.scene():
            return
            
        # 获取当前可见区域的场景坐标
        viewport_rect = self.viewport().rect()
        visible_scene_rect = self.mapToScene(viewport_rect).boundingRect()
        
        # 获取当前场景矩形
        current_rect = self.scene().sceneRect()
        
        # 扩展边距（超出可见区域多少时扩展）
        margin = 2000
        
        # 计算需要的扩展
        new_rect = current_rect
        
        if visible_scene_rect.left() < current_rect.left() + margin:
            new_rect.setLeft(visible_scene_rect.left() - margin)
        if visible_scene_rect.right() > current_rect.right() - margin:
            new_rect.setRight(visible_scene_rect.right() + margin)
        if visible_scene_rect.top() < current_rect.top() + margin:
            new_rect.setTop(visible_scene_rect.top() - margin)
        if visible_scene_rect.bottom() > current_rect.bottom() - margin:
            new_rect.setBottom(visible_scene_rect.bottom() + margin)
        
        # 如果需要扩展则应用
        if new_rect != current_rect:
            self.scene().setSceneRect(new_rect)

    def keyPressEvent(self, event):
        """处理键盘快捷键
        
        支持的快捷键：
        - Ctrl+Z: 撤销
        - Ctrl+Shift+Z 或 Ctrl+Y: 重做
        - Delete/Backspace: 删除选中节点
        """
        # 检查是否有节点正在编辑标题
        is_any_node_editing = False
        for item in self.scene().selectedItems():
            if isinstance(item, WorkflowNodeItem) and hasattr(item, '_is_editing_title') and item._is_editing_title:
                is_any_node_editing = True
                break
        
        # 检查scene的focusItem是否是节点或其子控件
        focus_item = self.scene().focusItem()
        is_focus_on_node = False
        if focus_item:
            # 检查focusItem是否是任何节点
            if isinstance(focus_item, WorkflowNodeItem):
                is_focus_on_node = True
            else:
                # 检查focusItem的父级链中是否有节点
                parent = focus_item.parentItem()
                while parent:
                    if isinstance(parent, WorkflowNodeItem):
                        is_focus_on_node = True
                        break
                    parent = parent.parentItem()
        
        # 如果有节点正在编辑标题或焦点在节点上，不处理删除键
        if (is_any_node_editing or is_focus_on_node) and (event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace):
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
            self.scene().delete_selected_with_undo()
            event.accept()
            return
        
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        """滚轮事件处理
        
        如果下拉菜单展开，则滚动下拉列表；
        否则进行画布缩放。
        """
        # 检查是否有下拉菜单展开
        active_combo = getattr(self.scene(), '_active_combo_box', None) if self.scene() else None
        try:
            if active_combo is not None and active_combo.view().isVisible():
                scrollbar = active_combo.view().verticalScrollBar()
                delta = event.angleDelta().y()
                step = scrollbar.singleStep() * 3
                scrollbar.setValue(scrollbar.value() - step if delta > 0 else scrollbar.value() + step)
                event.accept()
                return
        except:
            pass
        # 如果下拉菜单展开或有弹出窗口，阻止缩放
        if (self.scene() and getattr(self.scene(), '_combo_box_opened', False)) or QApplication.activePopupWidget() is not None:
            event.accept()
            return
        
        # 计算缩放因子
        factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        self.scale(factor, factor)
        self._update_overlay(event.position().toPoint(), force_show=True)
        self._overlay_timer.start(900)
        
        # 确保缩放时画布可以扩展
        self._ensure_infinite_canvas()
