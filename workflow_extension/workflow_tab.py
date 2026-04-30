import json
import logging

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTabWidget,
    QPushButton,
    QMenu,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from workflow_extension.builtins import register_builtin_nodes
from workflow_extension.canvas import WorkflowCanvasView, WorkflowNodeItem, WorkflowScene
from workflow_extension.engine import WorkflowExecutor
from workflow_extension.models import WorkflowEdgeModel, WorkflowGraphModel, WorkflowNodeModel
from workflow_extension.node_registry import NodeRegistry
from workflow_extension.serializer import export_json, export_python, load_workflow, save_workflow


class WorkflowTab(QWidget):
    def __init__(self, app_context=None, parent=None, enable_extended_node_ui=False):
        super().__init__(parent)
        self.app_context = app_context
        self.enable_extended_node_ui = bool(enable_extended_node_ui)
        self.registry = NodeRegistry()
        register_builtin_nodes(self.registry)
        self.executor = WorkflowExecutor(self.registry, self)
        self._latest_results = {}
        self._plot_x = []
        self._plot_y = []
        self._plot_y_ref = []
        self._plot_upper_aux = []
        self._plot_lower_main = []
        self._plot_lower_aux = []
        self._plot_mode = "cw"
        self._prop_editors = {}
        self._selected_node = None
        self._build_ui()
        self._bind_events()

    def _build_ui(self):
        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        
        # 基本操作按钮
        self.btn_new = QPushButton("新建")
        self.btn_save = QPushButton("保存")
        self.btn_load = QPushButton("加载")
        
        # 撤销/重做按钮
        self.btn_undo = QPushButton("撤销")
        self.btn_redo = QPushButton("重做")
        self.btn_undo.setToolTip("Ctrl+Z")
        self.btn_redo.setToolTip("Ctrl+Shift+Z 或 Ctrl+Y")
        
        # 运行相关按钮
        self.btn_run = QPushButton("运行")
        self.btn_stop = QPushButton("停止")
        self.btn_clear = QPushButton("清空")
        self.btn_delete = QPushButton("删除选中")
        
        # 导出按钮
        self.btn_export_json = QPushButton("导出JSON")
        self.btn_export_py = QPushButton("导出Python")
        self.btn_export_pdf = QPushButton("导出PDF")
        
        # 添加按钮到工具栏
        for btn in [
            self.btn_new,
            self.btn_save,
            self.btn_load,
            self.btn_undo,
            self.btn_redo,
            self.btn_run,
            self.btn_stop,
            self.btn_clear,
            self.btn_delete,
            self.btn_export_json,
            self.btn_export_py,
            self.btn_export_pdf,
        ]:
            toolbar.addWidget(btn)
        toolbar.addStretch()
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("节点库（双击添加）"))
        self.palette_search = QLineEdit()
        self.palette_search.setPlaceholderText("搜索节点名称/类型...")
        left_layout.addWidget(self.palette_search)
        self.palette = QTreeWidget()
        self.palette.setHeaderHidden(True)
        self.palette.setRootIsDecorated(True)
        self.palette.setAnimated(True)
        self.palette.setIndentation(14)
        self.palette.setAlternatingRowColors(True)
        grouped = self.registry.grouped()
        for category, specs in grouped.items():
            category_item = QTreeWidgetItem([category])
            category_item.setFlags(Qt.ItemIsEnabled)
            self.palette.addTopLevelItem(category_item)
            for spec in specs:
                item = QTreeWidgetItem([spec.title])
                item.setData(0, Qt.UserRole, spec.node_type)
                item.setToolTip(0, spec.node_type)
                category_item.addChild(item)
            category_item.setExpanded(True)
        left_layout.addWidget(self.palette)
        splitter.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        self.scene = WorkflowScene(self, enable_extended_node_ui=self.enable_extended_node_ui)
        self.scene.set_spec_resolver(self.registry.get)
        self.scene.on_node_param_changed = self._on_node_inline_params_changed
        self.canvas = WorkflowCanvasView(self.scene, self)
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._open_canvas_context_menu)
        center_layout.addWidget(self.canvas, 1)
        splitter.addWidget(center)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot_group = QGroupBox("工作流双图显示")
        plot_layout = QVBoxLayout(self.plot_group)
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(QWidget(), "全关谱")
        self.tab_widget.addTab(QWidget(), "CW谱")
        self.tab_widget.addTab(QWidget(), "IIR谱")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        plot_layout.addWidget(self.tab_widget)
        
        # 添加垂直分割器，使两个图表可以自由拉伸
        plot_splitter = QSplitter(Qt.Vertical)
        self.plot_widget_top = pg.PlotWidget()
        self.plot_widget_bottom = pg.PlotWidget()
        self.plot_widget_top.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget_bottom.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget_top.addLegend()
        self.plot_widget_bottom.addLegend()
        self.plot_curve_top_main = self.plot_widget_top.plot(pen=pg.mkPen("#3b82f6", width=2), name="CH1-X")
        self.plot_curve_top_aux = self.plot_widget_top.plot(pen=pg.mkPen("#ef4444", width=1.8), name="CH1-Y")
        self.plot_curve_bottom_main = self.plot_widget_bottom.plot(pen=pg.mkPen("#eab308", width=2), name="CH2-X")
        self.plot_curve_bottom_aux = self.plot_widget_bottom.plot(pen=pg.mkPen("#22c55e", width=1.8), name="CH2-Y")
        plot_splitter.addWidget(self.plot_widget_top)
        plot_splitter.addWidget(self.plot_widget_bottom)
        plot_splitter.setSizes([300, 300])  # 初始高度分配
        plot_layout.addWidget(plot_splitter, 1)
        
        right_layout.addWidget(self.plot_group, 1)
        splitter.addWidget(right)

        splitter.setSizes([220, 860, 320])
        self.tab_widget.setCurrentIndex(1)
        self._apply_plot_mode("cw")

    def _bind_events(self):
        # 基本事件绑定
        self.btn_new.clicked.connect(self._on_new)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_load.clicked.connect(self._on_load)
        self.btn_run.clicked.connect(self._on_run)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_delete.clicked.connect(self._on_delete_selected)
        self.btn_export_json.clicked.connect(self._on_export_json)
        self.btn_export_py.clicked.connect(self._on_export_py)
        self.btn_export_pdf.clicked.connect(self._on_export_pdf)
        
        # 撤销/重做事件绑定
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_redo.clicked.connect(self._on_redo)
        
        # 连接撤销/重做信号以更新按钮状态
        self.scene.undo_stack.can_undo_changed.connect(self.btn_undo.setEnabled)
        self.scene.undo_stack.can_redo_changed.connect(self.btn_redo.setEnabled)
        self.scene.undo_stack.stack_changed.connect(self._update_undo_redo_tooltips)
        
        # 初始化撤销/重做按钮状态
        self.btn_undo.setEnabled(self.scene.undo_stack.can_undo())
        self.btn_redo.setEnabled(self.scene.undo_stack.can_redo())
        self._update_undo_redo_tooltips()
        
        # 其他事件绑定
        self.palette.itemDoubleClicked.connect(self._on_palette_double_clicked)
        self.palette_search.textChanged.connect(self._on_palette_search)
        self.scene.node_selected.connect(self._on_node_selected)
        self.scene.graph_changed.connect(self._on_graph_changed)
        self.executor.node_started.connect(self._on_exec_node_started)
        self.executor.node_finished.connect(self._on_exec_node_finished)
        self.executor.node_failed.connect(self._on_exec_node_failed)
        self.executor.run_finished.connect(self._on_exec_finished)

    def _on_palette_double_clicked(self, item):
        node_type = item.data(0, Qt.UserRole)
        if not node_type:
            return
        spec = self.registry.get(node_type)
        center_pos = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        self.scene.add_node_with_undo(spec.node_type, spec.title, center_pos, params=dict(spec.default_params))
        self._log(f"已添加节点: {spec.title}")

    def _filter_palette(self, keyword):
        query = keyword.strip().lower()
        for i in range(self.palette.topLevelItemCount()):
            category_item = self.palette.topLevelItem(i)
            visible_count = 0
            for j in range(category_item.childCount()):
                node_item = category_item.child(j)
                title = node_item.text(0).lower()
                node_type = (node_item.data(0, Qt.UserRole) or "").lower()
                match = not query or query in title or query in node_type
                node_item.setHidden(not match)
                if match:
                    visible_count += 1
            category_item.setHidden(visible_count == 0)
            if query and visible_count:
                category_item.setExpanded(True)

    def _on_node_selected(self, node_model):
        self._selected_node = node_model
        self._prop_editors = {}

    def _persist_node_params(self):
        if not self._selected_node:
            return
        for key, editor in self._prop_editors.items():
            text = editor.text().strip()
            self._selected_node.params[key] = self._coerce_value(text)
        self.scene.update()

    def _on_node_inline_params_changed(self, node_model):
        if self._selected_node and self._selected_node.node_id == node_model.node_id:
            self._on_node_selected(node_model)

    def _open_canvas_context_menu(self, pos):
        scene_pos = self.canvas.mapToScene(pos)
        node_item = self.scene.find_node_at(scene_pos)
        menu = QMenu(self)

        if isinstance(node_item, WorkflowNodeItem):
            copy_action = menu.addAction("复制节点")
            copy_action.triggered.connect(lambda: self._copy_node(node_item))
            del_action = menu.addAction("删除节点")
            del_action.triggered.connect(lambda: self._delete_node(node_item))
            link_action = menu.addAction("从此节点开始连线")
            link_action.triggered.connect(lambda: self._start_link_from_node(node_item))
            if not node_item.spec.output_ports:
                link_action.setEnabled(False)
            menu.addSeparator()

        add_menu = menu.addMenu("添加节点")
        grouped = self.registry.grouped()
        for category, specs in grouped.items():
            category_menu = add_menu.addMenu(category)
            for spec in specs:
                action = category_menu.addAction(spec.title)
                action.triggered.connect(
                    lambda checked=False, node_type=spec.node_type, title=spec.title, s_pos=scene_pos: self._add_node_at(
                        node_type, title, s_pos
                    )
                )
        if not isinstance(node_item, WorkflowNodeItem):
            menu.addSeparator()
            delete_action = menu.addAction("删除选中节点")
            delete_action.triggered.connect(self.scene.delete_selected)
            delete_action.setEnabled(bool(self.scene.selectedItems()))
        menu.exec(self.canvas.viewport().mapToGlobal(pos))

    def _add_node_at(self, node_type, title, scene_pos):
        spec = self.registry.get(node_type)
        self.scene.add_node_with_undo(spec.node_type, title, scene_pos, params=dict(spec.default_params))
        self._log(f"已添加节点: {title}")

    def _copy_node(self, node_item):
        offset = self.canvas.mapToScene(40, 40) - self.canvas.mapToScene(0, 0)
        pos = node_item.pos() + offset
        self.scene.add_node_with_undo(
            node_item.model.node_type,
            node_item.model.title,
            pos,
            params=dict(node_item.model.params),
        )
        self._log(f"已复制节点: {node_item.model.title}")

    def _delete_node(self, node_item):
        self.scene.clearSelection()
        node_item.setSelected(True)
        self.scene.delete_selected()
        self._log("已删除节点。")

    def _start_link_from_node(self, node_item):
        ok = self.scene.begin_link_from_node(node_item)
        if ok:
            self._log("已进入连线模式：请左键点击目标节点输入端口。")
        else:
            self._log("该节点没有可用输出端口，无法开始连线。")

    @staticmethod
    def _coerce_value(text):
        if text.lower() in {"true", "false"}:
            return text.lower() == "true"
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    def _new_workflow(self):
        self.scene.clear_all()
        self._latest_results = {}
        self._reset_plot_buffers()
        self._log("已新建空白工作流。")


    def _save_workflow(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "保存工作流", "", "NVM Workflow (*.nvm_workflow)")
        if not file_path:
            return
        graph = self.scene.build_graph()
        save_workflow(graph, file_path)
        self._log(f"工作流已保存: {file_path}")

    def _load_workflow(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "加载工作流", "", "NVM Workflow (*.nvm_workflow)")
        if not file_path:
            return
        graph = load_workflow(file_path)
        self.scene.load_graph(graph)
        self._log(f"工作流已加载: {file_path}")

    def _export_json(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "导出 JSON", "", "JSON (*.json)")
        if not file_path:
            return
        export_json(self.scene.build_graph(), file_path)
        self._log(f"已导出 JSON: {file_path}")

    def _export_python(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "导出 Python", "", "Python (*.py)")
        if not file_path:
            return
        export_python(self.scene.build_graph(), file_path)
        self._log(f"已导出 Python: {file_path}")

    def _export_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", "", "PDF (*.pdf)")
        if not file_path:
            return
        payload = {
            "graph": {
                "nodes": [n.__dict__ for n in self.scene.build_graph().nodes],
                "edges": [e.__dict__ for e in self.scene.build_graph().edges],
            },
            "results": self._latest_results,
        }
        doc = QTextDocument()
        doc.setPlainText("NVMagUI Workflow Report\n\n" + json.dumps(payload, ensure_ascii=False, indent=2))
        printer = QPrinter()
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(file_path)
        doc.print_(printer)
        self._log(f"已导出 PDF: {file_path}")

    def _run_workflow(self):
        graph = self.scene.build_graph()
        if not graph.nodes:
            QMessageBox.warning(self, "提示", "当前工作流为空。")
            return
        app_context = self.app_context or self.parent()
        if app_context is None:
            QMessageBox.warning(self, "提示", "未找到主程序上下文，无法执行需要设备的工作流。")
            self._log("未找到主程序上下文，无法执行需要设备的工作流。")
            return
        self._latest_results = {}
        self._reset_plot_buffers()
        self._log("开始执行工作流。")
        context = {"app": app_context, "plot_callback": self._on_plot_payload, "workflow_tab": self}
        self.executor.run(graph, context)

    def _stop_workflow(self):
        self.executor.stop()
        self._log("已请求停止工作流执行。")

    def _on_exec_node_started(self, node_id):
        item = self.scene.node_items.get(node_id)
        if isinstance(item, WorkflowNodeItem):
            item.setBrush(pg.mkBrush("#2f5d9b"))
        self._log(f"[RUN] {node_id}")

    def _on_exec_node_finished(self, node_id, result):
        item = self.scene.node_items.get(node_id)
        if isinstance(item, WorkflowNodeItem):
            item.setBrush(pg.mkBrush("#2a7d46"))
        self._latest_results[node_id] = result
        self._sync_plot_from_result(result)
        self._log(f"[OK] {node_id} -> {result}")

    def _on_exec_node_failed(self, node_id, err):
        item = self.scene.node_items.get(node_id)
        if isinstance(item, WorkflowNodeItem):
            item.setBrush(pg.mkBrush("#8d2d2d"))
        self._log(f"[ERR] {node_id} -> {err}")

    def _on_exec_finished(self):
        self._log("工作流执行结束。")

    def _on_plot_payload(self, payload):
        x = payload.get("x")
        y = payload.get("y")
        y2 = payload.get("y2")
        if x is None or (y is None and y2 is None):
            return
        self._plot_x.append(x)
        self._plot_y.append(float("nan") if y is None else y)
        self._plot_lower_main.append(float("nan") if y2 is None else y2)
        self._plot_x = self._plot_x[-1200:]
        self._plot_y = self._plot_y[-1200:]
        self._plot_lower_main = self._plot_lower_main[-1200:]
        self.plot_curve_top_main.setData(self._plot_x, self._plot_y)
        self.plot_curve_bottom_main.setData(self._plot_x, self._plot_lower_main)

    def _reset_plot_buffers(self):
        self._plot_x = []
        self._plot_y = []
        self._plot_y_ref = []
        self._plot_upper_aux = []
        self._plot_lower_main = []
        self._plot_lower_aux = []
        self.plot_curve_top_main.setData([], [])
        self.plot_curve_top_aux.setData([], [])
        self.plot_curve_bottom_main.setData([], [])
        self.plot_curve_bottom_aux.setData([], [])

    def _set_plot_titles_and_labels(self, top_title, bottom_title, bottom_axis_label):
        self.plot_widget_top.setTitle(top_title)
        self.plot_widget_bottom.setTitle(bottom_title)
        self.plot_widget_top.setLabel("left", "Voltage", units="V")
        self.plot_widget_bottom.setLabel("left", "Voltage", units="V")
        self.plot_widget_top.setLabel("bottom", bottom_axis_label)
        self.plot_widget_bottom.setLabel("bottom", bottom_axis_label)

    def _on_tab_changed(self, index):
        if index == 0:
            self._apply_plot_mode("all_optical")
        elif index == 1:
            self._apply_plot_mode("cw")
        elif index == 2:
            self._apply_plot_mode("iir")

    def _apply_plot_mode(self, mode):
        self._plot_mode = mode
        index_map = {"all_optical": 0, "cw": 1, "iir": 2}
        if mode in index_map:
            self.tab_widget.blockSignals(True)
            self.tab_widget.setCurrentIndex(index_map[mode])
            self.tab_widget.blockSignals(False)
        if mode == "all_optical":
            self._set_plot_titles_and_labels("CH1 荧光路 直流信号", "CH2 激光路 直流信号", "Motor Angle")
            self.plot_curve_top_aux.setVisible(False)
            self.plot_curve_bottom_aux.setVisible(False)
        elif mode == "iir":
            self._set_plot_titles_and_labels("CH1 IIR通道时域波形", "CH2 IIR通道时域波形", "Time")
            self.plot_curve_top_aux.setVisible(False)
            self.plot_curve_bottom_aux.setVisible(False)
        else:
            self._set_plot_titles_and_labels("CH1 CW谱", "CH2 CW谱", "Frequency")
            self.plot_curve_top_aux.setVisible(True)
            self.plot_curve_bottom_aux.setVisible(True)
        self._refresh_plot_curves()

    def _sync_plot_from_result(self, result):
        if not isinstance(result, dict):
            return
        if {"mw_freq", "ch1_x", "ch1_y", "ch2_x", "ch2_y"}.issubset(result.keys()):
            self._apply_plot_mode("cw")
            self._plot_x = list(result.get("mw_freq", []))[-1200:]
            self._plot_y = list(result.get("ch1_x", []))[-1200:]
            self._plot_upper_aux = list(result.get("ch1_y", []))[-1200:]
            self._plot_lower_main = list(result.get("ch2_x", []))[-1200:]
            self._plot_lower_aux = list(result.get("ch2_y", []))[-1200:]
            self._refresh_plot_curves()
            return
        if {"motor_angle", "fluo_dc", "laser_dc"}.issubset(result.keys()):
            self._apply_plot_mode("all_optical")
            self._plot_x = list(result.get("motor_angle", []))[-1200:]
            self._plot_y = list(result.get("fluo_dc", []))[-1200:]
            self._plot_lower_main = list(result.get("laser_dc", []))[-1200:]
            self._plot_upper_aux = []
            self._plot_lower_aux = []
            self._refresh_plot_curves()
            return
        if {"ch1", "ch2", "time"}.issubset(result.keys()):
            self._apply_plot_mode("iir")
            self._plot_x = list(result.get("time", []))[-1200:]
            self._plot_y = list(result.get("ch1", []))[-1200:]
            self._plot_lower_main = list(result.get("ch2", []))[-1200:]
            self._plot_upper_aux = []
            self._plot_lower_aux = []
            self._refresh_plot_curves()

    def _refresh_plot_curves(self):
        self.plot_curve_top_main.setData(self._plot_x, self._plot_y)
        self.plot_curve_top_aux.setData(self._plot_x, self._plot_upper_aux)
        self.plot_curve_bottom_main.setData(self._plot_x, self._plot_lower_main)
        self.plot_curve_bottom_aux.setData(self._plot_x, self._plot_lower_aux)

    def _log(self, text):
        logging.info(f"[Workflow] {text}")

    def _on_undo(self):
        """撤销操作"""
        if self.scene.undo_stack.can_undo():
            success = self.scene.undo_stack.undo(self.scene)
            if success:
                self._log(f"已撤销: {self.scene.undo_stack.get_undo_description()}")
            else:
                self._log("撤销操作失败")

    def _on_redo(self):
        """重做操作"""
        if self.scene.undo_stack.can_redo():
            success = self.scene.undo_stack.redo(self.scene)
            if success:
                self._log(f"已重做: {self.scene.undo_stack.get_redo_description()}")
            else:
                self._log("重做操作失败")

    def _update_undo_redo_tooltips(self):
        """更新撤销/重做按钮的工具提示"""
        if self.scene.undo_stack.can_undo():
            undo_text = self.scene.undo_stack.get_undo_description()
            self.btn_undo.setToolTip(f"撤销: {undo_text} (Ctrl+Z)")
        else:
            self.btn_undo.setToolTip("撤销 (Ctrl+Z)")
            
        if self.scene.undo_stack.can_redo():
            redo_text = self.scene.undo_stack.get_redo_description()
            self.btn_redo.setToolTip(f"重做: {redo_text} (Ctrl+Shift+Z)")
        else:
            self.btn_redo.setToolTip("重做 (Ctrl+Shift+Z 或 Ctrl+Y)")

    def _on_new(self):
        self._new_workflow()

    def _on_load_demo(self):
        self._load_demo_workflow()

    def _on_save(self):
        self._save_workflow()

    def _on_load(self):
        self._load_workflow()

    def _on_run(self):
        self._run_workflow()

    def _on_stop(self):
        self._stop_workflow()

    def _on_clear(self):
        self.scene.clear_all()
        self._reset_plot_buffers()
        self._log("已清空工作流画布")

    def _on_delete_selected(self):
        self.scene.delete_selected_with_undo()
        self._log("已删除选中节点")

    def _on_export_json(self):
        self._export_json()

    def _on_export_py(self):
        self._export_python()

    def _on_export_pdf(self):
        self._export_pdf()

    def _on_palette_search(self):
        self._filter_palette(self.palette_search.text())

    def _on_graph_changed(self):
        """工作流图发生变化时的处理"""
        # 这里可以添加自动保存等功能
        pass
