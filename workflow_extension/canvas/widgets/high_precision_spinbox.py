"""高精度数值输入框

提供高精度的数值输入功能，避免Qt原生SpinBox的精度限制。
支持整数和浮点数，使用Decimal进行精确计算。
"""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget


def _node_helpers():
    """延迟导入节点辅助函数，避免循环依赖"""
    from workflow_extension.canvas.items.node_item import WorkflowNodeItem
    return WorkflowNodeItem


class HighPrecisionSpinBox(QWidget):
    """高精度数值输入框
    
    使用Decimal进行精确计算，避免Qt原生SpinBox的int32/float精度限制。
    支持键盘上下键调整数值，提供增减按钮。
    
    Signals:
        valueChanged (str): 数值变化时发出，参数为字符串形式的数值
    
    Attributes:
        _minimum (Decimal): 最小值
        _maximum (Decimal): 最大值
        _step (Decimal): 步长
        _integer (bool): 是否为整数模式
    """
    valueChanged = Signal(str)

    def __init__(self, value="0", minimum=None, maximum=None, step="1", integer=False, parent=None):
        """初始化高精度数值输入框
        
        Args:
            value: 初始值
            minimum: 最小值
            maximum: 最大值
            step: 步长
            integer: 是否为整数模式
            parent: 父控件
        """
        super().__init__(parent)
        self._minimum = self._to_decimal(minimum) if minimum is not None else None
        self._maximum = self._to_decimal(maximum) if maximum is not None else None
        self._step = self._to_decimal(step) if step is not None else Decimal("1")
        self._integer = bool(integer)

        # 创建水平布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 创建文本编辑框
        self._edit = QLineEdit(self._format_decimal_text(value))
        self._edit.installEventFilter(self)
        self._edit.editingFinished.connect(self._commit_text)
        layout.addWidget(self._edit, 1)

        # 创建增减按钮面板
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
        """获取当前文本值
        
        Returns:
            str: 当前文本
        """
        return self._edit.text()

    def setText(self, value):
        """设置文本值
        
        Args:
            value: 要设置的值
        """
        self._edit.setText(self._format_decimal_text(value))

    def eventFilter(self, obj, event):
        """事件过滤器，处理键盘事件
        
        支持上下键调整数值。
        
        Args:
            obj: 事件对象
            event: 事件
        
        Returns:
            bool: 是否拦截事件
        """
        if obj is self._edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                self.step_by(1)
                return True
            if event.key() == Qt.Key_Down:
                self.step_by(-1)
                return True
        return super().eventFilter(obj, event)

    def step_by(self, direction):
        """按步长调整数值
        
        Args:
            direction: 方向，1为增加，-1为减少
        """
        value = self._to_decimal(self._edit.text())
        value += self._step * Decimal(direction)
        if self._minimum is not None:
            value = max(self._minimum, value)
        if self._maximum is not None:
            value = min(self._maximum, value)
        self._edit.setText(self._format_decimal_text(value))
        self.valueChanged.emit(self._edit.text().strip())

    def _commit_text(self):
        """提交文本，验证并格式化数值"""
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
        """将值转换为Decimal
        
        Args:
            value: 要转换的值
        
        Returns:
            Decimal: 转换后的Decimal对象
        """
        text = _node_helpers()._extract_numeric_text(value, "0")
        try:
            return Decimal(text)
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _format_decimal_text(value):
        """格式化数值文本，去除末尾无意义的零
        
        Args:
            value: 要格式化的值
        
        Returns:
            str: 格式化后的字符串
        """
        return _node_helpers()._trim_decimal_zeros(_node_helpers()._extract_numeric_text(value, "0"))

