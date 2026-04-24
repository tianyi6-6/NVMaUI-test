#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试导入和编辑航点功能
"""

import sys
import json
import os
from datetime import datetime
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QTextEdit, QHBoxLayout
from PySide6.QtCore import Qt

class ImportEditTest(QMainWindow):
    """测试导入和编辑功能"""
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('导入和编辑功能测试')
        self.setGeometry(200, 200, 600, 400)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        # 按钮组
        button_layout = QHBoxLayout()
        
        self.create_test_file_btn = QPushButton('创建测试JSON文件')
        self.create_test_file_btn.clicked.connect(self.create_test_json_file)
        
        self.test_import_btn = QPushButton('测试导入功能')
        self.test_import_btn.clicked.connect(self.test_import_function)
        
        self.test_edit_btn = QPushButton('测试编辑功能')
        self.test_edit_btn.clicked.connect(self.test_edit_function)
        
        button_layout.addWidget(self.create_test_file_btn)
        button_layout.addWidget(self.test_import_btn)
        button_layout.addWidget(self.test_edit_btn)
        
        layout.addLayout(button_layout)
        
        # 显示区域
        self.display_text = QTextEdit()
        self.display_text.setReadOnly(True)
        layout.addWidget(self.display_text)
        
        central_widget.setLayout(layout)
    
    def create_test_json_file(self):
        """创建测试JSON文件"""
        # 创建测试数据
        test_data = {
            "NV Mag Station": {
                "名称": "测试实验站",
                "纬度": 29.559678,
                "经度": 119.176676
            },
            "航点数据": [
                {
                    "名称": "Point 1",
                    "时间戳": "2024-01-15 10:30:00",
                    "纬度": 29.560000,
                    "经度": 119.177000,
                    "激光测距仪(m)": 150.5,
                    "描述": "起始点"
                },
                {
                    "名称": "Point 2",
                    "时间戳": "2024-01-15 10:35:00",
                    "纬度": 29.561000,
                    "经度": 119.178000,
                    "激光测距仪(m)": 200.0,
                    "描述": "中间点"
                },
                {
                    "名称": "Point 3",
                    "时间戳": "2024-01-15 10:40:00",
                    "纬度": 29.562000,
                    "经度": 119.179000,
                    "激光测距仪(m)": 250.3,
                    "描述": "结束点"
                }
            ]
        }
        
        # 保存到文件
        save_dir = "D:/geo_sites_locator"
        try:
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, "测试航迹数据.json")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(test_data, f, ensure_ascii=False, indent=2)
            
            self.display_text.append(f"✅ 测试JSON文件创建成功: {filepath}")
            self.display_text.append("文件内容:")
            self.display_text.append(json.dumps(test_data, ensure_ascii=False, indent=2))
            
        except Exception as e:
            self.display_text.append(f"❌ 创建测试文件失败: {str(e)}")
    
    def test_import_function(self):
        """测试导入功能"""
        self.display_text.append("\n🔍 测试导入功能:")
        self.display_text.append("1. 点击'导入航迹'按钮")
        self.display_text.append("2. 选择刚才创建的测试JSON文件")
        self.display_text.append("3. 验证航点是否正确导入")
        self.display_text.append("4. 检查是否询问设置实验站")
    
    def test_edit_function(self):
        """测试编辑功能"""
        self.display_text.append("\n🔍 测试编辑功能:")
        self.display_text.append("1. 先导入一些航点数据")
        self.display_text.append("2. 在表格中选择一个航点")
        self.display_text.append("3. 点击'编辑航点'按钮")
        self.display_text.append("4. 验证对话框是否显示当前值")
        self.display_text.append("5. 修改一些值并保存")
        self.display_text.append("6. 检查表格是否更新")

def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = ImportEditTest()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 