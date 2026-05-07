"""
工作流执行引擎

本模块实现了工作流的执行逻辑，包括：
- WorkflowExecutor: 工作流执行器，负责按拓扑顺序执行节点
- 拓扑排序算法：确保节点按依赖关系正确执行
- 异步执行支持：通过信号槽机制提供执行状态反馈
- 错误处理机制：节点执行失败时的异常处理

该引擎是工作流系统的核心组件，负责协调节点的执行顺序和数据传递。
"""

from collections import defaultdict, deque
from typing import Dict, List

from PySide6.QtCore import QCoreApplication, QObject, Signal


class WorkflowExecutor(QObject):
    """
    工作流执行器
    
    负责按照拓扑顺序执行工作流中的所有节点，管理数据传递和状态反馈。
    支持异步执行和停止控制，通过信号槽机制提供实时状态更新。
    
    Signals:
        node_started (str): 节点开始执行信号，参数为节点ID
        node_finished (str, object): 节点执行完成信号，参数为节点ID和执行结果
        node_failed (str, str): 节点执行失败信号，参数为节点ID和错误信息
        run_finished: 工作流执行完成信号
    
    Attributes:
        registry (NodeRegistry): 节点注册器，用于获取节点规范
        _stop_requested (bool): 停止请求标志，用于中断执行
    """
    
    # 信号定义
    node_started = Signal(str)        # 节点开始执行
    node_finished = Signal(str, object)  # 节点执行完成
    node_failed = Signal(str, str)    # 节点执行失败
    run_finished = Signal()           # 工作流执行完成

    def __init__(self, registry, parent=None):
        """
        初始化工作流执行器
        
        Args:
            registry (NodeRegistry): 节点注册器实例
            parent (QObject, optional): 父对象，用于Qt对象树管理
        """
        super().__init__(parent)
        self.registry = registry
        self._stop_requested = False

    def stop(self):
        """请求停止工作流执行"""
        self._stop_requested = True

    def run(self, graph, context):
        """
        执行工作流
        
        按照拓扑顺序执行工作流中的所有节点，处理数据传递和异常情况。
        
        Args:
            graph (WorkflowGraphModel): 要执行的工作流图
            context (Dict[str, Any]): 执行上下文，包含应用实例、回调函数等
        """
        self._stop_requested = False
        
        # 计算节点执行顺序（拓扑排序）
        order = self._topological_order(graph)
        
        # 初始化输出数据字典
        outputs: Dict[str, object] = {}

        # 按顺序执行节点
        for node in order:
            # 处理UI事件，保持界面响应
            QCoreApplication.processEvents()
            
            # 检查停止请求
            if self._stop_requested:
                break
                
            # 发送节点开始信号
            self.node_started.emit(node.node_id)
            QCoreApplication.processEvents()
            
            try:
                # 获取节点规范
                spec = self.registry.get(node.node_type)
                
                # 收集输入数据（构建端口名到数据的映射字典）
                node_inputs = {}
                for edge in graph.edges:
                    if edge.to_node == node.node_id and edge.from_node in outputs:
                        node_inputs[edge.to_port] = outputs[edge.from_node]
                
                # 执行节点逻辑
                result = spec.executor(context, node, node_inputs) if spec.executor else {}
                
                # 保存输出结果
                outputs[node.node_id] = result
                
                # 发送节点完成信号
                self.node_finished.emit(node.node_id, result)
                QCoreApplication.processEvents()
                
            except Exception as exc:
                # 发送节点失败信号
                self.node_failed.emit(node.node_id, str(exc))
                break
                
        # 发送执行完成信号
        self.run_finished.emit()

    @staticmethod
    def _topological_order(graph):
        """
        计算工作流的拓扑排序
        
        使用Kahn算法计算节点的执行顺序，确保节点在依赖节点执行后执行。
        如果工作流存在环路，将抛出异常。
        
        Args:
            graph (WorkflowGraphModel): 工作流图
            
        Returns:
            List[WorkflowNodeModel]: 按执行顺序排列的节点列表
            
        Raises:
            ValueError: 当工作流存在环路时
        """
        # 计算每个节点的入度
        indegree = defaultdict(int)
        edges = defaultdict(list)
        nodes_by_id = {node.node_id: node for node in graph.nodes}
        
        # 构建邻接表和入度表
        for edge in graph.edges:
            edges[edge.from_node].append(edge.to_node)
            indegree[edge.to_node] += 1
            indegree.setdefault(edge.from_node, 0)

        # 找到所有入度为0的节点
        q = deque([nid for nid in nodes_by_id if indegree[nid] == 0])
        ordered = []
        
        # Kahn算法主循环
        while q:
            nid = q.popleft()
            ordered.append(nodes_by_id[nid])
            
            # 更新邻接节点的入度
            for nxt in edges[nid]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    q.append(nxt)

        # 检查是否存在环路
        if len(ordered) != len(graph.nodes):
            raise ValueError("工作流存在环路，无法执行。")
            
        return ordered
