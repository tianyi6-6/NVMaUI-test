"""
工作流序列化工具

本模块提供了工作流的序列化和反序列化功能，包括：
- load_json: 从JSON文件加载工作流
- export_json: 导出工作流为JSON格式
- _xor_crypt: XOR加密算法（保留用于向后兼容）

支持JSON格式的工作流保存和加载。
"""

import base64
import json
from dataclasses import asdict
from pathlib import Path

from workflow_extension.models import WorkflowEdgeModel, WorkflowGraphModel, WorkflowNodeModel


# XOR加密密钥，用于工作流文件加密
_KEY = b"NVMAG_WORKFLOW_KEY"


def _xor_crypt(data: bytes) -> bytes:
    """
    XOR加密/解密算法
    
    使用简单的XOR算法对数据进行加密或解密。XOR算法的特点是
    加密和解密使用相同的操作，便于实现。
    
    Args:
        data (bytes): 要加密或解密的数据
        
    Returns:
        bytes: 加密或解密后的数据
    """
    return bytes([b ^ _KEY[i % len(_KEY)] for i, b in enumerate(data)])


def save_workflow(graph: WorkflowGraphModel, file_path: str):
    """
    保存工作流到加密文件
    
    将工作流图序列化为JSON格式，然后使用XOR加密和Base64编码保存到文件。
    
    Args:
        graph (WorkflowGraphModel): 要保存的工作流图
        file_path (str): 保存文件路径
    """
    # 将数据类转换为字典并序列化为JSON
    raw = json.dumps(asdict(graph), ensure_ascii=False, indent=2).encode("utf-8")
    
    # 加密并编码
    encrypted = base64.b64encode(_xor_crypt(raw))
    
    # 写入文件
    Path(file_path).write_bytes(encrypted)


def load_workflow(file_path: str) -> WorkflowGraphModel:
    """
    从加密文件加载工作流
    
    读取加密的工作流文件，解密并反序列化为工作流图对象。
    
    Args:
        file_path (str): 工作流文件路径
        
    Returns:
        WorkflowGraphModel: 加载的工作流图对象
        
    Raises:
        FileNotFoundError: 当文件不存在时
        json.JSONDecodeError: 当文件格式错误时
    """
    # 读取加密文件
    encrypted = Path(file_path).read_bytes()
    
    # 解密并解码
    raw = _xor_crypt(base64.b64decode(encrypted))
    
    # 解析JSON
    payload = json.loads(raw.decode("utf-8"))
    
    # 创建工作流图对象
    graph = WorkflowGraphModel(
        version=payload.get("version", "1.0"), 
        name=payload.get("name", "Untitled")
    )
    
    # 恢复节点数据
    for n in payload.get("nodes", []):
        graph.nodes.append(
            WorkflowNodeModel(
                node_id=n["node_id"],
                node_type=n["node_type"],
                title=n["title"],
                position=tuple(n["position"]),
                params=n.get("params", {}),
            )
        )
    
    # 恢复边数据
    for e in payload.get("edges", []):
        graph.edges.append(
            WorkflowEdgeModel(
                from_node=e["from_node"],
                to_node=e["to_node"],
                from_port=e.get("from_port", "out"),
                to_port=e.get("to_port", "in"),
            )
        )
    
    return graph


def export_json(graph: WorkflowGraphModel, file_path: str):
    """
    导出工作流为JSON格式
    
    将工作流图以纯JSON格式导出，便于调试和与其他系统集成。
    
    Args:
        graph (WorkflowGraphModel): 要导出的工作流图
        file_path (str): 导出文件路径
    """
    json_data = json.dumps(asdict(graph), ensure_ascii=False, indent=2)
    Path(file_path).write_text(json_data, encoding="utf-8")


def load_json(file_path: str) -> WorkflowGraphModel:
    """
    从JSON文件加载工作流
    
    读取纯JSON格式的工作流文件并反序列化为工作流图对象。
    
    Args:
        file_path (str): JSON工作流文件路径
        
    Returns:
        WorkflowGraphModel: 加载的工作流图对象
        
    Raises:
        FileNotFoundError: 当文件不存在时
        json.JSONDecodeError: 当文件格式错误时
    """
    # 读取JSON文件
    raw = Path(file_path).read_text(encoding="utf-8")
    
    # 解析JSON
    payload = json.loads(raw)
    
    # 创建工作流图对象
    graph = WorkflowGraphModel(
        version=payload.get("version", "1.0"), 
        name=payload.get("name", "Untitled")
    )
    
    # 恢复节点数据
    for n in payload.get("nodes", []):
        graph.nodes.append(
            WorkflowNodeModel(
                node_id=n["node_id"],
                node_type=n["node_type"],
                title=n["title"],
                position=tuple(n["position"]),
                params=n.get("params", {}),
            )
        )
    
    # 恢复边数据
    for e in payload.get("edges", []):
        graph.edges.append(
            WorkflowEdgeModel(
                from_node=e["from_node"],
                to_node=e["to_node"],
                from_port=e.get("from_port", "out"),
                to_port=e.get("to_port", "in"),
            )
        )
    
    return graph
