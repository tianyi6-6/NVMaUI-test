#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作流撤销/重做系统
实现基于命令模式的撤销重做功能
"""

import copy
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional, Any
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal


class WorkflowCommand(ABC):
    """工作流命令基类"""
    
    def __init__(self, description: str):
        self.description = description
        self.command_id = uuid.uuid4().hex[:8]
    
    @abstractmethod
    def execute(self, scene) -> Any:
        """执行命令"""
        pass
    
    @abstractmethod
    def undo(self, scene) -> Any:
        """撤销命令"""
        pass
    
    @abstractmethod
    def redo(self, scene) -> Any:
        """重做命令"""
        pass


class AddNodeCommand(WorkflowCommand):
    """添加节点命令"""
    
    def __init__(self, node_type: str, title: str, pos, params=None, node_id=None):
        super().__init__(f"添加节点: {title}")
        self.node_type = node_type
        self.title = title
        self.pos = pos
        self.params = params or {}
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"
        self.created_node = None
    
    def execute(self, scene):
        """执行添加节点"""
        self.created_node = scene.add_node(
            node_type=self.node_type,
            title=self.title,
            pos=self.pos,
            params=self.params,
            node_id=self.node_id
        )
        return self.created_node
    
    def undo(self, scene):
        """撤销添加节点"""
        if self.created_node and self.created_node.model.node_id in scene.node_items:
            node_id = self.created_node.model.node_id
            # 删除相关连接
            for edge in list(scene.edges):
                if edge[0] == node_id or edge[2] == node_id:
                    scene.removeItem(edge[4])
                    scene.edges.remove(edge)
            # 删除节点
            scene.removeItem(self.created_node)
            scene.node_items.pop(node_id, None)
            scene.graph_changed.emit()
            return True
        return False
    
    def redo(self, scene):
        """重做添加节点"""
        return self.execute(scene)


class DeleteNodesCommand(WorkflowCommand):
    """删除节点命令"""
    
    def __init__(self, node_ids: List[str]):
        super().__init__(f"删除 {len(node_ids)} 个节点")
        self.node_ids = node_ids.copy()
        self.deleted_nodes = []
        self.deleted_edges = []
    
    def execute(self, scene):
        """执行删除节点"""
        # 保存被删除的节点和连接信息
        self.deleted_nodes = []
        self.deleted_edges = []
        
        for node_id in self.node_ids:
            if node_id in scene.node_items:
                node_item = scene.node_items[node_id]
                # 保存节点信息
                self.deleted_nodes.append({
                    'model': copy.deepcopy(node_item.model),
                    'spec': copy.deepcopy(node_item.spec)
                })
                
                # 保存相关连接信息
                for edge in list(scene.edges):
                    if edge[0] == node_id or edge[2] == node_id:
                        self.deleted_edges.append(copy.deepcopy(edge))
        
        # 执行删除
        for node_id in self.node_ids:
            if node_id in scene.node_items:
                node_item = scene.node_items[node_id]
                # 删除相关连接
                for edge in list(scene.edges):
                    if edge[0] == node_id or edge[2] == node_id:
                        scene.removeItem(edge[4])
                        scene.edges.remove(edge)
                # 删除节点
                scene.removeItem(node_item)
                scene.node_items.pop(node_id, None)
        
        scene.graph_changed.emit()
        return True
    
    def undo(self, scene):
        """撤销删除节点"""
        # 恢复节点
        for node_info in self.deleted_nodes:
            model = node_info['model']
            spec = node_info['spec']
            item = scene.add_node(
                node_type=model.node_type,
                title=model.title,
                pos=scene.mapFromScene or None,
                params=model.params,
                node_id=model.node_id
            )
            if item:
                item.setPos(model.position[0], model.position[1])
        
        # 恢复连接
        for edge_info in self.deleted_edges:
            from_id, from_port, to_id, to_port, _ = edge_info
            src_item = scene.node_items.get(from_id)
            dst_item = scene.node_items.get(to_id)
            if src_item and dst_item:
                from workflow_extension.canvas import WorkflowEdgeItem
                edge_item = WorkflowEdgeItem(src_item, from_port, dst_item, to_port)
                scene.addItem(edge_item)
                scene.edges.append((from_id, from_port, to_id, to_port, edge_item))
        
        scene.graph_changed.emit()
        return True
    
    def redo(self, scene):
        """重做删除节点"""
        return self.execute(scene)


class AddEdgeCommand(WorkflowCommand):
    """添加连接命令"""
    
    def __init__(self, src_node_id: str, src_port: str, dst_node_id: str, dst_port: str):
        super().__init__(f"添加连接: {src_node_id}.{src_port} -> {dst_node_id}.{dst_port}")
        self.src_node_id = src_node_id
        self.src_port = src_port
        self.dst_node_id = dst_node_id
        self.dst_port = dst_port
        self.created_edge = None
    
    def execute(self, scene):
        """执行添加连接"""
        src_item = scene.node_items.get(self.src_node_id)
        dst_item = scene.node_items.get(self.dst_node_id)
        
        if src_item and dst_item:
            from workflow_extension.canvas import WorkflowEdgeItem
            self.created_edge = WorkflowEdgeItem(src_item, self.src_port, dst_item, self.dst_port)
            scene.addItem(self.created_edge)
            scene.edges.append((self.src_node_id, self.src_port, self.dst_node_id, self.dst_port, self.created_edge))
            scene.graph_changed.emit()
            return True
        return False
    
    def undo(self, scene):
        """撤销添加连接"""
        if self.created_edge:
            scene.removeItem(self.created_edge)
            for edge in list(scene.edges):
                if edge[4] == self.created_edge:
                    scene.edges.remove(edge)
                    break
            scene.graph_changed.emit()
            return True
        return False
    
    def redo(self, scene):
        """重做添加连接"""
        return self.execute(scene)


class RemoveEdgeCommand(WorkflowCommand):
    """删除连接命令"""
    
    def __init__(self, edge_info):
        from_id, from_port, to_id, to_port, edge_item = edge_info
        super().__init__(f"删除连接: {from_id}.{from_port} -> {to_id}.{to_port}")
        self.from_id = from_id
        self.from_port = from_port
        self.to_id = to_id
        self.to_port = to_port
        self.removed_edge = edge_item
    
    def execute(self, scene):
        """执行删除连接"""
        if self.removed_edge:
            scene.removeItem(self.removed_edge)
            for edge in list(scene.edges):
                if edge[4] == self.removed_edge:
                    scene.edges.remove(edge)
                    break
            scene.graph_changed.emit()
            return True
        return False
    
    def undo(self, scene):
        """撤销删除连接"""
        src_item = scene.node_items.get(self.from_id)
        dst_item = scene.node_items.get(self.to_id)
        
        if src_item and dst_item:
            from workflow_extension.canvas import WorkflowEdgeItem
            edge_item = WorkflowEdgeItem(src_item, self.from_port, dst_item, self.to_port)
            scene.addItem(edge_item)
            scene.edges.append((self.from_id, self.from_port, self.to_id, self.to_port, edge_item))
            scene.graph_changed.emit()
            return True
        return False
    
    def redo(self, scene):
        """重做删除连接"""
        return self.execute(scene)


class MoveNodesCommand(WorkflowCommand):
    """移动节点命令"""
    
    def __init__(self, node_moves: List[tuple]):
        """
        node_moves: [(node_id, old_pos, new_pos), ...]
        """
        descriptions = []
        for node_id, old_pos, new_pos in node_moves:
            descriptions.append(f"{node_id}: ({old_pos[0]:.1f},{old_pos[1]:.1f}) -> ({new_pos[0]:.1f},{new_pos[1]:.1f})")
        super().__init__(f"移动 {len(node_moves)} 个节点")
        self.node_moves = node_moves.copy()
    
    def execute(self, scene):
        """执行移动节点（实际上移动已经在UI中发生了）"""
        return True
    
    def undo(self, scene):
        """撤销移动节点"""
        for node_id, old_pos, new_pos in self.node_moves:
            if node_id in scene.node_items:
                item = scene.node_items[node_id]
                item.setPos(old_pos[0], old_pos[1])
        return True
    
    def redo(self, scene):
        """重做移动节点"""
        for node_id, old_pos, new_pos in self.node_moves:
            if node_id in scene.node_items:
                item = scene.node_items[node_id]
                item.setPos(new_pos[0], new_pos[1])
        return True


class WorkflowUndoStack(QObject):
    """工作流撤销/重做栈"""
    
    # 信号
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    stack_changed = Signal()
    
    def __init__(self, max_size: int = 100):
        super().__init__()
        self.max_size = max_size
        self.undo_stack: List[WorkflowCommand] = []
        self.redo_stack: List[WorkflowCommand] = []
        self.current_state = None
    
    def push_command(self, command: WorkflowCommand, scene):
        """推送新命令到栈中"""
        # 如果有重做栈，清空它（因为新操作会改变历史）
        self.redo_stack.clear()
        
        # 添加到撤销栈
        self.undo_stack.append(command)
        
        # 限制栈大小
        if len(self.undo_stack) > self.max_size:
            self.undo_stack.pop(0)
        
        # 执行命令
        command.execute(scene)
        
        # 更新状态
        self._update_signals()
        self.stack_changed.emit()
    
    def undo(self, scene) -> bool:
        """撤销上一个操作"""
        if not self.can_undo():
            return False
        
        command = self.undo_stack.pop()
        success = command.undo(scene)
        
        if success:
            self.redo_stack.append(command)
            self._update_signals()
            self.stack_changed.emit()
        
        return success
    
    def redo(self, scene) -> bool:
        """重做下一个操作"""
        if not self.can_redo():
            return False
        
        command = self.redo_stack.pop()
        success = command.redo(scene)
        
        if success:
            self.undo_stack.append(command)
            self._update_signals()
            self.stack_changed.emit()
        
        return success
    
    def can_undo(self) -> bool:
        """是否可以撤销"""
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        """是否可以重做"""
        return len(self.redo_stack) > 0
    
    def get_undo_description(self) -> str:
        """获取撤销操作的描述"""
        if self.can_undo():
            return self.undo_stack[-1].description
        return "撤销"
    
    def get_redo_description(self) -> str:
        """获取重做操作的描述"""
        if self.can_redo():
            return self.redo_stack[-1].description
        return "重做"
    
    def clear(self):
        """清空撤销/重做栈"""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_signals()
        self.stack_changed.emit()
    
    def _update_signals(self):
        """更新信号状态"""
        self.can_undo_changed.emit(self.can_undo())
        self.can_redo_changed.emit(self.can_redo())
