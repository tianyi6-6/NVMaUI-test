from PySide6.QtCore import QObject, QEvent, Qt


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

