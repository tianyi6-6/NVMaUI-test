import sys
import math
import os
import json
from datetime import datetime
from typing import List, Tuple, Optional
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QDialog,
                               QWidget, QTableWidget, QTableWidgetItem, QPushButton, 
                               QLabel, QHeaderView, QMessageBox, QInputDialog, QGroupBox,
                               QLineEdit, QFormLayout, QSpinBox, QDoubleSpinBox, QTextEdit,
                               QFileDialog, QFrame, QSplitter)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPixmap, QPalette, QColor
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy as np


class GeoPoint:
    """地理坐标点类"""
    def __init__(self, name: str, lat: float, lon: float, timestamp: str = "", description: str = "", laser_distance: float = -1.0):
        self.name = name
        self.lat = lat  # 纬度
        self.lon = lon  # 经度
        self.timestamp = timestamp
        self.description = description
        self.laser_distance = laser_distance  # 激光测距仪距离(m)，-1表示未启动
    
    def distance_to(self, other: 'GeoPoint') -> float:
        """计算到另一个点的距离（使用Haversine公式）"""
        R = 6371  # 地球半径（公里）
        
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(other.lat), math.radians(other.lon)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = (math.sin(dlat/2)**2 + 
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2)
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c

class SatelliteMapWidget(QWidget):
    """卫星地图显示组件"""
    def __init__(self):
        super().__init__()
        self.experiment_station: Optional[GeoPoint] = None
        self.waypoints: List[GeoPoint] = []
        self.is_collecting = False
        self.distance_range = 800  # 默认800m
        
        # 创建matplotlib图形
        self.figure = Figure(figsize=(12, 10))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        
        # 设置布局
        layout = QVBoxLayout()
        
        # 添加matplotlib工具栏
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        
        # 初始化地图
        self.init_map()
    
    def set_distance_range(self, range_meters: int):
        """设置距离范围"""
        self.distance_range = range_meters
        self.update_map_range()
        self.redraw_map()
    
    def init_map(self):
        """初始化地图"""
        self.ax.clear()
        
        # 设置默认地图范围（基于默认坐标119°E, 29°N）
        # 使用距离范围设置地图大小
        center_lon = 119
        center_lat = 29
        
        # 将距离范围转换为经纬度范围（近似）
        # 1度纬度约等于111km，1度经度在29°N约等于97km
        lat_margin = (self.distance_range / 1000.0) / 111.0
        lon_margin = (self.distance_range / 1000.0) / 97.0
        
        self.ax.set_xlim(center_lon - lon_margin, center_lon + lon_margin)
        self.ax.set_ylim(center_lat - lat_margin, center_lat + lat_margin)
        
        # 设置标签
        self.ax.set_xlabel('Longitude (°E)')
        self.ax.set_ylabel('Latitude (°N)')
        self.ax.set_title(f'Experimental Area Map ({self.distance_range}m × {self.distance_range}m)')
        self.ax.grid(True, alpha=0.3)
        
        # 绘制简化的海岸线
        self.draw_coastline()
        
        self.canvas.draw()
    
    def draw_coastline(self):
        """绘制简化的海岸线"""
        # 基于新的地图范围绘制简化的海岸线
        # 这里绘制一个简单的矩形表示陆地边界
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        
        # 绘制一个简化的海岸线矩形
        coastline_lon = [xlim[0], xlim[1], xlim[1], xlim[0], xlim[0]]
        coastline_lat = [ylim[0], ylim[0], ylim[1], ylim[1], ylim[0]]
        self.ax.plot(coastline_lon, coastline_lat, 'b-', linewidth=1, alpha=0.3)
        
        # 绘制距离范围边界框
        if self.experiment_station:
            center_lat = self.experiment_station.lat
            center_lon = self.experiment_station.lon
            
            lat_margin = (self.distance_range / 1000.0) / 111.0
            lon_margin = (self.distance_range / 1000.0) / (111.0 * math.cos(math.radians(center_lat)))
            
            # 绘制距离范围边界框
            boundary_lon = [center_lon - lon_margin, center_lon + lon_margin, 
                           center_lon + lon_margin, center_lon - lon_margin, 
                           center_lon - lon_margin]
            boundary_lat = [center_lat - lat_margin, center_lat - lat_margin, 
                           center_lat + lat_margin, center_lat + lat_margin, 
                           center_lat - lat_margin]
            self.ax.plot(boundary_lon, boundary_lat, 'g--', linewidth=2, alpha=0.7, 
                        label=f'{self.distance_range}m Boundary')
    

    
    def set_experiment_station(self, lat: float, lon: float, name: str = "实验站"):
        """设置实验站位置"""
        self.experiment_station = GeoPoint(name, lat, lon)
        self.update_map_range()
        self.redraw_map()
    
    def update_map_range(self):
        """更新地图范围以实验站为中心的指定距离正方形"""
        if self.experiment_station:
            center_lat = self.experiment_station.lat
            center_lon = self.experiment_station.lon
            
            # 将距离范围转换为经纬度范围（近似）
            # 1度纬度约等于111km，1度经度在center_lat约等于111*cos(center_lat)km
            lat_margin = (self.distance_range / 1000.0) / 111.0
            lon_margin = (self.distance_range / 1000.0) / (111.0 * math.cos(math.radians(center_lat)))
            
            self.ax.set_xlim(center_lon - lon_margin, center_lon + lon_margin)
            self.ax.set_ylim(center_lat - lat_margin, center_lat + lat_margin)
        else:
            # 如果没有实验站，使用默认范围
            center_lon = 119
            center_lat = 29
            lat_margin = (self.distance_range / 1000.0) / 111.0
            lon_margin = (self.distance_range / 1000.0) / (111.0 * math.cos(math.radians(center_lat)))
            
            self.ax.set_xlim(center_lon - lon_margin, center_lon + lon_margin)
            self.ax.set_ylim(center_lat - lat_margin, center_lat + lat_margin)
    
    def add_waypoint(self, waypoint: GeoPoint):
        """添加航点"""
        self.waypoints.append(waypoint)
        self.redraw_map()
    
    def clear_waypoints(self):
        """清空航点"""
        self.waypoints.clear()
        self.redraw_map()
    
    def set_collecting_status(self, is_collecting: bool):
        """设置采集状态"""
        self.is_collecting = is_collecting
        self.redraw_map()
    
    def redraw_map(self):
        """重绘地图"""
        self.ax.clear()
        
        # 更新地图范围
        self.update_map_range()
        
        # 设置标签
        self.ax.set_xlabel('Longitude (°E)')
        self.ax.set_ylabel('Latitude (°N)')
        self.ax.set_title(f'Experimental Area Map ({self.distance_range}m × {self.distance_range}m)')
        self.ax.grid(True, alpha=0.3)
        
        # 绘制简化的海岸线
        self.draw_coastline()
        
        # 绘制实验站（黄色高亮）
        if self.experiment_station:
            self.ax.scatter(self.experiment_station.lon, self.experiment_station.lat, 
                          c='yellow', s=200, alpha=0.8, zorder=10, edgecolors='orange', linewidth=2)
            self.ax.annotate(f'{self.experiment_station.name}\n({self.experiment_station.lat:.6f}°, {self.experiment_station.lon:.6f}°)', 
                           (self.experiment_station.lon, self.experiment_station.lat),
                           xytext=(10, 10), textcoords='offset points',
                           fontsize=10, color='black', weight='bold',
                           bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.8))
        
        # 绘制航点（红色点）
        if self.waypoints:
            waypoint_lats = [p.lat for p in self.waypoints]
            waypoint_lons = [p.lon for p in self.waypoints]
            
            self.ax.scatter(waypoint_lons, waypoint_lats, c='red', s=100, alpha=0.8, zorder=5)
            
            # 添加航点标签（只显示序号）
            for i, waypoint in enumerate(self.waypoints):
                self.ax.annotate(f"{i+1}", (waypoint.lon, waypoint.lat),
                               xytext=(5, 5), textcoords='offset points',
                               fontsize=10, color='red', weight='bold',
                               bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))
            
            # 绘制航迹线
            if len(self.waypoints) > 1:
                self.ax.plot(waypoint_lons, waypoint_lats, 'r--', linewidth=2, alpha=0.6)
            
            # 绘制拟合直线
            if len(self.waypoints) >= 2:
                self.draw_fitted_line()
        
        # 保持固定地图范围，不自动调整
        # 地图范围已在init_map中设置为固定值
        
        self.canvas.draw()
    
    def draw_fitted_line(self):
        """绘制拟合直线"""
        if len(self.waypoints) < 2:
            return
        
        # 获取航点坐标
        lats = [p.lat for p in self.waypoints]
        lons = [p.lon for p in self.waypoints]
        
        # 检查是否所有航点都在同一经度线上（垂直直线）
        if len(set(lons)) == 1:
            # 垂直直线情况：所有航点经度相同
            vertical_lon = lons[0]
            heading_angle = 90.0  # 垂直直线，航向角为90度
            
            # 计算直线到实验站的距离（水平距离）
            distance_to_station = 0
            if self.experiment_station:
                distance_to_station = abs(self.experiment_station.lon - vertical_lon) * 111.0 * 1000 * math.cos(math.radians(self.experiment_station.lat))
            
            # 绘制垂直直线
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()
            
            # 垂直直线与地图边界的交点
            line_points = []
            for y in [ylim[0], ylim[1]]:
                if xlim[0] <= vertical_lon <= xlim[1]:
                    line_points.append((vertical_lon, y))
            
            if len(line_points) >= 2:
                line_x = [p[0] for p in line_points]
                line_y = [p[1] for p in line_points]
                
                label_text = f'Heading: {heading_angle:.1f}° Dist: {distance_to_station:.1f}m'
                self.ax.plot(line_x, line_y, 'b-', linewidth=3, alpha=0.8, 
                            label=label_text)
                self.ax.legend()
            return
        
        # 检查是否所有航点都在同一纬度线上（水平直线）
        if len(set(lats)) == 1:
            # 水平直线情况：所有航点纬度相同
            horizontal_lat = lats[0]
            heading_angle = 0.0  # 水平直线，航向角为0度
            
            # 计算直线到实验站的距离（垂直距离）
            distance_to_station = 0
            if self.experiment_station:
                distance_to_station = abs(self.experiment_station.lat - horizontal_lat) * 111.0 * 1000
            
            # 绘制水平直线
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()
            
            # 水平直线与地图边界的交点
            line_points = []
            for x in [xlim[0], xlim[1]]:
                if ylim[0] <= horizontal_lat <= ylim[1]:
                    line_points.append((x, horizontal_lat))
            
            if len(line_points) >= 2:
                line_x = [p[0] for p in line_points]
                line_y = [p[1] for p in line_points]
                
                label_text = f'Heading: {heading_angle:.1f}° Dist: {distance_to_station:.1f}m'
                self.ax.plot(line_x, line_y, 'b-', linewidth=3, alpha=0.8, 
                            label=label_text)
                self.ax.legend()
            return
        
        # 使用numpy进行直线拟合
        try:
            coeffs = np.polyfit(lons, lats, 1)
            slope = coeffs[0]
            intercept = coeffs[1]
            
            # 检查斜率是否为无穷大或NaN
            if not np.isfinite(slope) or not np.isfinite(intercept):
                return
            
            # 计算航向角（以正北为0度，顺时针为正）
            heading_angle = math.degrees(math.atan(slope))
            if heading_angle < 0:
                heading_angle += 360
            
            # 计算直线到实验站的距离
            distance_to_station = 0
            if self.experiment_station:
                station_lat = self.experiment_station.lat
                station_lon = self.experiment_station.lon
                
                # 点到直线距离公式
                # 直线方程: lat = slope * lon + intercept
                # 标准形式: slope * lon - lat + intercept = 0
                # 点(x0,y0)到直线ax+by+c=0的距离: |ax0+by0+c|/sqrt(a^2+b^2)
                a = slope
                b = -1
                c = intercept
                
                denominator = math.sqrt(a**2 + b**2)
                if denominator > 1e-10:  # 避免除零错误
                    distance_to_line = abs(a * station_lon + b * station_lat + c) / denominator
                    # 转换为米（近似）
                    distance_to_station = distance_to_line * 111.0 * 1000  # 1度约等于111km
                else:
                    # 实验站正好在直线上
                    distance_to_station = 0.0
            
            # 计算直线的起点和终点（在地图范围内）
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()
            
            # 计算直线与地图边界的交点
            line_points = []
            
            # 与左右边界相交
            for x in [xlim[0], xlim[1]]:
                y = slope * x + intercept
                if ylim[0] <= y <= ylim[1]:
                    line_points.append((x, y))
            
            # 与上下边界相交
            for y in [ylim[0], ylim[1]]:
                if abs(slope) > 1e-10:  # 避免除零错误
                    x = (y - intercept) / slope
                    if xlim[0] <= x <= xlim[1]:
                        line_points.append((x, y))
            
            # 如果找到了交点，绘制直线
            if len(line_points) >= 2:
                # 按x坐标排序
                line_points.sort(key=lambda p: p[0])
                
                # 绘制拟合直线
                line_x = [p[0] for p in line_points]
                line_y = [p[1] for p in line_points]
                
                # 创建标签，显示航向角和距离
                label_text = f'Heading: {heading_angle:.1f}° Dist: {distance_to_station:.1f}m'
                
                self.ax.plot(line_x, line_y, 'b-', linewidth=3, alpha=0.8, 
                            label=label_text)
                
                # 添加图例
                self.ax.legend()
                
        except (np.linalg.LinAlgError, ValueError, RuntimeWarning) as e:
            # 处理拟合失败的情况
            print(f"直线拟合失败: {e}")
            return

class WaypointTableWidget(QWidget):
    """航点表格组件"""
    def __init__(self):
        super().__init__()
        self.waypoints: List[GeoPoint] = []
        self.on_waypoints_changed = None
        self.is_collecting = False
        self.experiment_station = None
        
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout()
        
        # 按钮组（移动到表格上方）
        button_layout = QHBoxLayout()
        
        self.add_btn = QPushButton('新增航点')
        self.add_btn.clicked.connect(self.add_waypoint)
        self.add_btn.setEnabled(False)  # 初始禁用
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
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
        """)
        
        self.delete_btn = QPushButton('删除选中航点')
        self.delete_btn.clicked.connect(self.delete_selected_waypoint)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #c62828;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        
        self.clear_btn = QPushButton('清空航点')
        self.clear_btn.clicked.connect(self.clear_waypoints)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #9e9e9e;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #757575;
            }
            QPushButton:pressed {
                background-color: #616161;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        
        self.import_btn = QPushButton('导入航迹')
        self.import_btn.clicked.connect(self.import_waypoints)
        self.import_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        
        self.edit_btn = QPushButton('编辑航点')
        self.edit_btn.clicked.connect(self.edit_selected_waypoint)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.import_btn)
        button_layout.addStretch()
        
        # 创建表格
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(['序号', '时间戳', '纬度', '经度', '距离(m)', '激光测距(m)', '描述'])
        
        # 设置表格属性
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        
        # 禁用表格直接编辑
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # 为所有列添加双击编辑功能
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        
        layout.addLayout(button_layout)
        layout.addWidget(self.table)
        
        self.setLayout(layout)
    
    def set_collecting_status(self, is_collecting: bool):
        """设置采集状态"""
        self.is_collecting = is_collecting
        self.add_btn.setEnabled(is_collecting)
    
    def create_waypoint_dialog(self, title: str, default_waypoint: GeoPoint = None) -> tuple:
        """创建航点编辑对话框，返回对话框和控件元组"""
        from PySide6.QtWidgets import QDialog, QGridLayout, QDialogButtonBox, QDateTimeEdit
        from PySide6.QtCore import QDateTime
        
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.resize(400, 350)
        
        layout = QGridLayout()
        
        # 设置默认值
        if default_waypoint:
            # 编辑模式：使用现有航点的值
            try:
                current_time = datetime.strptime(default_waypoint.timestamp, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                current_time = datetime.now()
            
            lat_deg = int(default_waypoint.lat)
            lat_min = (default_waypoint.lat - lat_deg) * 60.0
            lon_deg = int(default_waypoint.lon)
            lon_min = (default_waypoint.lon - lon_deg) * 60.0
            laser_distance = default_waypoint.laser_distance
            description = default_waypoint.description
        else:
            # 新增模式：使用默认值
            current_time = datetime.now()
            lat_deg = 29
            lat_min = 33.60528
            lon_deg = 119
            lon_min = 10.60056
            laser_distance = -1
            description = ""
        
        # 时间戳输入
        layout.addWidget(QLabel('时间戳:'), 0, 0)
        timestamp_edit = QDateTimeEdit()
        timestamp_edit.setDateTime(QDateTime(current_time))
        timestamp_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        timestamp_edit.setCalendarPopup(True)
        layout.addWidget(timestamp_edit, 0, 1, 1, 4)
        
        # 纬度输入
        layout.addWidget(QLabel('纬度:'), 1, 0)
        lat_deg_spin = QSpinBox()
        lat_deg_spin.setRange(-90, 90)
        lat_deg_spin.setValue(lat_deg)
        layout.addWidget(lat_deg_spin, 1, 1)
        layout.addWidget(QLabel('度'), 1, 2)
        
        lat_min_spin = QDoubleSpinBox()
        lat_min_spin.setRange(0, 59.999999)
        lat_min_spin.setDecimals(6)
        lat_min_spin.setValue(lat_min)
        layout.addWidget(lat_min_spin, 1, 3)
        layout.addWidget(QLabel('分'), 1, 4)
        
        # 经度输入
        layout.addWidget(QLabel('经度:'), 2, 0)
        lon_deg_spin = QSpinBox()
        lon_deg_spin.setRange(-180, 180)
        lon_deg_spin.setValue(lon_deg)
        layout.addWidget(lon_deg_spin, 2, 1)
        layout.addWidget(QLabel('度'), 2, 2)
        
        lon_min_spin = QDoubleSpinBox()
        lon_min_spin.setRange(0, 59.999999)
        lon_min_spin.setDecimals(6)
        lon_min_spin.setValue(lon_min)
        layout.addWidget(lon_min_spin, 2, 3)
        layout.addWidget(QLabel('分'), 2, 4)
        
        # 激光测距仪输入
        layout.addWidget(QLabel('激光测距仪(m):'), 3, 0)
        laser_distance_spin = QDoubleSpinBox()
        laser_distance_spin.setRange(-1, 10000)
        laser_distance_spin.setDecimals(2)
        laser_distance_spin.setValue(laser_distance)
        laser_distance_spin.setSuffix(' m')
        layout.addWidget(laser_distance_spin, 3, 1, 1, 4)
        
        # 描述输入
        layout.addWidget(QLabel('描述:'), 4, 0)
        desc_edit = QLineEdit()
        desc_edit.setText(description)
        layout.addWidget(desc_edit, 4, 1, 1, 4)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box, 5, 0, 1, 5)
        
        dialog.setLayout(layout)
        
        return dialog, (timestamp_edit, lat_deg_spin, lat_min_spin, lon_deg_spin, lon_min_spin, laser_distance_spin, desc_edit)
    
    def add_waypoint(self):
        """添加新航点"""
        if not self.is_collecting:
            QMessageBox.warning(self, '警告', '请先开启航迹采集')
            return
        
        dialog, (timestamp_edit, lat_deg_spin, lat_min_spin, lon_deg_spin, lon_min_spin, laser_distance_spin, desc_edit) = self.create_waypoint_dialog('输入航点信息')
        
        if dialog.exec() == QDialog.Accepted:
            # 获取时间戳
            timestamp = timestamp_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
            
            # 转换为十进制度数
            lat = lat_deg_spin.value() + lat_min_spin.value() / 60.0
            lon = lon_deg_spin.value() + lon_min_spin.value() / 60.0
            laser_distance = laser_distance_spin.value()
            description = desc_edit.text()
            
            # 创建航点
            waypoint = GeoPoint(f"Point {len(self.waypoints)+1}", lat, lon, timestamp, description, laser_distance)
            self.waypoints.append(waypoint)
            self.update_table()
    
    def delete_selected_waypoint(self):
        """删除选中的航点"""
        current_row = self.table.currentRow()
        if current_row >= 0 and current_row < len(self.waypoints):
            reply = QMessageBox.question(self, '确认删除', 
                                       f'确定要删除航点 {current_row + 1} 吗？',
                                       QMessageBox.Yes | QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                self.waypoints.pop(current_row)
                self.update_table()
        else:
            QMessageBox.warning(self, '警告', '请先选择要删除的航点')
    
    def edit_selected_waypoint(self):
        """编辑选中的航点"""
        current_row = self.table.currentRow()
        if current_row < 0 or current_row >= len(self.waypoints):
            QMessageBox.warning(self, '警告', '请先选择要编辑的航点')
            return
        
        waypoint = self.waypoints[current_row]
        dialog, (timestamp_edit, lat_deg_spin, lat_min_spin, lon_deg_spin, lon_min_spin, laser_distance_spin, desc_edit) = self.create_waypoint_dialog('编辑航点信息', waypoint)
        
        if dialog.exec() == QDialog.Accepted:
            # 获取时间戳
            timestamp = timestamp_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
            
            # 转换为十进制度数
            lat = lat_deg_spin.value() + lat_min_spin.value() / 60.0
            lon = lon_deg_spin.value() + lon_min_spin.value() / 60.0
            laser_distance = laser_distance_spin.value()
            description = desc_edit.text()
            
            # 更新航点
            waypoint.timestamp = timestamp
            waypoint.lat = lat
            waypoint.lon = lon
            waypoint.laser_distance = laser_distance
            waypoint.description = description
            
            self.update_table()
    
    def import_waypoints(self):
        """从JSON文件导入航点"""
        # 选择文件
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            '选择航迹数据文件', 
            'D:/geo_sites_locator', 
            'JSON文件 (*.json);;所有文件 (*)'
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查数据格式
            if '航点数据' not in data:
                QMessageBox.warning(self, '格式错误', '文件格式不正确，缺少"航点数据"字段')
                return
            
            waypoints_data = data['航点数据']
            if not isinstance(waypoints_data, list):
                QMessageBox.warning(self, '格式错误', '"航点数据"字段必须是数组')
                return
            
            # 清空现有航点
            self.waypoints.clear()
            
            # 导入航点
            for i, wp_data in enumerate(waypoints_data):
                try:
                    # 提取航点数据
                    name = wp_data.get('名称', f'Point {i+1}')
                    timestamp = wp_data.get('时间戳', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    lat = float(wp_data.get('纬度', 0))
                    lon = float(wp_data.get('经度', 0))
                    laser_distance = float(wp_data.get('激光测距仪(m)', -1))
                    description = wp_data.get('描述', '')
                    
                    # 创建航点对象
                    waypoint = GeoPoint(name, lat, lon, timestamp, description, laser_distance)
                    self.waypoints.append(waypoint)
                    
                except (ValueError, KeyError) as e:
                    QMessageBox.warning(self, '数据错误', f'第{i+1}个航点数据格式错误: {str(e)}')
                    continue
            
            # 更新表格和地图
            self.update_table()
            
            # 显示导入结果
            QMessageBox.information(self, '导入成功', f'成功导入 {len(self.waypoints)} 个航点')
            
            # 如果数据中包含实验站信息，询问是否设置
            if 'NV Mag Station' in data:
                station_data = data['NV Mag Station']
                reply = QMessageBox.question(
                    self, 
                    '设置实验站', 
                    f'是否要设置实验站为:\n名称: {station_data.get("名称", "未知")}\n纬度: {station_data.get("纬度", 0):.6f}°\n经度: {station_data.get("经度", 0):.6f}°',
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    # 通知主窗口设置实验站
                    if hasattr(self, 'on_experiment_station_changed') and self.on_experiment_station_changed:
                        self.on_experiment_station_changed(
                            station_data.get("纬度", 0),
                            station_data.get("经度", 0),
                            station_data.get("名称", "NV Mag Station")
                        )
            
        except FileNotFoundError:
            QMessageBox.critical(self, '文件错误', f'找不到文件: {filepath}')
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, 'JSON错误', f'JSON格式错误: {str(e)}')
        except Exception as e:
            QMessageBox.critical(self, '导入错误', f'导入过程中发生错误: {str(e)}')
    
    def on_cell_double_clicked(self, row, col):
        """单元格双击处理"""
        if row >= len(self.waypoints):
            return
            
        if col == 1:  # 时间戳列
            self.edit_timestamp(row)
        elif col == 2:  # 纬度列
            self.edit_latitude(row)
        elif col == 3:  # 经度列
            self.edit_longitude(row)
        elif col == 5:  # 激光测距仪列
            self.edit_laser_distance(row)
        elif col == 6:  # 描述列
            self.edit_description(row)
    
    def edit_timestamp(self, row):
        """编辑时间戳"""
        if row >= len(self.waypoints):
            return
        
        waypoint = self.waypoints[row]
        
        # 解析当前时间戳
        try:
            current_time = datetime.strptime(waypoint.timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            current_time = datetime.now()
        
        # 创建时间编辑对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QDateTimeEdit
        from PySide6.QtCore import QDateTime
        
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑时间戳')
        dialog.setModal(True)
        dialog.resize(300, 150)
        
        layout = QVBoxLayout()
        
        # 时间戳输入
        timestamp_edit = QDateTimeEdit()
        timestamp_edit.setDateTime(QDateTime(current_time))
        timestamp_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        timestamp_edit.setCalendarPopup(True)
        
        layout.addWidget(timestamp_edit)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            new_timestamp = timestamp_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
            waypoint.timestamp = new_timestamp
            self.update_table()
    
    def edit_latitude(self, row):
        """编辑纬度"""
        if row >= len(self.waypoints):
            return
        
        waypoint = self.waypoints[row]
        
        # 解析当前纬度
        lat_deg = int(waypoint.lat)
        lat_min = (waypoint.lat - lat_deg) * 60.0
        
        # 创建纬度编辑对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QLabel
        from PySide6.QtCore import QDateTime
        
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑纬度')
        dialog.setModal(True)
        dialog.resize(300, 150)
        
        layout = QVBoxLayout()
        
        # 纬度输入
        lat_layout = QHBoxLayout()
        lat_deg_spin = QSpinBox()
        lat_deg_spin.setRange(-90, 90)
        lat_deg_spin.setValue(lat_deg)
        
        lat_min_spin = QDoubleSpinBox()
        lat_min_spin.setRange(0, 59.999999)
        lat_min_spin.setDecimals(6)
        lat_min_spin.setValue(lat_min)
        
        lat_layout.addWidget(QLabel('纬度:'))
        lat_layout.addWidget(lat_deg_spin)
        lat_layout.addWidget(QLabel('度'))
        lat_layout.addWidget(lat_min_spin)
        lat_layout.addWidget(QLabel('分'))
        
        layout.addLayout(lat_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            new_lat = lat_deg_spin.value() + lat_min_spin.value() / 60.0
            waypoint.lat = new_lat
            self.update_table()
    
    def edit_longitude(self, row):
        """编辑经度"""
        if row >= len(self.waypoints):
            return
        
        waypoint = self.waypoints[row]
        
        # 解析当前经度
        lon_deg = int(waypoint.lon)
        lon_min = (waypoint.lon - lon_deg) * 60.0
        
        # 创建经度编辑对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QLabel
        from PySide6.QtCore import QDateTime
        
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑经度')
        dialog.setModal(True)
        dialog.resize(300, 150)
        
        layout = QVBoxLayout()
        
        # 经度输入
        lon_layout = QHBoxLayout()
        lon_deg_spin = QSpinBox()
        lon_deg_spin.setRange(-180, 180)
        lon_deg_spin.setValue(lon_deg)
        
        lon_min_spin = QDoubleSpinBox()
        lon_min_spin.setRange(0, 59.999999)
        lon_min_spin.setDecimals(6)
        lon_min_spin.setValue(lon_min)
        
        lon_layout.addWidget(QLabel('经度:'))
        lon_layout.addWidget(lon_deg_spin)
        lon_layout.addWidget(QLabel('度'))
        lon_layout.addWidget(lon_min_spin)
        lon_layout.addWidget(QLabel('分'))
        
        layout.addLayout(lon_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            new_lon = lon_deg_spin.value() + lon_min_spin.value() / 60.0
            waypoint.lon = new_lon
            self.update_table()
    
    def edit_laser_distance(self, row):
        """编辑激光测距仪距离"""
        if row >= len(self.waypoints):
            return
        
        waypoint = self.waypoints[row]
        
        # 创建激光测距仪编辑对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QDoubleSpinBox, QLabel
        
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑激光测距仪距离')
        dialog.setModal(True)
        dialog.resize(300, 150)
        
        layout = QVBoxLayout()
        
        # 激光测距仪输入
        laser_layout = QHBoxLayout()
        laser_distance_spin = QDoubleSpinBox()
        laser_distance_spin.setRange(-1, 10000)
        laser_distance_spin.setDecimals(2)
        laser_distance_spin.setValue(waypoint.laser_distance)
        laser_distance_spin.setSuffix(' m')
        
        laser_layout.addWidget(QLabel('激光测距仪距离:'))
        laser_layout.addWidget(laser_distance_spin)
        
        layout.addLayout(laser_layout)
        
        # 说明文字
        info_label = QLabel('注意: -1表示未启动激光测距仪')
        info_label.setStyleSheet("color: #666666; font-size: 10px;")
        layout.addWidget(info_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            new_laser_distance = laser_distance_spin.value()
            waypoint.laser_distance = new_laser_distance
            self.update_table()
    
    def edit_description(self, row):
        """编辑描述"""
        if row >= len(self.waypoints):
            return
        
        waypoint = self.waypoints[row]
        
        # 创建描述编辑对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QTextEdit, QLabel
        
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑描述')
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout()
        
        # 描述输入
        layout.addWidget(QLabel('描述:'))
        desc_edit = QTextEdit()
        desc_edit.setText(waypoint.description)
        desc_edit.setMaximumHeight(150)
        layout.addWidget(desc_edit)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            new_description = desc_edit.toPlainText()
            waypoint.description = new_description
            self.update_table()
    
    def on_item_changed(self, item):
        """表格项目改变时的处理（已禁用直接编辑，保留方法以防需要）"""
        # 由于禁用了直接编辑，此方法不再需要处理编辑事件
        pass
    
    def clear_waypoints(self):
        """清空航点"""
        if not self.waypoints:
            return
        
        reply = QMessageBox.question(self, '确认清空', 
                                   '确定要清空所有航点吗？',
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.waypoints.clear()
            self.update_table()
    
    def update_table(self):
        """更新表格显示"""
        self.table.setRowCount(len(self.waypoints))
        
        for i, waypoint in enumerate(self.waypoints):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(waypoint.timestamp))
            self.table.setItem(i, 2, QTableWidgetItem(f'{waypoint.lat:.6f}'))
            self.table.setItem(i, 3, QTableWidgetItem(f'{waypoint.lon:.6f}'))
            
            # 计算到实验站的距离
            if hasattr(self, 'experiment_station') and self.experiment_station:
                distance = waypoint.distance_to(self.experiment_station)
                self.table.setItem(i, 4, QTableWidgetItem(f'{distance * 1e3:.2f}'))
            else:
                self.table.setItem(i, 4, QTableWidgetItem('N/A'))
            
            # 激光测距仪数据
            if waypoint.laser_distance == -1:
                self.table.setItem(i, 5, QTableWidgetItem('未启动'))
            else:
                self.table.setItem(i, 5, QTableWidgetItem(f'{waypoint.laser_distance:.2f}'))
            
            self.table.setItem(i, 6, QTableWidgetItem(waypoint.description))
        
        # 如果航点数>=2，进行直线拟合和航速估计
        if len(self.waypoints) >= 2:
            self.fit_line_and_calculate_speed()
        
        if self.on_waypoints_changed:
            self.on_waypoints_changed(self.waypoints)
    
    def fit_line_and_calculate_speed(self):
        """拟合直线并计算航速"""
        if len(self.waypoints) < 2:
            return
        
        # 获取航点坐标
        lats = [p.lat for p in self.waypoints]
        lons = [p.lon for p in self.waypoints]
        
        # 检查是否所有航点都在同一经度线上（垂直直线）
        if len(set(lons)) == 1:
            # 垂直直线情况：所有航点经度相同
            vertical_lon = lons[0]
            heading_angle = 90.0  # 垂直直线，航向角为90度
            
            # 计算直线到实验站的距离（水平距离）
            distance_to_station = 0
            if self.experiment_station:
                distance_to_station = abs(self.experiment_station.lon - vertical_lon) * 111.0 * 1000 * math.cos(math.radians(self.experiment_station.lat))
            
            print(f"垂直直线 - 航向角: {heading_angle:.1f}° 距离: {distance_to_station:.1f}m")
            return
        
        # 检查是否所有航点都在同一纬度线上（水平直线）
        if len(set(lats)) == 1:
            # 水平直线情况：所有航点纬度相同
            horizontal_lat = lats[0]
            heading_angle = 0.0  # 水平直线，航向角为0度
            
            # 计算直线到实验站的距离（垂直距离）
            distance_to_station = 0
            if self.experiment_station:
                distance_to_station = abs(self.experiment_station.lat - horizontal_lat) * 111.0 * 1000
            
            print(f"水平直线 - 航向角: {heading_angle:.1f}° 距离: {distance_to_station:.1f}m")
            return
        
        # 使用numpy进行直线拟合
        try:
            coeffs = np.polyfit(lons, lats, 1)
            slope = coeffs[0]
            intercept = coeffs[1]
            
            # 检查斜率是否为无穷大或NaN
            if not np.isfinite(slope) or not np.isfinite(intercept):
                print("直线拟合失败：斜率或截距为无穷大或NaN")
                return
            
            # 计算航向角（以正北为0度，顺时针为正）
            heading_angle = math.degrees(math.atan(slope))
            if heading_angle < 0:
                heading_angle += 360
            
            # 计算直线到实验站的距离
            distance_to_station = 0
            if self.experiment_station:
                station_lat = self.experiment_station.lat
                station_lon = self.experiment_station.lon
                
                # 点到直线距离公式
                # 直线方程: lat = slope * lon + intercept
                # 标准形式: slope * lon - lat + intercept = 0
                # 点(x0,y0)到直线ax+by+c=0的距离: |ax0+by0+c|/sqrt(a^2+b^2)
                a = slope
                b = -1
                c = intercept
                
                denominator = math.sqrt(a**2 + b**2)
                if denominator > 1e-10:  # 避免除零错误
                    distance_to_line = abs(a * station_lon + b * station_lat + c) / denominator
                    # 转换为米（近似）
                    distance_to_station = distance_to_line * 111.0 * 1000  # 1度约等于111km
                else:
                    # 实验站正好在直线上
                    distance_to_station = 0.0
            
            print(f"拟合直线 - 航向角: {heading_angle:.1f}° 距离: {distance_to_station:.1f}m")
            
        except (np.linalg.LinAlgError, ValueError, RuntimeWarning) as e:
            # 处理拟合失败的情况
            print(f"直线拟合失败: {e}")
            return
        
        # 计算航速
        if len(self.waypoints) >= 2:
            # 计算总距离
            total_distance = 0
            for i in range(len(self.waypoints) - 1):
                total_distance += self.waypoints[i].distance_to(self.waypoints[i + 1])
            
            # 计算总时间
            try:
                time1 = datetime.strptime(self.waypoints[0].timestamp, "%Y-%m-%d %H:%M:%S")
                time2 = datetime.strptime(self.waypoints[-1].timestamp, "%Y-%m-%d %H:%M:%S")
                time_diff = (time2 - time1).total_seconds() / 3600  # 转换为小时
                
                if time_diff > 0:
                    speed = total_distance / time_diff  # km/h
                    print(f"总距离: {total_distance * 1000:.2f}m")
                    print(f"总时间: {time_diff:.2f}小时")
                    print(f"平均航速: {speed:.2f}km/h")
                else:
                    print("时间差为0，无法计算航速")
            except ValueError as e:
                print(f"时间格式错误，无法计算航速: {e}")
    
    def set_experiment_station(self, station: GeoPoint):
        """设置实验站"""
        self.experiment_station = station
        self.update_table()
    
    def get_waypoints(self) -> List[GeoPoint]:
        """获取航点列表"""
        return self.waypoints.copy()

class ControlPanelWidget(QWidget):
    """控制面板组件"""
    def __init__(self):
        super().__init__()
        self.on_experiment_station_changed = None
        self.on_collecting_status_changed = None
        self.on_save_data = None
        self.on_distance_range_changed = None
        self.on_init_default_route = None
        
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout()
        
        # 实验站设置组
        station_group = QGroupBox('实验站设置')
        station_layout = QFormLayout()
        
        self.station_name_edit = QLineEdit('NV Mag Station')
        self.station_lat_deg = QSpinBox()
        self.station_lat_deg.setRange(-90, 90)
        self.station_lat_deg.setValue(29)  # 默认纬度29度
        
        self.station_lat_min = QDoubleSpinBox()
        self.station_lat_min.setRange(0, 59.999999)
        self.station_lat_min.setDecimals(6)
        self.station_lat_min.setValue(33.58668)
        
        self.station_lon_deg = QSpinBox()
        self.station_lon_deg.setRange(-180, 180)
        self.station_lon_deg.setValue(119)  # 默认经度119度
        
        self.station_lon_min = QDoubleSpinBox()
        self.station_lon_min.setRange(0, 59.999999)
        self.station_lon_min.setDecimals(6)
        self.station_lon_min.setValue(10.62336)
        
        station_layout.addRow('站点名称:', self.station_name_edit)
        station_layout.addRow('纬度(度):', self.station_lat_deg)
        station_layout.addRow('纬度(分):', self.station_lat_min)
        station_layout.addRow('经度(度):', self.station_lon_deg)
        station_layout.addRow('经度(分):', self.station_lon_min)
        
        self.set_station_btn = QPushButton('设置实验站')
        self.set_station_btn.clicked.connect(self.set_experiment_station)
        station_layout.addRow(self.set_station_btn)
        
        station_group.setLayout(station_layout)
        
        # 距离区域范围设置组
        range_group = QGroupBox('距离区域范围设置')
        range_layout = QFormLayout()
        
        self.distance_range_spin = QSpinBox()
        self.distance_range_spin.setRange(100, 10000)  # 100m到10km
        self.distance_range_spin.setValue(800)  # 默认800m
        self.distance_range_spin.setSuffix(' m')
        self.distance_range_spin.valueChanged.connect(self.on_distance_range_changed_internal)
        
        range_layout.addRow('显示范围:', self.distance_range_spin)
        
        range_group.setLayout(range_layout)
        
        # 航迹采集控制组
        control_group = QGroupBox('航迹采集控制')
        control_layout = QVBoxLayout()
        
        self.collecting_btn = QPushButton('开启航迹采集')
        self.collecting_btn.clicked.connect(self.toggle_collecting)
        self.collecting_btn.setStyleSheet("""
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
        
        self.init_default_route_btn = QPushButton('初始化默认航线')
        self.init_default_route_btn.clicked.connect(self.init_default_route)
        self.init_default_route_btn.setEnabled(False)  # 初始禁用
        self.init_default_route_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        
        control_layout.addWidget(self.collecting_btn)
        control_layout.addWidget(self.init_default_route_btn)
        control_group.setLayout(control_layout)
        
        # 状态显示组
        status_group = QGroupBox('状态信息')
        status_layout = QVBoxLayout()
        
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
        
        status_layout.addWidget(self.status_label)
        status_group.setLayout(status_layout)
        
        layout.addWidget(station_group)
        layout.addWidget(range_group)
        layout.addWidget(control_group)
        layout.addWidget(status_group)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def on_distance_range_changed_internal(self):
        """距离范围改变时的内部处理"""
        if self.on_distance_range_changed:
            self.on_distance_range_changed(self.distance_range_spin.value())
    
    def set_experiment_station(self):
        """设置实验站"""
        name = self.station_name_edit.text()
        lat_deg = self.station_lat_deg.value()
        lat_min = self.station_lat_min.value()
        lon_deg = self.station_lon_deg.value()
        lon_min = self.station_lon_min.value()
        
        lat = lat_deg + lat_min / 60.0
        lon = lon_deg + lon_min / 60.0
        
        if self.on_experiment_station_changed:
            self.on_experiment_station_changed(lat, lon, name)
        
        self.status_label.setText(f'NV Mag Station: {name}\n({lat:.6f}°, {lon:.6f}°)')
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
    
    def toggle_collecting(self):
        """切换采集状态"""
        if self.collecting_btn.text() == '开启航迹采集':
            # 开启采集
            self.collecting_btn.setText('停止并保存航迹')
            self.collecting_btn.setStyleSheet("""
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
            
            # 启用初始化默认航线按钮
            self.init_default_route_btn.setEnabled(True)
            
            if self.on_collecting_status_changed:
                self.on_collecting_status_changed(True)
        else:
            # 停止采集并保存数据
            self.collecting_btn.setText('开启航迹采集')
            self.collecting_btn.setStyleSheet("""
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
            
            # 禁用初始化默认航线按钮
            self.init_default_route_btn.setEnabled(False)
            
            if self.on_collecting_status_changed:
                self.on_collecting_status_changed(False)
            
            # 自动保存数据
            if self.on_save_data:
                self.on_save_data()
    
    def init_default_route(self):
        """初始化默认航线 - 在实验站以北100m创建9个航点"""
        # 检查是否已设置实验站
        if not hasattr(self, 'on_experiment_station_changed') or not self.on_experiment_station_changed:
            QMessageBox.warning(self, '警告', '请先设置实验站位置')
            return
        
        # 检查是否正在采集
        if self.collecting_btn.text() != '停止并保存航迹':
            QMessageBox.warning(self, '警告', '请先开启航迹采集')
            return
        
        # 获取当前实验站坐标
        lat_deg = self.station_lat_deg.value()
        lat_min = self.station_lat_min.value()
        lon_deg = self.station_lon_deg.value()
        lon_min = self.station_lon_min.value()
        
        station_lat = lat_deg + lat_min / 60.0
        station_lon = lon_deg + lon_min / 60.0
        
        # 计算北向100m的位置
        # 1度纬度约等于111km，所以100m约等于100/111000度
        north_offset = 100.0 / (111.0 * 1000.0)  # 转换为度
        north_lat = station_lat + north_offset
        
        # 创建9个航点，间隔10m
        waypoint_interval = 10.0 / (111.0 * 1000.0)  # 10m转换为度
        
        # 通知主窗口创建默认航点
        if hasattr(self, 'on_init_default_route') and self.on_init_default_route:
            self.on_init_default_route(station_lat, station_lon, north_lat, waypoint_interval)
        
        QMessageBox.information(self, '初始化完成', '已创建9个默认航点，位于实验站以北100m处，间隔10m')
    


class FlightTrackApp(QMainWindow):
    """主应用程序"""
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('航迹采集系统')
        self.setGeometry(100, 100, 1600, 1000)
        
                # 设置应用程序样式
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
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
            }
        """)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧控制面板
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        
        self.control_panel = ControlPanelWidget()
        left_layout.addWidget(self.control_panel)
        
        # 航点表格
        table_group = QGroupBox('航点记录')
        table_layout = QVBoxLayout()
        self.waypoint_table = WaypointTableWidget()
        table_layout.addWidget(self.waypoint_table)
        table_group.setLayout(table_layout)
        left_layout.addWidget(table_group)
        
        left_panel.setLayout(left_layout)
        
        # 右侧地图显示
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        
        map_group = QGroupBox('实验区地图')
        map_layout = QVBoxLayout()
        self.map_widget = SatelliteMapWidget()
        map_layout.addWidget(self.map_widget)
        map_group.setLayout(map_layout)
        right_layout.addWidget(map_group)
        
        right_panel.setLayout(right_layout)
        
        # 添加到分割器
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([600, 1000])  # 设置初始分割比例
        
        # 主布局
        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        central_widget.setLayout(main_layout)
        
        # 连接信号
        self.control_panel.on_experiment_station_changed = self.on_experiment_station_changed
        self.control_panel.on_collecting_status_changed = self.on_collecting_status_changed
        self.control_panel.on_save_data = self.save_data
        self.control_panel.on_distance_range_changed = self.on_distance_range_changed
        self.control_panel.on_init_default_route = self.init_default_route
        self.waypoint_table.on_waypoints_changed = self.on_waypoints_changed
        self.waypoint_table.on_experiment_station_changed = self.on_experiment_station_changed
    
    def on_experiment_station_changed(self, lat: float, lon: float, name: str):
        """实验站位置改变"""
        station = GeoPoint(name, lat, lon)
        self.map_widget.set_experiment_station(lat, lon, name)
        self.waypoint_table.set_experiment_station(station)
    
    def on_collecting_status_changed(self, is_collecting: bool):
        """采集状态改变"""
        self.waypoint_table.set_collecting_status(is_collecting)
        self.map_widget.set_collecting_status(is_collecting)
    
    def on_distance_range_changed(self, range_meters: int):
        """距离范围改变"""
        self.map_widget.set_distance_range(range_meters)
    
    def on_waypoints_changed(self, waypoints: List[GeoPoint]):
        """航点列表改变"""
        # 清空地图上的航点
        self.map_widget.clear_waypoints()
        
        # 重新添加所有航点
        for waypoint in waypoints:
            self.map_widget.add_waypoint(waypoint)
    
    def init_default_route(self, station_lat: float, station_lon: float, north_lat: float, waypoint_interval: float):
        """初始化默认航线"""
        # 清空现有航点
        self.waypoint_table.waypoints.clear()
        
        # 创建9个航点，从北向100m开始，向南间隔10m
        current_time = datetime.now()
        
        for i in range(9):
            # 计算航点位置（从北向南）
            waypoint_lat = north_lat - (i * waypoint_interval)
            waypoint_lon = station_lon  # 经度保持不变
            
            # 创建时间戳（每个航点间隔1分钟）
            waypoint_time = current_time.replace(second=0, microsecond=0)  # 去掉秒和微秒
            waypoint_time = waypoint_time.replace(minute=waypoint_time.minute)  # 每个航点间隔1分钟
            
            # 创建航点
            waypoint = GeoPoint(
                name=f"Default Point {i+1}",
                lat=waypoint_lat,
                lon=waypoint_lon,
                timestamp=waypoint_time.strftime("%Y-%m-%d %H:%M:%S"),
                description=f"默认航点 {i+1} - 北向航线",
                laser_distance=-1.0
            )
            
            self.waypoint_table.waypoints.append(waypoint)
        
        # 更新表格和地图
        self.waypoint_table.update_table()
    
    def save_data(self):
        """保存数据"""
        waypoints = self.waypoint_table.get_waypoints()
        if not waypoints:
            QMessageBox.warning(self, '警告', '没有航点数据可保存')
            # 更新状态标签
            self.control_panel.status_label.setText('就绪')
            self.control_panel.status_label.setStyleSheet("""
                QLabel {
                    background-color: #e8f5e8;
                    border: 1px solid #4CAF50;
                    padding: 10px;
                    border-radius: 5px;
                    color: #2e7d32;
                    font-weight: bold;
                }
            """)
            return
        
        # 自动创建保存目录
        save_dir = "D:/geo_sites_locator"
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, '创建目录失败', f'无法创建目录 {save_dir}:\n{str(e)}')
            # 更新状态标签
            self.control_panel.status_label.setText('保存失败')
            self.control_panel.status_label.setStyleSheet("""
                QLabel {
                    background-color: #ffebee;
                    border: 1px solid #f44336;
                    padding: 10px;
                    border-radius: 5px;
                    color: #c62828;
                    font-weight: bold;
                }
            """)
            return
        
        # 生成文件名（包含航迹起始和结束时间戳）
        if len(waypoints) >= 2:
            start_time = waypoints[0].timestamp.replace(" ", "_").replace(":", "")
            end_time = waypoints[-1].timestamp.replace(" ", "_").replace(":", "")
            filename = f"航迹数据_{start_time}_to_{end_time}.json"
        else:
            # 如果只有一个航点，使用该航点的时间戳
            single_time = waypoints[0].timestamp.replace(" ", "_").replace(":", "")
            filename = f"航迹数据_{single_time}.json"
        
        filepath = os.path.join(save_dir, filename)
        
        # 准备数据
        data = {
            "NV Mag Station": {
                "名称": self.control_panel.station_name_edit.text(),
                "纬度": self.control_panel.station_lat_deg.value() + self.control_panel.station_lat_min.value() / 60.0,
                "经度": self.control_panel.station_lon_deg.value() + self.control_panel.station_lon_min.value() / 60.0
            },
            "航点数据": []
        }
        
        for waypoint in waypoints:
            data["航点数据"].append({
                "名称": waypoint.name,
                "时间戳": waypoint.timestamp,
                "纬度": waypoint.lat,
                "经度": waypoint.lon,
                "激光测距仪(m)": waypoint.laser_distance,
                "描述": waypoint.description
            })
        
        # 保存到文件
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(self, '保存成功', f'数据已保存到:\n{filepath}')
            
            # 清空航点
            self.waypoint_table.clear_waypoints()
            
            # 更新状态标签
            self.control_panel.status_label.setText('保存完成，就绪')
            self.control_panel.status_label.setStyleSheet("""
                QLabel {
                    background-color: #e8f5e8;
                    border: 1px solid #4CAF50;
                    padding: 10px;
                    border-radius: 5px;
                    color: #2e7d32;
                    font-weight: bold;
                }
            """)
            
        except Exception as e:
            QMessageBox.critical(self, '保存失败', f'保存数据时出错:\n{str(e)}')
            # 更新状态标签
            self.control_panel.status_label.setText('保存失败')
            self.control_panel.status_label.setStyleSheet("""
                QLabel {
                    background-color: #ffebee;
                    border: 1px solid #f44336;
                    padding: 10px;
                    border-radius: 5px;
                    color: #c62828;
                    font-weight: bold;
                }
            """)

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle('Fusion')
    
    # 创建主窗口
    window = FlightTrackApp()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
