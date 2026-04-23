# encoding=utf-8
from General import *
import os
import sys
import time
import random
import logging
import traceback
import psutil
from datetime import datetime
import numpy as np
import PySide6.QtGui as QtGui
from PySide6.QtGui import QIntValidator
from collections import deque
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QTabWidget, QFormLayout, QSplitter,
    QGroupBox, QGridLayout, QCheckBox, QComboBox, QSizePolicy, QMessageBox, QListWidget, QListWidgetItem,
    QScrollArea, QTableWidget, QTableWidgetItem, QAbstractItemView, QRadioButton, QHeaderView, QButtonGroup,
    QFileDialog, QStatusBar, QFrame,
)
from PySide6.QtCore import QTimer, Qt, QDateTime, QObject, Signal, QThread
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter

# 状态管理器和各类基础功能面板
from manager import *
from dc_panel import OscilloscopeDCPanel
from daq_panel import OscilloscopePanel
# from iir_panel import OscilloscopeIIRPanel
from iir_dc_panel import OscilloscopeIIRDCPanel
from cw_panel import OscilloscopeCWPanel
from dc_cw_panel import OscilloscopeDCCWPanel
from ultra_cw_panel import OscilloscopeAllOpticalCWPanel
from pid_panel import OscilloscopePIDPanel
from laser_phase_optimization_panel import LaserPhaseOptimizationPanel
from workflow_extension.workflow_tab import WorkflowTab

# 数据处理功能
from utils.signal_process import *

from interface.Thermometer_4ch import Thermometer_4CH_Backend
from interface.usm20 import Ultramotor_Backend
# from interface.Lockin.Test_LIA_Mini_DoubleMW import LIA_API
from interface.Lockin.LIA_Mini_DoubleMW import LIA_API
# from interface.Lockin.LIA_Mini_DoubleMW_RS485 import LIA_API
# from interface.Lockin.LIA_Mini_DoubleMW_Ethernet_20250717 import LIA_API

class LogSignal(QObject):
    new_log = Signal(str)


class QTextEditLogger(logging.Handler):
    def __init__(self, signal_obj: LogSignal):
        super().__init__()
        self.signal_obj = signal_obj

    def emit(self, record):
        msg = self.format(record)
        self.signal_obj.new_log.emit(msg)


class ExperimentApp(QWidget):
    # 状态栏信号
    config_sent_signal = Signal(bool)  # 配置下发状态
    ch1_cw_updated_signal = Signal(bool)  # CH1 CW谱更新状态
    ch2_cw_updated_signal = Signal(bool)  # CH2 CW谱更新状态
    
    def __init__(self, device_name="样机1", exp_config_path="config/exp_config_dev1.ini", 
                 sys_config_path="config/system_config_dev1.ini", lockin_port="192.168.3.100:5005", 
                 ultramotor_port="COM12", log_path="log/experiment_log.txt"):
        super().__init__()
        
        # 保存配置参数
        self.device_name = device_name
        self.exp_config_path = exp_config_path
        self.sys_config_path = sys_config_path
        self.lockin_port = lockin_port
        self.ultramotor_port = ultramotor_port
        self.log_path = log_path
        
        # 设置窗口标题
        window_title = f'金刚石磁探测器 - 自动化实验控制程序 - {device_name}'
        self.setWindowTitle(window_title)
        
        # 初始化日志系统
        self._setup_logging()
        
        self.dev = Virtual_Device()
        self.state_manager = DevStateManager()
        self.state_manager.state_changed.connect(self.on_state_changed)
        self.sys_config = load_config(self.sys_config_path)
        self.config = load_config(self.exp_config_path)
        self.libusb_path = self.sys_config.get('Path', 'libusb_path')

        # 实验参数和设备类导入
        self.param_config = self.load_config_summary()
        self.param_inputs = {}  # 输入框列表
        self.param_states = {}  # 状态列表
        self.param_buttons = {}  # 按钮列表
        self.param_category_index = {}  # 参数类型列表，同类参数打包成单次下发
        self.device_param_buttons = {}
        # 树状参数类型索引数据结构
        for name in self.param_config.keys():
            category = self.param_config[name]['category'].strip()
            if category not in self.param_category_index.keys():
                self.param_category_index[category] = [name]
            else:
                self.param_category_index[category].append(name)

        # 连接辅助设备 - 温度计
        self.thermometer = Thermometer_4CH_Backend(self.libusb_path)
        self.thermometer.new_data.connect(self.update_temp_plot)

        # 连接辅助设备 - 超声电机
        self.ultramotor = Ultramotor_Backend(port=self.ultramotor_port)
        self.ultramotor.status_updated.connect(self.update_motor_plot)

        # 创建文件目录
        self.save_dir = self.sys_config.get('Path', 'local_data_path') + '/' + time.strftime('%Y%m%d',
                                                                                             time.localtime(
                                                                                                 time.time())) + '/'
        if not os.path.exists(self.sys_config.get('Path', 'local_data_path')):
            os.mkdir(self.sys_config.get('Path', 'local_data_path'))
        create_dir(self.save_dir)

        self.save_dir_laser_phase = self.save_dir + 'Laser_Phase_Optimization'
        create_dir(self.save_dir_laser_phase)

        self.save_dir_temp = self.save_dir + 'Temperature/'
        create_dir(self.save_dir_temp)
        self.temp_log_file = self.save_dir_temp + gettimestr() + '_temperature.csv'

        self.save_dir_motor = self.save_dir + 'UltraMotor/'
        create_dir(self.save_dir_motor)
        self.motor_log_file = self.save_dir_motor + gettimestr() + '_motor.csv'

        self.save_dir_osc_dc = self.save_dir + 'Oscilloscope_DC/'
        create_dir(self.save_dir_osc_dc)
        self.save_dir_osc_ac = self.save_dir + 'Oscilloscope_AC/'
        create_dir(self.save_dir_osc_ac)

        self.save_dir_iir = self.save_dir + 'LIA_IIR/'
        create_dir(self.save_dir_iir)

        self.save_dir_dc_cw = self.save_dir + 'DC_CW/'
        create_dir(self.save_dir_dc_cw)

        self.save_dir_cw = self.save_dir + 'CW/'
        create_dir(self.save_dir_cw)

        self.save_dir_pid = self.save_dir + 'PID/'
        create_dir(self.save_dir_pid)


        # 初始化待维护数据
        self.dev_connected = False
        self.cpu_label = None
        self.mem_label = None
        self.general_temp_data = []
        self.general_ch1_data = []
        self.general_ch2_data = []
        self.general_time_data = []
        self.exp_data_x = []
        self.exp_data_y = []

        self.device_management_panel = self.create_device_management_panel()
        self.experiment_data_panel = self.create_experiment_data_panel()
        # self.oscilloscope_panel = self.create_oscilloscope_panel()
        self.oscilloscope_panel = OscilloscopePanel(self)
        self.oscilloscope_dc_panel = OscilloscopeDCPanel(self)
        # self.oscilloscope_iir_panel = OscilloscopeIIRPanel(self)
        # self.oscilloscope_iir_discrete_panel = OscilloscopeIIRDiscretePanel(self)
        self.oscilloscope_cw_panel = OscilloscopeCWPanel(self)
        self.ultra_cw_panel = OscilloscopeAllOpticalCWPanel(self)
        self.oscilloscope_iir_dc_panel = OscilloscopeIIRDCPanel(self)
        self.oscilloscope_dc_cw_panel = OscilloscopeDCCWPanel(self)
        self.pid_panel = OscilloscopePIDPanel(self)
        self.laser_phase_optimization_panel = LaserPhaseOptimizationPanel(self)
        # self.power_management_panel = PowerPanel(self)

        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.device_management_panel, "设备管理")
        # self.tabs.addTab(self.power_management_panel, "电源管理")
        # self.tabs.addTab(self.experiment_data_panel, "实验数据显示")
        self.tabs.addTab(self.oscilloscope_panel, "示波器模式-AC")
        self.tabs.addTab(self.oscilloscope_dc_panel, "示波器模式-DC")
        # self.tabs.addTab(self.oscilloscope_iir_panel, "锁相放大器模式-IIR")
        self.tabs.addTab(self.oscilloscope_iir_dc_panel, "锁相放大器模式-直流完整形式-IIR")
        # self.tabs.addTab(self.oscilloscope_iir_discrete_panel, "锁相放大器模式-非连续IIR")
        self.tabs.addTab(self.oscilloscope_cw_panel, "CW谱数据采集")
        self.tabs.addTab(self.oscilloscope_dc_cw_panel, "直流CW谱数据采集")
        self.tabs.addTab(self.ultra_cw_panel, "全光谱数据采集")
        self.tabs.addTab(self.pid_panel, "PID控制模式")
        self.tabs.addTab(self.laser_phase_optimization_panel, "激光解调相消相位优化")
        self.workflow_tab = WorkflowTab(app_context=self, parent=self)
        self.tabs.addTab(self.workflow_tab, "自定义实验-节点工作流")
        main_layout.addWidget(self.tabs)

        # 创建状态栏
        self.create_status_bar()
        main_layout.addWidget(self.status_bar)

        self.log_group = QGroupBox("日志输出")
        self.log_group.setFixedHeight(150)
        log_layout = QHBoxLayout()

        # 信息日志
        self.log_output_info = QTextEdit()
        self.log_output_info.setMaximumHeight(150)
        self.log_output_info.setReadOnly(True)

        # 调试日志
        self.log_output_debug = QTextEdit()
        self.log_output_debug.setMaximumHeight(150)
        self.log_output_debug.setReadOnly(True)

        log_layout.addWidget(self.log_output_info)
        log_layout.addWidget(self.log_output_debug)

        # 信号代理
        self.log_signal = LogSignal()
        self.log_signal.new_log.connect(self.log_output_info.append)
        self.log_signal_debug = LogSignal()
        self.log_signal_debug.new_log.connect(self.log_output_debug.append)

        # 创建 logger handler
        logger_info = QTextEditLogger(self.log_signal)
        logger_info.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

        info_logger = logging.getLogger("Experiment")
        info_logger.setLevel(logging.INFO)
        # 确保Experiment logger也会输出到文件
        info_logger.propagate = True

        info_logger.addHandler(logger_info)
        
        # 创建调试日志handler
        logger_debug = QTextEditLogger(self.log_signal_debug)
        logger_debug.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

        # 获取根logger并添加调试UI handler
        root_logger = logging.getLogger()
        root_logger.addHandler(logger_debug)
        root_logger.setLevel(logging.DEBUG)

        # 测试输出
        logging.info(f"日志系统已初始化 - 设备: {device_name}")
        logging.info(f"※初次上电时请注意，在进行其他操作前需要先点击[下发所有配置]按钮进行初始化。")

        # QMessageBox.information(self, "注意事项", f"初次上电时请注意，在进行其他操作前需要先点击[下发所有配置]按钮进行初始化。\n不然你就得重启设备了。-_-")

        self.log_group.setLayout(log_layout)
        main_layout.addWidget(self.log_group)

        self.resize(1300, 650)
        self.setLayout(main_layout)

        # 温度计状态更新
        self.thermometer_timer = QTimer()
        self.thermometer_timer.timeout.connect(self.thermometer.read)
        # 状态更新
        self.motor_update_status_button = QPushButton("更新电机状态")
        self.motor_timer = QTimer()
        self.motor_timer.timeout.connect(self.ultramotor.update_status)

        # 系统状态更新
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_system_info)
        self.update_timer.start(1000)

        # 连接状态栏信号
        self.config_sent_signal.connect(self.update_config_status)
        self.ch1_cw_updated_signal.connect(self.update_ch1_cw_status)
        self.ch2_cw_updated_signal.connect(self.update_ch2_cw_status)

        self.state_manager.set_state(DevState.OFFLINE)

    def _setup_logging(self):
        """设置日志系统"""
        # 确保log目录存在
        log_dir = os.path.dirname(self.log_path)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 添加一个全局 StreamHandler，将所有日志打印到终端
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.DEBUG)  # 打印所有日志
        stream_handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s'))

        # 添加文件日志处理器，将所有日志保存到文件
        file_handler = logging.FileHandler(self.log_path, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # 保存所有日志级别
        file_handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(name)s - %(message)s'))

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(stream_handler)
        root_logger.addHandler(file_handler)

    def update_motor_plot(self, status_dict):
        try:
            self.motor_buffer_len = int(self.motor_angle_buffer_input.text())
        except:
            pass
        ts = time.time()
        angle = status_dict['angle']
        self.motor_time_buffer.append(ts)
        self.motor_angle_buffer.append(angle)
        self.motor_status_label.setText(f"电机状态：{status_dict['status1']}\n"
                                        f"驱动板状态：{status_dict['status2']}\n"
                                        f"当前角度：{status_dict['angle']}\n"
                                        f"当前转速：{status_dict['speed']}")
        # for i, v in enumerate(temps):
        #     self.temperature_buffer[i].append(v)
        #     self.temp_curves[i].setData(list(self.temperature_time_buffer[-self.thermometer_buffer_len:]), list(self.temperature_buffer[i][-self.thermometer_buffer_len:]))
        self.motor_angle_curve.setData(self.motor_time_buffer[-self.motor_buffer_len:],
                                       self.motor_angle_buffer[-self.motor_buffer_len:])
        with open(self.motor_log_file, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([ts, angle])

    def update_temp_plot(self, temps, ts):
        try:
            self.thermometer_buffer_len = int(self.thermometer_buffer_input.text())
        except:
            pass
        self.temperature_time_buffer.append(ts)
        for i, v in enumerate(temps):
            self.temperature_buffer[i].append(v)
            self.temp_curves[i].setData(list(self.temperature_time_buffer[-self.thermometer_buffer_len:]),
                                        list(self.temperature_buffer[i][-self.thermometer_buffer_len:]))

        with open(self.temp_log_file, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([ts] + temps)

    def on_state_changed(self, state):
        self.device_status_label.setText(f"系统状态：{state.name}")
        if state == DevState.OFFLINE:
            # 设备未连接
            for name, field in self.param_inputs.items():
                self.param_buttons[name].setEnabled(False)
            for name in self.param_category_index.keys():
                self.device_param_buttons[name].setEnabled(False)
            self.send_btn.setEnabled(False)
            self.flush_input_output_btn.setEnabled(False)
            self.save_exp_config_btn.setEnabled(False)
            self.test_connection_btn.setEnabled(False)
        elif state == DevState.IDLE:
            for name, field in self.param_inputs.items():
                if self.param_config[name]["editable"]:
                    self.param_buttons[name].setEnabled(True)
            for name in self.param_category_index.keys():
                self.device_param_buttons[name].setEnabled(True)
            self.send_btn.setEnabled(True)
            self.flush_input_output_btn.setEnabled(True)
            self.save_exp_config_btn.setEnabled(True)
            self.test_connection_btn.setEnabled(True)

        else:
            for name in self.param_category_index.keys():
                self.device_param_buttons[name].setEnabled(False)
            # 设备被占用
            for name, field in self.param_inputs.items():
                self.param_buttons[name].setEnabled(False)
            self.send_btn.setEnabled(False)
            self.flush_input_output_btn.setEnabled(False)
            self.save_exp_config_btn.setEnabled(False)
            self.test_connection_btn.setEnabled(False)

    def load_config_summary(self):
        summary = {}
        for section in self.config.sections():
            desc = self.config.get(section, "desc", fallback="")
            type = self.config.get(section, "type", fallback="")
            unit = self.config.get(section, "unit", fallback="")
            label = self.config.get(section, "label", fallback="")
            value = self.config.get(section, "value", fallback="")
            minv = self.config.get(section, "min", fallback="")
            maxv = self.config.get(section, "max", fallback="")
            editable = self.config.get(section, "editable", fallback="")
            category = self.config.get(section, "category", fallback="")
            summary[section] = {}

            v = eval(f"{type}({value})")
            minv = eval(f"{type}({minv})") if minv else ""
            maxv = eval(f"{type}({maxv})") if maxv else ""
            editable = bool(eval(editable))

            summary[section]["desc"] = desc
            summary[section]["type"] = type
            summary[section]["unit"] = unit
            summary[section]["label"] = label
            summary[section]["value"] = v  # 已经经过类型化转换
            summary[section]["minv"] = minv  # 已经经过类型化转换
            summary[section]["maxv"] = maxv  # 已经经过类型化转换
            summary[section]["editable"] = editable
            summary[section]["category"] = category

        return summary

    def make_on_text_changed(self, line_edit, name):
        def on_text_changed():
            # print(f'触发高亮：{name}, {self.param_states[name].text}-->{line_edit.text()}' )
            current = line_edit.text().strip()
            if current != self.param_states[name].text():
                line_edit.setStyleSheet("background-color: #80C8FF")  # 浅黄
            else:
                line_edit.setStyleSheet("")

        return on_text_changed

    def set_dev_params(self, dev_name):
        # print(f'设置{dev_name}的所有参数。')
        for name in self.param_category_index[dev_name]:
            self.set_param(name, self.param_inputs[name].text(), delay_flag=True)
        self.dev.set_dev(dev_name)

    def set_param(self, name, value, ui_flag=True, delay_flag=False):
        self.param_inputs[name].setText(f"")  # 不这样就触发不了。

        if type(value) == type(""):
            val_str = value
            val_type = self.param_config[name]["type"]
            try:
                value = eval(f"{val_type}({val_str})")
            except:
                logging.debug(f"参数{name}设置的值{val_str}不合法。")
                if ui_flag:
                    self.param_inputs[name].setText(f"{self.param_config[name]['value']}")
                return False
        # 合法性检查
        if self.param_config[name]["minv"] <= value <= self.param_config[name]["maxv"]:
            # 有时需要强制重复下发，不要做这种检查
            # if self.param_config[name]["value"] == value:
            #     self.param_inputs[name].setText(f"{value}")
            #     return False
            # 下发，回传配置值
            actual_value = self.dev.set_param(name, value)
            self.param_config[name]["value"] = actual_value
            logging.info(f"将参数<{name}>设置为<{value}>，实际设置为<{actual_value}>。")
            if ui_flag:
                self.param_states[name].setText(f"{actual_value}")
                self.param_inputs[name].setText(f"{actual_value}")

            # todo:根据参数进行设置
        else:
            logging.debug(f"参数{name}设置的值{value}越界。")
            if ui_flag:
                self.param_inputs[name].setText(f"{self.param_config[name]['value']}")
            return False
        # 如果不延迟指令，则直接将参数配置好，发送到设备
        if not delay_flag:
            self.dev.set_dev(self.param_config[name]["category"])
        return actual_value

    def set_all_params(self):
        logging.info("向设备发送所有参数。")
        for name, field in self.param_inputs.items():
            self.set_param(name, field.text(), delay_flag=True)
        for catname in self.device_param_buttons.keys():
            self.device_param_buttons[catname].click()
        # 发送配置下发状态信号
        self.config_sent_signal.emit(True)
        QMessageBox.information(self, f"设备初始化完成", f"将设备的所有参数配置下发。")

    def create_device_management_panel(self):
        panel = QWidget()
        layout = QGridLayout()

        self.param_group = QGroupBox("设备参数配置")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QHBoxLayout(scroll_content)
        button_layout = QVBoxLayout()

        self.param_table = QTableWidget(len(self.param_config), 8)
        self.param_table.setHorizontalHeaderLabels(
            ["对应设备", "实验参数", "参数名称", "当前值", "合法范围", "输入新值", "下发单参数", "下发设备参数"])
        self.param_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.param_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.param_table.setFixedHeight(250)
        # 设置表格宽度

        self.param_table.setColumnWidth(0, 80)  # 设备类型
        self.param_table.setColumnWidth(1, 200)  # 实验参数
        self.param_table.setColumnWidth(2, 200)  # 参数名称列
        self.param_table.setColumnWidth(3, 100)  # 当前值
        self.param_table.setColumnWidth(4, 200)  # 合法范围
        self.param_table.setColumnWidth(5, 100)  # 输入新值
        self.param_table.setColumnWidth(6, 100)  # 输入新值
        self.param_table.setColumnWidth(7, 100)  # 输入新值

        sorted_param_config_keys = sorted(self.param_config.keys(), key=lambda x: self.param_config[x]['category'])
        sorted_category_keys = sorted(self.param_category_index.keys())

        # todo: 当前写法不规范，层级有问题
        self.catlabels = {'LIA': '锁相放大器', 'MW': '微波源', 'Laser': '激光器', 'Virtual': '设备内存',
                          'Motor': '电机'}
        prev_row = 0
        for catkey in sorted_category_keys:
            x = len(self.param_category_index[catkey])
            self.param_table.setSpan(prev_row, 0, x, 1)
            self.param_table.setSpan(prev_row, 7, x, 1)

            label_item = QTableWidgetItem(self.catlabels[catkey])
            # self.param_table.setItem(prev_row, 0, catlabels[catkey])
            # print(catkey, prev_row, 0, label_item)
            self.param_table.setItem(prev_row, 0, label_item)

            button = QPushButton(f"{self.catlabels[catkey]}\n参数下发")

            def make_on_click_dev(dev_name=catkey):
                return lambda: self.set_dev_params(dev_name)

            button.clicked.connect(make_on_click_dev(dev_name=catkey))
            self.device_param_buttons[catkey] = button
            # button.clicked.connect()
            self.param_table.setCellWidget(prev_row, 7, button)

            prev_row = prev_row + x

        for row, name in enumerate(sorted_param_config_keys):
            # category = self.param_config[name]["category"]
            label = self.param_config[name]["label"]
            val = self.param_config[name]["value"]
            desc = self.param_config[name]["desc"]
            minv = self.param_config[name]["minv"]
            maxv = self.param_config[name]["maxv"]

            label_item = QTableWidgetItem(label)
            label_item.setToolTip(desc)
            self.param_table.setItem(row, 1, label_item)

            name_item = QTableWidgetItem(name)
            name_item.setToolTip(desc)
            self.param_table.setItem(row, 2, name_item)

            self.param_states[name] = QTableWidgetItem(f"{val}")
            self.param_states[name].setToolTip(desc)
            self.param_table.setItem(row, 3, self.param_states[name])

            range_item = QTableWidgetItem(f"{minv}-{maxv}")
            range_item.setToolTip(desc)
            self.param_table.setItem(row, 4, range_item)

            input_field = QLineEdit()
            if not self.param_config[name]["editable"]:
                input_field.setDisabled(True)
            input_field.setToolTip(desc)
            input_field.setText(f"{val}")

            highlight_func = self.make_on_text_changed(input_field, name)
            input_field.textChanged.connect(highlight_func)

            self.param_table.setRowHeight(row, 35)
            self.param_table.setCellWidget(row, 5, input_field)
            self.param_inputs[name] = input_field

            button = QPushButton("下发")
            if not self.param_config[name]["editable"]:
                button.setDisabled(True)
            self.param_buttons[name] = button

            def make_on_click(param_name=name, field=input_field, delay_flag=False):
                return lambda: self.set_param(param_name, field.text())

            button.clicked.connect(make_on_click())
            self.param_table.setCellWidget(row, 6, button)
            self.param_table.setRowHeight(row, 35)

        scroll_layout.addWidget(self.param_table)
        scroll.setMinimumHeight(300)
        scroll.setMinimumWidth(1200)
        scroll.setWidget(scroll_content)

        self.connect_btn = QPushButton("连接设备")
        self.connect_btn.clicked.connect(self.connect_dev)

        self.test_connection_btn = QPushButton("检验设备通信功能")
        self.test_connection_btn.clicked.connect(self.test_connection_dev)

        self.flush_input_output_btn = QPushButton("清空通信输入输出缓存")
        self.flush_input_output_btn.clicked.connect(self.flush_input_output)

        self.send_btn = QPushButton("下发所有配置")
        self.send_btn.clicked.connect(self.set_all_params)

        self.save_exp_config_btn = QPushButton("保存所有配置到本地文件")
        self.save_exp_config_btn.clicked.connect(self.save_config)

        button_layout.addWidget(self.connect_btn)
        button_layout.addWidget(self.test_connection_btn)
        button_layout.addWidget(self.flush_input_output_btn)
        button_layout.addWidget(self.send_btn)
        button_layout.addWidget(self.save_exp_config_btn)

        scroll_layout.addLayout(button_layout)
        self.param_group.setLayout(scroll_layout)

        self.system_group = QGroupBox("系统状态")

        # setting_layout = QVBoxLayout()

        sys_layout = QGridLayout()
        self.device_status_widgets = {}

        self.device_status_label = QLabel(f"设备状态：--")
        self.thermometer_status_label = QLabel(f"温度计状态：--")
        sys_layout.addWidget(self.device_status_label)
        sys_layout.addWidget(self.thermometer_status_label)
        self.device_status = False

        self.cpu_label = QLabel("CPU 使用率：0%")
        self.mem_label = QLabel("内存占用：0%")
        sys_layout.addWidget(self.cpu_label, 4, 0)
        sys_layout.addWidget(self.mem_label, 5, 0)

        # 温度计设备连接控件
        self.thermometer_device_checkbox = QCheckBox("启用温度计设备")
        self.thermometer_device_checkbox.stateChanged.connect(self.handle_thermometer_toggle)

        thermo_input_layout = QHBoxLayout()

        self.thermometer_buffer_len = 300
        self.thermometer_buffer_input = QLineEdit(str(self.thermometer_buffer_len))

        # thermo_input_layout.addWidget(self.thermometer_device_checkbox)
        thermo_input_layout.addWidget(QLabel("温度显示缓存："))
        thermo_input_layout.addWidget(self.thermometer_buffer_input)
        thermo_input_layout.addWidget(QLabel("s"))

        sys_layout.addWidget(self.thermometer_device_checkbox, 6, 0)
        sys_layout.addLayout(thermo_input_layout, 7, 0)

        self.system_group.setLayout(sys_layout)
        self.system_group.setFixedSize(300, 350)

        # ---- 电机状态区域 ----
        self.motor_group = QGroupBox("超声电机状态")
        motor_layout = QVBoxLayout()

        # 状态标签
        self.motor_status_label = QLabel("电机状态：--\n驱动板状态：--\n当前角度：--\n当前转速：--")
        motor_layout.addWidget(self.motor_status_label)

        # 设备启用
        self.motor_device_checkbox = QCheckBox("启用超声电机设备")
        self.motor_update_status_button = QPushButton("更新电机状态")
        self.motor_update_status_button.clicked.connect(self.ultramotor.update_status)
        motor_layout.addWidget(self.motor_update_status_button)

        self.motor_device_checkbox.stateChanged.connect(self.handle_motor_toggle)
        motor_layout.addWidget(self.motor_device_checkbox)

        # 转动方向控制（互斥选项）
        direction_layout = QHBoxLayout()
        direction_layout.addWidget(QLabel("转动方向："))

        self.motor_direction_group = QButtonGroup(self)  # 创建互斥组
        self.motor_forward_radio = QRadioButton("正转")
        self.motor_reverse_radio = QRadioButton("反转")
        self.motor_auto_radio = QRadioButton("自动")

        self.motor_direction_group.setExclusive(True)  # 强制互斥
        self.motor_direction_group.addButton(self.motor_forward_radio, 0)
        self.motor_direction_group.addButton(self.motor_reverse_radio, 1)
        self.motor_direction_group.addButton(self.motor_auto_radio, 2)

        self.motor_auto_radio.setChecked(True)  # 默认选中"自动"

        direction_layout.addWidget(self.motor_forward_radio)
        direction_layout.addWidget(self.motor_reverse_radio)
        direction_layout.addWidget(self.motor_auto_radio)
        motor_layout.addLayout(direction_layout)

        # 设置初始方向（来自配置）
        motor_direction = self.param_config["ultra_motor_direction"]["value"]
        if motor_direction == 0:
            self.motor_reverse_radio.setChecked(True)
        elif motor_direction == 1:
            self.motor_forward_radio.setChecked(True)
        elif motor_direction == 2:
            self.motor_auto_radio.setChecked(True)
        self.motor_forward_radio.toggled.connect(self.on_motor_direction_checkbox_changed)
        self.motor_reverse_radio.toggled.connect(self.on_motor_direction_checkbox_changed)
        self.motor_auto_radio.toggled.connect(self.on_motor_direction_checkbox_changed)

        # 角度设置
        angle_layout = QHBoxLayout()
        self.motor_angle_input = QLineEdit()
        self.motor_angle_input.setPlaceholderText("输入角度")
        self.motor_angle_input.setFixedWidth(80)
        angle_layout.addWidget(self.motor_angle_input)
        angle_layout.addWidget(QLabel("°"))
        self.motor_angle_set_button = QPushButton("设置超声电机角度")
        self.motor_angle_set_button.clicked.connect(self.on_motor_set_angle)
        angle_layout.addWidget(self.motor_angle_set_button)
        motor_layout.addLayout(angle_layout)
        self.motor_stop_button = QPushButton("电机停转")
        motor_layout.addWidget(self.motor_stop_button)

        self.motor_stop_button.clicked.connect(self.on_motor_stop)

        # 缓存设置
        motor_buffer_input_layout = QHBoxLayout()

        self.angle_buffer_len = 300
        self.motor_angle_buffer_input = QLineEdit(str(self.angle_buffer_len))

        # thermo_input_layout.addWidget(self.thermometer_device_checkbox)
        motor_buffer_input_layout.addWidget(QLabel("电机角度显示缓存："))
        motor_buffer_input_layout.addWidget(self.motor_angle_buffer_input)
        motor_buffer_input_layout.addWidget(QLabel("s"))

        motor_layout.addLayout(motor_buffer_input_layout)

        # ---
        self.motor_group.setLayout(motor_layout)
        self.motor_group.setFixedSize(300, 350)

        # setting_layout.addWidget(self.system_group)
        # setting_layout.addWidget(self.motor_group)

        self.data_group = QGroupBox("常规数据显示")
        data_layout = QVBoxLayout()

        self.temp_plot = pg.PlotWidget(title="温度数据")
        self.temp_plot.setLabel("left", "Temperature", units="°C")
        self.temp_plot.setLabel("bottom", "Time", units="s")
        self.temp_plot.addLegend()

        self.temp_curves = [self.temp_plot.plot(pen=color, name=f'CH{i + 1}') for i, color in
                            enumerate(['r', 'g', 'b', 'y'])]
        self.temp_plot.showGrid(True)

        self.motor_angle_plot = pg.PlotWidget(title="超声电机角度数据")
        self.data_group.setFixedSize(600, 350)

        self.motor_angle_plot.addLegend()
        self.motor_angle_curve = self.motor_angle_plot.plot(pen='r', name="CH1")
        self.motor_angle_plot.setLabel("left", "Angle", units="°")
        self.motor_angle_plot.setLabel("bottom", "Time", units="s")
        self.motor_angle_plot.showGrid(True)

        data_layout.addWidget(self.temp_plot)
        data_layout.addWidget(self.motor_angle_plot)
        self.data_group.setLayout(data_layout)

        self.temperature_time_buffer = []
        self.temperature_buffer = [[], [], [], []]

        self.motor_time_buffer = []
        self.motor_angle_buffer = []

        layout.addWidget(self.param_group, 0, 0, 1, 4)
        layout.addWidget(self.system_group, 1, 0, 1, 2)
        layout.addWidget(self.motor_group, 1, 1, 1, 2)
        layout.addWidget(self.data_group, 1, 2, 2, 2)

        panel.setLayout(layout)

        return panel

    def flush_input_output(self):
        self.dev.flush_input_output()

    def on_motor_set_angle(self):
        if not self.ultramotor.is_connect():
            logging.debug("电机尚未连接。")
            return
        angle = 0
        try:
            angle = float(self.motor_angle_input.text())
        except:
            logging.debug("电机角度不合法。")
            return
        if angle < 0 or angle > 360:
            logging.debug("电机角度越界。")
            return

        direction = self.param_config["ultra_motor_direction"]["value"]
        speed = self.param_config["ultra_motor_speed"]["value"]

        current_angle = self.ultramotor.current_angle
        forward_angle = (current_angle - angle) % 360

        logging.info(f"当前角度：{current_angle}, 目标角度：{angle}, 判断正转所需：{forward_angle}")
        if direction == 2:  # 自动选择方向
            motor_direction_flag = forward_angle > 180
            self.ultramotor.rotate_motor(speed, angle, direction=motor_direction_flag)
        else:  # 手动选择方向
            self.ultramotor.rotate_motor(speed, angle, direction=bool(direction))

    def on_motor_stop(self):
        if not self.ultramotor.is_connect():
            logging.debug("电机尚未连接。")
            return
        logging.info("停机超声电机。")
        self.ultramotor.stop_motor()

    def on_motor_direction_checkbox_changed(self):
        sender = self.sender()
        if not sender.isChecked():
            return

        direction = 0
        if self.motor_forward_radio == sender:
            direction = 1
        elif self.motor_reverse_radio == sender:
            direction = 0
        elif self.motor_auto_radio == sender:
            direction = 2
        self.set_param("ultra_motor_direction", direction)
        logging.info("重设超声电机正反转方向。")

    def handle_thermometer_toggle(self, state):
        if state:
            self.temperature_time_buffer = []
            self.temperature_buffer = [[], [], [], []]
            if self.thermometer.connect_thermometer():
                logging.debug("成功连接温度计。")
                self.thermometer_status_label.setText("温度计状态：已连接")
                self.thermometer_timer.start(1000)
            else:
                logging.debug("温度计连接失败。")
                self.thermometer_status_label.setText("温度计状态：连接失败")
        else:
            logging.debug("断开温度计连接。")
            self.thermometer.disconnect_thermometer()
            self.thermometer_status_label.setText("温度计状态：未连接")
            self.thermometer_timer.stop()

    def handle_motor_toggle(self, state):
        if state:
            self.motor_time_buffer = []
            self.motor_angle_buffer = []
            if self.ultramotor.connect_motor():
                logging.debug("超声电机成功连接。")
                # TODO:临时取消角度显示功能
                # self.motor_timer.start(1000)
            else:
                logging.debug("超声电机连接失败。")
                self.motor_status_label.setText("电机状态：连接失败\n驱动板状态：--\n当前角度：--\n当前转速：--\n")
        else:
            logging.debug("断开超声电机连接。")
            self.ultramotor.disconnect_motor()
            self.motor_status_label.setText("电机状态：--\n驱动板状态：--\n当前角度：--\n当前转速：--\n")
            # self.motor_timer.stop()

    def test_connection_dev(self):
        checked_flag, data_num, checked_num = self.dev.error_check(data_num=65535)
        # logging.info(f"测试通信功能，正常接收到的数据{checked_num}/{data_num}。")
        QMessageBox.information(self, f"通信测试完成",
                                f"正常接收到数据{checked_num}/{data_num}。\n{'通信成功。' if checked_flag else '通信故障。'}")

    def connect_dev(self):
        if self.state_manager.current_state() == DevState.OFFLINE:
            logging.debug("尝试连接设备。")
            try:
                # self.dev = Device() # todo：替换为设备连接与初始化内容
                # self.dev = LIA_API(libusb_path=self.libusb_path)
                self.dev = LIA_API(port=self.lockin_port)
                if self.dev.connect_device():
                    # 设备连接成功
                    logging.info("设备连接成功。")
                    self.state_manager.set_state(DevState.IDLE)
                    self.connect_btn.setText("断开设备")
                else:
                    traceback.print_exc()
                    self.dev = None
                    logging.debug(f"设备连接失败。 [No Exception]")
                    return
            except Exception as e:
                self.dev = None
                logging.debug(f"设备连接失败。[{e}]")
                return

        elif self.state_manager.current_state() == DevState.IDLE:
            logging.debug("尝试断开设备。")
            self.dev.disconnect_device()
            self.dev.close()
            self.dev = None
            # self.dev = None # todo:替换为设备断开内容，并释放内存。
            self.state_manager.set_state(DevState.OFFLINE)
            logging.info("设备已断开。")
            self.connect_btn.setText("连接设备")

    def save_exp_config(self, save_dir):
        save_fname = save_dir + 'exp_config.ini'
        with open(save_fname, 'w', encoding='utf-8') as f:
            self.config.write(f)
        logging.info(f"实验配置文件已保存为: {save_fname}")
        # QMessageBox.information(self, "保存成功", f"实验配置已保存为 {save_fname}")

    def save_config(self):
        for name, field in self.param_inputs.items():
            val = field.text().strip()
            if val:
                self.config[name]['value'] = val
        with open(self.exp_config_path, 'w', encoding='utf-8') as f:
            self.config.write(f)
        QMessageBox.information(self, "下发成功", "参数已写入配置文件。")

    def update_system_info(self):
        self.cpu_label.setText(f"CPU使用率：{psutil.cpu_percent()}%")
        self.mem_label.setText(f"内存占用：{psutil.virtual_memory().percent}%")

    def create_experiment_data_panel(self):
        panel = QWidget()
        layout = QVBoxLayout()

        control_layout = QHBoxLayout()
        self.exp_selector = QComboBox()
        self.exp_selector.addItems(["实验A", "实验B", "实验C"])
        self.exp_cmd_input = QLineEdit()
        self.exp_cmd_input.setPlaceholderText("命令行参数...")
        self.exp_start_btn = QPushButton("开始实验")
        self.exp_stop_btn = QPushButton("停止实验")
        self.exp_start_btn.clicked.connect(self.start_experiment)
        self.exp_stop_btn.clicked.connect(self.stop_experiment)
        control_layout.addWidget(QLabel("实验选择："))
        control_layout.addWidget(self.exp_selector)
        control_layout.addWidget(self.exp_cmd_input)
        control_layout.addWidget(self.exp_start_btn)
        control_layout.addWidget(self.exp_stop_btn)

        self.exp_plot = pg.PlotWidget(title="实验数据")
        self.exp_curve = self.exp_plot.plot(pen='y')

        layout.addLayout(control_layout)
        layout.addWidget(self.exp_plot)
        panel.setLayout(layout)
        return panel

    def start_experiment(self):
        cmd_args = self.exp_cmd_input.text()
        experiment = self.exp_selector.currentText()
        logging.info(f"实验开始: {experiment} 参数: {cmd_args}")

    def stop_experiment(self):
        logging.info("实验停止")

    def create_status_bar(self):
        """创建状态栏"""
        self.status_bar = QFrame()
        self.status_bar.setFrameStyle(QFrame.StyledPanel)
        self.status_bar.setFixedHeight(30)
        
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(10, 5, 10, 5)
        
        # 配置下发状态
        self.config_status_label = QLabel("配置下发: ")
        self.config_status_indicator = QLabel("●")
        self.config_status_indicator.setStyleSheet("color: red; font-weight: bold;")
        self.config_status_indicator.setToolTip("红色表示未下发配置，绿色表示已下发配置")
        
        # CH1 CW谱更新状态
        self.ch1_cw_status_label = QLabel("CH1 CW谱: ")
        self.ch1_cw_status_indicator = QLabel("●")
        self.ch1_cw_status_indicator.setStyleSheet("color: red; font-weight: bold;")
        self.ch1_cw_status_indicator.setToolTip("红色表示未更新CH1 CW谱，绿色表示已更新CH1 CW谱")
        
        # CH2 CW谱更新状态
        self.ch2_cw_status_label = QLabel("CH2 CW谱: ")
        self.ch2_cw_status_indicator = QLabel("●")
        self.ch2_cw_status_indicator.setStyleSheet("color: red; font-weight: bold;")
        self.ch2_cw_status_indicator.setToolTip("红色表示未更新CH2 CW谱，绿色表示已更新CH2 CW谱")
        
        # 添加分隔符
        separator1 = QLabel("|")
        separator1.setStyleSheet("color: gray; margin: 0 10px;")
        separator2 = QLabel("|")
        separator2.setStyleSheet("color: gray; margin: 0 10px;")
        
        status_layout.addWidget(self.config_status_label)
        status_layout.addWidget(self.config_status_indicator)
        status_layout.addWidget(separator1)
        status_layout.addWidget(self.ch1_cw_status_label)
        status_layout.addWidget(self.ch1_cw_status_indicator)
        status_layout.addWidget(separator2)
        status_layout.addWidget(self.ch2_cw_status_label)
        status_layout.addWidget(self.ch2_cw_status_indicator)
        status_layout.addStretch()  # 添加弹性空间
        
        self.status_bar.setLayout(status_layout)

    def update_config_status(self, sent):
        """更新配置下发状态"""
        if sent:
            self.config_status_indicator.setStyleSheet("color: green; font-weight: bold;")
            self.config_status_indicator.setToolTip("配置已下发")
        else:
            self.config_status_indicator.setStyleSheet("color: red; font-weight: bold;")
            self.config_status_indicator.setToolTip("配置未下发")

    def update_ch1_cw_status(self, updated):
        """更新CH1 CW谱状态"""
        if updated:
            self.ch1_cw_status_indicator.setStyleSheet("color: green; font-weight: bold;")
            self.ch1_cw_status_indicator.setToolTip("CH1 CW谱已更新")
        else:
            self.ch1_cw_status_indicator.setStyleSheet("color: red; font-weight: bold;")
            self.ch1_cw_status_indicator.setToolTip("CH1 CW谱未更新")

    def update_ch2_cw_status(self, updated):
        """更新CH2 CW谱状态"""
        if updated:
            self.ch2_cw_status_indicator.setStyleSheet("color: green; font-weight: bold;")
            self.ch2_cw_status_indicator.setToolTip("CH2 CW谱已更新")
        else:
            self.ch2_cw_status_indicator.setStyleSheet("color: red; font-weight: bold;")
            self.ch2_cw_status_indicator.setToolTip("CH2 CW谱未更新")


if __name__ == '__main__':

    app = QApplication(sys.argv)
    window = ExperimentApp()
    window.show()
    sys.exit(app.exec())

