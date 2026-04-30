"""
节点注册系统

本模块定义了工作流节点的规范和注册机制，包括：
- NodePortSpec: 节点端口规范定义
- NodeParamSpec: 节点参数规范定义  
- NodeSpec: 节点完整规范定义
- NodeRegistry: 节点注册器，提供节点注册和查询功能

该系统支持动态注册自定义节点，为工作流系统提供可扩展性。
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List


@dataclass
class NodePortSpec:
    """
    节点端口规范定义
    
    用于定义节点的输入/输出端口特性，包括端口名称和数据类型。
    
    Attributes:
        name (str): 端口名称，在节点中必须唯一
        data_type (str): 端口数据类型，支持: any, float, int, array, bool, trigger
    """
    name: str
    data_type: str = "any"


@dataclass
class NodeParamSpec:
    """
    节点参数规范定义
    
    用于定义节点可配置参数的UI表现形式和约束条件。
    
    Attributes:
        key (str): 参数键名，用于在节点参数字典中标识该参数
        label (str): 参数显示标签，在UI中显示给用户
        editor (str): 编辑器类型，支持: text, int, float, select, bool, device_param
        options (List[str]): 选择项列表，当editor为"select"时使用
        minimum (float): 数值最小值，当editor为"int"或"float"时使用
        maximum (float): 数值最大值，当editor为"int"或"float"时使用
        step (float): 数值步长，当editor为"int"或"float"时使用
        category (str): 参数所属的一级分类，用于层级结构
        subcategory (str): 参数所属的二级分类，用于层级结构
        device_param (bool): 是否为设备参数，支持当前值、合法范围、输入新值
        current_value (str): 当前值（设备参数专用）
        valid_range (str): 合法范围（设备参数专用）
        unit (str): 参数单位
    """
    key: str
    label: str
    editor: str = "text"  # text|int|float|select|bool|device_param
    options: List[str] = field(default_factory=list)
    minimum: float = 0.0
    maximum: float = 999999.0
    step: float = 1.0
    category: str = ""  # 一级分类
    subcategory: str = ""  # 二级分类
    device_param: bool = False  # 是否为设备参数
    current_value: str = ""  # 当前值
    valid_range: str = ""  # 合法范围
    unit: str = ""  # 单位


@dataclass
class NodeSpec:
    """
    节点完整规范定义

    定义节点的所有特性，包括基本信息、端口配置、参数配置和执行逻辑。

    Attributes:
        node_type (str): 节点类型标识符，必须唯一
        title (str): 节点显示标题，在UI中显示给用户
        category (str): 节点分类，用于在节点库中分组显示
        default_params (Dict[str, object]): 默认参数配置
        input_ports (List[NodePortSpec]): 输入端口列表
        output_ports (List[NodePortSpec]): 输出端口列表
        param_specs (List[NodeParamSpec]): 参数规范列表
        executor (Callable): 节点执行函数，定义节点的业务逻辑
        on_param_change (Callable): 参数变化回调函数，用于处理参数依赖
    """
    node_type: str
    title: str
    category: str
    default_params: Dict[str, object] = field(default_factory=dict)
    input_ports: List[NodePortSpec] = field(default_factory=lambda: [NodePortSpec("in", "any")])
    output_ports: List[NodePortSpec] = field(default_factory=lambda: [NodePortSpec("out", "any")])
    param_specs: List[NodeParamSpec] = field(default_factory=list)
    executor: Callable = None
    on_param_change: Callable = None


class NodeRegistry:
    """
    节点注册器
    
    负责管理所有已注册的节点规范，提供节点的注册、查询和分组功能。
    支持动态注册新节点类型，为系统提供可扩展性。
    
    Attributes:
        _specs (Dict[str, NodeSpec]): 节点规范字典，以node_type为键
    """
    
    def __init__(self):
        """初始化节点注册器，创建空的节点规范字典"""
        self._specs: Dict[str, NodeSpec] = {}

    def register(self, spec: NodeSpec):
        """
        注册节点规范
        
        将节点规范添加到注册表中，如果节点类型已存在则覆盖。
        
        Args:
            spec (NodeSpec): 要注册的节点规范
        """
        self._specs[spec.node_type] = spec

    def get(self, node_type: str) -> NodeSpec:
        """
        获取节点规范
        
        根据节点类型获取对应的节点规范。
        
        Args:
            node_type (str): 节点类型标识符
            
        Returns:
            NodeSpec: 对应的节点规范
            
        Raises:
            KeyError: 当节点类型不存在时
        """
        return self._specs[node_type]

    def all_specs(self):
        """
        获取所有节点规范
        
        Returns:
            List[NodeSpec]: 所有已注册节点规范的列表
        """
        return list(self._specs.values())

    def grouped(self):
        """
        按分类获取节点规范
        
        将所有节点规范按category分组，便于在UI中分类显示。
        
        Returns:
            Dict[str, List[NodeSpec]]: 以分类名为键，节点规范列表为值的字典
        """
        groups = {}
        for spec in self._specs.values():
            groups.setdefault(spec.category, []).append(spec)
        return groups
