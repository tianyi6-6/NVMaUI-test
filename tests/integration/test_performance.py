"""
性能测试

测试工作流系统的性能指标，包括：
- 节点执行性能
- 工作流执行性能
- UI响应性能
- 内存使用性能
- 大规模数据处理性能
"""

import pytest
import time
import psutil
import gc
import threading
from unittest.mock import Mock
from workflow_extension.models import WorkflowGraphModel, WorkflowNodeModel, WorkflowEdgeModel
from workflow_extension.engine import WorkflowExecutor
from workflow_extension.node_registry import NodeRegistry
from workflow_extension.builtins import register_builtin_nodes
from workflow_extension.serializer import save_workflow, load_workflow


class TestNodeExecutionPerformance:
    """节点执行性能测试类"""
    
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
    
    @pytest.mark.performance
    def test_data_source_performance(self, executor, test_context, performance_monitor):
        """测试数据源节点性能"""
        node = WorkflowNodeModel(
            node_id="perf_data_source",
            node_type="data.source",
            title="性能测试数据源",
            position=(0, 0),
            params={}
        )
        
        # 执行多次测试
        iterations = 100
        performance_monitor.start()
        
        for i in range(iterations):
            # 使用正确的节点执行方式
            spec = executor.registry.get(node.node_type)
            result = spec.executor(test_context, node, []) if spec.executor else {}
            assert "x" in result
            assert "y" in result
        
        performance_monitor.stop()
        duration = performance_monitor.get_duration()
        
        # 验证性能（平均每次执行应该在1ms以内）
        avg_time = duration / iterations
        assert avg_time < 0.001  # 1ms以内
    
    @pytest.mark.performance
    def test_delay_node_performance(self, executor, test_context, performance_monitor):
        """测试延时节点性能"""
        node = WorkflowNodeModel(
            node_id="perf_delay",
            node_type="logic.delay",
            title="性能测试延时",
            position=(0, 0),
            params={"delay_ms": 10}  # 10ms延时
        )
        
        performance_monitor.start()
        result = executor._execute_node(node, test_context, [])
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证延时准确性（10ms ± 2ms）
        assert 0.008 <= duration <= 0.012
        assert result["delay_ms"] == 10
    
    @pytest.mark.performance
    def test_plot_stream_performance(self, executor, test_context, performance_monitor):
        """测试绘图流节点性能"""
        node = WorkflowNodeModel(
            node_id="perf_plot",
            node_type="plot.stream",
            title="性能测试绘图",
            position=(0, 0),
            params={}
        )
        
        # 创建大量输入数据
        input_data = {
            "x": list(range(1000)),
            "y": [i * 0.1 for i in range(1000)],
            "series": "performance_test"
        }
        
        performance_monitor.start()
        result = executor._execute_node(node, test_context, [input_data])
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证性能（处理1000个数据点应该在10ms以内）
        assert duration < 0.01
        assert result == input_data
        assert test_context["plot_callback"].call_count == 1


class TestWorkflowExecutionPerformance:
    """工作流执行性能测试类"""
    
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
    
    @pytest.mark.performance
    def test_linear_workflow_performance(self, executor, test_context, performance_monitor):
        """测试线性工作流性能"""
        # 创建100个节点的线性工作流
        nodes = []
        edges = []
        
        for i in range(100):
            nodes.append(WorkflowNodeModel(
                node_id=f"linear_node_{i}",
                node_type="data.source" if i == 0 else "logic.delay",
                title=f"线性节点{i}",
                position=(float(i * 50), 0),
                params={"delay_ms": 1} if i > 0 else {}
            ))
            
            if i > 0:
                edges.append(WorkflowEdgeModel(
                    from_node=f"linear_node_{i-1}",
                    to_node=f"linear_node_{i}"
                ))
        
        workflow = WorkflowGraphModel(
            name="线性性能测试工作流",
            nodes=nodes,
            edges=edges
        )
        
        performance_monitor.start()
        executor.run(workflow, test_context)
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证性能（100个节点应该在2秒内完成）
        assert duration < 2.0
        assert len(test_context["plot_callback"].call_args_list) >= 1
    
    @pytest.mark.performance
    def test_parallel_workflow_performance(self, executor, test_context, performance_monitor):
        """测试并行工作流性能"""
        # 创建并行工作流：10个数据源 -> 1个汇总节点
        nodes = []
        edges = []
        
        # 10个数据源
        for i in range(10):
            nodes.append(WorkflowNodeModel(
                node_id=f"parallel_source_{i}",
                node_type="data.source",
                title=f"并行数据源{i}",
                position=(0, float(i * 30)),
                params={}
            ))
        
        # 1个汇总节点
        nodes.append(WorkflowNodeModel(
            node_id="collector",
            node_type="plot.stream",
            title="数据汇总",
            position=(200, 150),
            params={}
        ))
        
        # 连接所有数据源到汇总
        for i in range(10):
            edges.append(WorkflowEdgeModel(
                from_node=f"parallel_source_{i}",
                to_node="collector"
            ))
        
        workflow = WorkflowGraphModel(
            name="并行性能测试工作流",
            nodes=nodes,
            edges=edges
        )
        
        performance_monitor.start()
        executor.run(workflow, test_context)
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证性能（并行执行应该比串行快）
        assert duration < 1.0
        assert test_context["plot_callback"].call_count >= 10
    
    @pytest.mark.performance
    def test_complex_workflow_performance(self, executor, test_context, performance_monitor):
        """测试复杂工作流性能"""
        # 创建包含分支和合并的复杂工作流
        nodes = []
        edges = []
        
        # 源节点
        nodes.append(WorkflowNodeModel(
            node_id="source",
            node_type="data.source",
            title="数据源",
            position=(0, 100),
            params={}
        ))
        
        # 5个并行分支
        for i in range(5):
            # 条件节点
            nodes.append(WorkflowNodeModel(
                node_id=f"condition_{i}",
                node_type="logic.condition",
                title=f"条件{i}",
                position=(100, float(i * 40)),
                params={"threshold": 0.5}
            ))
            
            # 延时节点
            nodes.append(WorkflowNodeModel(
                node_id=f"delay_{i}",
                node_type="logic.delay",
                title=f"延时{i}",
                position=(200, float(i * 40)),
                params={"delay_ms": 5}
            ))
            
            # 连接
            edges.append(WorkflowEdgeModel(
                from_node="source",
                to_node=f"condition_{i}"
            ))
            edges.append(WorkflowEdgeModel(
                from_node=f"condition_{i}",
                to_node=f"delay_{i}"
            ))
        
        # 汇总节点
        nodes.append(WorkflowNodeModel(
            node_id="collector",
            node_type="plot.stream",
            title="汇总",
            position=(300, 100),
            params={}
        ))
        
        # 连接所有分支到汇总
        for i in range(5):
            edges.append(WorkflowEdgeModel(
                from_node=f"delay_{i}",
                to_node="collector"
            ))
        
        workflow = WorkflowGraphModel(
            name="复杂性能测试工作流",
            nodes=nodes,
            edges=edges
        )
        
        performance_monitor.start()
        executor.run(workflow, test_context)
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证性能（复杂工作流应该在3秒内完成）
        assert duration < 3.0
        assert test_context["plot_callback"].call_count >= 5


class TestMemoryPerformance:
    """内存性能测试类"""
    
    @pytest.mark.performance
    def test_memory_usage_during_execution(self, performance_monitor):
        """测试执行期间的内存使用"""
        # 获取初始内存使用
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 创建大型工作流
        nodes = []
        edges = []
        
        for i in range(500):
            nodes.append(WorkflowNodeModel(
                node_id=f"memory_node_{i}",
                node_type="data.source",
                title=f"内存测试节点{i}",
                position=(float(i * 10), 0),
                params={"large_data": "x" * 1000}  # 较大的参数数据
            ))
            
            if i > 0:
                edges.append(WorkflowEdgeModel(
                    from_node=f"memory_node_{i-1}",
                    to_node=f"memory_node_{i}"
                ))
        
        workflow = WorkflowGraphModel(
            name="内存性能测试工作流",
            nodes=nodes,
            edges=edges
        )
        
        # 创建执行器
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        executor = WorkflowExecutor(registry)
        
        test_context = {
            "plot_callback": Mock(),
            "test_mode": True
        }
        
        performance_monitor.start()
        executor.run(workflow, test_context)
        performance_monitor.stop()
        
        # 获取执行后内存使用
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 强制垃圾回收
        gc.collect()
        
        # 获取垃圾回收后内存使用
        gc_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 验证内存使用合理（增长不超过100MB）
        memory_growth = gc_memory - initial_memory
        assert memory_growth < 100  # 不应该增长超过100MB
        
        # 验证内存泄漏（垃圾回收后内存应该释放）
        assert gc_memory <= final_memory + 10  # 允许10MB误差
    
    @pytest.mark.performance
    def test_large_data_handling(self, performance_monitor):
        """测试大数据处理性能"""
        # 创建包含大数据的工作流
        large_data = {
            "x": list(range(10000)),  # 10000个点
            "y": [i * 0.001 for i in range(10000)],
            "metadata": {"info": "large dataset"} * 1000
        }
        
        nodes = [
            WorkflowNodeModel(
                node_id="large_data_source",
                node_type="data.source",
                title="大数据源",
                position=(0, 0),
                params={}
            ),
            WorkflowNodeModel(
                node_id="large_data_plot",
                node_type="plot.stream",
                title="大数据绘图",
                position=(200, 0),
                params={}
            )
        ]
        
        edges = [
            WorkflowEdgeModel(
                from_node="large_data_source",
                to_node="large_data_plot"
            )
        ]
        
        workflow = WorkflowGraphModel(
            name="大数据性能测试工作流",
            nodes=nodes,
            edges=edges
        )
        
        # 创建执行器
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        executor = WorkflowExecutor(registry)
        
        test_context = {
            "plot_callback": Mock(),
            "test_mode": True
        }
        
        # 模拟大数据源返回
        original_executor = None
        def mock_large_data_executor(context, node, inputs):
            if node.node_type == "data.source":
                return large_data
            elif node.node_type == "plot.stream":
                return inputs[0] if inputs else {}
        
        # 临时替换执行器
        for node_type, spec in registry._specs.items.items():
            if node_type in ["data.source", "plot.stream"]:
                spec.executor = mock_large_data_executor
        
        performance_monitor.start()
        executor.run(workflow, test_context)
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证大数据处理性能（10000个数据点应该在500ms内完成）
        assert duration < 0.5
        assert test_context["plot_callback"].call_count == 1


class TestSerializationPerformance:
    """序列化性能测试类"""
    
    @pytest.mark.performance
    def test_large_workflow_serialization(self, temp_dir, performance_monitor):
        """测试大型工作流序列化性能"""
        # 创建大型工作流
        nodes = []
        edges = []
        
        for i in range(1000):
            nodes.append(WorkflowNodeModel(
                node_id=f"large_serial_node_{i}",
                node_type="test.type",
                title=f"大型序列化节点{i}",
                position=(float(i), float(i)),
                params={
                    "param1": f"value_{i}" * 10,  # 较大的字符串
                    "param2": i,
                    "param3": [i, i+1, i+2] * 10  # 较大的列表
                }
            ))
            
            if i > 0:
                edges.append(WorkflowEdgeModel(
                    from_node=f"large_serial_node_{i-1}",
                    to_node=f"large_serial_node_{i}"
                ))
        
        large_workflow = WorkflowGraphModel(
            name="大型序列化测试工作流",
            nodes=nodes,
            edges=edges
        )
        
        file_path = temp_dir / "large_performance_test.nvw"
        
        # 测试保存性能
        performance_monitor.start()
        save_workflow(large_workflow, str(file_path))
        performance_monitor.checkpoint("save_complete")
        
        # 测试加载性能
        loaded_workflow = load_workflow(str(file_path))
        performance_monitor.checkpoint("load_complete")
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        checkpoints = dict(performance_monitor.checkpoints)
        
        # 验证结果正确性
        assert len(loaded_workflow.nodes) == 1000
        assert len(loaded_workflow.edges) == 999
        
        # 验证性能
        assert duration < 5.0  # 总时间不超过5秒
        assert checkpoints["save_complete"] < 3.0  # 保存不超过3秒
        assert checkpoints["load_complete"] - checkpoints["save_complete"] < 2.0  # 加载不超过2秒
        
        # 验证文件大小
        file_size = file_path.stat().st_size / 1024 / 1024  # MB
        assert file_size > 0  # 文件应该有内容
        assert file_size < 50  # 文件大小合理（小于50MB）
    
    @pytest.mark.performance
    def test_json_export_performance(self, temp_dir, performance_monitor):
        """测试JSON导出性能"""
        # 创建中等大小的工作流用于JSON导出测试
        nodes = []
        edges = []
        
        for i in range(500):
            nodes.append(WorkflowNodeModel(
                node_id=f"json_export_node_{i}",
                node_type="test.export",
                title=f"JSON导出节点{i}",
                position=(float(i * 2), float(i)),
                params={"data": f"test_data_{i}" * 5}
            ))
            
            if i > 0:
                edges.append(WorkflowEdgeModel(
                    from_node=f"json_export_node_{i-1}",
                    to_node=f"json_export_node_{i}"
                ))
        
        workflow = WorkflowGraphModel(
            name="JSON导出性能测试工作流",
            nodes=nodes,
            edges=edges
        )
        
        file_path = temp_dir / "json_export_performance_test.json"
        
        performance_monitor.start()
        from workflow_extension.serializer import export_json
        export_json(workflow, str(file_path))
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证性能（JSON导出500个节点应该在2秒内完成）
        assert duration < 2.0
        
        # 验证文件大小和内容
        assert file_path.exists()
        file_size = file_path.stat().st_size / 1024  # KB
        assert file_size > 0
        assert file_size < 1000  # 小于1MB


class TestConcurrencyPerformance:
    """并发性能测试类"""
    
    @pytest.mark.performance
    def test_concurrent_workflow_execution(self, performance_monitor):
        """测试并发工作流执行"""
        # 创建多个工作流
        workflows = []
        
        for workflow_id in range(5):
            nodes = [
                WorkflowNodeModel(
                    node_id=f"concurrent_source_{workflow_id}",
                    node_type="data.source",
                    title=f"并发数据源{workflow_id}",
                    position=(0, 0),
                    params={"workflow_id": workflow_id}
                ),
                WorkflowNodeModel(
                    node_id=f"concurrent_delay_{workflow_id}",
                    node_type="logic.delay",
                    title=f"并发延时{workflow_id}",
                    position=(100, 0),
                    params={"delay_ms": 50}
                )
            ]
            
            edges = [
                WorkflowEdgeModel(
                    from_node=f"concurrent_source_{workflow_id}",
                    to_node=f"concurrent_delay_{workflow_id}"
                )
            ]
            
            workflows.append(WorkflowGraphModel(
                name=f"并发工作流{workflow_id}",
                nodes=nodes,
                edges=edges
            ))
        
        # 创建执行器
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        
        def execute_workflow(workflow, workflow_id):
            executor = WorkflowExecutor(registry)
            test_context = {
                "plot_callback": Mock(),
                "test_mode": True,
                "workflow_id": workflow_id
            }
            executor.run(workflow, test_context)
        
        # 并发执行
        threads = []
        performance_monitor.start()
        
        for i, workflow in enumerate(workflows):
            thread = threading.Thread(target=execute_workflow, args=(workflow, i))
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证并发性能（5个工作流并发应该在2秒内完成）
        assert duration < 2.0
    
    @pytest.mark.performance
    def test_ui_thread_responsiveness(self, performance_monitor):
        """测试UI线程响应性"""
        # 模拟UI操作
        ui_operations = []
        
        def simulate_ui_operation():
            """模拟UI操作"""
            time.sleep(0.01)  # 模拟UI处理时间
            return "ui_result"
        
        # 在后台执行工作流的同时进行UI操作
        def background_workflow():
            registry = NodeRegistry()
            register_builtin_nodes(registry)
            executor = WorkflowExecutor(registry)
            
            workflow = WorkflowGraphModel(
                name="后台工作流",
                nodes=[
                    WorkflowNodeModel(
                        node_id="bg_source",
                        node_type="data.source",
                        title="后台数据源",
                        position=(0, 0),
                        params={}
                    )
                ],
                edges=[]
            )
            
            test_context = {"test_mode": True}
            executor.run(workflow, test_context)
        
        performance_monitor.start()
        
        # 启动后台工作流
        bg_thread = threading.Thread(target=background_workflow)
        bg_thread.start()
        
        # 在工作流执行期间模拟UI操作
        ui_start_time = time.time()
        while bg_thread.is_alive():
            ui_result = simulate_ui_operation()
            ui_operations.append(ui_result)
            
            # 防止无限循环
            if time.time() - ui_start_time > 5.0:
                break
        
        bg_thread.join()
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证UI响应性
        assert len(ui_operations) > 0  # 应该有UI操作
        assert duration < 5.0  # 总时间合理


class TestPerformanceRegression:
    """性能回归测试类"""
    
    @pytest.mark.performance
    def test_performance_baseline(self, performance_monitor):
        """性能基准测试"""
        # 定义性能基准
        performance_baselines = {
            "simple_node_execution": 0.001,  # 1ms
            "linear_workflow_50_nodes": 1.0,  # 1秒
            "parallel_workflow_10_nodes": 0.5,  # 500ms
            "memory_usage_growth": 50.0,  # 50MB
            "serialization_100_nodes": 0.5  # 500ms
        }
        
        # 简单节点执行基准
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        executor = WorkflowExecutor(registry)
        
        node = WorkflowNodeModel(
            node_id="baseline_node",
            node_type="data.source",
            title="基准测试节点",
            position=(0, 0),
            params={}
        )
        
        test_context = {"test_mode": True}
        
        performance_monitor.start()
        result = executor._execute_node(node, test_context, [])
        performance_monitor.stop()
        
        simple_node_time = performance_monitor.get_duration()
        
        # 验证性能回归
        assert simple_node_time < performance_baselines["simple_node_execution"], \
            f"简单节点执行性能回归: {simple_node_time:.3f}s > {performance_baselines['simple_node_execution']}s"
        
        # 线性工作流基准
        nodes = []
        edges = []
        
        for i in range(50):
            nodes.append(WorkflowNodeModel(
                node_id=f"baseline_linear_{i}",
                node_type="logic.delay",
                title=f"基准线性{i}",
                position=(float(i * 20), 0),
                params={"delay_ms": 1}
            ))
            
            if i > 0:
                edges.append(WorkflowEdgeModel(
                    from_node=f"baseline_linear_{i-1}",
                    to_node=f"baseline_linear_{i}"
                ))
        
        workflow = WorkflowGraphModel(
            name="基准线性工作流",
            nodes=nodes,
            edges=edges
        )
        
        performance_monitor.start()
        executor.run(workflow, test_context)
        performance_monitor.stop()
        
        linear_workflow_time = performance_monitor.get_duration()
        
        assert linear_workflow_time < performance_baselines["linear_workflow_50_nodes"], \
            f"线性工作流性能回归: {linear_workflow_time:.3f}s > {performance_baselines['linear_workflow_50_nodes']}s"
        
        # 输出性能报告
        print(f"\n性能基准测试结果:")
        print(f"简单节点执行: {simple_node_time:.3f}s (基准: {performance_baselines['simple_node_execution']}s)")
        print(f"线性工作流(50节点): {linear_workflow_time:.3f}s (基准: {performance_baselines['linear_workflow_50_nodes']}s)")
