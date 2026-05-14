#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试时间戳功能
"""

import sys
from datetime import datetime
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QDateTimeEdit, QDialog, QDialogButtonBox
from PySide6.QtCore import QDateTime

class TimestampTest(QMainWindow):
    """测试时间戳功能"""
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('时间戳功能测试')
        self.setGeometry(200, 200, 400, 300)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        # 测试按钮
        self.test_btn = QPushButton('测试时间戳输入')
        self.test_btn.clicked.connect(self.test_timestamp_input)
        
        # 显示标签
        self.result_label = QLabel('点击按钮测试时间戳输入')
        self.result_label.setWordWrap(True)
        
        layout.addWidget(self.test_btn)
        layout.addWidget(self.result_label)
        layout.addStretch()
        
        central_widget.setLayout(layout)
    
    def test_timestamp_input(self):
        """测试时间戳输入"""
        # 获取当前时间
        current_time = datetime.now()
        
        # 创建时间戳输入对话框
        dialog = QDialog(self)
        dialog.setWindowTitle('测试时间戳输入')
        dialog.setModal(True)
        dialog.resize(300, 150)
        
        layout = QVBoxLayout()
        
        # 时间戳输入控件
        timestamp_edit = QDateTimeEdit()
        timestamp_edit.setDateTime(QDateTime(current_time))
        timestamp_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        timestamp_edit.setCalendarPopup(True)  # 允许弹出日历选择
        
        layout.addWidget(timestamp_edit)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            timestamp = timestamp_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
            self.result_label.setText(f'选择的时间戳: {timestamp}')
            
            # 验证时间戳格式
            try:
                parsed_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                self.result_label.setText(f'选择的时间戳: {timestamp}\n验证成功: {parsed_time}')
            except ValueError as e:
                self.result_label.setText(f'时间戳格式错误: {e}')

def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = TimestampTest()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 