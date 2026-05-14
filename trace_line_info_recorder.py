import sys
import os
import csv
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QGridLayout, QPushButton, QLabel, 
                               QLineEdit, QTextEdit, QGroupBox, QMessageBox,
                               QFileDialog, QTableWidget, QTableWidgetItem,
                               QHeaderView, QFrame, QSplitter)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPalette, QColor

class TraceLineRecorder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.trace_data_dir = "D:/trace_data"
        self.current_trace = None
        self.trace_points = []
        self.is_recording = False
        
        # 确保数据目录存在
        os.makedirs(self.trace_data_dir, exist_ok=True)
        
        self.init_ui()
        self.setup_timer()
        
    def init_ui(self):
        self.setWindowTitle("航迹信息记录器")
        self.setGeometry(100, 100, 1200, 800)
        
        # 设置样式
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 8px 16px;
                text-align: center;
                font-size: 14px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QLineEdit, QTextEdit {
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 5px;
                font-size: 12px;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
            }
        """)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QHBoxLayout(central_widget)
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧控制面板
        left_panel = self.create_control_panel()
        splitter.addWidget(left_panel)
        
        # 右侧数据显示面板
        right_panel = self.create_data_panel()
        splitter.addWidget(right_panel)
        
        # 设置分割器比例
        splitter.setSizes([400, 800])
        
    def create_control_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 记录控制组
        control_group = QGroupBox("记录控制")
        control_layout = QVBoxLayout(control_group)
        
        # 开始记录按钮
        self.start_btn = QPushButton("开始记录航迹")
        self.start_btn.clicked.connect(self.start_trace)
        control_layout.addWidget(self.start_btn)
        
        # 记录中间点按钮
        self.midpoint_btn = QPushButton("记录中间点")
        self.midpoint_btn.clicked.connect(self.record_midpoint)
        self.midpoint_btn.setEnabled(False)
        control_layout.addWidget(self.midpoint_btn)
        
        # 结束记录按钮
        self.end_btn = QPushButton("记录结束点")
        self.end_btn.clicked.connect(self.end_trace)
        self.end_btn.setEnabled(False)
        control_layout.addWidget(self.end_btn)
        
        layout.addWidget(control_group)
        
        # 航迹参数组
        params_group = QGroupBox("规划航迹参数")
        params_layout = QGridLayout(params_group)
        
        # 航速
        params_layout.addWidget(QLabel("航线规划航速 (m/s):"), 0, 0)
        self.speed_edit = QLineEdit()
        self.speed_edit.setText()
        self.speed_edit.setPlaceholderText("输入航速")
        params_layout.addWidget(self.speed_edit, 0, 1)
        
        # 定深
        params_layout.addWidget(QLabel("航线规划航定深 (m):"), 1, 0)
        self.depth_edit = QLineEdit()
        self.depth_edit.setPlaceholderText("输入定深")
        params_layout.addWidget(self.depth_edit, 1, 1)
        
        # 距离
        params_layout.addWidget(QLabel("航线规划距离 (m):"), 2, 0)
        self.distance_edit = QLineEdit()
        self.distance_edit.setPlaceholderText("输入距离")
        params_layout.addWidget(self.distance_edit, 2, 1)
        
        # 目标姿态
        params_layout.addWidget(QLabel("目标姿态倾角（°）:"), 3, 0)
        self.attitude_edit = QLineEdit()
        self.attitude_edit.setPlaceholderText("输入目标姿态")
        params_layout.addWidget(self.attitude_edit, 3, 1)
        
        # 航迹航向角（移除，改为每个航点记录）
        # params_layout.addWidget(QLabel("航迹航向角（°）:"), 4, 0)
        # self.heading_edit = QLineEdit()
        # self.heading_edit.setPlaceholderText("输入航向角")
        # params_layout.addWidget(self.heading_edit, 4, 1)
        
        # 线圈电流
        params_layout.addWidget(QLabel("线圈电流 (A):"), 4, 0)
        self.coil_current_edit = QLineEdit()
        self.coil_current_edit.setPlaceholderText("输入线圈电流")
        params_layout.addWidget(self.coil_current_edit, 4, 1)
        
        layout.addWidget(params_group)
        
        # 备注组
        note_group = QGroupBox("备注信息")
        note_layout = QVBoxLayout(note_group)
        
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("输入备注信息...")
        self.note_edit.setMaximumHeight(100)
        note_layout.addWidget(self.note_edit)
        
        layout.addWidget(note_group)
        
        # 状态显示
        status_group = QGroupBox("记录状态")
        status_layout = QVBoxLayout(status_group)
        
        self.status_label = QLabel("未开始记录")
        self.status_label.setStyleSheet("color: #666666; font-weight: normal;")
        status_layout.addWidget(self.status_label)
        
        self.time_label = QLabel("")
        self.time_label.setStyleSheet("color: #666666; font-weight: normal;")
        status_layout.addWidget(self.time_label)
        
        layout.addWidget(status_group)
        
        layout.addStretch()
        return panel
        
    def create_data_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 当前航迹信息组
        current_group = QGroupBox("当前航迹信息")
        current_layout = QGridLayout(current_group)
        
        current_layout.addWidget(QLabel("起始时间:"), 0, 0)
        self.start_time_label = QLabel("--")
        current_layout.addWidget(self.start_time_label, 0, 1)
        
        current_layout.addWidget(QLabel("最近点时间:"), 1, 0)
        self.last_time_label = QLabel("--")
        current_layout.addWidget(self.last_time_label, 1, 1)
        
        current_layout.addWidget(QLabel("结束时间:"), 2, 0)
        self.end_time_label = QLabel("--")
        current_layout.addWidget(self.end_time_label, 2, 1)
        
        current_layout.addWidget(QLabel("记录点数:"), 3, 0)
        self.point_count_label = QLabel("0")
        current_layout.addWidget(self.point_count_label, 3, 1)
        
        layout.addWidget(current_group)
        
        # 航迹点列表
        points_group = QGroupBox("航迹点列表")
        points_layout = QVBoxLayout(points_group)
        
        self.points_table = QTableWidget()
        self.points_table.setColumnCount(11)
        self.points_table.setHorizontalHeaderLabels(["序号", "时间戳", "类型", "超短基线(m)", "激光测距仪(m)", "航点序号", "纬度(度分)", "经度(度分)", "海拔(m)", "航向角(°)", "备注"])
        self.points_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.points_table.setMaximumHeight(300)
        
        # 启用表格编辑
        self.points_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self.points_table.itemChanged.connect(self.on_table_item_changed)
        
        # 禁用经纬度列的编辑（因为现在是度分秒格式）
        self.points_table.setItemDelegateForColumn(6, None)  # 纬度列
        self.points_table.setItemDelegateForColumn(7, None)  # 经度列
        self.points_table.setItemDelegateForColumn(8, None)  # 海拔列
        self.points_table.setItemDelegateForColumn(9, None)  # 航向角列
        
        # 添加标志位防止递归
        self._updating_table = False
        
        points_layout.addWidget(self.points_table)
        
        layout.addWidget(points_group)
        
        # 操作按钮
        buttons_layout = QHBoxLayout()
        
        self.clear_btn = QPushButton("清空当前航迹")
        self.clear_btn.clicked.connect(self.clear_current_trace)
        self.clear_btn.setEnabled(False)
        buttons_layout.addWidget(self.clear_btn)
        
        self.export_btn = QPushButton("导出航迹数据")
        self.export_btn.clicked.connect(self.export_trace_data)
        self.export_btn.setEnabled(False)
        buttons_layout.addWidget(self.export_btn)
        self.export_btn.setVisible(False)

        layout.addLayout(buttons_layout)
        layout.addStretch()
        
        return panel
        
    def setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time_display)
        self.timer.start(1000)  # 每秒更新一次
        
    def update_time_display(self):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.time_label.setText(f"当前时间: {current_time}")
        
    def start_trace(self):
        if self.is_recording:
            QMessageBox.warning(self, "警告", "已在记录中，请先结束当前航迹")
            return
            
        # 验证必填字段
        if not self.speed_edit.text().strip():
            QMessageBox.warning(self, "警告", "请输入航速")
            return
        if not self.depth_edit.text().strip():
            QMessageBox.warning(self, "警告", "请输入定深")
            return
        if not self.distance_edit.text().strip():
            QMessageBox.warning(self, "警告", "请输入距离")
            return
        if not self.attitude_edit.text().strip():
            QMessageBox.warning(self, "警告", "请输入目标姿态")
            return
        # if not self.heading_edit.text().strip():
        #     QMessageBox.warning(self, "警告", "请输入航迹航向角")
        #     return
        if not self.coil_current_edit.text().strip():
            QMessageBox.warning(self, "警告", "请输入线圈电流")
            return
            
        # 创建新航迹
        start_time = datetime.now()
        self.current_trace = {
            'start_time': start_time,
            'last_time': start_time,
            'end_time': None,
            'speed': self.speed_edit.text().strip(),
            'depth': self.depth_edit.text().strip(),
            'distance': self.distance_edit.text().strip(),
            'attitude': self.attitude_edit.text().strip(),
            # 'heading': self.heading_edit.text().strip(),
            'coil_current': self.coil_current_edit.text().strip(),
            'note': self.note_edit.toPlainText().strip()
        }
        
        self.trace_points = [{
            'index': 1,
            'timestamp': start_time,
            'type': '起始点',
            'usbl_distance': 0.0,  # 起始点超短基线距离为0
            'laser_distance': 0.0,  # 起始点激光测距仪距离为0
            'waypoint_number': 'START',  # 起始点航点序号
            'latitude': None,  # 起始点纬度
            'longitude': None,  # 起始点经度
            'altitude': None,  # 起始点海拔
            'heading': None,  # 起始点航向角
            'note': '航迹开始 - 超短基线: 0.00m - 激光测距仪: 0.00m - 航点: START'
        }]
        
        self.is_recording = True
        self.update_ui_state()
        self.update_points_table()
        self.update_status("正在记录航迹...")
        
    def record_midpoint(self):
        if not self.is_recording:
            QMessageBox.warning(self, "警告", "请先开始记录航迹")
            return
            
        # 先生成记录航迹时间信息，避免延时不准
        current_time = datetime.now()
        self.current_trace['last_time'] = current_time
        
        # 弹出距离、航点序号和经纬度输入对话框
        from PySide6.QtWidgets import QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QDialogButtonBox, QSpinBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("记录中间点信息")
        dialog.setModal(True)
        dialog.resize(500, 300)
        
        layout = QVBoxLayout(dialog)
        
        # 超短基线距离输入
        usbl_distance_layout = QHBoxLayout()
        usbl_distance_layout.addWidget(QLabel("超短基线距离 (米):"))
        usbl_distance_edit = QLineEdit()
        usbl_distance_edit.setText("0")
        usbl_distance_edit.setPlaceholderText("输入超短基线距离")
        usbl_distance_layout.addWidget(usbl_distance_edit)
        layout.addLayout(usbl_distance_layout)
        
        # 激光测距仪距离输入
        laser_distance_layout = QHBoxLayout()
        laser_distance_layout.addWidget(QLabel("激光测距仪距离 (米):"))
        laser_distance_edit = QLineEdit()
        laser_distance_edit.setText("0")
        laser_distance_edit.setPlaceholderText("输入激光测距仪距离")
        laser_distance_layout.addWidget(laser_distance_edit)
        layout.addLayout(laser_distance_layout)
        
        # 航点序号输入
        waypoint_layout = QHBoxLayout()
        waypoint_layout.addWidget(QLabel("航点序号:"))
        waypoint_edit = QLineEdit()
        waypoint_edit.setText("-1")
        waypoint_edit.setPlaceholderText("输入航点序号")
        waypoint_layout.addWidget(waypoint_edit)
        layout.addLayout(waypoint_layout)
        
        # 纬度输入（度分）
        latitude_layout = QHBoxLayout()
        latitude_layout.addWidget(QLabel("纬度:"))
        
        # 度
        lat_deg_label = QLabel("度:")
        lat_deg_spin = QSpinBox()
        lat_deg_spin.setRange(0, 90)
        lat_deg_spin.setValue(29)
        lat_deg_spin.setSuffix("°")
        
        # 分（小数点后5位精度）
        lat_min_label = QLabel("分:")
        lat_min_edit = QLineEdit()
        lat_min_edit.setPlaceholderText("0.00000")
        lat_min_edit.setMaximumWidth(100)
        
        # 南北半球选择
        lat_hemisphere_label = QLabel("半球:")
        lat_hemisphere_edit = QLineEdit()
        lat_hemisphere_edit.setPlaceholderText("N/S")
        lat_hemisphere_edit.setMaximumWidth(50)
        lat_hemisphere_edit.setText("N")  # 默认北半球
        
        latitude_layout.addWidget(lat_deg_label)
        latitude_layout.addWidget(lat_deg_spin)
        latitude_layout.addWidget(lat_min_label)
        latitude_layout.addWidget(lat_min_edit)
        latitude_layout.addWidget(lat_hemisphere_label)
        latitude_layout.addWidget(lat_hemisphere_edit)
        layout.addLayout(latitude_layout)
        
        # 经度输入（度分）
        longitude_layout = QHBoxLayout()
        longitude_layout.addWidget(QLabel("经度:"))
        
        # 度
        lon_deg_label = QLabel("度:")
        lon_deg_spin = QSpinBox()
        lon_deg_spin.setRange(0, 180)
        lon_deg_spin.setValue(119)
        lon_deg_spin.setSuffix("°")
        
        # 分（小数点后5位精度）
        lon_min_label = QLabel("分:")
        lon_min_edit = QLineEdit()
        lon_min_edit.setPlaceholderText("0.00000")
        lon_min_edit.setMaximumWidth(100)
        
        # 东西半球选择
        lon_hemisphere_label = QLabel("半球:")
        lon_hemisphere_edit = QLineEdit()
        lon_hemisphere_edit.setPlaceholderText("E/W")
        lon_hemisphere_edit.setMaximumWidth(50)
        lon_hemisphere_edit.setText("E")  # 默认东半球
        
        longitude_layout.addWidget(lon_deg_label)
        longitude_layout.addWidget(lon_deg_spin)
        longitude_layout.addWidget(lon_min_label)
        longitude_layout.addWidget(lon_min_edit)
        longitude_layout.addWidget(lon_hemisphere_label)
        longitude_layout.addWidget(lon_hemisphere_edit)
        layout.addLayout(longitude_layout)
        
        # 海拔输入
        altitude_layout = QHBoxLayout()
        altitude_layout.addWidget(QLabel("海拔 (米):"))
        altitude_edit = QLineEdit()
        altitude_edit.setText("105.0")
        altitude_edit.setPlaceholderText("输入海拔高度")
        altitude_layout.addWidget(altitude_edit)
        layout.addLayout(altitude_layout)
        
        # 航向角输入
        heading_layout = QHBoxLayout()
        heading_layout.addWidget(QLabel("航向角 (度):"))
        heading_edit = QLineEdit()
        heading_edit.setText("0")
        heading_edit.setPlaceholderText("输入航向角")
        heading_layout.addWidget(heading_edit)
        layout.addLayout(heading_layout)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # 显示对话框
        if dialog.exec() == QDialog.Accepted:
            usbl_distance_text = usbl_distance_edit.text().strip()
            laser_distance_text = laser_distance_edit.text().strip()
            waypoint_text = waypoint_edit.text().strip()
            
            # 至少需要输入一种距离
            if not usbl_distance_text and not laser_distance_text:
                QMessageBox.warning(self, "警告", "请至少输入一种距离（超短基线或激光测距仪）")
                return
            
            # 处理超短基线距离
            usbl_distance = None
            if usbl_distance_text:
                try:
                    usbl_distance = float(usbl_distance_text)
                except ValueError:
                    QMessageBox.warning(self, "警告", "超短基线距离必须是数字")
                    return
            
            # 处理激光测距仪距离
            laser_distance = None
            if laser_distance_text:
                try:
                    laser_distance = float(laser_distance_text)
                except ValueError:
                    QMessageBox.warning(self, "警告", "激光测距仪距离必须是数字")
                    return
            
            # 处理度分秒格式的经纬度
            latitude = None
            longitude = None
            
            # 处理海拔
            altitude = None
            altitude_text = altitude_edit.text().strip()
            if altitude_text:
                try:
                    altitude = float(altitude_text)
                except ValueError:
                    QMessageBox.warning(self, "警告", "海拔必须是数字")
                    return
            
            # 处理航向角
            heading = None
            heading_text = heading_edit.text().strip()
            if heading_text:
                try:
                    heading = float(heading_text)
                    if not (0 <= heading <= 360):
                        QMessageBox.warning(self, "警告", "航向角必须在0到360度之间")
                        return
                except ValueError:
                    QMessageBox.warning(self, "警告", "航向角必须是数字")
                    return
            
            # 转换纬度（度分转十进制度）
            lat_hemisphere = lat_hemisphere_edit.text().strip().upper()
            if lat_hemisphere in ['N', 'S']:
                lat_deg = lat_deg_spin.value()
                lat_min_text = lat_min_edit.text().strip()
                
                if lat_min_text:
                    try:
                        lat_min = float(lat_min_text)
                        if not (0 <= lat_min < 60):
                            QMessageBox.warning(self, "警告", "纬度分必须在0到60之间")
                            return
                        
                        # 度分转十进制度
                        lat_decimal = lat_deg + lat_min / 60.0
                        if lat_hemisphere == 'S':
                            lat_decimal = -lat_decimal
                        latitude = lat_decimal
                    except ValueError:
                        QMessageBox.warning(self, "警告", "纬度分必须是数字")
                        return
                
            # 转换经度（度分转十进制度）
            lon_hemisphere = lon_hemisphere_edit.text().strip().upper()
            if lon_hemisphere in ['E', 'W']:
                lon_deg = lon_deg_spin.value()
                lon_min_text = lon_min_edit.text().strip()
                
                if lon_min_text:
                    try:
                        lon_min = float(lon_min_text)
                        if not (0 <= lon_min < 60):
                            QMessageBox.warning(self, "警告", "经度分必须在0到60之间")
                            return
                        
                        # 度分转十进制度
                        lon_decimal = lon_deg + lon_min / 60.0
                        if lon_hemisphere == 'W':
                            lon_decimal = -lon_decimal
                        longitude = lon_decimal
                    except ValueError:
                        QMessageBox.warning(self, "警告", "经度分必须是数字")
                        return
            
            # 添加中间点
            point_index = len(self.trace_points) + 1
            
            # 格式化度分显示
            lat_display = ""
            lon_display = ""
            
            if latitude is not None:
                lat_abs = abs(latitude)
                lat_deg = int(lat_abs)
                lat_min = (lat_abs - lat_deg) * 60
                lat_hemi = "N" if latitude >= 0 else "S"
                lat_display = f"{lat_deg}°{lat_min:.5f}'{lat_hemi}"
                
            if longitude is not None:
                lon_abs = abs(longitude)
                lon_deg = int(lon_abs)
                lon_min = (lon_abs - lon_deg) * 60
                lon_hemi = "E" if longitude >= 0 else "W"
                lon_display = f"{lon_deg}°{lon_min:.5f}'{lon_hemi}"
            
            self.trace_points.append({
                'index': point_index,
                'timestamp': current_time,
                'type': '中间点',
                'usbl_distance': usbl_distance,
                'laser_distance': laser_distance,
                'waypoint_number': waypoint_text,
                'latitude': latitude,
                'longitude': longitude,
                'altitude': altitude,
                'heading': heading,
                'note': self._generate_point_note(point_index-1, usbl_distance, laser_distance, waypoint_text, lat_display, lon_display, altitude, heading)
            })
            
            self.update_points_table()
            self.update_status(f"已记录中间点 #{point_index-1} - 超短基线距离: {usbl_distance:.2f}m - 激光测距仪距离：{laser_distance:.2f}m - 航点: {waypoint_text}")
        else:
            # 用户取消，恢复last_time
            if len(self.trace_points) > 0:
                self.current_trace['last_time'] = self.trace_points[-1]['timestamp']
        
    def end_trace(self):
        if not self.is_recording:
            QMessageBox.warning(self, "警告", "请先开始记录航迹")
            return
            
        # 先生成记录航迹时间信息，避免延时不准
        end_time = datetime.now()
        self.current_trace['end_time'] = end_time
        
        # 弹出距离和航点序号输入对话框
        from PySide6.QtWidgets import QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QDialogButtonBox
        
        # dialog = QDialog(self)
        # dialog.setWindowTitle("记录结束点信息")
        # dialog.setModal(True)
        # dialog.resize(300, 150)
        #
        # layout = QVBoxLayout(dialog)
        
        # 距离输入
        # distance_layout = QHBoxLayout()
        # distance_layout.addWidget(QLabel("距离 (米):"))
        # distance_edit = QLineEdit()
        # distance_edit.setPlaceholderText("输入距离")
        # distance_layout.addWidget(distance_edit)
        # layout.addLayout(distance_layout)
        
        # 航点序号输入
        # waypoint_layout = QHBoxLayout()
        # waypoint_layout.addWidget(QLabel("航点序号:"))
        # waypoint_edit = QLineEdit()
        # waypoint_edit.setPlaceholderText("输入航点序号")
        # waypoint_layout.addWidget(waypoint_edit)
        # layout.addLayout(waypoint_layout)
        
        # 按钮
        # button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # button_box.accepted.connect(dialog.accept)
        # button_box.rejected.connect(dialog.reject)
        # layout.addWidget(button_box)
        
        # 显示对话框
        # if dialog.exec() == QDialog.Accepted:
        #     distance_text = distance_edit.text().strip()
        #     waypoint_text = waypoint_edit.text().strip()
        #
        #     if not distance_text:
        #         QMessageBox.warning(self, "警告", "请输入距离")
        #         return
        #
        #     try:
        #         distance = float(distance_text)
        #     except ValueError:
        #         QMessageBox.warning(self, "警告", "距离必须是数字")
        #         return
            
        # 添加结束点
        point_index = len(self.trace_points) + 1
        self.trace_points.append({
            'index': point_index,
            'timestamp': end_time,
            'type': '结束点',
            'usbl_distance': 0.0,  # 结束点超短基线距离为0
            'laser_distance': 0.0,  # 结束点激光测距仪距离为0
            'waypoint_number': 0,
            'latitude': None,  # 结束点纬度
            'longitude': None,  # 结束点经度
            'altitude': None,  # 结束点海拔
            'heading': None,  # 结束点航向角
            'note': f'航迹结束 - 超短基线: 0.00m - 激光测距仪: 0.00m - 航点: Stop Point'
        })
            
        # 保存航迹数据
        self.save_trace_data()

        self.is_recording = False
        self.update_ui_state()
        self.update_points_table()
        self.update_status("航迹记录完成")
            
        QMessageBox.information(self, "完成", "航迹数据已保存")

        
    def save_trace_data(self):
        if not self.current_trace:
            return
            
        # 生成文件名
        timestamp = self.current_trace['start_time'].strftime("%Y%m%d_%H%M%S")
        filename = f"trace_{timestamp}.csv"
        filepath = os.path.join(self.trace_data_dir, filename)
        
        # 保存主航迹信息
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['起始时间戳', '最近点时间戳', '结束时间戳', '航线规划航速(m/s)', '航线规划定深(m)', '航线规划距离(m)', '航线规划目标姿态倾角（°）', '航迹航向角（°）', '线圈电流(A)', '备注'])
            writer.writerow([
                self.current_trace['start_time'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                self.current_trace['last_time'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                self.current_trace['end_time'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                self.current_trace['speed'],
                self.current_trace['depth'],
                self.current_trace['distance'],
                self.current_trace['attitude'],
                self.current_trace['heading'],
                self.current_trace['coil_current'],
                self.current_trace['note']
            ])
        
        # 保存航迹点详细信息
        points_filename = f"trace_points_{timestamp}.csv"
        points_filepath = os.path.join(self.trace_data_dir, points_filename)
        
        with open(points_filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['序号', '时间戳', '类型', '超短基线距离(m)', '激光测距仪距离(m)', '航点序号', '纬度(十进制度)', '经度(十进制度)', '纬度(度分)', '经度(度分)', '海拔(m)', '航向角(°)', '备注'])
            for point in self.trace_points:
                # 格式化度分显示
                lat_dm = ""
                lon_dm = ""
                
                if point.get('latitude') is not None:
                    lat = point['latitude']
                    lat_abs = abs(lat)
                    lat_deg = int(lat_abs)
                    lat_min = (lat_abs - lat_deg) * 60
                    lat_hemi = "N" if lat >= 0 else "S"
                    lat_dm = f"{lat_deg}°{lat_min:.5f}'{lat_hemi}"
                    
                if point.get('longitude') is not None:
                    lon = point['longitude']
                    lon_abs = abs(lon)
                    lon_deg = int(lon_abs)
                    lon_min = (lon_abs - lon_deg) * 60
                    lon_hemi = "E" if lon >= 0 else "W"
                    lon_dm = f"{lon_deg}°{lon_min:.5f}'{lon_hemi}"
                
                writer.writerow([
                    point['index'],
                    point['timestamp'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    point['type'],
                    f"{point.get('usbl_distance', ''):.2f}" if point.get('usbl_distance') is not None else '',
                    f"{point.get('laser_distance', ''):.2f}" if point.get('laser_distance') is not None else '',
                    point.get('waypoint_number', ''),
                    str(point.get('latitude', '')) if point.get('latitude') is not None else '',
                    str(point.get('longitude', '')) if point.get('longitude') is not None else '',
                    lat_dm,
                    lon_dm,
                    f"{point.get('altitude', ''):.2f}" if point.get('altitude') is not None else '',
                    f"{point.get('heading', ''):.1f}" if point.get('heading') is not None else '',
                    point['note']
                ])
                
    def clear_current_trace(self):
        if self.is_recording:
            QMessageBox.warning(self, "警告", "正在记录中，无法清空")
            return
            
        self.current_trace = None
        self.trace_points = []
        self.update_ui_state()
        self.update_points_table()
        self.update_status("未开始记录")
        
    def export_trace_data(self):
        if not self.current_trace:
            QMessageBox.warning(self, "警告", "没有可导出的航迹数据")
            return
            
        # 选择保存位置
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出航迹数据", 
            os.path.join(self.trace_data_dir, "trace_export.csv"),
            "CSV Files (*.csv)"
        )
        
        if filepath:
            self.save_trace_data()
            QMessageBox.information(self, "成功", f"航迹数据已导出到: {filepath}")
            
    def update_ui_state(self):
        self.start_btn.setEnabled(not self.is_recording)
        self.midpoint_btn.setEnabled(self.is_recording)
        self.end_btn.setEnabled(self.is_recording)
        self.clear_btn.setEnabled(self.current_trace is not None)
        self.export_btn.setEnabled(self.current_trace is not None)
        
        # 更新参数输入框状态
        readonly = self.is_recording
        self.speed_edit.setReadOnly(readonly)
        self.depth_edit.setReadOnly(readonly)
        self.distance_edit.setReadOnly(readonly)
        self.attitude_edit.setReadOnly(readonly)
        # self.heading_edit.setReadOnly(readonly)  # 已移除航向角全局输入
        self.coil_current_edit.setReadOnly(readonly)
        self.note_edit.setReadOnly(readonly)
        
    def update_points_table(self):
        # 防止递归调用
        if self._updating_table:
            return
            
        self._updating_table = True
        self.points_table.setRowCount(len(self.trace_points))
        
        for i, point in enumerate(self.trace_points):
            self.points_table.setItem(i, 0, QTableWidgetItem(str(point['index'])))
            self.points_table.setItem(i, 1, QTableWidgetItem(point['timestamp'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]))
            self.points_table.setItem(i, 2, QTableWidgetItem(point['type']))
            
            # 格式化超短基线距离显示
            usbl_display = ""
            if point.get('usbl_distance') is not None:
                usbl_display = f"{point['usbl_distance']:.2f}"
            self.points_table.setItem(i, 3, QTableWidgetItem(usbl_display))
            
            # 格式化激光测距仪距离显示
            laser_display = ""
            if point.get('laser_distance') is not None:
                laser_display = f"{point['laser_distance']:.2f}"
            self.points_table.setItem(i, 4, QTableWidgetItem(laser_display))
            
            self.points_table.setItem(i, 5, QTableWidgetItem(point.get('waypoint_number', '')))
            
            # 格式化纬度显示（度分）
            lat_display = ""
            if point.get('latitude') is not None:
                lat = point['latitude']
                lat_abs = abs(lat)
                lat_deg = int(lat_abs)
                lat_min = (lat_abs - lat_deg) * 60
                lat_hemi = "N" if lat >= 0 else "S"
                lat_display = f"{lat_deg}°{lat_min:.5f}'{lat_hemi}"
            self.points_table.setItem(i, 6, QTableWidgetItem(lat_display))
            
            # 格式化经度显示（度分）
            lon_display = ""
            if point.get('longitude') is not None:
                lon = point['longitude']
                lon_abs = abs(lon)
                lon_deg = int(lon_abs)
                lon_min = (lon_abs - lon_deg) * 60
                lon_hemi = "E" if lon >= 0 else "W"
                lon_display = f"{lon_deg}°{lon_min:.5f}'{lon_hemi}"
            self.points_table.setItem(i, 7, QTableWidgetItem(lon_display))
            
            # 格式化海拔显示
            altitude_display = ""
            if point.get('altitude') is not None:
                altitude_display = f"{point['altitude']:.2f}"
            self.points_table.setItem(i, 8, QTableWidgetItem(altitude_display))
            
            # 格式化航向角显示
            heading_display = ""
            if point.get('heading') is not None:
                heading_display = f"{point['heading']:.1f}"
            self.points_table.setItem(i, 9, QTableWidgetItem(heading_display))
            
            self.points_table.setItem(i, 10, QTableWidgetItem(point['note']))
            
        self._updating_table = False
            
        # 更新当前航迹信息
        if self.current_trace:
            self.start_time_label.setText(self.current_trace['start_time'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
            self.last_time_label.setText(self.current_trace['last_time'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
            if self.current_trace['end_time']:
                self.end_time_label.setText(self.current_trace['end_time'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
            else:
                self.end_time_label.setText("--")
            self.point_count_label.setText(str(len(self.trace_points)))
        else:
            self.start_time_label.setText("--")
            self.last_time_label.setText("--")
            self.end_time_label.setText("--")
            self.point_count_label.setText("0")
            
    def on_table_item_changed(self, item):
        """表格项目编辑完成时的处理"""
        # 防止递归调用
        if self._updating_table:
            return
            
        if not self.trace_points:
            return
            
        row = item.row()
        col = item.column()
        new_value = item.text()
        
        if row >= len(self.trace_points):
            return
            
        point = self.trace_points[row]
        
        # 根据列更新相应的数据
        if col == 3:  # 超短基线距离列
            try:
                usbl_distance = float(new_value) if new_value.strip() else None
                point['usbl_distance'] = usbl_distance
                # 更新备注
                self._update_point_note(point, row)
                self.update_status(f"已更新第{row+1}行超短基线距离: {usbl_distance:.2f}m" if usbl_distance is not None else f"已更新第{row+1}行超短基线距离: 清空")
            except ValueError:
                QMessageBox.warning(self, "警告", "超短基线距离必须是数字")
                # 恢复原值
                self._updating_table = True
                if point.get('usbl_distance') is not None:
                    item.setText(f"{point['usbl_distance']:.2f}")
                else:
                    item.setText("")
                self._updating_table = False
                return
                
        elif col == 4:  # 激光测距仪距离列
            try:
                laser_distance = float(new_value) if new_value.strip() else None
                point['laser_distance'] = laser_distance
                # 更新备注
                self._update_point_note(point, row)
                self.update_status(f"已更新第{row+1}行激光测距仪距离: {laser_distance:.2f}m" if laser_distance is not None else f"已更新第{row+1}行激光测距仪距离: 清空")
            except ValueError:
                QMessageBox.warning(self, "警告", "激光测距仪距离必须是数字")
                # 恢复原值
                self._updating_table = True
                if point.get('laser_distance') is not None:
                    item.setText(f"{point['laser_distance']:.2f}")
                else:
                    item.setText("")
                self._updating_table = False
                return
                
        elif col == 5:  # 航点序号列
            point['waypoint_number'] = new_value
            # 更新备注
            self._update_point_note(point, row)
            self.update_status(f"已更新第{row+1}行航点序号: {new_value}")
            
        elif col == 6:  # 纬度列 - 已禁用编辑
            pass
        elif col == 7:  # 经度列 - 已禁用编辑
            pass
        elif col == 8:  # 海拔列 - 已禁用编辑
            pass
        elif col == 9:  # 航向角列 - 已禁用编辑
            pass
                
        elif col == 10:  # 备注列
            point['note'] = new_value
            self.update_status(f"已更新第{row+1}行备注")
            
        # 只更新备注列，避免递归
        if col in [3, 4, 5]:  # 超短基线距离列、激光测距仪距离列或航点序号列
            self._updating_table = True
            # 只更新备注列
            self.points_table.setItem(row, 10, QTableWidgetItem(point['note']))
            self._updating_table = False
        
    def _generate_point_note(self, point_num, usbl_distance, laser_distance, waypoint, lat_display, lon_display, altitude, heading):
        """生成航迹点备注信息"""
        note_parts = [f'中间点 #{point_num} - 航点: {waypoint}']
        
        # 添加距离信息
        distance_parts = []
        if usbl_distance is not None:
            distance_parts.append(f'超短基线: {usbl_distance:.2f}m')
        if laser_distance is not None:
            distance_parts.append(f'激光测距仪: {laser_distance:.2f}m')
        if distance_parts:
            note_parts.append(' - '.join(distance_parts))
        
        if lat_display and lon_display:
            note_parts.append(f'坐标: ({lat_display}, {lon_display})')
        
        if altitude is not None:
            note_parts.append(f'海拔: {altitude:.2f}m')
            
        if heading is not None:
            note_parts.append(f'航向: {heading:.1f}°')
            
        return ' - '.join(note_parts)
    
    def _update_point_note(self, point, row):
        """更新航迹点备注信息"""
        if point['type'] == '起始点':
            usbl_dist = point.get('usbl_distance', 0.0)
            laser_dist = point.get('laser_distance', 0.0)
            point['note'] = f'航迹开始 - 超短基线: {usbl_dist:.2f}m - 激光测距仪: {laser_dist:.2f}m - 航点: {point.get("waypoint_number", "")}'
        elif point['type'] == '中间点':
            # 格式化经纬度显示
            lat_display = ""
            lon_display = ""
            if point.get('latitude') is not None:
                lat = point['latitude']
                lat_abs = abs(lat)
                lat_deg = int(lat_abs)
                lat_min = (lat_abs - lat_deg) * 60
                lat_hemi = "N" if lat >= 0 else "S"
                lat_display = f"{lat_deg}°{lat_min:.5f}'{lat_hemi}"
                
            if point.get('longitude') is not None:
                lon = point['longitude']
                lon_abs = abs(lon)
                lon_deg = int(lon_abs)
                lon_min = (lon_abs - lon_deg) * 60
                lon_hemi = "E" if lon >= 0 else "W"
                lon_display = f"{lon_deg}°{lon_min:.5f}'{lon_hemi}"
            
            point['note'] = self._generate_point_note(row, point.get('usbl_distance'), point.get('laser_distance'), point.get('waypoint_number', ''), lat_display, lon_display, point.get('altitude'), point.get('heading'))
        elif point['type'] == '结束点':
            usbl_dist = point.get('usbl_distance', 0.0)
            laser_dist = point.get('laser_distance', 0.0)
            point['note'] = f'航迹结束 - 超短基线: {usbl_dist:.2f}m - 激光测距仪: {laser_dist:.2f}m - 航点: {point.get("waypoint_number", "")}'
    
    def update_status(self, message):
        self.status_label.setText(message)
        if "正在记录" in message:
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        elif "完成" in message:
            self.status_label.setStyleSheet("color: #2196F3; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("color: #666666; font-weight: normal;")

def main():
    app = QApplication(sys.argv)
    
    # 设置应用程序信息
    app.setApplicationName("航迹信息记录器")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("DNVCS")
    
    window = TraceLineRecorder()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
