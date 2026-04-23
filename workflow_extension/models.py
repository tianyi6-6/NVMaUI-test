"""
工作流数据模型定义

本模块定义了工作流系统的核心数据结构，包括：
- WorkflowNodeModel: 工作流节点模型
- WorkflowEdgeModel: 工作流边（连接）模型  
- WorkflowGraphModel: 工作流图模型

这些数据类用于序列化/反序列化工作流文件，以及在内存中表示工作流结构。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class WorkflowNodeModel:
    """
    工作流节点数据模型
    
    用于表示工作流中的单个节点，包含节点的基本信息、位置和参数配置。
    
    Attributes:
        node_id (str): 节点唯一标识符，在图中必须唯一
        node_type (str): 节点类型，对应注册表中的节点类型标识
        title (str): 节点显示标题，在UI中显示给用户
        position (Tuple[float, float]): 节点在画布中的坐标位置 (x, y)
        params (Dict[str, object]): 节点参数配置，键值对形式存储
    """
    node_id: str
    node_type: str
    title: str
    position: Tuple[float, float]
    params: Dict[str, object] = field(default_factory=dict)


@dataclass
class WorkflowEdgeModel:
    """
    工作流边（连接）数据模型
    
    用于表示节点之间的连接关系，定义数据流向。
    
    Attributes:
        from_node (str): 源节点ID，数据来源节点
        to_node (str): 目标节点ID，数据接收节点
        from_port (str): 源端口名称，默认为"out"
        to_port (str): 目标端口名称，默认为"in"
    """
    from_node: str
    to_node: str
    from_port: str = "out"
    to_port: str = "in"


@dataclass
class WorkflowGraphModel:
    """
    工作流图数据模型
    
    用于表示完整的工作流，包含所有节点和边的集合。
    
    Attributes:
        version (str): 工作流版本号，用于兼容性检查
        name (str): 工作流名称，用户可编辑
        nodes (List[WorkflowNodeModel]): 工作流中所有节点的列表
        edges (List[WorkflowEdgeModel]): 工作流中所有连接边的列表
    """
    version: str = "1.0"
    name: str = "Untitled"
    nodes: List[WorkflowNodeModel] = field(default_factory=list)
    edges: List[WorkflowEdgeModel] = field(default_factory=list)
