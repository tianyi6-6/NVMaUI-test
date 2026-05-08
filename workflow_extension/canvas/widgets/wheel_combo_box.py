"""滚轮下拉框

自定义的下拉框控件，支持通知场景下拉框的打开/关闭状态。
用于防止下拉框打开时触发画布的缩放操作。
"""

from PySide6.QtWidgets import QComboBox


class WheelComboBox(QComboBox):
    """滚轮下拉框
    
    继承自QComboBox，在下拉框打开/关闭时通知场景。
    这样可以防止在下拉框打开时意外触发画布的缩放操作。
    
    Attributes:
        _node_item: 关联的节点项
    """
    def __init__(self, node_item=None, parent=None):
        """初始化滚轮下拉框
        
        Args:
            node_item: 关联的节点项
            parent: 父控件
        """
        super().__init__(parent)
        self._node_item = node_item

    def _set_popup_opened(self, opened):
        """设置下拉框打开状态
        
        通知场景下拉框的打开/关闭状态，以便场景可以相应地处理事件。
        
        Args:
            opened: 是否打开
        """
        try:
            scene = self._node_item.scene() if self._node_item is not None else None
            if scene is not None:
                scene._combo_box_opened = opened
                scene._active_combo_box = self if opened else None
        except:
            pass

    def showPopup(self):
        """显示下拉框
        
        在显示前通知场景下拉框即将打开。
        """
        self._set_popup_opened(True)
        super().showPopup()

    def hidePopup(self):
        """隐藏下拉框
        
        在隐藏后通知场景下拉框已关闭。
        """
        super().hidePopup()
        self._set_popup_opened(False)

