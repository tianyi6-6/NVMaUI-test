#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试崩溃修复
"""

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QTextEdit
from PySide6.QtCore import Qt

class CrashFixTest(QMainWindow):
    """测试崩溃修复"""
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('崩溃修复测试')
        self.setGeometry(200, 200, 500, 300)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        # 测试按钮
        self.test_btn = QPushButton('测试初始化默认航线功能')
        self.test_btn.clicked.connect(self.test_init_default_route)
        
        # 显示区域
        self.display_text = QTextEdit()
        self.display_text.setReadOnly(True)
        
        layout.addWidget(self.test_btn)
        layout.addWidget(self.display_text)
        
        central_widget.setLayout(layout)
    
    def test_init_default_route(self):
        """测试初始化默认航线功能"""
        self.display_text.append("🔧 崩溃修复测试:")
        self.display_text.append("")
        self.display_text.append("✅ 修复内容:")
        self.display_text.append("1. 在init_default_waypoints方法中暂时禁用回调")
        self.display_text.append("2. 使用try-finally确保回调被正确恢复")
        self.display_text.append("3. 避免update_table()触发的递归调用")
        self.display_text.append("")
        self.display_text.append("🧪 测试步骤:")
        self.display_text.append("1. 运行主程序: python geo_sites_locator.py")
        self.display_text.append("2. 设置实验站位置")
        self.display_text.append("3. 点击'初始化默认航线'按钮")
        self.display_text.append("4. 验证程序不会崩溃")
        self.display_text.append("5. 检查是否生成9个航点")
        self.display_text.append("6. 验证地图是否正确显示航点")
        self.display_text.append("")
        self.display_text.append("🎯 预期结果:")
        self.display_text.append("- 程序不会崩溃")
        self.display_text.append("- 成功生成9个默认航点")
        self.display_text.append("- 地图正确显示3x3网格")
        self.display_text.append("- 表格正确显示航点信息")
        self.display_text.append("- 可以正常编辑航点")

def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = CrashFixTest()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 