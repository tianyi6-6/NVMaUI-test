#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试TimerThread类的功能
"""

import time
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel
from PySide6.QtCore import QThread, Signal, QTimer

class TimerThread(QThread):
    timer_finished = Signal()
    
    def __init__(self, target_time):
        super().__init__()
        self.target_time = target_time
        self._cancelled = False
        
    def run(self):
        print(f"定时器线程开始，目标时间: {time.strftime('%H:%M:%S', time.localtime(self.target_time))}")
        while time.time() < self.target_time and not self._cancelled:
            time.sleep(0.001)  # 1ms检查间隔
        if not self._cancelled:
            print("定时器完成，发送信号")
            self.timer_finished.emit()
        else:
            print("定时器被取消")
    
    def cancel(self):
        print("取消定时器")
        self._cancelled = True

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TimerThread测试")
        self.setGeometry(100, 100, 400, 200)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建控件
        self.status_label = QLabel("状态: 空闲")
        self.start_btn = QPushButton("开始定时(5秒)")
        self.cancel_btn = QPushButton("取消定时")
        self.cancel_btn.setEnabled(False)
        
        # 连接信号
        self.start_btn.clicked.connect(self.start_timer)
        self.cancel_btn.clicked.connect(self.cancel_timer)
        
        # 添加到布局
        layout.addWidget(self.status_label)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.cancel_btn)
        
        # 定时器线程
        self.timer_thread = None
        
    def start_timer(self):
        target_time = time.time() + 5  # 5秒后
        self.timer_thread = TimerThread(target_time)
        self.timer_thread.timer_finished.connect(self.on_timer_finished)
        self.timer_thread.start()
        
        self.status_label.setText("状态: 等待定时...")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        
    def cancel_timer(self):
        if self.timer_thread and self.timer_thread.isRunning():
            self.timer_thread.cancel()
            self.timer_thread.wait()
            self.timer_thread = None
            
        self.status_label.setText("状态: 空闲")
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        
    def on_timer_finished(self):
        self.status_label.setText("状态: 定时完成!")
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.timer_thread = None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec()) 