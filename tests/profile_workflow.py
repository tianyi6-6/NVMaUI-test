#!/usr/bin/env python3
"""
工作流性能分析工具

提供工作流系统的性能分析功能，包括：
- cProfile性能分析
- 内存使用分析
- 函数调用统计
- 性能瓶颈识别
"""

import cProfile
import pstats
import io
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import Mock

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from workflow_extension.models import WorkflowGraphModel, WorkflowNodeModel, WorkflowEdgeModel
from workflow_extension.engine import WorkflowExecutor
from workflow_extension.node_registry import NodeRegistry
from workflow_extension.builtins import register_builtin_nodes


class WorkflowProfiler:
    """工作流性能分析器"""
    
    def __init__(self):
        self.profiler = cProfile.Profile()
        self.results = {}
    
    def profile_node_execution(self, node_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """分析单个节点执行性能"""
        if params is None:
            params = {}
        
        # 创建节点
        node = WorkflowNodeModel(
            node_id="profile_node",
            node_type=node_type,
            title="性能分析节点",
            position=(0, 0),
            params=params
        )
        
        # 创建执行器
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        executor = WorkflowExecutor(registry)
        
        test_context = {"test_mode": True}
        
        # 开始性能分析
        self.profiler.enable()
        
        try:
            # 执行节点多次以获得平均性能
            iterations = 100
            start_time = time.time()
            
            for _ in range(iterations):
                result = executor._execute_node(node, test_context, [])
            
            end_time = time.time()
            
        finally:
            self.profiler.disable()
        
        # 计算性能指标
        total_time = end_time - start_time
        avg_time = total_time / iterations
        
        # 获取统计信息
        stats = pstats.Stats(self.profiler)
        stats.sort_stats('cumulative')
        
        # 捕获统计输出
        stats_stream = io.StringIO()
        stats.print_stats(20)  # 打印前20个最耗时的函数
        stats_output = stats_stream.getvalue()
        
        return {
            "node_type": node_type,
            "iterations": iterations,
            "total_time": total_time,
            "avg_time": avg_time,
            "stats_output": stats_output
        }
    
    def profile_workflow_execution(self, workflow: WorkflowGraphModel) -> Dict[str, Any]:
        """分析工作流执行性能"""
        # 创建执行器
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        executor = WorkflowExecutor(registry)
        
        test_context = {"test_mode": True}
        
        # 开始性能分析
        self.profiler.enable()
        
        try:
            start_time = time.time()
            executor.run(workflow, test_context)
            end_time = time.time()
            
        finally:
            self.profiler.disable()
        
        # 计算性能指标
        total_time = end_time - start_time
        
        # 获取统计信息
        stats = pstats.Stats(self.profiler)
        stats.sort_stats('cumulative')
        
        # 捕获统计输出
        stats_stream = io.StringIO()
        stats.print_stats(30)  # 打印前30个最耗时的函数
        stats_output = stats_stream.getvalue()
        
        # 获取函数调用统计
        function_stats = {}
        for func_info, (cc, nc, tt, ct, callers) in stats.stats.items():
            filename, line, func_name = func_info
            function_stats[func_name] = {
                "call_count": cc,
                "total_time": tt,
                "cumulative_time": ct,
                "per_call": tt / cc if cc > 0 else 0
            }
        
        return {
            "workflow_name": workflow.name,
            "node_count": len(workflow.nodes),
            "edge_count": len(workflow.edges),
            "total_time": total_time,
            "stats_output": stats_output,
            "function_stats": function_stats
        }
    
    def profile_memory_usage(self, workflow: WorkflowGraphModel) -> Dict[str, Any]:
        """分析内存使用情况"""
        import psutil
        import gc
        
        # 获取当前进程
        process = psutil.Process()
        
        # 记录初始内存
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 创建执行器
        registry = NodeRegistry()
        register_builtin_nodes(registry)
        executor = WorkflowExecutor(registry)
        
        test_context = {"test_mode": True}
        
        # 执行工作流
        start_time = time.time()
        executor.run(workflow, test_context)
        end_time = time.time()
        
        # 记录执行后内存
        execution_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 强制垃圾回收
        gc.collect()
        
        # 记录垃圾回收后内存
        gc_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        return {
            "workflow_name": workflow.name,
            "execution_time": end_time - start_time,
            "initial_memory_mb": initial_memory,
            "execution_memory_mb": execution_memory,
            "gc_memory_mb": gc_memory,
            "memory_growth_mb": gc_memory - initial_memory,
            "memory_leak_detected": gc_memory > execution_memory + 10  # 10MB误差范围
        }
    
    def generate_performance_report(self, output_file: str = None) -> str:
        """生成性能报告"""
        if not output_file:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"performance_report_{timestamp}.txt"
        
        report_lines = []
        report_lines.append("工作流系统性能分析报告")
        report_lines.append("=" * 50)
        report_lines.append(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        
        # 添加所有分析结果
        for key, result in self.results.items():
            report_lines.append(f"=== {key} ===")
            
            if "node_type" in result:
                # 节点性能分析结果
                report_lines.append(f"节点类型: {result['node_type']}")
                report_lines.append(f"执行次数: {result['iterations']}")
                report_lines.append(f"总时间: {result['total_time']:.4f}s")
                report_lines.append(f"平均时间: {result['avg_time']:.6f}s")
                
            elif "workflow_name" in result:
                # 工作流性能分析结果
                report_lines.append(f"工作流名称: {result['workflow_name']}")
                report_lines.append(f"节点数量: {result['node_count']}")
                report_lines.append(f"连接数量: {result['edge_count']}")
                report_lines.append(f"执行时间: {result['total_time']:.4f}s")
                
                if "function_stats" in result:
                    report_lines.append("\n函数调用统计:")
                    for func_name, stats in result['function_stats'].items():
                        report_lines.append(f"  {func_name}: {stats['call_count']}次, "
                                         f"{stats['cumulative_time']:.4f}s")
                
                if "initial_memory_mb" in result:
                    # 内存使用分析结果
                    report_lines.append(f"初始内存: {result['initial_memory_mb']:.2f}MB")
                    report_lines.append(f"执行内存: {result['execution_memory_mb']:.2f}MB")
                    report_lines.append(f"GC后内存: {result['gc_memory_mb']:.2f}MB")
                    report_lines.append(f"内存增长: {result['memory_growth_mb']:.2f}MB")
                    report_lines.append(f"内存泄漏: {'是' if result['memory_leak_detected'] else '否'}")
            
            report_lines.append("")
        
        # 写入文件
        report_content = "\n".join(report_lines)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        return output_file


def create_test_workflows() -> Dict[str, WorkflowGraphModel]:
    """创建测试工作流"""
    workflows = {}
    
    # 简单工作流
    simple_nodes = [
        WorkflowNodeModel(
            node_id="simple_source",
            node_type="data.source",
            title="简单数据源",
            position=(50, 50),
            params={}
        ),
        WorkflowNodeModel(
            node_id="simple_delay",
            node_type="logic.delay",
            title="简单延时",
            position=(200, 50),
            params={"delay_ms": 10}
        )
    ]
    
    simple_edges = [
        WorkflowEdgeModel(
            from_node="simple_source",
            to_node="simple_delay"
        )
    ]
    
    workflows["simple"] = WorkflowGraphModel(
        name="简单工作流",
        nodes=simple_nodes,
        edges=simple_edges
    )
    
    # 复杂工作流
    complex_nodes = []
    complex_edges = []
    
    # 创建10个并行分支
    for i in range(10):
        # 数据源
        complex_nodes.append(WorkflowNodeModel(
            node_id=f"complex_source_{i}",
            node_type="data.source",
            title=f"复杂数据源{i}",
            position=(0, float(i * 40)),
            params={}
        ))
        
        # 条件判断
        complex_nodes.append(WorkflowNodeModel(
            node_id=f"complex_condition_{i}",
            node_type="logic.condition",
            title=f"复杂条件{i}",
            position=(150, float(i * 40)),
            params={"threshold": 0.5}
        ))
        
        # 延时
        complex_nodes.append(WorkflowNodeModel(
            node_id=f"complex_delay_{i}",
            node_type="logic.delay",
            title=f"复杂延时{i}",
            position=(300, float(i * 40)),
            params={"delay_ms": 5}
        ))
        
        # 连接
        complex_edges.append(WorkflowEdgeModel(
            from_node=f"complex_source_{i}",
            to_node=f"complex_condition_{i}"
        ))
        complex_edges.append(WorkflowEdgeModel(
            from_node=f"complex_condition_{i}",
            to_node=f"complex_delay_{i}"
        ))
    
    # 汇总节点
    complex_nodes.append(WorkflowNodeModel(
        node_id="complex_collector",
        node_type="plot.stream",
        title="复杂汇总",
        position=(450, 200),
        params={}
    ))
    
    # 连接所有延时节点到汇总
    for i in range(10):
        complex_edges.append(WorkflowEdgeModel(
            from_node=f"complex_delay_{i}",
            to_node="complex_collector"
        ))
    
    workflows["complex"] = WorkflowGraphModel(
        name="复杂工作流",
        nodes=complex_nodes,
        edges=complex_edges
    )
    
    # 大型工作流
    large_nodes = []
    large_edges = []
    
    for i in range(100):
        large_nodes.append(WorkflowNodeModel(
            node_id=f"large_node_{i}",
            node_type="data.source" if i % 2 == 0 else "logic.delay",
            title=f"大型节点{i}",
            position=(float(i * 20), float((i % 10) * 30)),
            params={"delay_ms": 1} if i % 2 == 1 else {}
        ))
        
        if i > 0:
            large_edges.append(WorkflowEdgeModel(
                from_node=f"large_node_{i-1}",
                to_node=f"large_node_{i}"
            ))
    
    workflows["large"] = WorkflowGraphModel(
        name="大型工作流",
        nodes=large_nodes,
        edges=large_edges
    )
    
    return workflows


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="工作流性能分析工具")
    
    parser.add_argument(
        "--nodes",
        action="store_true",
        help="分析节点执行性能"
    )
    
    parser.add_argument(
        "--workflows",
        action="store_true",
        help="分析工作流执行性能"
    )
    
    parser.add_argument(
        "--memory",
        action="store_true",
        help="分析内存使用情况"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="执行所有性能分析"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="输出报告文件路径"
    )
    
    args = parser.parse_args()
    
    if not any([args.nodes, args.workflows, args.memory, args.all]):
        parser.print_help()
        return
    
    # 创建性能分析器
    profiler = WorkflowProfiler()
    
    print("开始性能分析...")
    
    # 分析节点性能
    if args.nodes or args.all:
        print("\n=== 节点性能分析 ===")
        
        node_types = ["data.source", "logic.delay", "plot.stream", "logic.condition"]
        
        for node_type in node_types:
            print(f"分析节点: {node_type}")
            
            try:
                result = profiler.profile_node_execution(node_type)
                profiler.results[f"node_{node_type}"] = result
                
                print(f"  平均执行时间: {result['avg_time']:.6f}s")
                print(f"  总执行时间: {result['total_time']:.4f}s")
                
            except Exception as e:
                print(f"  分析失败: {e}")
    
    # 分析工作流性能
    if args.workflows or args.all:
        print("\n=== 工作流性能分析 ===")
        
        workflows = create_test_workflows()
        
        for workflow_name, workflow in workflows.items():
            print(f"分析工作流: {workflow_name}")
            
            try:
                result = profiler.profile_workflow_execution(workflow)
                profiler.results[f"workflow_{workflow_name}"] = result
                
                print(f"  执行时间: {result['total_time']:.4f}s")
                print(f"  节点数量: {result['node_count']}")
                print(f"  连接数量: {result['edge_count']}")
                
            except Exception as e:
                print(f"  分析失败: {e}")
    
    # 分析内存使用
    if args.memory or args.all:
        print("\n=== 内存使用分析 ===")
        
        workflows = create_test_workflows()
        
        for workflow_name, workflow in workflows.items():
            print(f"分析内存使用: {workflow_name}")
            
            try:
                result = profiler.profile_memory_usage(workflow)
                profiler.results[f"memory_{workflow_name}"] = result
                
                print(f"  内存增长: {result['memory_growth_mb']:.2f}MB")
                print(f"  内存泄漏: {'是' if result['memory_leak_detected'] else '否'}")
                
            except Exception as e:
                print(f"  分析失败: {e}")
    
    # 生成报告
    print("\n=== 生成性能报告 ===")
    
    try:
        report_file = profiler.generate_performance_report(args.output)
        print(f"性能报告已生成: {report_file}")
        
        # 显示关键性能指标
        print("\n关键性能指标:")
        for key, result in profiler.results.items():
            if "avg_time" in result:
                print(f"  {key}: {result['avg_time']:.6f}s (平均)")
            elif "total_time" in result and "node_count" in result:
                avg_per_node = result['total_time'] / result['node_count']
                print(f"  {key}: {result['total_time']:.4f}s (总计), {avg_per_node:.6f}s/节点")
            elif "memory_growth_mb" in result:
                print(f"  {key}: {result['memory_growth_mb']:.2f}MB (内存增长)")
        
    except Exception as e:
        print(f"生成报告失败: {e}")
    
    print("\n性能分析完成!")


if __name__ == "__main__":
    main()
