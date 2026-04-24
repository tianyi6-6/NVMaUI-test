#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试线段拖拽功能
"""

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QPointF
from workflow_extension.canvas import WorkflowScene, WorkflowCanvasView
from workflow_extension.node_registry import NodeRegistry
from workflow_extension.builtins import register_builtin_nodes


class TestEdgeDragWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("测试线段拖拽功能")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建工作流场景和视图
        self.scene = WorkflowScene()
        self.view = WorkflowCanvasView(self.scene)
        layout.addWidget(self.view)
        
        # 注册节点
        self.registry = NodeRegistry()
        register_builtin_nodes(self.registry)
        self.scene.set_spec_resolver(self.registry.get)
        
        # 添加一些测试节点
        self._add_test_nodes()
        
        # 添加说明文本
        self.statusBar().showMessage("测试说明：1. 点击节点端口创建连接 2. 点击线段端点可以拖拽移动线段 3. 拖拽到空白处线段会消失")
    
    def _add_test_nodes(self):
        """添加测试节点"""
        # 添加几个节点用于测试
        node1 = self.scene.add_node(
            node_type="demo.define_right",
            title="定义右侧角度区间",
            pos=QPointF(200, 200),
            params={"width": 0.08}
        )
        
        node2 = self.scene.add_node(
            node_type="demo.right_fine_scan", 
            title="执行右区精扫",
            pos=QPointF(500, 300),
            params={"points": 51}
        )
        
        node3 = self.scene.add_node(
            node_type="plot.stream",
            title="流式绘图", 
            pos=QPointF(800, 200),
            params={}
        )
        
        print("测试节点已添加，请测试线段拖拽功能")


def main():
    app = QApplication(sys.argv)
    
    window = TestEdgeDragWindow()
    window.show()
    
    print("线段拖拽测试程序已启动")
    print("功能说明：")
    print("1. 从输出端口拖拽到输入端口创建连接")
    print("2. 点击线段的端点（输入/输出端口附近）可以拖拽移动线段")
    print("3. 拖拽到新的端口会重新连接")
    print("4. 拖拽到空白处会删除线段")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
