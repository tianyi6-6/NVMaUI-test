"""
工作流集成测试

测试完整工作流的执行功能，包括：
- 简单工作流执行
- 复杂工作流执行
- 错误处理工作流
- 并行执行测试
- 状态监控测试
"""

import pytest
import time
from unittest.mock import Mock, patch
from workflow_extension.models import WorkflowGraphModel, WorkflowNodeModel, WorkflowEdgeModel
from workflow_extension.engine import WorkflowExecutor
from workflow_extension.node_registry import NodeRegistry
from workflow_extension.builtins import register_builtin_nodes


class TestSimpleWorkflowExecution:
    """简单工作流执行测试类"""
    
    @pytest.fixture
    def simple_workflow(self):
        """简单工作流：数据源 -> 延时 -> 绘图"""
        nodes = [
            WorkflowNodeModel(
                node_id="data_source",
                node_type="data.source",
                title="数据源",
                position=(50.0, 50.0),
                params={}
            ),
            WorkflowNodeModel(
                node_id="delay",
                node_type="logic.delay",
                title="延时",
                position=(200.0, 50.0),
                params={"delay_ms": 50}
            ),
            WorkflowNodeModel(
                node_id="plot",
                node_type="plot.stream",
                title="绘图",
                position=(350.0, 50.0),
                params={}
            )
        ]
        
        edges = [
            WorkflowEdgeModel(
                from_node="data_source",
                to_node="delay",
                from_port="out",
                to_port="in"
            ),
            WorkflowEdgeModel(
                from_node="delay",
                to_node="plot",
                from_port="out",
                to_port="in"
            )
        ]
        
        return WorkflowGraphModel(
            name="简单测试工作流",
            nodes=nodes,
            edges=edges
        )
    
    @pytest.fixture
    def executor(self):
        """创建工作流执行器"""
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        return WorkflowExecutor(registry)
    
    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        plot_callback = Mock()
        return {
            "plot_callback": plot_callback,
            "test_mode": True
        }
    
    @pytest.mark.integration
    def test_simple_workflow_execution(self, simple_workflow, executor, test_context):
        """测试简单工作流执行"""
        # 执行工作流
        executor.run(simple_workflow, test_context)
        
        # 验证绘图回调被调用
        assert test_context["plot_callback"].call_count > 0
        
        # 验证回调参数格式（延时节点传递的是delay_ms参数）
        call_args = test_context["plot_callback"].call_args
        if call_args:
            plot_data = call_args[0][0] if call_args[0] else {}
            # 绘图节点接收到的是延时节点的输出，包含delay_ms
            assert "delay_ms" in plot_data or "x" in plot_data or "y" in plot_data
    
    @pytest.mark.integration
    def test_workflow_execution_signals(self, simple_workflow, executor, test_context):
        """测试工作流执行信号"""
        # 监听信号
        started_signals = []
        finished_signals = []
        failed_signals = []
        run_finished = False
        
        def on_node_started(node_id):
            started_signals.append(node_id)
        
        def on_node_finished(node_id, result):
            finished_signals.append((node_id, result))
        
        def on_node_failed(node_id, error):
            failed_signals.append((node_id, error))
        
        def on_run_finished():
            nonlocal run_finished
            run_finished = True
        
        # 连接信号
        executor.node_started.connect(on_node_started)
        executor.node_finished.connect(on_node_finished)
        executor.node_failed.connect(on_node_failed)
        executor.run_finished.connect(on_run_finished)
        
        # 执行工作流
        executor.run(simple_workflow, test_context)
        
        # 验证信号
        assert len(started_signals) == 3  # 三个节点
        assert len(finished_signals) == 3  # 三个节点完成
        assert len(failed_signals) == 0   # 没有失败
        assert run_finished is True        # 执行完成
        
        # 验证节点执行顺序
        expected_order = ["data_source", "delay", "plot"]
        assert started_signals == expected_order
    
    @pytest.mark.integration
    def test_workflow_stop_execution(self, simple_workflow, executor, test_context):
        """测试工作流停止执行"""
        # 创建较长的延时工作流
        long_delay_workflow = WorkflowGraphModel(
            name="长延时测试工作流",
            nodes=[
                WorkflowNodeModel(
                    node_id="data_source",
                    node_type="data.source",
                    title="数据源",
                    position=(50.0, 50.0),
                    params={}
                ),
                WorkflowNodeModel(
                    node_id="long_delay",
                    node_type="logic.delay",
                    title="长延时",
                    position=(200.0, 50.0),
                    params={"delay_ms": 1000}  # 1秒延时
                )
            ],
            edges=[
                WorkflowEdgeModel(
                    from_node="data_source",
                    to_node="long_delay",
                    from_port="out",
                    to_port="in"
                )
            ]
        )
        
        # 监听信号
        started_nodes = []
        finished_nodes = []
        
        def on_node_started(node_id):
            started_nodes.append(node_id)
        
        def on_node_finished(node_id, result):
            finished_nodes.append(node_id)
        
        executor.node_started.connect(on_node_started)
        executor.node_finished.connect(on_node_finished)
        
        # 在另一个线程中执行工作流
        import threading
        execution_thread = threading.Thread(
            target=executor.run, 
            args=(long_delay_workflow, test_context)
        )
        execution_thread.start()
        
        # 等待第一个节点开始执行
        time.sleep(0.1)
        
        # 停止执行
        executor.stop()
        
        # 等待线程结束
        execution_thread.join(timeout=2.0)
        
        # 验证执行被中断
        assert len(started_nodes) >= 1  # 至少开始了一个节点
        # 第二个节点可能没有完成（因为被停止）
        assert "long_delay" not in finished_nodes or len(finished_nodes) < 2


class TestComplexWorkflowExecution:
    """复杂工作流执行测试类"""
    
    @pytest.fixture
    def complex_workflow(self):
        """复杂工作流：包含分支和合并"""
        nodes = [
            # 数据源
            WorkflowNodeModel(
                node_id="source",
                node_type="data.source",
                title="数据源",
                position=(50.0, 100.0),
                params={}
            ),
            # 分支1：条件判断
            WorkflowNodeModel(
                node_id="condition1",
                node_type="logic.condition",
                title="条件判断1",
                position=(200.0, 50.0),
                params={"threshold": 0.5}
            ),
            # 分支2：延时
            WorkflowNodeModel(
                node_id="delay1",
                node_type="logic.delay",
                title="延时1",
                position=(200.0, 150.0),
                params={"delay_ms": 10}
            ),
            # 合并节点
            WorkflowNodeModel(
                node_id="merge",
                node_type="plot.stream",
                title="合并绘图",
                position=(350.0, 100.0),
                params={}
            )
        ]
        
        edges = [
            # 源到两个分支
            WorkflowEdgeModel(
                from_node="source",
                to_node="condition1",
                from_port="out",
                to_port="in"
            ),
            WorkflowEdgeModel(
                from_node="source",
                to_node="delay1",
                from_port="out",
                to_port="in"
            ),
            # 两个分支到合并
            WorkflowEdgeModel(
                from_node="condition1",
                to_node="merge",
                from_port="out",
                to_port="in"
            ),
            WorkflowEdgeModel(
                from_node="delay1",
                to_node="merge",
                from_port="out",
                to_port="in"
            )
        ]
        
        return WorkflowGraphModel(
            name="复杂测试工作流",
            nodes=nodes,
            edges=edges
        )
    
    @pytest.fixture
    def executor(self):
        """创建工作流执行器"""
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        return WorkflowExecutor(registry)
    
    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        return {
            "plot_callback": Mock(),
            "test_mode": True
        }
    
    @pytest.mark.integration
    def test_complex_workflow_execution(self, complex_workflow, executor, test_context):
        """测试复杂工作流执行"""
        # 执行工作流
        executor.run(complex_workflow, test_context)
        
        # 验证绘图回调被调用（可能多次，因为有两个分支）
        assert test_context["plot_callback"].call_count >= 1
    
    @pytest.mark.integration
    def test_workflow_data_flow(self, complex_workflow, executor, test_context):
        """测试工作流数据流"""
        # 监听节点完成信号以捕获数据流
        node_results = {}
        
        def on_node_finished(node_id, result):
            node_results[node_id] = result
        
        executor.node_finished.connect(on_node_finished)
        
        # 执行工作流
        executor.run(complex_workflow, test_context)
        
        # 验证数据流
        assert "source" in node_results
        assert "condition1" in node_results
        assert "delay1" in node_results
        
        # 验证数据源产生数据
        source_result = node_results["source"]
        assert "x" in source_result
        assert "y" in source_result
        
        # 验证条件判断使用数据
        condition_result = node_results["condition1"]
        assert "passed" in condition_result
        assert "value" in condition_result
        assert "threshold" in condition_result


class TestErrorHandlingWorkflow:
    """错误处理工作流测试类"""
    
    @pytest.fixture
    def error_workflow(self):
        """包含错误的工作流"""
        nodes = [
            WorkflowNodeModel(
                node_id="source",
                node_type="data.source",
                title="正常数据源",
                position=(50.0, 50.0),
                params={}
            ),
            WorkflowNodeModel(
                node_id="error_node",
                node_type="nonexistent.type",  # 不存在的节点类型
                title="错误节点",
                position=(200.0, 50.0),
                params={}
            ),
            WorkflowNodeModel(
                node_id="backup",
                node_type="plot.stream",
                title="备用绘图",
                position=(350.0, 50.0),
                params={}
            )
        ]
        
        edges = [
            WorkflowEdgeModel(
                from_node="source",
                to_node="error_node",
                from_port="out",
                to_port="in"
            ),
            WorkflowEdgeModel(
                from_node="error_node",
                to_node="backup",
                from_port="out",
                to_port="in"
            )
        ]
        
        return WorkflowGraphModel(
            name="错误处理测试工作流",
            nodes=nodes,
            edges=edges
        )
    
    @pytest.fixture
    def executor(self):
        """创建工作流执行器"""
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        return WorkflowExecutor(registry)
    
    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        return {
            "plot_callback": Mock(),
            "test_mode": True
        }
    
    @pytest.mark.integration
    def test_workflow_error_handling(self, error_workflow, executor, test_context):
        """测试工作流错误处理"""
        # 监听信号
        failed_nodes = []
        finished_nodes = []
        
        def on_node_failed(node_id, error):
            failed_nodes.append((node_id, error))
        
        def on_node_finished(node_id, result):
            finished_nodes.append((node_id, result))
        
        def on_run_finished():
            pass
        
        executor.node_failed.connect(on_node_failed)
        executor.node_finished.connect(on_node_finished)
        executor.run_finished.connect(on_run_finished)
        
        # 执行工作流
        executor.run(error_workflow, test_context)
        
        # 验证错误处理
        assert len(failed_nodes) == 1  # 一个节点失败
        assert failed_nodes[0][0] == "error_node"  # 错误节点失败
        assert "error" in failed_nodes[0][1]  # 包含错误信息
        
        # 验证正常节点仍然执行
        assert "source" in [node_id for node_id, _ in finished_nodes]
        
        # 备用节点不应该执行（因为上游失败）
        backup_executed = any(node_id == "backup" for node_id, _ in finished_nodes)
        assert not backup_executed


class TestWorkflowPerformance:
    """工作流性能测试类"""
    
    @pytest.fixture
    def performance_workflow(self):
        """性能测试工作流：多个节点并行执行"""
        nodes = []
        edges = []
        
        # 创建多个独立的数据源
        for i in range(10):
            nodes.append(WorkflowNodeModel(
                node_id=f"source_{i}",
                node_type="data.source",
                title=f"数据源{i}",
                position=(50.0, float(i * 30)),
                params={}
            ))
        
        # 创建一个汇总节点
        nodes.append(WorkflowNodeModel(
            node_id="collector",
            node_type="plot.stream",
            title="数据汇总",
            position=(200.0, 150.0),
            params={}
        ))
        
        # 连接所有数据源到汇总节点
        for i in range(10):
            edges.append(WorkflowEdgeModel(
                from_node=f"source_{i}",
                to_node="collector",
                from_port="out",
                to_port="in"
            ))
        
        return WorkflowGraphModel(
            name="性能测试工作流",
            nodes=nodes,
            edges=edges
        )
    
    @pytest.fixture
    def executor(self):
        """创建工作流执行器"""
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        return WorkflowExecutor(registry)
    
    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        return {
            "plot_callback": Mock(),
            "test_mode": True
        }
    
    @pytest.mark.integration
    @pytest.mark.performance
    def test_workflow_performance(self, performance_workflow, executor, test_context, performance_monitor):
        """测试工作流执行性能"""
        # 监听执行完成信号
        execution_completed = False
        
        def on_run_finished():
            nonlocal execution_completed
            execution_completed = True
        
        executor.run_finished.connect(on_run_finished)
        
        # 开始性能监控
        performance_monitor.start()
        
        # 执行工作流
        executor.run(performance_workflow, test_context)
        
        # 停止性能监控
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证执行完成
        assert execution_completed is True
        
        # 验证性能（应该在合理时间内完成）
        assert duration < 5.0  # 5秒内完成
        
        # 验证所有节点都执行了
        assert test_context["plot_callback"].call_count >= 10  # 至少10次调用


class TestWorkflowStateManagement:
    """工作流状态管理测试类"""
    
    @pytest.fixture
    def state_workflow(self):
        """状态管理测试工作流"""
        nodes = [
            WorkflowNodeModel(
                node_id="start",
                node_type="demo.start",
                title="开始",
                position=(50.0, 50.0),
                params={"seed": 42}
            ),
            WorkflowNodeModel(
                node_id="device",
                node_type="demo.init_device",
                title="初始化设备",
                position=(200.0, 50.0),
                params={}
            ),
            WorkflowNodeModel(
                node_id="scan",
                node_type="demo.coarse_scan",
                title="扫描",
                position=(350.0, 50.0),
                params={"points": 50}
            )
        ]
        
        edges = [
            WorkflowEdgeModel(
                from_node="start",
                to_node="device",
                from_port="out",
                to_port="in"
            ),
            WorkflowEdgeModel(
                from_node="device",
                to_node="scan",
                from_port="out",
                to_port="in"
            )
        ]
        
        return WorkflowGraphModel(
            name="状态管理测试工作流",
            nodes=nodes,
            edges=edges
        )
    
    @pytest.fixture
    def executor(self):
        """创建工作流执行器"""
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        return WorkflowExecutor(registry)
    
    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        return {
            "plot_callback": Mock(),
            "test_mode": True
        }
    
    @pytest.mark.integration
    def test_workflow_state_propagation(self, state_workflow, executor, test_context):
        """测试工作流状态传播"""
        # 监听节点完成信号
        node_results = {}
        
        def on_node_finished(node_id, result):
            node_results[node_id] = result
        
        executor.node_finished.connect(on_node_finished)
        
        # 执行工作流
        executor.run(state_workflow, test_context)
        
        # 验证状态传播
        assert "start" in node_results
        assert "device" in node_results
        assert "scan" in node_results
        
        # 验证开始节点设置了状态
        start_result = node_results["start"]
        assert "seed" in start_result
        assert start_result["seed"] == 42
        
        # 验证扫描节点使用了状态
        scan_result = node_results["scan"]
        assert "curve_x" in scan_result
        assert "curve_y" in scan_result
        assert len(scan_result["curve_x"]) == 50  # 扫描点数
        assert len(scan_result["curve_y"]) == 50
