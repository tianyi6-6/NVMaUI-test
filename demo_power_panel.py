#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电源控制面板演示脚本
展示重构后的实际设备控制功能
"""

import sys
import os
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget, QLabel, QPushButton, QTextEdit
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from power_panel import PowerPanel

class DemoWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("电源控制面板演示")
        self.setMinimumSize(800, 600)
        
        layout = QVBoxLayout()
        
        # 标题
        title = QLabel("电源控制面板 - 实际设备控制演示")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 说明文字
        description = QLabel("""
本演示展示了重构后的电源控制面板功能：

✓ 支持实际设备控制（DP832、UDP3305S）
✓ 实时设备连接状态显示
✓ 电压、电流、功率实时监控
✓ 设备输出开关控制
✓ 完善的错误处理和日志记录
✓ 多设备同时控制

使用方法：
1. 确保设备已连接并配置正确
2. 勾选"Enable Communication"启用通信
3. 等待连接状态变为"Connected"
4. 进行设备控制操作
        """)
        description.setFont(QFont("Arial", 10))
        description.setWordWrap(True)
        layout.addWidget(description)
        
        # 启动按钮
        self.start_btn = QPushButton("启动电源控制面板")
        self.start_btn.setFont(QFont("Arial", 12))
        self.start_btn.clicked.connect(self.start_power_panel)
        layout.addWidget(self.start_btn)
        
        # 状态显示
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        layout.addWidget(QLabel("状态信息:"))
        layout.addWidget(self.status_text)
        
        self.setLayout(layout)
        
        # 电源面板实例
        self.power_panel = None
        
        # 添加初始状态信息
        self.add_status("演示程序已启动")
        self.add_status("点击按钮启动电源控制面板")

    def start_power_panel(self):
        """启动电源控制面板"""
        try:
            if self.power_panel is None:
                self.power_panel = PowerPanel()
                self.power_panel.show()
                self.add_status("电源控制面板已启动")
                self.start_btn.setText("面板已启动")
                self.start_btn.setEnabled(False)
            else:
                self.power_panel.show()
                self.power_panel.raise_()
                self.add_status("电源控制面板已显示")
        except Exception as e:
            self.add_status(f"启动失败: {str(e)}")

    def add_status(self, message):
        """添加状态信息"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_text.append(f"[{timestamp}] {message}")

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用程序信息
    app.setApplicationName("电源控制面板演示")
    app.setApplicationVersion("2.0")
    
    # 创建演示窗口
    demo = DemoWindow()
    demo.show()
    
    # 运行应用程序
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 