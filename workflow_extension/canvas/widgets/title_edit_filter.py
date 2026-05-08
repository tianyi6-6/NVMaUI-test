"""标题编辑框事件过滤器

用于处理节点标题编辑时的键盘事件。
支持Enter键完成编辑、Escape键取消编辑。
"""

from PySide6.QtCore import QObject, QEvent, Qt


class TitleEditEventFilter(QObject):
    """标题编辑框的事件过滤器
    
    拦截键盘事件以处理编辑完成和取消操作。
    
    Attributes:
        _edit_widget: 编辑框控件
        _node_item: 节点项
    """
    def __init__(self, edit_widget, node_item):
        """初始化事件过滤器
        
        Args:
            edit_widget: 编辑框控件
            node_item: 节点项
        """
        super().__init__()
        self._edit_widget = edit_widget
        self._node_item = node_item
    
    def eventFilter(self, obj, event):
        """事件过滤器处理函数
        
        Args:
            obj: 事件对象
            event: 事件
        
        Returns:
            bool: 是否拦截事件
        """
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

