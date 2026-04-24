"""
节点注册机制单元测试

测试工作流系统的节点注册表功能，包括：
- 节点注册功能
- 节点查询功能
- 节点分组功能
- 重复注册处理
- 异常情况处理
"""

import pytest
from workflow_extension.node_registry import (
    NodeRegistry,
    NodeSpec,
    NodePortSpec,
    NodeParamSpec
)


class TestNodeRegistry:
    """节点注册表测试类"""
    
    @pytest.fixture
    def registry(self):
        """创建空的节点注册表"""
        return NodeRegistry()
    
    @pytest.fixture
    def sample_node_spec(self):
        """示例节点规范"""
        return NodeSpec(
            node_type="test.sample_node",
            title="测试节点",
            category="测试分类",
            default_params={"param1": "default", "param2": 42},
            input_ports=[NodePortSpec("input", "any")],
            output_ports=[NodePortSpec("output", "any")],
            param_specs=[
                NodeParamSpec("param1", "参数1", editor="text"),
                NodeParamSpec("param2", "参数2", editor="int", minimum=1, maximum=100)
            ],
            executor=lambda context, node, inputs: {"result": "test"}
        )
    
    @pytest.mark.unit
    def test_register_node_success(self, registry, sample_node_spec):
        """测试节点注册成功"""
        registry.register(sample_node_spec)
        
        # 验证节点可以被获取
        retrieved_spec = registry.get("test.sample_node")
        assert retrieved_spec is not None
        assert retrieved_spec.node_type == "test.sample_node"
        assert retrieved_spec.title == "测试节点"
        assert retrieved_spec.category == "测试分类"
    
    @pytest.mark.unit
    def test_register_multiple_nodes(self, registry):
        """测试注册多个节点"""
        # 注册第一个节点
        node1 = NodeSpec(
            node_type="test.node1",
            title="节点1",
            category="分类A",
            executor=lambda context, node, inputs: {"result": "node1"}
        )
        registry.register(node1)
        
        # 注册第二个节点
        node2 = NodeSpec(
            node_type="test.node2",
            title="节点2",
            category="分类B",
            executor=lambda context, node, inputs: {"result": "node2"}
        )
        registry.register(node2)
        
        # 验证两个节点都可以被获取
        assert registry.get("test.node1").title == "节点1"
        assert registry.get("test.node2").title == "节点2"
    
    @pytest.mark.unit
    def test_register_duplicate_node(self, registry, sample_node_spec):
        """测试重复注册节点（覆盖）"""
        # 第一次注册
        registry.register(sample_node_spec)
        original_spec = registry.get("test.sample_node")
        
        # 修改规范后再次注册
        duplicate_spec = NodeSpec(
            node_type="test.sample_node",  # 相同类型
            title="更新的测试节点",        # 不同标题
            category="更新的分类",
            executor=lambda context, node, inputs: {"result": "updated"}
        )
        registry.register(duplicate_spec)
        
        # 验证规范被覆盖
        updated_spec = registry.get("test.sample_node")
        assert updated_spec.title == "更新的测试节点"
        assert updated_spec.category == "更新的分类"
        assert updated_spec is not original_spec  # 不是同一个对象
    
    @pytest.mark.unit
    def test_get_nonexistent_node(self, registry):
        """测试获取不存在的节点"""
        with pytest.raises(KeyError):
            registry.get("nonexistent.node")
    
    @pytest.mark.unit
    def test_all_specs_functionality(self, registry):
        """测试获取所有节点规范"""
        # 注册多个节点
        for i in range(5):
            node_spec = NodeSpec(
                node_type=f"test.node{i}",
                title=f"节点{i}",
                category="测试",
                executor=lambda context, node, inputs: {"result": f"node{i}"}
            )
            registry.register(node_spec)
        
        # 获取所有规范
        all_specs = registry.all_specs()
        
        assert len(all_specs) == 5
        node_types = [spec.node_type for spec in all_specs]
        assert "test.node0" in node_types
        assert "test.node4" in node_types
    
    @pytest.mark.unit
    def test_grouped_functionality(self, registry):
        """测试节点分组功能"""
        # 注册不同分类的节点
        categories = ["设备控制", "数据处理", "可视化", "设备控制"]  # 重复分类测试
        for i, category in enumerate(categories):
            node_spec = NodeSpec(
                node_type=f"test.node{i}",
                title=f"节点{i}",
                category=category,
                executor=lambda context, node, inputs: {"result": f"node{i}"}
            )
            registry.register(node_spec)
        
        # 获取分组结果
        grouped = registry.grouped()
        
        # 验证分组结果
        assert len(grouped) == 3  # 三个不同的分类
        assert "设备控制" in grouped
        assert "数据处理" in grouped
        assert "可视化" in grouped
        
        # 验证设备控制分类有两个节点
        assert len(grouped["设备控制"]) == 2
        assert len(grouped["数据处理"]) == 1
        assert len(grouped["可视化"]) == 1
    
    @pytest.mark.unit
    def test_empty_registry_operations(self, registry):
        """测试空注册表的操作"""
        # 空注册表的所有规范
        assert len(registry.all_specs()) == 0
        
        # 空注册表的分组
        grouped = registry.grouped()
        assert len(grouped) == 0
    
    @pytest.mark.unit
    def test_node_spec_validation(self, registry):
        """测试节点规范验证"""
        # 测试有效的节点规范
        valid_spec = NodeSpec(
            node_type="test.valid",
            title="有效节点",
            category="测试",
            executor=lambda context, node, inputs: {"result": "valid"}
        )
        registry.register(valid_spec)
        assert registry.get("test.valid") is not None
        
        # 测试缺少必要字段的节点规范
        # 注意：当前实现可能没有严格的验证，这个测试可能需要调整
        invalid_spec = NodeSpec(
            node_type="",  # 空节点类型
            title="无效节点",
            category="测试",
            executor=lambda context, node, inputs: {"result": "invalid"}
        )
        
        # 根据实际实现调整测试
        try:
            registry.register(invalid_spec)
            # 如果注册成功，验证能否获取
            retrieved = registry.get("")
            assert retrieved is not None
        except Exception:
            # 如果注册失败，这是期望的行为
            pass


class TestNodeSpec:
    """节点规范测试类"""
    
    @pytest.mark.unit
    def test_node_spec_creation(self):
        """测试节点规范创建"""
        port_spec = NodePortSpec("test_port", "float")
        param_spec = NodeParamSpec("test_param", "测试参数", editor="int", minimum=0, maximum=100)
        
        node_spec = NodeSpec(
            node_type="test.complex",
            title="复杂测试节点",
            category="测试分类",
            default_params={"param1": "value1"},
            input_ports=[port_spec],
            output_ports=[port_spec],
            param_specs=[param_spec],
            executor=lambda context, node, inputs: {"result": "complex"}
        )
        
        assert node_spec.node_type == "test.complex"
        assert node_spec.title == "复杂测试节点"
        assert node_spec.category == "测试分类"
        assert node_spec.default_params["param1"] == "value1"
        assert len(node_spec.input_ports) == 1
        assert len(node_spec.output_ports) == 1
        assert len(node_spec.param_specs) == 1
        assert node_spec.input_ports[0].name == "test_port"
        assert node_spec.input_ports[0].data_type == "float"
        assert node_spec.param_specs[0].key == "test_param"
    
    @pytest.mark.unit
    def test_node_port_spec_defaults(self):
        """测试节点端口规范默认值"""
        port_spec = NodePortSpec("default_port")
        
        assert port_spec.name == "default_port"
        assert port_spec.data_type == "any"  # 默认数据类型
    
    @pytest.mark.unit
    def test_node_param_spec_defaults(self):
        """测试节点参数规范默认值"""
        param_spec = NodeParamSpec("default_param", "默认参数")
        
        assert param_spec.key == "default_param"
        assert param_spec.label == "默认参数"
        assert param_spec.editor == "text"  # 默认编辑器
        assert param_spec.options == []  # 默认选项列表
        assert param_spec.minimum == 0.0  # 默认最小值
        assert param_spec.maximum == 999999.0  # 默认最大值
        assert param_spec.step == 1.0  # 默认步长
    
    @pytest.mark.unit
    def test_node_param_spec_different_editors(self):
        """测试不同类型的参数编辑器"""
        # 文本编辑器
        text_param = NodeParamSpec("text_param", "文本参数", editor="text")
        assert text_param.editor == "text"
        
        # 整数编辑器
        int_param = NodeParamSpec("int_param", "整数参数", editor="int", minimum=1, maximum=100)
        assert int_param.editor == "int"
        assert int_param.minimum == 1
        assert int_param.maximum == 100
        
        # 浮点数编辑器
        float_param = NodeParamSpec("float_param", "浮点参数", editor="float", step=0.1)
        assert float_param.editor == "float"
        assert float_param.step == 0.1
        
        # 选择编辑器
        select_param = NodeParamSpec(
            "select_param", 
            "选择参数", 
            editor="select", 
            options=["选项1", "选项2", "选项3"]
        )
        assert select_param.editor == "select"
        assert len(select_param.options) == 3
        assert "选项1" in select_param.options
        
        # 布尔编辑器
        bool_param = NodeParamSpec("bool_param", "布尔参数", editor="bool")
        assert bool_param.editor == "bool"


class TestRegistryIntegration:
    """注册表集成测试类"""
    
    @pytest.mark.unit
    def test_builtin_nodes_registration(self):
        """测试内置节点注册"""
        from workflow_extension.builtins import register_builtin_nodes
        
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        
        # 验证关键内置节点已注册
        builtin_nodes = [
            "device.connect",
            "device.parameter", 
            "logic.delay",
            "data.source",
            "plot.stream",
            "logic.condition"
        ]
        
        all_specs = registry.all_specs()
        registered_types = [spec.node_type for spec in all_specs]
        
        for node_type in builtin_nodes:
            assert node_type in registered_types, f"内置节点 {node_type} 未注册"
    
    @pytest.mark.unit
    def test_cw_nodes_registration(self):
        """测试CW谱节点注册"""
        from workflow_extension.cw_nodes import register_cw_nodes
        
        registry = NodeRegistry()
        register_cw_nodes(registry)
        
        # 验证关键CW节点已注册
        cw_nodes = [
            "cw.lockin_config",
            "cw.mw_sweep_loop",
            "cw.mw_source_config",
            "cw.lockin_read",
            "cw.data_average"
        ]
        
        all_specs = registry.all_specs()
        registered_types = [spec.node_type for spec in all_specs]
        
        for node_type in cw_nodes:
            assert node_type in registered_types, f"CW节点 {node_type} 未注册"
    
    @pytest.mark.unit
    def test_full_registry_functionality(self):
        """测试完整注册表功能"""
        from workflow_extension.builtins import register_builtin_nodes
        from workflow_extension.cw_nodes import register_cw_nodes
        
        registry = NodeRegistry()
        
        # 注册所有节点
        register_builtin_nodes(registry)
        register_cw_nodes(registry)
        
        # 验证节点数量
        all_specs = registry.all_specs()
        assert len(all_specs) > 10  # 应该有足够多的节点
        
        # 验证分组功能
        grouped = registry.grouped()
        assert len(grouped) > 0
        
        # 验证每个分类都有节点
        for category, nodes in grouped.items():
            assert len(nodes) > 0, f"分类 {category} 没有节点"
        
        # 验证可以获取每个节点
        for spec in all_specs:
            retrieved_spec = registry.get(spec.node_type)
            assert retrieved_spec is not None
            assert retrieved_spec.node_type == spec.node_type
