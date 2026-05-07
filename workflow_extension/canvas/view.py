from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsView, QLabel

from workflow_extension.canvas.items.node_item import WorkflowNodeItem
from workflow_extension.canvas.scene import WorkflowScene


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
        if (self.scene() and getattr(self.scene(), '_combo_box_opened', False)) or QApplication.activePopupWidget() is not None:
            event.accept()
            return
        
        factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        self.scale(factor, factor)
        self._update_overlay(event.position().toPoint(), force_show=True)
        self._overlay_timer.start(900)
        
        # Ensure canvas can expand during zoom
        self._ensure_infinite_canvas()
