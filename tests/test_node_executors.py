"""
节点执行器单元测试

测试工作流系统中各种节点的执行器功能，包括：
- 内置节点执行器测试
- CW谱节点执行器测试
- 异常处理测试
- 参数验证测试
"""

import pytest
import time
from unittest.mock import Mock, patch
from workflow_extension.models import WorkflowNodeModel
from workflow_extension.builtins import (
    _exec_device_connect,
    _exec_parameter_config,
    _exec_delay,
    _exec_data_source,
    _exec_plot_stream,
    _exec_logic_condition
)
from workflow_extension.cw_nodes import (
    _exec_lockin_config,
    _exec_mw_source_config,
    _exec_lockin_read,
    _exec_data_average
)


class TestBuiltinNodeExecutors:
    """内置节点执行器测试类"""
    
    @pytest.mark.unit
    def test_device_connect_success(self, test_context):
        """测试设备连接成功情况"""
        node = WorkflowNodeModel(
            node_id="device_1",
            node_type="device.connect",
            title="设备连接",
            position=(0, 0),
            params={}
        )
        
        result = _exec_device_connect(test_context, node, [])
        
        assert result["connected"] is True
        assert "message" in result
        assert "设备已存在连接实例" in result["message"]
    
    @pytest.mark.unit
    def test_device_connect_no_app(self):
        """测试设备连接无应用实例情况"""
        context = {}  # 无app实例
        node = WorkflowNodeModel(
            node_id="device_1",
            node_type="device.connect",
            title="设备连接",
            position=(0, 0),
            params={}
        )
        
        result = _exec_device_connect(context, node, [])
        
        assert result["connected"] is False
        assert result["message"] == "未连接"
    
    @pytest.mark.unit
    def test_parameter_config(self, test_context):
        """测试参数配置节点"""
        node = WorkflowNodeModel(
            node_id="param_1",
            node_type="device.parameter",
            title="参数配置",
            position=(0, 0),
            params={"test_param": "test_value", "number": 123}
        )
        
        result = _exec_parameter_config(test_context, node, [])
        
        assert result["configured"] is True
        assert "params" in result
        assert result["params"]["test_param"] == "test_value"
        assert result["params"]["number"] == 123
    
    @pytest.mark.unit
    def test_delay_executor(self, test_context):
        """测试延时执行器"""
        node = WorkflowNodeModel(
            node_id="delay_1",
            node_type="logic.delay",
            title="延时",
            position=(0, 0),
            params={"delay_ms": 100}
        )
        
        start_time = time.time()
        result = _exec_delay(test_context, node, [])
        end_time = time.time()
        
        assert result["delay_ms"] == 100
        # 验证实际延时时间（允许10ms误差）
        assert (end_time - start_time) >= 0.09
    
    @pytest.mark.unit
    def test_data_source_executor(self, test_context):
        """测试数据源执行器"""
        node = WorkflowNodeModel(
            node_id="data_1",
            node_type="data.source",
            title="数据源",
            position=(0, 0),
            params={}
        )
        
        result = _exec_data_source(test_context, node, [])
        
        assert "x" in result
        assert "y" in result
        assert isinstance(result["x"], float)
        assert isinstance(result["y"], float)
        assert 0 <= result["y"] <= 1  # 随机值范围检查
    
    @pytest.mark.unit
    def test_plot_stream_executor(self, test_context):
        """测试绘图流执行器"""
        node = WorkflowNodeModel(
            node_id="plot_1",
            node_type="plot.stream",
            title="绘图",
            position=(0, 0),
            params={}
        )
        
        # 测试有输入数据的情况
        input_data = {"x": 1.0, "y": 2.0, "series": "test"}
        result = _exec_plot_stream(test_context, node, [input_data])
        
        assert result == input_data
        # 验证回调函数被调用
        test_context["plot_callback"].assert_called_once_with(input_data)
    
    @pytest.mark.unit
    def test_plot_stream_no_input(self, test_context):
        """测试绘图流执行器无输入情况"""
        node = WorkflowNodeModel(
            node_id="plot_1",
            node_type="plot.stream",
            title="绘图",
            position=(0, 0),
            params={}
        )
        
        result = _exec_plot_stream(test_context, node, [])
        
        assert result == {}
        # 无输入时不应该调用回调
        test_context["plot_callback"].assert_not_called()
    
    @pytest.mark.unit
    def test_logic_condition_executor(self, test_context):
        """测试逻辑条件执行器"""
        node = WorkflowNodeModel(
            node_id="logic_1",
            node_type="logic.condition",
            title="逻辑判断",
            position=(0, 0),
            params={"threshold": 0.5}
        )
        
        # 测试通过条件
        input_data = {"y": 0.8}
        result = _exec_logic_condition(test_context, node, [input_data])
        
        assert result["passed"] is True
        assert result["value"] == 0.8
        assert result["threshold"] == 0.5
        
        # 测试不通过条件
        input_data = {"y": 0.3}
        result = _exec_logic_condition(test_context, node, [input_data])
        
        assert result["passed"] is False
        assert result["value"] == 0.3


class TestCWNodeExecutors:
    """CW谱节点执行器测试类"""
    
    @pytest.mark.unit
    def test_lockin_config_success(self, test_context):
        """测试锁相放大器配置成功"""
        node = WorkflowNodeModel(
            node_id="lockin_1",
            node_type="cw.lockin_config",
            title="锁相配置",
            position=(0, 0),
            params={
                "mod_freq": 1000,
                "sample_freq": 10000,
                "time_constant": 10,
                "sensitivity": 1.0
            }
        )
        
        result = _exec_lockin_config(test_context, node, [])
        
        assert result["configured"] is True
        assert result["mod_freq"] == 1000
        assert result["sample_freq"] == 10000
        assert result["time_constant"] == 10
        assert result["sensitivity"] == 1.0
    
    @pytest.mark.unit
    def test_mw_source_config_success(self, test_context):
        """测试微波源配置成功"""
        node = WorkflowNodeModel(
            node_id="mw_1",
            node_type="cw.mw_source_config",
            title="微波源配置",
            position=(0, 0),
            params={"power": 0, "fm_sens": 1.0}
        )
        
        input_data = {"mw_freq": 1500}
        result = _exec_mw_source_config(test_context, node, [input_data])
        
        assert result["configured"] is True
        assert result["mw_freq"] == 1500
        assert result["power"] == 0
        assert result["fm_sens"] == 1.0
    
    @pytest.mark.unit
    def test_lockin_read_success(self, test_context):
        """测试锁相数据读取成功"""
        node = WorkflowNodeModel(
            node_id="read_1",
            node_type="cw.lockin_read",
            title="数据读取",
            position=(0, 0),
            params={"channels": ["input1-x", "input1-y"], "sample_points": 10}
        )
        
        with patch('workflow_extension.cw_nodes._simulate_lockin_reading') as mock_read:
            import numpy as np
            mock_data = np.random.random((10, 2))
            mock_read.return_value = mock_data
            
            result = _exec_lockin_read(test_context, node, [])
            
            assert result["configured"] is True
            assert "channels" in result
            assert "sample_points" in result
            assert result["channels"] == ["input1-x", "input1-y"]
            assert result["sample_points"] == 10
    
    @pytest.mark.unit
    def test_data_average_success(self, test_context):
        """测试数据平均处理成功"""
        node = WorkflowNodeModel(
            node_id="avg_1",
            node_type="cw.data_average",
            title="数据平均",
            position=(0, 0),
            params={}
        )
        
        # 创建模拟数据
        import numpy as np
        cw_data = np.random.random((100, 10, 2))  # 100个点，10个样本，2个通道
        input_data = {"cw_data": cw_data}
        
        result = _exec_data_average(test_context, node, [input_data])
        
        assert "cw_data_avg" in result
        assert "original_shape" in result
        assert "processed_shape" in result
        assert result["original_shape"] == (100, 10, 2)
        assert result["processed_shape"] == (100, 2)  # 平均后维度变化


class TestNodeExecutorExceptions:
    """节点执行器异常处理测试类"""
    
    @pytest.mark.unit
    def test_lockin_config_exception(self, test_context):
        """测试锁相配置异常处理"""
        node = WorkflowNodeModel(
            node_id="lockin_error",
            node_type="cw.lockin_config",
            title="锁相配置",
            position=(0, 0),
            params={"mod_freq": "invalid"}  # 无效参数
        )
        
        result = _exec_lockin_config(test_context, node, [])
        
        assert result["configured"] is False
        assert "error" in result
    
    @pytest.mark.unit
    def test_mw_source_config_exception(self, test_context):
        """测试微波源配置异常处理"""
        node = WorkflowNodeModel(
            node_id="mw_error",
            node_type="cw.mw_source_config",
            title="微波源配置",
            position=(0, 0),
            params={"power": "invalid"}  # 无效参数
        )
        
        result = _exec_mw_source_config(test_context, node, [])
        
        assert result["configured"] is False
        assert "error" in result
    
    @pytest.mark.unit
    def test_data_average_exception(self, test_context):
        """测试数据平均异常处理"""
        node = WorkflowNodeModel(
            node_id="avg_error",
            node_type="cw.data_average",
            title="数据平均",
            position=(0, 0),
            params={}
        )
        
        # 传入无效数据
        input_data = {"cw_data": "invalid_data"}
        result = _exec_data_average(test_context, node, [input_data])
        
        assert "error" in result


class TestNodeExecutorPerformance:
    """节点执行器性能测试类"""
    
    @pytest.mark.unit
    @pytest.mark.performance
    def test_delay_performance(self, test_context, performance_monitor):
        """测试延时节点性能"""
        node = WorkflowNodeModel(
            node_id="delay_perf",
            node_type="logic.delay",
            title="延时性能测试",
            position=(0, 0),
            params={"delay_ms": 50}  # 50ms延时
        )
        
        performance_monitor.start()
        result = _exec_delay(test_context, node, [])
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        assert result["delay_ms"] == 50
        # 验证执行时间在合理范围内（50ms ± 10ms）
        assert 0.04 <= duration <= 0.06
    
    @pytest.mark.unit
    @pytest.mark.performance
    def test_data_source_performance(self, test_context, performance_monitor):
        """测试数据源节点性能"""
        node = WorkflowNodeModel(
            node_id="data_perf",
            node_type="data.source",
            title="数据源性能测试",
            position=(0, 0),
            params={}
        )
        
        performance_monitor.start()
        result = _exec_data_source(test_context, node, [])
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 数据源生成应该很快（< 10ms）
        assert duration < 0.01
        assert "x" in result
        assert "y" in result
