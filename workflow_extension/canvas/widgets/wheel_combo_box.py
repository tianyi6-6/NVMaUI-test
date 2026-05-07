from PySide6.QtWidgets import QComboBox


class WheelComboBox(QComboBox):
    def __init__(self, node_item=None, parent=None):
        super().__init__(parent)
        self._node_item = node_item

    def _set_popup_opened(self, opened):
        try:
            scene = self._node_item.scene() if self._node_item is not None else None
            if scene is not None:
                scene._combo_box_opened = opened
                scene._active_combo_box = self if opened else None
        except:
            pass

    def showPopup(self):
        self._set_popup_opened(True)
        super().showPopup()

    def hidePopup(self):
        super().hidePopup()
        self._set_popup_opened(False)

