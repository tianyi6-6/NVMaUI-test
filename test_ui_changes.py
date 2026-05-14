#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试UI修改：合并按钮功能
"""

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel
from PySide6.QtCore import Qt

class TestUI(QMainWindow):
    """测试UI修改"""
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('UI修改测试')
        self.setGeometry(200, 200, 400, 300)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        # 测试按钮
        self.test_btn = QPushButton('开启航迹采集')
        self.test_btn.clicked.connect(self.toggle_collecting)
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        
        # 状态标签
        self.status_label = QLabel('就绪')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #e8f5e8;
                border: 1px solid #4CAF50;
                padding: 10px;
                border-radius: 5px;
                color: #2e7d32;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.test_btn)
        layout.addWidget(self.status_label)
        layout.addStretch()
        
        central_widget.setLayout(layout)
    
    def toggle_collecting(self):
        """切换采集状态"""
        if self.test_btn.text() == '开启航迹采集':
            # 开启采集
            self.test_btn.setText('停止并保存航迹')
            self.test_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ff9800;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #f57c00;
                }
                QPushButton:pressed {
                    background-color: #ef6c00;
                }
            """)
            self.status_label.setText('航迹采集中...')
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #fff3e0;
                    border: 1px solid #ff9800;
                    padding: 10px;
                    border-radius: 5px;
                    color: #e65100;
                    font-weight: bold;
                }
            """)
        else:
            # 停止采集并保存数据
            self.test_btn.setText('开启航迹采集')
            self.test_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QPushButton:pressed {
                    background-color: #3d8b40;
                }
            """)
            self.status_label.setText('正在保存数据...')
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #e8f5e8;
                    border: 1px solid #4CAF50;
                    padding: 10px;
                    border-radius: 5px;
                    color: #2e7d32;
                    font-weight: bold;
                }
            """)
            
            # 模拟保存完成
            import time
            time.sleep(1)
            self.status_label.setText('保存完成，就绪')

def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = TestUI()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 