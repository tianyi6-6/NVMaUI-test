#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试初始化默认航线功能
"""

import sys
import math
from datetime import datetime
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QTextEdit, QHBoxLayout
from PySide6.QtCore import Qt

class DefaultRouteTest(QMainWindow):
    """测试初始化默认航线功能"""
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('初始化默认航线功能测试')
        self.setGeometry(200, 200, 600, 400)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        # 按钮组
        button_layout = QHBoxLayout()
        
        self.test_default_route_btn = QPushButton('测试默认航线生成')
        self.test_default_route_btn.clicked.connect(self.test_default_route_generation)
        
        self.test_edit_restriction_btn = QPushButton('测试编辑限制')
        self.test_edit_restriction_btn.clicked.connect(self.test_edit_restriction)
        
        button_layout.addWidget(self.test_default_route_btn)
        button_layout.addWidget(self.test_edit_restriction_btn)
        
        layout.addLayout(button_layout)
        
        # 显示区域
        self.display_text = QTextEdit()
        self.display_text.setReadOnly(True)
        layout.addWidget(self.display_text)
        
        central_widget.setLayout(layout)
    
    def test_default_route_generation(self):
        """测试默认航线生成"""
        self.display_text.append("\n🔍 测试默认航线生成功能:")
        self.display_text.append("1. 设置实验站位置（例如：29.559678°, 119.176676°）")
        self.display_text.append("2. 点击'初始化默认航线'按钮（紫色按钮）")
        self.display_text.append("3. 验证是否生成9个航点（3x3网格）")
        self.display_text.append("4. 检查航点间距是否约为100米")
        self.display_text.append("5. 验证时间戳是否按5分钟间隔递增")
        
        # 计算示例坐标
        center_lat = 29.559678
        center_lon = 119.176676
        
        # 设置网格间距（约100米）
        lat_spacing = 100.0 / (111.0 * 1000)  # 100米转换为度
        lon_spacing = 100.0 / (111.0 * 1000 * math.cos(math.radians(center_lat)))  # 100米转换为度
        
        self.display_text.append(f"\n📐 示例计算:")
        self.display_text.append(f"实验站坐标: {center_lat:.6f}°, {center_lon:.6f}°")
        self.display_text.append(f"纬度间距: {lat_spacing:.8f}° (约100米)")
        self.display_text.append(f"经度间距: {lon_spacing:.8f}° (约100米)")
        
        # 显示9个航点的坐标
        self.display_text.append(f"\n📍 生成的9个航点坐标:")
        point_index = 1
        for row in range(-1, 2):  # -1, 0, 1
            for col in range(-1, 2):  # -1, 0, 1
                lat = center_lat + row * lat_spacing
                lon = center_lon + col * lon_spacing
                self.display_text.append(f"Point {point_index}: {lat:.6f}°, {lon:.6f}°")
                point_index += 1
    
    def test_edit_restriction(self):
        """测试编辑限制功能"""
        self.display_text.append("\n🔒 测试编辑限制功能:")
        self.display_text.append("1. 在航点表格中双击纬度或经度列")
        self.display_text.append("2. 验证是否显示提示信息")
        self.display_text.append("3. 确认无法直接编辑经纬度")
        self.display_text.append("4. 使用'编辑航点'按钮来修改坐标")
        self.display_text.append("5. 验证其他列（时间戳、激光测距、描述）仍可编辑")
        
        self.display_text.append("\n✅ 预期行为:")
        self.display_text.append("- 双击纬度/经度列时显示提示对话框")
        self.display_text.append("- 提示信息：'请使用编辑航点按钮来修改经纬度坐标'")
        self.display_text.append("- 表格值不会改变")
        self.display_text.append("- 时间戳、激光测距、描述列仍可正常编辑")

def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = DefaultRouteTest()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 