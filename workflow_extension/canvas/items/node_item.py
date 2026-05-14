"""工作流节点项

提供工作流画布中节点的可视化表示，支持参数编辑、端口连接、大小调整等功能。
"""

import os
import re
from decimal import Decimal, InvalidOperation
from functools import partial

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsProxyWidget,
    QGraphicsRectItem,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from workflow_extension.models import WorkflowNodeModel
from workflow_extension.node_registry import NodeSpec
from workflow_extension.canvas.widgets.high_precision_spinbox import HighPrecisionSpinBox
from workflow_extension.canvas.widgets.title_edit_filter import TitleEditEventFilter
from workflow_extension.canvas.widgets.wheel_combo_box import WheelComboBox


class WorkflowNodeItem(QGraphicsRectItem):
    """工作流节点项
    
    在画布上表示一个工作流节点，包含以下功能：
    - 显示节点标题和参数
    - 输入/输出端口
    - 参数编辑（支持多种类型：文本、整数、浮点数、布尔、下拉选择）
    - 设备参数的特殊展示（当前值/范围/设置值）
    - 节点大小调整（扩展模式）
    - 标题编辑（扩展模式）
    - 参数分组显示（扩展模式）
    
    Attributes:
        model (WorkflowNodeModel): 节点数据模型
        spec (NodeSpec): 节点规范
        _enable_extended_node_ui (bool): 是否启用扩展UI功能
    """
    def __init__(self, model: WorkflowNodeModel, spec: NodeSpec, on_param_changed=None, enable_extended_node_ui=False):
        """初始化节点项
        
        Args:
            model: 节点数据模型
            spec: 节点规范
            on_param_changed: 参数变化回调函数
            enable_extended_node_ui: 是否启用扩展UI功能（调整大小、编辑标题等）
        """
        super().__init__(0, 0, 280, 180)
        self.model = model
        self.spec = spec
        self._on_param_changed = on_param_changed
        self._enable_extended_node_ui = bool(enable_extended_node_ui)
        # 设置节点位置
        self.setPos(QPointF(model.position[0], model.position[1]))
        # 设置节点可移动、可选中
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # 设置边框样式
        self.setPen(QPen(QColor("#9a9a9a"), 1.2))
        # 布局相关参数
        self._header_h = 34  # 标题栏高度
        self._port_radius = 5  # 端点半径
        self._port_hit_padding = 8  # 端口点击区域内边距
        # 端口位置字典
        self._input_ports = {}
        self._output_ports = {}
        # 参数控件代理
        self._proxy = None
        # 参数编辑器字典：key -> widget
        self._param_editors = {}
        self.params_store = dict(model.params)
        self.param_widgets = {}
        self.is_expanded = False
        self._collapse_btn_rect = QRectF()
        self._pending_specs = None
        self._min_node_width = 260
        self._min_node_height = 130
        self._max_node_width = 920
        self._max_node_height = 2000
        # 调整大小相关
        self._resize_handle_size = 14
        self._is_resizing = False
        self._resize_start_scene_pos = None
        self._resize_start_size = (280, 180)
        self._user_resized = bool(self.model.params.get("__node_user_resized__", False)) and self._enable_extended_node_ui
        # 标题编辑相关
        self._title_edit_proxy = None
        self._title_edit_widget = None
        self._is_editing_title = False
        self._edit_event_filter = None  # 事件过滤器
        # 启用悬停事件（用于调整大小光标）
        self.setAcceptHoverEvents(self._enable_extended_node_ui)
        self.setRect(0, 0, 280, self._header_h + 10)
        if self._enable_extended_node_ui:
            saved_size = self.model.params.get("__node_size__")
            if isinstance(saved_size, (list, tuple)) and len(saved_size) == 2:
                try:
                    self._apply_node_size(float(saved_size[0]), float(saved_size[1]), user_resized=True)
                    self._user_resized = True
                except (TypeError, ValueError):
                    pass
        self._rebuild_ports()

    def _build_param_widget(self):
        """构建参数控件
        
        根据节点规范创建参数编辑控件。
        扩展模式下支持参数分组显示，非扩展模式下只显示前4个参数。
        """
        if self._proxy is not None:
            scene = self.scene()
            if scene is not None:
                scene.removeItem(self._proxy)
            self._proxy = None
        card = QWidget()
        specs = self.spec.param_specs if self.spec else []
        
        if self._enable_extended_node_ui:
            # 检查是否有参数设置了 category
            has_category = any(p.category for p in specs)
            
            main_layout = QVBoxLayout(card)
            main_layout.setContentsMargins(8, 4, 8, 4)
            main_layout.setSpacing(6)
            
            if has_category:
                # 按层级分组参数（一级分类 -> 二级分类 -> 参数项）
                categories = {}
                for p in specs:
                    category = p.category or "未分类"
                    subcategory = p.subcategory or "默认项"
                    if category not in categories:
                        categories[category] = {}
                    if subcategory not in categories[category]:
                        categories[category][subcategory] = []
                    categories[category][subcategory].append(p)
                
                for category_name, subgroups in categories.items():
                    group = QGroupBox(category_name)
                    group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #ccc; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
                    group_layout = QVBoxLayout()
                    selector_row = QHBoxLayout()
                    is_device_init_node = self.model.node_type == "device.connect"
                    selector_label = QLabel("实验参数" if is_device_init_node else "二级分类")
                    selector = WheelComboBox(self)
                    subcategory_names = list(subgroups.keys())
                    selector.addItems(subcategory_names)
                    selector_row.addWidget(selector_label)
                    selector_row.addWidget(selector)
                    group_layout.addLayout(selector_row)

                    sub_params_container = QWidget()
                    sub_params_layout = QFormLayout(sub_params_container)
                    sub_params_layout.setContentsMargins(0, 0, 0, 0)
                    sub_params_layout.setSpacing(4)
                    group_layout.addWidget(sub_params_container)

                    selected_key = (
                        f"__selected_experiment_param__::{category_name}"
                        if is_device_init_node
                        else f"__selected_subcategory__::{category_name}"
                    )
                    legacy_key = f"__selected_subcategory__::{category_name}"
                    saved_subcategory = str(self.params_store.get(selected_key, self.params_store.get(legacy_key, "")))
                    default_subcategory = saved_subcategory if saved_subcategory in subcategory_names else subcategory_names[0]
                    selector.setCurrentText(default_subcategory)
                    self.model.params[selected_key] = default_subcategory

                    self._fill_subcategory_form(
                        sub_params_layout,
                        subgroups.get(default_subcategory, []),
                    )
                    selector.currentTextChanged.connect(
                        partial(
                            self._on_subcategory_changed,
                            selected_key,
                            subgroups,
                            sub_params_layout,
                        )
                    )

                    group.setLayout(group_layout)
                    main_layout.addWidget(group)
            else:
                # 没有设置 category 的参数，直接显示，不分组
                form = QFormLayout()
                form.setContentsMargins(0, 0, 0, 0)
                form.setSpacing(4)
                for p in specs:
                    current = self.params_store.get(p.key, "")
                    self._add_param_to_form(form, p, current)
                main_layout.addLayout(form)

            if any(p.device_param for p in specs):
                apply_btn = QPushButton("应用本节点所有参数")
                apply_btn.setStyleSheet(
                    "QPushButton { background: #2f7fd9; color: white; border: 1px solid #2b74c7; padding: 4px 10px; border-radius: 4px; }"
                    "QPushButton:hover { background: #3b8cea; }"
                    "QPushButton:pressed { background: #296fbd; }"
                )
                apply_btn.clicked.connect(self._apply_device_pending_params)
                main_layout.addWidget(apply_btn)
                main_layout.addStretch(1)
        else:
            # 非扩展模式保持紧凑展示，避免影响其他标签页
            form = QFormLayout(card)
            form.setContentsMargins(8, 4, 8, 4)
            form.setSpacing(4)
            for p in specs[:4]:
                current = self.params_store.get(p.key, "")
                self._add_param_to_form(form, p, current)
        
        self._proxy = QGraphicsProxyWidget(self)
        self._proxy.setWidget(card)
        self._proxy.setPos(6, self._header_h + 26)
        self._proxy.setZValue(2)
        if self._enable_extended_node_ui:
            self._resize_proxy_widget()
            hint_w = card.sizeHint().width() + 22
            hint_h = self._header_h + 36 + card.sizeHint().height()
            if not self._user_resized:
                self._apply_node_size(hint_w, hint_h, user_resized=False)
            else:
                cur = self.rect()
                self._apply_node_size(cur.width(), max(cur.height(), hint_h), user_resized=True)
        else:
            target_h = max(130, self._header_h + 36 + card.sizeHint().height())
            self.setRect(0, 0, 280, target_h)
    
    def _add_param_to_form(self, form, p, current):
        """将参数添加到表单布局
        
        根据参数类型创建相应的编辑控件：
        - device_param: 设备参数，显示当前值/范围/设置值
        - bool: 复选框
        - select: 下拉选择框
        - int/float: 高精度数值输入框
        - text: 文本输入框
        
        Args:
            form: 表单布局
            p: 参数规范
            current: 当前参数值
        """
        if p.device_param:
            # 设备参数：统一展示“当前值 / 范围 / 设置值”
            param_widget = QWidget()
            param_widget.setObjectName("deviceParamContainer")
            param_layout = QVBoxLayout(param_widget)
            param_layout.setContentsMargins(0, 0, 0, 0)
            param_layout.setSpacing(3)
            
            # 第一行：当前值和范围
            info_layout = QHBoxLayout()
            info_layout.setSpacing(10)
            
            current_display = self._format_device_display_value(p.current_value, p.unit)
            range_display = self._format_device_range(p.valid_range, p.unit)
            current_label = QLabel(f"当前值: {current_display}")
            current_label.setStyleSheet("color: #666; font-size: 10px;")
            range_label = QLabel(f"合法范围: {range_display}")
            range_label.setStyleSheet("color: #666; font-size: 10px;")
            pending_label = QLabel("待应用")
            pending_label.setStyleSheet(
                "color: #ffffff; background: #e67e22; font-size: 10px; padding: 1px 6px; border-radius: 7px;"
            )
            
            info_layout.addWidget(current_label)
            info_layout.addWidget(range_label)
            info_layout.addStretch(1)
            info_layout.addWidget(pending_label)
            param_layout.addLayout(info_layout)
            
            # 第二行：设置值（可编辑）
            input_layout = QHBoxLayout()
            input_layout.setSpacing(5)
            set_label = QLabel("设置值:")
            set_label.setStyleSheet("color: #444; font-size: 10px;")
            input_layout.addWidget(set_label)
            
            if p.editor == "select":
                editor = WheelComboBox(self)
                editor.addItems([str(x) for x in p.options])
                idx = editor.findText(str(current))
                editor.setCurrentIndex(max(idx, 0))
                editor.currentTextChanged.connect(
                    lambda v, key=p.key: (self._set_param_value(key, v), _refresh_pending_state(v))
                )
            elif p.editor == "int":
                editor = HighPrecisionSpinBox(
                    current,
                    minimum=p.minimum,
                    maximum=p.maximum,
                    step=p.step,
                    integer=True,
                    parent=self._proxy.widget() if self._proxy is not None else None,
                )
                # 整数和浮点数统一使用HighPrecisionSpinBox，避免Qt原生SpinBox的int32/float精度限制。
                editor.valueChanged.connect(
                    lambda v, key=p.key: (self._set_param_value(key, v), _refresh_pending_state(v))
                )
            elif p.editor == "float":
                editor = HighPrecisionSpinBox(
                    current,
                    minimum=p.minimum,
                    maximum=p.maximum,
                    step=p.step,
                    integer=False,
                    parent=self._proxy.widget() if self._proxy is not None else None,
                )
                # 浮点参数底层用字符串/Decimal处理，用户输入任意小数位数都不会被float截断。
                editor.valueChanged.connect(
                    lambda v, key=p.key: (self._set_param_value(key, v), _refresh_pending_state(v))
                )
            else:
                editor = QLineEdit(str(current))
                editor.editingFinished.connect(
                    lambda e=editor, key=p.key: (self._set_param_value(key, e.text().strip()), _refresh_pending_state(e.text().strip()))
                )
            
            editor.setFixedWidth(120)
            input_layout.addWidget(editor)
            
            if p.unit:
                unit_label = QLabel(p.unit)
                unit_label.setStyleSheet("color: #888; font-size: 10px;")
                input_layout.addWidget(unit_label)
            
            input_layout.addStretch(1)
            param_layout.addLayout(input_layout)

            def _refresh_pending_state(new_value):
                is_pending = self._is_device_value_pending(p, p.current_value, new_value)
                pending_label.setVisible(is_pending)
                if is_pending:
                    param_widget.setStyleSheet(
                        "#deviceParamContainer { background: #fff6eb; border: 1px solid #f0c083; border-radius: 4px; }"
                    )
                else:
                    param_widget.setStyleSheet("#deviceParamContainer { background: transparent; border: none; }")

            _refresh_pending_state(current)
            form.addRow(p.label, param_widget)
        elif p.editor == "bool":
            # 布尔参数
            editor = QCheckBox()
            editor.setChecked(bool(current))
            editor._param_key = p.key  # 存储参数键以便后续查找
            editor.toggled.connect(lambda v, key=p.key: self._set_param_value(key, v))
            form.addRow(p.label, editor)
            self._param_editors[p.key] = editor
        elif p.editor == "select":
            # 下拉选择
            editor = WheelComboBox(self)
            editor.addItems([str(x) for x in p.options])
            idx = editor.findText(str(current))
            editor.setCurrentIndex(max(idx, 0))
            editor._param_key = p.key  # 存储参数键以便后续查找
            editor.currentTextChanged.connect(lambda v, key=p.key: self._set_param_value(key, v))
            form.addRow(p.label, editor)
            self._param_editors[p.key] = editor
        elif p.editor == "int":
            # 整数输入
            editor = HighPrecisionSpinBox(
                current,
                minimum=p.minimum,
                maximum=p.maximum,
                step=p.step,
                integer=True,
                parent=self._proxy.widget() if self._proxy is not None else None,
            )
            # 整数和浮点数统一使用HighPrecisionSpinBox，避免Qt原生SpinBox的int32/float精度限制。
            editor._param_key = p.key  # 存储参数键以便后续查找
            editor.valueChanged.connect(lambda v, key=p.key: self._set_param_value(key, v))
            form.addRow(p.label, editor)
            self._param_editors[p.key] = editor
        elif p.editor == "float":
            # 浮点数输入
            editor = HighPrecisionSpinBox(
                current,
                minimum=p.minimum,
                maximum=p.maximum,
                step=p.step,
                integer=False,
                parent=self._proxy.widget() if self._proxy is not None else None,
            )
            # 浮点参数底层用字符串/Decimal处理，用户输入任意小数位数都不会被float截断。
            editor._param_key = p.key  # 存储参数键以便后续查找
            editor.valueChanged.connect(lambda v, key=p.key: self._set_param_value(key, v))
            form.addRow(p.label, editor)
            self._param_editors[p.key] = editor
        else:
            # 文本输入
            editor = QLineEdit(str(current))
            editor._param_key = p.key  # 存储参数键以便后续查找
            editor.editingFinished.connect(
                lambda e=editor, key=p.key: self._set_param_value(key, e.text().strip())
            )
            if self._is_device_select_file_param(p.key):
                editor_row = self._create_file_path_editor_row(editor, p.key)
                form.addRow(p.label, editor_row)
            else:
                form.addRow(p.label, editor)
            self._param_editors[p.key] = editor

    def _is_device_select_file_param(self, key):
        return self.model.node_type == "device.select" and key in {
            "exp_config_path",
            "sys_config_path",
            "lockin_port",
            "log_path",
        }

    def _create_file_path_editor_row(self, editor, key):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        browse_btn = QPushButton()
        browse_btn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        browse_btn.setFixedWidth(32)
        browse_btn.setToolTip("选择文件")
        browse_btn.clicked.connect(lambda: self._browse_file_path(editor, key))
        layout.addWidget(editor, 1)
        layout.addWidget(browse_btn)
        return row

    def _browse_file_path(self, editor, key):
        current_path = editor.text().strip()
        file_path, _ = QFileDialog.getOpenFileName(
            editor,
            "选择文件",
            current_path,
            "所有文件 (*)",
        )
        if not file_path:
            return
        
        # 判断文件是否在项目目录内，如果在则保存相对路径，否则保存绝对路径
        project_root = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        file_path_abs = os.path.abspath(file_path)
        
        try:
            relative_path = os.path.relpath(file_path_abs, project_root)
            if not relative_path.startswith('..'):
                # 文件在项目目录内，使用相对路径
                display_path = relative_path.replace('\\', '/')
            else:
                # 文件在项目目录外，使用绝对路径
                display_path = file_path_abs.replace('\\', '/')
        except ValueError:
            # 跨驱动器等情况，使用绝对路径
            display_path = file_path_abs.replace('\\', '/')
        
        editor.setText(display_path)
        self._set_param_value(key, display_path)

    @staticmethod
    def _extract_numeric(value, default=0.0):
        if value is None:
            return default
        text = str(value).strip()
        match = re.search(r"[-+]?\d*\.?\d+", text)
        if not match:
            return default
        try:
            return float(match.group())
        except ValueError:
            return default

    @staticmethod
    def _extract_numeric_text(value, default="0"):
        text = "" if value is None else str(value).strip()
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
        return match.group() if match else str(default)

    @staticmethod
    def _trim_decimal_zeros(number_text):
        try:
            decimal_value = Decimal(str(number_text))
        except (InvalidOperation, ValueError):
            return str(number_text)
        plain_text = format(decimal_value, "f")
        if "." in plain_text:
            plain_text = plain_text.rstrip("0").rstrip(".")
        return plain_text or "0"

    @staticmethod
    def _format_decimal_text(value):
        # 仅用于UI初始展示：自动去掉浮点数字符串末尾无意义的0，不改变用户后续手动输入的原始字符串。
        return WorkflowNodeItem._trim_decimal_zeros(WorkflowNodeItem._extract_numeric_text(value, "0"))

    @staticmethod
    def _format_device_display_value(value, unit):
        text = "" if value is None else str(value).strip()
        if not text:
            return "-"
        number_text = WorkflowNodeItem._extract_numeric_text(text, "")
        if number_text:
            formatted_number = WorkflowNodeItem._trim_decimal_zeros(number_text)
            return f"{formatted_number}{unit}" if unit else formatted_number
        return text

    @staticmethod
    def _format_device_range(valid_range, unit):
        text = "" if valid_range is None else str(valid_range).strip()
        if not text:
            return "-"
        if unit and unit not in text:
            if "-" in text:
                start, end = text.split("-", 1)
                return f"{start}{unit}-{end}{unit}"
            return f"{text}{unit}"
        return text

    @staticmethod
    def _is_device_value_pending(param_spec, current_value, input_value):
        if param_spec.editor in {"int", "float"}:
            try:
                current_num = Decimal(WorkflowNodeItem._extract_numeric_text(current_value, "0"))
                input_num = Decimal(WorkflowNodeItem._extract_numeric_text(input_value, "0"))
                return current_num != input_num
            except InvalidOperation:
                return str(current_value).strip() != str(input_value).strip()
        return str(current_value).strip() != str(input_value).strip()

    def _clear_form_layout(self, form_layout):
        while form_layout.count():
            item = form_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                continue
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_form_layout(child_layout)

    def _fill_subcategory_form(self, form_layout, param_specs):
        self._clear_form_layout(form_layout)
        for p in param_specs:
            current = self.params_store.get(p.key, "")
            self._add_param_to_form(form_layout, p, current)

    def _on_subcategory_changed(self, selected_key, subgroups, form_layout, selected_subcategory):
        self.model.params[selected_key] = selected_subcategory
        self.params_store[selected_key] = selected_subcategory
        self._fill_subcategory_form(form_layout, subgroups.get(selected_subcategory, []))
        if self._enable_extended_node_ui:
            self._resize_to_content_if_needed()
        if self._on_param_changed:
            self._on_param_changed(self.model)

    def _set_param_value(self, key, value):
        """设置参数值并处理参数依赖
        
        Args:
            key: 参数键
            value: 参数值
        """
        self.model.params[key] = value
        self.params_store[key] = value

        # 处理参数依赖
        if self.spec and hasattr(self.spec, 'on_param_change'):
            if self.spec.on_param_change:
                updates = self.spec.on_param_change(key, value, self.model.params)
                if updates:
                    for update_key, update_value in updates.items():
                        if update_key != key:
                            self.model.params[update_key] = update_value
                            self.params_store[update_key] = update_value
                            # 更新UI中的对应编辑器
                            self._update_param_editor(update_key, update_value)

        if self._on_param_changed:
            self._on_param_changed(self.model)

    def _update_param_editor(self, key, value):
        """更新UI中指定参数的编辑器值"""
        # 从存储的编辑器字典中查找并更新
        if key in self._param_editors:
            widget = self._param_editors[key]
            if isinstance(widget, HighPrecisionSpinBox):
                widget.setText(value)
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QComboBox):
                idx = widget.findText(str(value))
                widget.setCurrentIndex(max(idx, 0))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))

    def _apply_device_pending_params(self):
        """将本节点设备参数的设置值应用为当前值。"""
        updated = False
        for p in (self.spec.param_specs if self.spec else []):
            if not p.device_param:
                continue
            if p.key not in self.model.params:
                continue
            new_value = self.model.params[p.key]
            if not self._is_device_value_pending(p, p.current_value, new_value):
                continue
            if p.editor == "int":
                p.current_value = str(int(round(float(new_value))))
            elif p.editor == "float":
                # 设备浮点参数不转换为float，避免保存/应用时丢失高精度；仅当前值展示会自动去掉末尾0。
                p.current_value = str(new_value).strip()
            else:
                p.current_value = str(new_value)
            updated = True

        if updated:
            # 避免在按钮点击槽函数中立即销毁当前代理控件，导致Qt对象生命周期异常。
            QTimer.singleShot(0, self._refresh_after_apply_pending)

    def _refresh_after_apply_pending(self):
        if self.is_expanded and self._proxy is not None:
            self._build_param_widget()
        self._rebuild_ports()
        if self._on_param_changed:
            self._on_param_changed(self.model)

    def _status_color(self):
        brush = self.brush()
        if brush.style() != Qt.NoBrush:
            return brush.color()
        return QColor("#de6d1f")

    def _resize_proxy_widget(self):
        if not self._enable_extended_node_ui:
            return
        if self._proxy is None or self._proxy.widget() is None:
            return
        content_w = max(120, int(self.rect().width() - 12))
        widget = self._proxy.widget()
        widget.setMinimumWidth(content_w)
        widget.setMaximumWidth(content_w)
        widget.adjustSize()
        self._proxy.resize(content_w, widget.sizeHint().height())

    def _apply_node_size(self, width, height, user_resized=False):
        if not self._enable_extended_node_ui:
            return
        width = max(self._min_node_width, min(float(width), self._max_node_width))
        height = max(self._min_node_height, min(float(height), self._max_node_height))
        self.setRect(0, 0, width, height)
        self._resize_proxy_widget()
        self._rebuild_ports()
        if user_resized:
            self._user_resized = True
            self.model.params["__node_user_resized__"] = True
            self.model.params["__node_size__"] = [round(width, 2), round(height, 2)]
        if self.scene():
            self.scene().update_edges_for_node(self.model.node_id)
        self.update()

    def _resize_to_content_if_needed(self):
        if not self._enable_extended_node_ui:
            return
        if self._proxy is None or self._proxy.widget() is None:
            return
        widget = self._proxy.widget()
        widget.adjustSize()
        target_h = self._header_h + 36 + widget.sizeHint().height()
        if self._user_resized:
            self._apply_node_size(self.rect().width(), max(self.rect().height(), target_h), user_resized=True)
        else:
            target_w = widget.sizeHint().width() + 22
            self._apply_node_size(target_w, target_h, user_resized=False)

    def _resize_handle_rect(self):
        r = self.rect()
        s = self._resize_handle_size
        return QRectF(r.width() - s - 3, r.height() - s - 3, s, s)

    def _rebuild_ports(self):
        """重建端口位置
        
        根据当前节点大小和端口规范重新计算所有端口的位置。
        输入端口在左侧，输出端口在右侧。
        """
        self._input_ports = {}
        self._output_ports = {}
        left_base = self._header_h + 16
        right_base = self._header_h + 16
        for i, p in enumerate(self.spec.input_ports):
            self._input_ports[p.name] = QPointF(6, left_base + i * 22)
        for i, p in enumerate(self.spec.output_ports):
            self._output_ports[p.name] = QPointF(self.rect().width() - 6, right_base + i * 22)

    def toggle_collapse(self):
        if self.is_expanded:
            self._sync_params_from_widgets()
            self.destroy_params_ui()
            self.is_expanded = False
            self.setRect(0, 0, self.rect().width(), self._header_h + 10)
        else:
            self.is_expanded = True
            self.render_params_ui()
        self._rebuild_ports()
        if self.scene():
            self.scene().update_edges_for_node(self.model.node_id)
        self.update()

    def render_params_ui(self):
        if self._proxy is not None:
            return
        self._build_param_widget()
        if self._proxy is not None and self._proxy.widget() is not None:
            widget = self._proxy.widget()
            widget.adjustSize()
            if self._enable_extended_node_ui:
                hint_w = widget.sizeHint().width() + 22
                hint_h = self._header_h + 36 + widget.sizeHint().height()
                if not self._user_resized:
                    self._apply_node_size(hint_w, hint_h, user_resized=False)
                else:
                    cur = self.rect()
                    self._apply_node_size(cur.width(), max(cur.height(), hint_h), user_resized=True)
            else:
                target_h = max(130, self._header_h + 36 + widget.sizeHint().height())
                self.setRect(0, 0, 280, target_h)
        self._rebuild_ports()

    def destroy_params_ui(self):
        if self._proxy is not None:
            scene = self.scene()
            if scene is not None:
                scene.removeItem(self._proxy)
            self._proxy = None
        self._param_editors.clear()
        self.param_widgets.clear()

    def _sync_params_from_widgets(self):
        for key, editor in self._param_editors.items():
            if isinstance(editor, HighPrecisionSpinBox):
                self.params_store[key] = editor.text()
            elif isinstance(editor, QLineEdit):
                self.params_store[key] = editor.text().strip()
            elif isinstance(editor, QSpinBox):
                self.params_store[key] = editor.value()
            elif isinstance(editor, QComboBox):
                self.params_store[key] = editor.currentText()
            elif isinstance(editor, QCheckBox):
                self.params_store[key] = editor.isChecked()
        self.model.params.update(self.params_store)

    def anchor(self, port_name, is_output):
        """获取指定端口的场景坐标
        
        Args:
            port_name: 端口名称
            is_output: 是否为输出端口
        
        Returns:
            QPointF: 端口在场景中的坐标
        """
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
        """查找指定场景位置的端口
        
        Args:
            scene_pos: 场景坐标位置
            require_output: 是否要求输出端口（None表示任意）
        
        Returns:
            (is_output, port_name) 或 None
        """
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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._collapse_btn_rect.contains(event.pos()):
            self.toggle_collapse()
            event.accept()
            return
        if self._enable_extended_node_ui and event.button() == Qt.LeftButton and self._resize_handle_rect().contains(event.pos()):
            self._is_resizing = True
            self._resize_start_scene_pos = event.scenePos()
            self._resize_start_size = (self.rect().width(), self.rect().height())
            self.setFlag(QGraphicsItem.ItemIsMovable, False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing and self._resize_start_scene_pos is not None:
            delta = event.scenePos() - self._resize_start_scene_pos
            new_w = self._resize_start_size[0] + delta.x()
            new_h = self._resize_start_size[1] + delta.y()
            self._apply_node_size(new_w, new_h, user_resized=True)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_resizing:
            self._is_resizing = False
            self._resize_start_scene_pos = None
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        if self._enable_extended_node_ui and self._resize_handle_rect().contains(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)
    
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
        """绘制节点
        
        绘制节点的背景、标题栏和选中状态。
        选中时绘制蓝色高亮边框。
        
        Args:
            painter: 绘图器
            option: 绘图选项
            widget: 父控件
        """
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

        btn_size = 16
        btn_x = body_rect.width() - btn_size - 8
        btn_y = (self._header_h - btn_size) / 2
        self._collapse_btn_rect = QRectF(btn_x, btn_y, btn_size, btn_size)
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.setBrush(QBrush(QColor("#d0d0d0")))
        painter.drawRoundedRect(self._collapse_btn_rect, 3, 3)
        painter.setPen(QPen(QColor("#333333")))
        painter.drawText(self._collapse_btn_rect, Qt.AlignCenter, "▼" if not self.is_expanded else "▲")

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

        if self._enable_extended_node_ui:
            handle_rect = self._resize_handle_rect()
            painter.setPen(QPen(QColor("#8e8e8e"), 1))
            painter.setBrush(QBrush(QColor("#d9d9d9")))
            painter.drawRoundedRect(handle_rect, 2, 2)
            painter.setPen(QPen(QColor("#9f9f9f"), 1))
            painter.drawLine(handle_rect.right() - 8, handle_rect.bottom() - 2, handle_rect.right() - 2, handle_rect.bottom() - 8)
            painter.drawLine(handle_rect.right() - 12, handle_rect.bottom() - 2, handle_rect.right() - 2, handle_rect.bottom() - 12)


