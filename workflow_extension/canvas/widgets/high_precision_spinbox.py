from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget


def _node_helpers():
    from workflow_extension.canvas.items.node_item import WorkflowNodeItem
    return WorkflowNodeItem


class HighPrecisionSpinBox(QWidget):
    valueChanged = Signal(str)

    def __init__(self, value="0", minimum=None, maximum=None, step="1", integer=False, parent=None):
        super().__init__(parent)
        self._minimum = self._to_decimal(minimum) if minimum is not None else None
        self._maximum = self._to_decimal(maximum) if maximum is not None else None
        self._step = self._to_decimal(step) if step is not None else Decimal("1")
        self._integer = bool(integer)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._edit = QLineEdit(self._format_decimal_text(value))
        self._edit.installEventFilter(self)
        self._edit.editingFinished.connect(self._commit_text)
        layout.addWidget(self._edit, 1)

        button_panel = QWidget()
        button_layout = QVBoxLayout(button_panel)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)

        self._up_button = QPushButton("▲")
        self._down_button = QPushButton("▼")
        for button in (self._up_button, self._down_button):
            button.setFixedSize(18, 11)
            button.setFocusPolicy(Qt.NoFocus)
            button.setStyleSheet("QPushButton { padding: 0px; font-size: 8px; }")
            button_layout.addWidget(button)

        layout.addWidget(button_panel)
        self._up_button.clicked.connect(lambda: self.step_by(1))
        self._down_button.clicked.connect(lambda: self.step_by(-1))

    def text(self):
        return self._edit.text()

    def setText(self, value):
        self._edit.setText(self._format_decimal_text(value))

    def eventFilter(self, obj, event):
        if obj is self._edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                self.step_by(1)
                return True
            if event.key() == Qt.Key_Down:
                self.step_by(-1)
                return True
        return super().eventFilter(obj, event)

    def step_by(self, direction):
        value = self._to_decimal(self._edit.text())
        value += self._step * Decimal(direction)
        if self._minimum is not None:
            value = max(self._minimum, value)
        if self._maximum is not None:
            value = min(self._maximum, value)
        self._edit.setText(self._format_decimal_text(value))
        self.valueChanged.emit(self._edit.text().strip())

    def _commit_text(self):
        text = self._edit.text().strip()
        if not text:
            text = "0"
        value = self._to_decimal(text)
        if self._minimum is not None:
            value = max(self._minimum, value)
        if self._maximum is not None:
            value = min(self._maximum, value)
        if self._integer:
            value = value.to_integral_value()
        committed = self._format_decimal_text(value)
        self._edit.setText(committed)
        self.valueChanged.emit(committed)

    @staticmethod
    def _to_decimal(value):
        text = _node_helpers()._extract_numeric_text(value, "0")
        try:
            return Decimal(text)
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _format_decimal_text(value):
        return _node_helpers()._trim_decimal_zeros(_node_helpers()._extract_numeric_text(value, "0"))

