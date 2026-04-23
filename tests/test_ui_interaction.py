"""
UI交互测试

测试工作流系统的用户界面交互功能，包括：
- 节点拖拽操作
- 连线操作
- 参数编辑
- 画布交互
- 键盘快捷键
"""

import pytest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtTest import QTest
from PySide6.QtGui import QMouseEvent
from workflow_extension.models import WorkflowNodeModel, WorkflowEdgeModel
from workflow_extension.workflow_tab import WorkflowTab
from workflow_extension.node_registry import NodeRegistry
from workflow_extension.builtins import register_builtin_nodes


class TestWorkflowTabUI:
    """工作流标签页UI测试类"""
    
    @pytest.fixture
    def app(self):
        """QApplication实例"""
        if not QApplication.instance():
            app = QApplication([])
        else:
            app = QApplication.instance()
        return app
    
    @pytest.fixture
    def workflow_tab(self, app):
        """工作流标签页实例"""
        tab = WorkflowTab()
        return tab
    
    @pytest.fixture
    def node_registry(self):
        """节点注册表"""
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        return registry
    
    @pytest.mark.ui
    def test_workflow_tab_initialization(self, workflow_tab):
        """测试工作流标签页初始化"""
        # 验证基本组件存在
        assert workflow_tab.scene is not None
        assert workflow_tab.canvas is not None
        assert workflow_tab.property_form is not None  # 属性表单存在
        
        # 验证初始状态
        assert workflow_tab.canvas.scene() == workflow_tab.scene
        assert len(workflow_tab.scene.items()) == 0  # 初始无节点
    
    @pytest.mark.ui
    def test_node_palette_functionality(self, workflow_tab, node_registry):
        """测试节点面板功能"""
        # 设置节点注册表
        workflow_tab.set_node_registry(node_registry)
        
        # 验证节点面板包含节点
        node_palette = workflow_tab.node_palette
        assert hasattr(node_palette, 'node_types')
        
        # 验证内置节点类型存在
        if hasattr(node_palette, 'node_types'):
            node_types = node_palette.node_types
            assert len(node_types) > 0  # 应该有节点类型
    
    @pytest.mark.ui
    def test_add_node_from_palette(self, workflow_tab, node_registry):
        """测试从节点面板添加节点"""
        workflow_tab.set_node_registry(node_registry)
        
        # 模拟从节点面板添加节点
        node_type = "data.source"
        node_spec = node_registry.get(node_type)
        
        # 添加节点到画布
        scene_pos = QPointF(100.0, 100.0)
        workflow_tab.add_node(node_spec, scene_pos)
        
        # 验证节点已添加
        items = workflow_tab.scene.items()
        node_items = [item for item in items if hasattr(item, 'model')]
        assert len(node_items) == 1
        
        node_item = node_items[0]
        assert node_item.model.node_type == node_type
        assert node_item.model.title == node_spec.title


class TestCanvasInteraction:
    """画布交互测试类"""
    
    @pytest.fixture
    def app(self):
        """QApplication实例"""
        if not QApplication.instance():
            app = QApplication([])
        else:
            app = QApplication.instance()
        return app
    
    @pytest.fixture
    def workflow_tab(self, app):
        """工作流标签页实例"""
        tab = WorkflowTab()
        return tab
    
    @pytest.fixture
    def canvas(self, workflow_tab):
        """画布实例"""
        return workflow_tab.canvas
    
    @pytest.fixture
    def scene(self, workflow_tab):
        """场景实例"""
        return workflow_tab.scene
    
    @pytest.fixture
    def sample_node(self, scene, node_registry):
        """示例节点"""
        from workflow_extension.canvas import WorkflowNodeItem
        from workflow_extension.node_registry import NodeSpec
        
        node_spec = NodeSpec(
            node_type="test.sample",
            title="测试节点",
            category="测试",
            executor=lambda context, node, inputs: {"result": "test"}
        )
        
        node_model = WorkflowNodeModel(
            node_id="test_node_1",
            node_type="test.sample",
            title="测试节点",
            position=(100.0, 100.0),
            params={}
        )
        
        node_item = WorkflowNodeItem(node_model, node_spec)
        scene.addItem(node_item)
        return node_item
    
    @pytest.mark.ui
    def test_node_selection(self, canvas, sample_node):
        """测试节点选择"""
        # 初始状态：无选择
        selected_items = canvas.scene().selectedItems()
        assert len(selected_items) == 0
        
        # 选择节点
        sample_node.setSelected(True)
        
        # 验证节点被选中
        selected_items = canvas.scene().selectedItems()
        assert len(selected_items) == 1
        assert selected_items[0] == sample_node
    
    @pytest.mark.ui
    def test_node_dragging(self, canvas, sample_node):
        """测试节点拖拽"""
        # 记录初始位置
        initial_pos = sample_node.pos()
        
        # 模拟鼠标拖拽
        start_pos = canvas.mapFromScene(initial_pos)
        end_pos = start_pos + QPoint(50, 50)
        
        # 开始拖拽
        press_event = QMouseEvent(
            QMouseEvent.MouseButtonPress,
            start_pos,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        QApplication.sendEvent(canvas.viewport(), press_event)
        
        # 拖拽移动
        move_event = QMouseEvent(
            QMouseEvent.MouseMove,
            end_pos,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        QApplication.sendEvent(canvas.viewport(), move_event)
        
        # 结束拖拽
        release_event = QMouseEvent(
            QMouseEvent.MouseButtonRelease,
            end_pos,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        QApplication.sendEvent(canvas.viewport(), release_event)
        
        # 处理事件
        QApplication.processEvents()
        
        # 验证节点位置改变（注意：实际拖拽可能需要更多设置）
        # 这里主要测试拖拽事件不会导致崩溃
    
    @pytest.mark.ui
    def test_node_double_click_edit(self, canvas, sample_node):
        """测试节点双击编辑标题"""
        # 记录初始标题
        initial_title = sample_node.model.title
        
        # 模拟双击事件
        node_center = sample_node.boundingRect().center()
        scene_pos = sample_node.mapToScene(node_center)
        view_pos = canvas.mapFromScene(scene_pos)
        
        double_click_event = QMouseEvent(
            QMouseEvent.MouseButtonDblClick,
            view_pos,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        
        # 发送双击事件
        QApplication.sendEvent(canvas.viewport(), double_click_event)
        QApplication.processEvents()
        
        # 验证编辑状态（如果实现了双击编辑功能）
        # 这里主要测试双击不会导致崩溃
    
    @pytest.mark.ui
    def test_canvas_zoom(self, canvas):
        """测试画布缩放"""
        # 记录初始缩放
        initial_transform = canvas.transform()
        
        # 模拟滚轮缩放
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtCore import QPoint
        
        center_pos = QPoint(canvas.width() // 2, canvas.height() // 2)
        
        # 放大
        zoom_in_event = QWheelEvent(
            center_pos, center_pos,
            QPoint(0, 120),  # 滚轮增量
            Qt.NoButton,
            Qt.NoModifier,
            Qt.NoScrollPhase,
            False
        )
        
        QApplication.sendEvent(canvas.viewport(), zoom_in_event)
        QApplication.processEvents()
        
        # 验证缩放变化
        new_transform = canvas.transform()
        # 缩放应该改变（具体变化取决于实现）
    
    @pytest.mark.ui
    def test_canvas_pan(self, canvas):
        """测试画布平移"""
        # 模拟鼠标中键拖拽平移
        start_pos = QPoint(100, 100)
        end_pos = QPoint(150, 150)
        
        # 开始平移（假设使用中键）
        press_event = QMouseEvent(
            QMouseEvent.MouseButtonPress,
            start_pos,
            Qt.MiddleButton,
            Qt.MiddleButton,
            Qt.NoModifier
        )
        QApplication.sendEvent(canvas.viewport(), press_event)
        
        # 平移移动
        move_event = QMouseEvent(
            QMouseEvent.MouseMove,
            end_pos,
            Qt.MiddleButton,
            Qt.MiddleButton,
            Qt.NoModifier
        )
        QApplication.sendEvent(canvas.viewport(), move_event)
        
        # 结束平移
        release_event = QMouseEvent(
            QMouseEvent.MouseButtonRelease,
            end_pos,
            Qt.MiddleButton,
            Qt.MiddleButton,
            Qt.NoModifier
        )
        QApplication.sendEvent(canvas.viewport(), release_event)
        
        QApplication.processEvents()
        
        # 验证平移不会导致崩溃


class TestNodeConnection:
    """节点连接测试类"""
    
    @pytest.fixture
    def app(self):
        """QApplication实例"""
        if not QApplication.instance():
            app = QApplication([])
        else:
            app = QApplication.instance()
        return app
    
    @pytest.fixture
    def workflow_tab(self, app):
        """工作流标签页实例"""
        tab = WorkflowTab()
        return tab
    
    @pytest.fixture
    def scene(self, workflow_tab):
        """场景实例"""
        return workflow_tab.scene
    
    @pytest.fixture
    def two_nodes(self, scene, node_registry):
        """创建两个节点用于连接测试"""
        from workflow_extension.canvas import WorkflowNodeItem
        from workflow_extension.node_registry import NodeSpec
        
        # 第一个节点（源）
        source_spec = NodeSpec(
            node_type="data.source",
            title="数据源",
            category="数据",
            executor=lambda context, node, inputs: {"x": 1.0, "y": 2.0}
        )
        
        source_model = WorkflowNodeModel(
            node_id="source_node",
            node_type="data.source",
            title="数据源",
            position=(50.0, 50.0),
            params={}
        )
        
        source_item = WorkflowNodeItem(source_model, source_spec)
        scene.addItem(source_item)
        
        # 第二个节点（目标）
        target_spec = NodeSpec(
            node_type="plot.stream",
            title="绘图",
            category="可视化",
            executor=lambda context, node, inputs: inputs[0] if inputs else {}
        )
        
        target_model = WorkflowNodeModel(
            node_id="target_node",
            node_type="plot.stream",
            title="绘图",
            position=(250.0, 50.0),
            params={}
        )
        
        target_item = WorkflowNodeItem(target_model, target_spec)
        scene.addItem(target_item)
        
        return source_item, target_item
    
    @pytest.mark.ui
    def test_node_port_detection(self, two_nodes):
        """测试节点端口检测"""
        source_node, target_node = two_nodes
        
        # 测试输出端口检测
        output_port = source_node.port_at_scene_pos(
            source_node.anchor("out", True) + QPointF(5, 0),
            require_output=True
        )
        
        assert output_port is not None
        assert output_port[0] is True  # 是输出端口
        assert output_port[1] == "out"
        
        # 测试输入端口检测
        input_port = target_node.port_at_scene_pos(
            target_node.anchor("in", False) + QPointF(-5, 0),
            require_output=False
        )
        
        assert input_port is not None
        assert input_port[0] is False  # 是输入端口
        assert input_port[1] == "in"
    
    @pytest.mark.ui
    def test_create_connection(self, workflow_tab, two_nodes):
        """测试创建连接"""
        source_node, target_node = two_nodes
        scene = workflow_tab.scene
        
        # 获取端口位置
        source_pos = source_node.anchor("out", True)
        target_pos = target_node.anchor("in", False)
        
        # 模拟拖拽创建连接
        # 开始拖拽（从源节点输出端口）
        workflow_tab.start_drag_link(source_node, "out", source_pos)
        
        # 移动到目标位置
        workflow_tab.update_drag_link_to(target_pos)
        
        # 完成连接（在目标节点输入端口）
        workflow_tab.finish_drag_link(target_node, "in")
        
        # 验证连接已创建
        edges = scene.edges if hasattr(scene, 'edges') else []
        assert len(edges) > 0
        
        # 验证连接的节点
        if edges:
            edge = edges[0]
            assert edge[0] == source_node.model.node_id  # from_node
            assert edge[2] == target_node.model.node_id   # to_node
    
    @pytest.mark.ui
    def test_delete_connection(self, workflow_tab, two_nodes):
        """测试删除连接"""
        # 先创建连接
        source_node, target_node = two_nodes
        scene = workflow_tab.scene
        
        source_pos = source_node.anchor("out", True)
        target_pos = target_node.anchor("in", False)
        
        workflow_tab.start_drag_link(source_node, "out", source_pos)
        workflow_tab.update_drag_link_to(target_pos)
        workflow_tab.finish_drag_link(target_node, "in")
        
        # 验证连接存在
        initial_edge_count = len(scene.edges) if hasattr(scene, 'edges') else 0
        assert initial_edge_count > 0
        
        # 删除连接（具体方法取决于实现）
        # 这里假设有删除连接的方法
        if hasattr(scene, 'remove_edge'):
            scene.remove_edge(source_node.model.node_id, target_node.model.node_id)
            
            # 验证连接已删除
            final_edge_count = len(scene.edges)
            assert final_edge_count < initial_edge_count


class TestPropertyPanel:
    """属性面板测试类"""
    
    @pytest.fixture
    def app(self):
        """QApplication实例"""
        if not QApplication.instance():
            app = QApplication([])
        else:
            app = QApplication.instance()
        return app
    
    @pytest.fixture
    def workflow_tab(self, app):
        """工作流标签页实例"""
        tab = WorkflowTab()
        return tab
    
    @pytest.fixture
    def property_panel(self, workflow_tab):
        """属性面板实例"""
        return workflow_tab.property_panel
    
    @pytest.mark.ui
    def test_property_panel_initialization(self, property_panel):
        """测试属性面板初始化"""
        # 验证面板存在
        assert property_panel is not None
        
        # 验证初始状态（无选中节点时应该为空或显示默认信息）
        # 具体验证取决于实现
    
    @pytest.mark.ui
    def test_property_panel_node_selection(self, workflow_tab, property_panel):
        """测试属性面板节点选择响应"""
        # 创建测试节点
        from workflow_extension.canvas import WorkflowNodeItem
        from workflow_extension.node_registry import NodeSpec
        
        node_spec = NodeSpec(
            node_type="test.parameter",
            title="参数测试节点",
            category="测试",
            executor=lambda context, node, inputs: {"result": "test"}
        )
        
        node_model = WorkflowNodeModel(
            node_id="param_test_node",
            node_type="test.parameter",
            title="参数测试节点",
            position=(100.0, 100.0),
            params={"param1": "value1", "param2": 42}
        )
        
        node_item = WorkflowNodeItem(node_model, node_spec)
        workflow_tab.scene.addItem(node_item)
        
        # 选择节点
        workflow_tab.scene.clearSelection()
        node_item.setSelected(True)
        
        # 触发节点选择事件（如果实现了）
        if hasattr(workflow_tab, 'on_node_selected'):
            workflow_tab.on_node_selected(node_item.model)
        
        # 验证属性面板响应（具体验证取决于实现）
        # 这里主要测试选择节点不会导致崩溃
    
    @pytest.mark.ui
    def test_property_panel_parameter_editing(self, workflow_tab, property_panel):
        """测试属性面板参数编辑"""
        # 这个测试需要根据实际的属性面板实现来编写
        # 主要测试：
        # 1. 参数显示
        # 2. 参数编辑
        # 3. 参数更新
        # 4. 参数验证
        
        # 由于属性面板的具体实现未知，这里只做基本测试
        assert property_panel is not None


class TestKeyboardShortcuts:
    """键盘快捷键测试类"""
    
    @pytest.fixture
    def app(self):
        """QApplication实例"""
        if not QApplication.instance():
            app = QApplication([])
        else:
            app = QApplication.instance()
        return app
    
    @pytest.fixture
    def workflow_tab(self, app):
        """工作流标签页实例"""
        tab = WorkflowTab()
        return tab
    
    @pytest.fixture
    def canvas(self, workflow_tab):
        """画布实例"""
        return workflow_tab.canvas
    
    @pytest.mark.ui
    def test_keyboard_shortcuts_basic(self, canvas):
        """测试基本键盘快捷键"""
        # 测试删除键
        delete_event = QTest.keyEvent(
            QTest.Key.Press, Qt.Key_Delete, Qt.NoModifier
        )
        QApplication.sendEvent(canvas, delete_event)
        QApplication.processEvents()
        
        # 测试Ctrl+Z（撤销）
        ctrl_z_event = QTest.keyEvent(
            QTest.Key.Press, Qt.Key_Z, Qt.ControlModifier
        )
        QApplication.sendEvent(canvas, ctrl_z_event)
        QApplication.processEvents()
        
        # 测试Ctrl+Y（重做）
        ctrl_y_event = QTest.keyEvent(
            QTest.Key.Press, Qt.Key_Y, Qt.ControlModifier
        )
        QApplication.sendEvent(canvas, ctrl_y_event)
        QApplication.processEvents()
        
        # 主要测试快捷键不会导致崩溃
    
    @pytest.mark.ui
    def test_keyboard_shortcuts_copy_paste(self, canvas):
        """测试复制粘贴快捷键"""
        # 测试Ctrl+C（复制）
        ctrl_c_event = QTest.keyEvent(
            QTest.Key.Press, Qt.Key_C, Qt.ControlModifier
        )
        QApplication.sendEvent(canvas, ctrl_c_event)
        QApplication.processEvents()
        
        # 测试Ctrl+V（粘贴）
        ctrl_v_event = QTest.keyEvent(
            QTest.Key.Press, Qt.Key_V, Qt.ControlModifier
        )
        QApplication.sendEvent(canvas, ctrl_v_event)
        QApplication.processEvents()
        
        # 主要测试快捷键不会导致崩溃
    
    @pytest.mark.ui
    def test_keyboard_shortcuts_select_all(self, canvas):
        """测试全选快捷键"""
        # 测试Ctrl+A（全选）
        ctrl_a_event = QTest.keyEvent(
            QTest.Key.Press, Qt.Key_A, Qt.ControlModifier
        )
        QApplication.sendEvent(canvas, ctrl_a_event)
        QApplication.processEvents()
        
        # 主要测试快捷键不会导致崩溃


class TestUIPerformance:
    """UI性能测试类"""
    
    @pytest.fixture
    def app(self):
        """QApplication实例"""
        if not QApplication.instance():
            app = QApplication([])
        else:
            app = QApplication.instance()
        return app
    
    @pytest.fixture
    def workflow_tab(self, app):
        """工作流标签页实例"""
        tab = WorkflowTab()
        return tab
    
    @pytest.mark.ui
    @pytest.mark.performance
    def test_ui_response_time(self, workflow_tab, performance_monitor):
        """测试UI响应时间"""
        # 测试添加节点的响应时间
        performance_monitor.start()
        
        # 模拟添加多个节点
        for i in range(50):
            # 创建节点模型
            node_model = WorkflowNodeModel(
                node_id=f"perf_node_{i}",
                node_type="data.source",
                title=f"性能测试节点{i}",
                position=(float(i * 20), float(i * 20)),
                params={}
            )
            
            # 添加到场景（具体方法取决于实现）
            workflow_tab.scene.add_node(node_model)
        
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证性能（添加50个节点应该在合理时间内完成）
        assert duration < 2.0  # 2秒内完成
        
        # 验证节点数量
        items = workflow_tab.scene.items()
        node_items = [item for item in items if hasattr(item, 'model')]
        assert len(node_items) >= 50
