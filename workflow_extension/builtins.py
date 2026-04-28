"""
内置节点实现

本模块提供了工作流系统的基础内置节点，包括：
- 设备连接节点：检查设备连接状态
- 参数配置节点：配置和传递参数
- 延时节点：执行延时操作
- 数据源节点：生成随机测试数据
- 绘图流节点：实时数据可视化
- 逻辑条件节点：条件判断和分支控制
- 数学运算节点：基本数学运算
- 数据转换节点：数据格式转换

这些节点为工作流提供了基础功能支持，可作为构建复杂工作流的组件。
"""

import math
import random
import time
from typing import Dict

from PySide6.QtCore import QCoreApplication

from workflow_extension.node_registry import NodeParamSpec, NodePortSpec, NodeRegistry, NodeSpec





def register_builtin_nodes(registry: NodeRegistry):
    # 注册初始化设备节点
    from workflow_extension.device_init_node import register_device_init_nodes
    register_device_init_nodes(registry)

    # 注册CW谱数据采集节点
    from workflow_extension.cw_nodes import register_cw_nodes
    register_cw_nodes(registry)

    # 注册全光谱数据采集节点
    from workflow_extension.all_optical_nodes import register_all_optical_nodes
    register_all_optical_nodes(registry)

    # 注册IIR谱数据采集节点
    from workflow_extension.iir_nodes import register_iir_nodes
    register_iir_nodes(registry)

    # 注册超声电机状态节点
    from workflow_extension.ultramotor_nodes import register_ultramotor_nodes
    register_ultramotor_nodes(registry)

    # 注册设备选择节点
    from workflow_extension.device_select_nodes import register_device_select_nodes
    register_device_select_nodes(registry)
