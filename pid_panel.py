# encoding=utf-8
import time
import numpy as np
import PySide6.QtGui as QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QCheckBox, QComboBox, QDateTimeEdit,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QScrollArea,
    QGroupBox, QGridLayout, QSizePolicy
)
from PySide6.QtCore import QDateTime, QTimer, QObject, Signal, QThread
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from manager import *
from scipy.signal import detrend
import os


def gettimestr():
    import time
    return time.strftime('%Y-%m-%d %H_%M_%S', time.localtime(time.time()))


# ----------------- Model -----------------
class OscilloscopePIDModel(QObject):
    # PID数据格式：(1R, 1X, 1Y, 1Error, 1Feedback, 2R, 2X, 2Y, 2Error, 2Feedback, Fluo_DC, Laser_DC)
    data_updated = Signal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray,  np.ndarray,
                         np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.running = False
        self.sample_rate = self.parent.parent.parent.param_config["lockin_sample_rate"]['value']
        self.sample_interval = 1 / self.sample_rate
        self.acq_time = 1  # 采集时长，单位为秒
        self.auto_save_time_interval = 2400  # 自动保存时间间隔，单位为秒
        self.pid_sample_rate = 50
        self.pid_sample_interval = 1 / self.pid_sample_rate
        self.save_dir = None
        self.acq_save_start_time = None
        self.is_run = False


    def init_pid_settings(self):
        ex_ratio = self.parent.parent.parent.param_config['lockin_pid_ex_ratio']['value']
        rd_ratio = self.parent.parent.parent.param_config['lockin_pid_rd_ratio']['value']
        self.pid_sample_rate = int(25e6 / (ex_ratio + 1) / (rd_ratio + 1)) # Hz
        logging.info(f"PID设置采样率：{self.pid_sample_rate:.1f}Hz, EX_Ratio={ex_ratio}, RD_Ratio={rd_ratio}")
        self.pid_sample_interval = 1 / self.pid_sample_rate
        p1 = self.parent.parent.parent.param_config['lockin_PID_ch1_P']['value']
        i1 = self.parent.parent.parent.param_config['lockin_PID_ch1_I']['value']
        d1 = self.parent.parent.parent.param_config['lockin_PID_ch1_D']['value']
        t1 = self.parent.parent.parent.param_config['lockin_PID_ch1_T']['value']
        p2 = self.parent.parent.parent.param_config['lockin_PID_ch2_P']['value']
        i2 = self.parent.parent.parent.param_config['lockin_PID_ch2_I']['value']
        d2 = self.parent.parent.parent.param_config['lockin_PID_ch2_D']['value']
        t2 = self.parent.parent.parent.param_config['lockin_PID_ch2_T']['value']
        ch1_pid_enable = self.parent.parent.ch1_pid_enable_checkbox.isChecked()
        ch2_pid_enable = self.parent.parent.ch2_pid_enable_checkbox.isChecked()

        pid_enable_list = [ch1_pid_enable, ch2_pid_enable]
        p_params = [p1, p2]
        i_params = [i1, i2]
        d_params = [d1, d2]
        t_params = [t1, t2]

        for i in range(2):
            if pid_enable_list[i]:
                logging.info(f"开启CH{i + 1} PID模式, P={p_params[i]}, I={i_params[i]}, D={d_params[i]}, T={t_params[i]}")
            else:
                logging.info(f"关闭CH{i + 1} PID模式，PID参数不生效，全置为零")
                p_params[i] = 0
                i_params[i] = 0
                d_params[i] = 0

        mw_freq_params = [float(self.parent.parent.ch1_init_feedback_freq.text()) * 1e6, 
                          float(self.parent.parent.ch2_init_feedback_freq.text()) * 1e6]

        # 关键设备下发PID指令
        for i in range(2):
            self.parent.parent.parent.dev.PID_config(PID_ch_num=i + 1, 
                                                     set_point=0, 
                                                     output_offset=int((mw_freq_params[i] - 2.6e9) * 0.5 * 1048576), 
                                                     kp=p_params[i], 
                                                     ki=i_params[i], 
                                                     kd=d_params[i], 
                                                     kt=t_params[i], 
                                                     Cal_ex=rd_ratio, 
                                                     RD_ex=ex_ratio, 
                                                     PID_LIA_CH=1, # 0=X, 1=Y
                                                     )
        for i in range(2):
            self.parent.parent.parent.dev.PID_enable(i + 1)
        
        
    def start(self):
        self.is_run = True
        logging.info(f"定时计时到达，准备开始进行PID模式数据采集。定时保存时间间隔：{self.auto_save_time_interval} s")
        self.running = True
        init_start_time = self.parent.get_start_time()
        self.acq_save_start_time = time.time()
        N = 0
        self.save_dir = self.parent.parent.save_dir + f'PID_data_{gettimestr()}/'
        if not os.path.exists(self.save_dir):
            os.mkdir(self.save_dir)
        self.parent.parent.parent.save_exp_config(self.save_dir)
        # 传递PID配置参数
        self.init_pid_settings()


        # 启动PID采集模式
        self.parent.parent.parent.dev.start_infinite_pid_acq()
        
        while self.running:
            start_time = time.time()
            try:
                # 获取PID数据，格式：(1R, 1X, 1Y, 1Error, 1Feedback, 2R, 2X, 2Y, 2Error, 2Feedback, Fluo_DC, Laser_DC)
                pid_data = self.parent.parent.parent.dev.get_infinite_pid_points(data_num=int(self.pid_sample_rate * self.acq_time))
            except:
                break
            stop_time = time.time()
            mac_time = np.linspace(start_time, stop_time, len(pid_data[0]))
            
            # 解析PID数据
            data1R = pid_data[0]  # 通道1 R值
            data1X = pid_data[1]  # 通道1 X值
            data1Y = pid_data[2]  # 通道1 Y值
            data1Error = pid_data[3]  # 通道1 误差
            data1Feedback = pid_data[4]  # 通道1 反馈
            data2R = pid_data[5]  # 通道2 R值
            data2X = pid_data[6]  # 通道2 X值
            data2Y = pid_data[7]  # 通道2 Y值
            data2Error = pid_data[8]  # 通道2 误差
            data2Feedback = pid_data[9]  # 通道2 反馈
            dataFluoDC = pid_data[10]  # 荧光直流
            dataLaserDC = pid_data[11]  # 激光直流
            
            N_new = len(data1R)

            time_data = np.linspace(init_start_time + N * self.pid_sample_interval, 
                                    init_start_time + (N + N_new) * self.pid_sample_interval, 
                                    len(data1R), 
                                    endpoint=False)

            N += N_new

            self.data_updated.emit(mac_time, time_data, data1R, data1X, data1Y, data1Error, data1Feedback,
                                 data2R, data2X, data2Y, data2Error, data2Feedback, dataFluoDC, dataLaserDC)
        
        self.is_run = False

    def stop(self):
        logging.info("结束PID模式数据采集。")
        self.running = False
        while self.is_run:
            time.sleep(0.001)
        self.parent.parent.parent.dev.stop_infinite_pid_acq()
        for i in range(2):
            self.parent.parent.parent.dev.PID_disable(i + 1)
        self.parent.parent.save_data()

    def set_sample_rate(self, rate):
        self.sample_rate = rate
        self.sample_interval = 1.0 / rate
    
    def set_auto_save_time_interval(self, interval):
        self.auto_save_time_interval = interval


# ----------------- ViewModel -----------------
class OscilloscopePIDViewModel(QObject):
    data_ready = Signal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray,np.ndarray,
                       np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = OscilloscopePIDModel(self)
        self.thread = QThread()
        self.model.moveToThread(self.thread)

        self.thread.started.connect(self.model.start)
        self.model.data_updated.connect(self.data_ready)
        self.start_time = None

    def get_start_time(self):
        return self.start_time

    def start(self):
        target_start_time = self.parent.get_start_time()
        self.start_time = target_start_time
        if not self.thread.isRunning():
            while time.time() < target_start_time:
                time.sleep(0.001)  # 等待定时开始时间
            self.thread.start()

    def save_data(self, ui_mode=False):
        self.parent.save_data(ui_mode)

    def stop(self):
        self.model.stop()
        self.thread.quit()
        self.thread.wait()

    def change_sample_rate(self, rate):
        self.model.set_sample_rate(rate)
    
    def change_auto_save_time_interval(self, interval):
        self.model.set_auto_save_time_interval(interval)


# ----------------- View -----------------
class OscilloscopePIDPanel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        if hasattr(self.parent, 'save_dir_pid'):
            self.save_dir = self.parent.save_dir_pid
        else:
            self.save_dir = './'
        self.setWindowTitle("PID数据采集")
        self.resize(1200, 800)

        self.state_manager = parent.state_manager
        self.state_manager.state_changed.connect(self.on_state_changed)

        self.vm = OscilloscopePIDViewModel(self)
        self.vm.data_ready.connect(self.update_display)

        # PID数据缓存
        self.full_data1R = []  # 通道1 R值
        self.full_data1X = []  # 通道1 X值
        self.full_data1Y = []  # 通道1 Y值
        self.full_data1Error = []  # 通道1 误差
        self.full_data1Feedback = []  # 通道1 反馈
        self.full_data2R = []  # 通道2 R值
        self.full_data2X = []  # 通道2 X值
        self.full_data2Y = []  # 通道2 Y值
        self.full_data2Error = []  # 通道2 误差
        self.full_data2Feedback = []  # 通道2 反馈
        self.full_dataFluoDC = []  # 荧光直流
        self.full_dataLaserDC = []  # 激光直流
        self.full_mac_time = []
        self.full_time_data = []

        self.acq_time = 60
        self.display_length = 1000  # 屏幕显示长度（可调）
        self.init_start_time = time.time()
        
        # PID参数相关
        self.param_config = self.load_pid_param_config()
        self.param_inputs = {}  # 输入框列表
        self.param_states = {}  # 状态列表
        self.param_buttons = {}  # 按钮列表
        
        self.init_ui()
        
        # 初始化按钮状态
        self.on_state_changed(self.state_manager.current_state())

    def load_pid_param_config(self):
        """加载PID相关参数配置"""
        pid_param_config = {}
        for name, config in self.parent.param_config.items():
            if 'PID' in name.upper():
                pid_param_config[name] = config
        return pid_param_config

    def on_state_changed(self, state):
        if state == DevState.OFFLINE:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
            # 禁用所有参数输入和下发按钮
            for name, field in self.param_inputs.items():
                field.setEnabled(False)
            for name, button in self.param_buttons.items():
                button.setEnabled(False)
            self.send_all_pid_params_btn.setEnabled(False)
        elif state == DevState.IDLE:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
            # 启用所有可编辑的参数输入和下发按钮
            for name, field in self.param_inputs.items():
                if self.param_config[name]["editable"]:
                    field.setEnabled(True)
            for name, button in self.param_buttons.items():
                if self.param_config[name]["editable"]:
                    button.setEnabled(True)
            self.send_all_pid_params_btn.setEnabled(True)
        elif state == DevState.PID_RUNNING:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
            # 禁用所有参数输入和下发按钮
            for name, field in self.param_inputs.items():
                field.setEnabled(False)
            for name, button in self.param_buttons.items():
                button.setEnabled(False)
            self.send_all_pid_params_btn.setEnabled(False)
        else:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
            # 禁用所有参数输入和下发按钮
            for name, field in self.param_inputs.items():
                field.setEnabled(False)
            for name, button in self.param_buttons.items():
                button.setEnabled(False)
            self.send_all_pid_params_btn.setEnabled(False)

    def flush_buffer(self):
        self.full_data1R = []
        self.full_data1X = []
        self.full_data1Y = []
        self.full_data1Error = []
        self.full_data1Feedback = []
        self.full_data2R = []
        self.full_data2X = []
        self.full_data2Y = []
        self.full_data2Error = []
        self.full_data2Feedback = []
        self.full_dataFluoDC = []
        self.full_dataLaserDC = []
        self.full_time_data = []
        self.full_mac_time = []
        self.init_start_time = time.time()

    def handle_linear_auto_adjust_change(self):
        if self.linear_auto_adjust_combo.currentIndex() == 0:
            self.linear_auto_adjust_flag = 0  # 关闭
        else:
            self.linear_auto_adjust_flag = 1  # 开启，自动校正

    def make_on_text_changed(self, line_edit, name):
        def on_text_changed():
            current = line_edit.text().strip()
            if current != self.param_states[name].text():
                line_edit.setStyleSheet("background-color: #80C8FF")  # 浅蓝
            else:
                line_edit.setStyleSheet("")
        return on_text_changed

    def set_pid_param(self, name, value, ui_flag=True):
        """设置PID参数"""
        # self.param_inputs[name].setText("")  # 清空以触发变化检测

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
            # 下发参数到设备
            actual_value = self.parent.set_param(name, value, ui_flag=True, delay_flag=False)
            self.param_config[name]["value"] = actual_value
            # logging.info(f"[PID层级] 将PID参数<{name}>设置为<{value}>，实际设置为<{actual_value}>。")
            if ui_flag:
                self.param_states[name].setText(f"{actual_value}")
                self.param_inputs[name].setText(f"{actual_value}")
        else:
            logging.debug(f"参数{name}设置的值{value}越界。")
            if ui_flag:
                self.param_inputs[name].setText(f"{self.param_config[name]['value']}")
            return False

    def create_pid_param_table(self):
        """创建PID参数配置表格"""
        param_group = QGroupBox("PID参数配置")
        param_group.setCheckable(True)  # 设置为可折叠
        param_group.setChecked(True)    # 默认展开
        layout = QVBoxLayout()

        self.param_table = QTableWidget(len(self.param_config), 6)
        self.param_table.setHorizontalHeaderLabels(
            ["参数名称", "当前值", "合法范围", "输入新值", "下发参数", "单位"])
        self.param_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.param_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.param_table.setFixedHeight(150)  # 减小Y方向尺寸

        # 设置表格列宽自适应
        self.param_table.horizontalHeader().setStretchLastSection(False)
        self.param_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)  # 参数名称自适应
        self.param_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 当前值自适应
        self.param_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 合法范围自适应
        self.param_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 输入新值自适应
        self.param_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 下发参数自适应
        self.param_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)  # 单位自适应

        sorted_param_config_keys = sorted(self.param_config.keys())

        for row, name in enumerate(sorted_param_config_keys):
            label = self.param_config[name]["label"]
            val = self.param_config[name]["value"]
            desc = self.param_config[name]["desc"]
            minv = self.param_config[name]["minv"]
            maxv = self.param_config[name]["maxv"]
            unit = self.param_config[name]["unit"]

            name_item = QTableWidgetItem(label)
            name_item.setToolTip(desc)
            self.param_table.setItem(row, 0, name_item)

            self.param_states[name] = QTableWidgetItem(f"{val}")
            self.param_states[name].setToolTip(desc)
            self.param_table.setItem(row, 1, self.param_states[name])

            range_item = QTableWidgetItem(f"{minv}-{maxv}")
            range_item.setToolTip(desc)
            self.param_table.setItem(row, 2, range_item)

            input_field = QLineEdit()
            if not self.param_config[name]["editable"]:
                input_field.setDisabled(True)
            input_field.setToolTip(desc)

            # print(f'PID参数{name}，设置为:{val}')
            input_field.setText(f"{val}")  # 使用当前param_config中的默认值

            highlight_func = self.make_on_text_changed(input_field, name)
            input_field.textChanged.connect(highlight_func)

            self.param_table.setRowHeight(row, 25)  # 减小行高
            self.param_table.setCellWidget(row, 3, input_field)
            self.param_inputs[name] = input_field

            button = QPushButton("下发")
            if not self.param_config[name]["editable"]:
                button.setDisabled(True)
            self.param_buttons[name] = button

            def make_on_click(param_name=name, field=input_field):
                return lambda: self.set_pid_param(param_name, field.text())

            button.clicked.connect(make_on_click())
            self.param_table.setCellWidget(row, 4, button)

            unit_item = QTableWidgetItem(unit if unit else "")
            self.param_table.setItem(row, 5, unit_item)

        layout.addWidget(self.param_table)

        # 添加批量操作按钮
        button_layout = QHBoxLayout()
        self.send_all_pid_params_btn = QPushButton("下发所有PID参数")
        self.send_all_pid_params_btn.clicked.connect(self.set_all_pid_params)
        button_layout.addWidget(self.send_all_pid_params_btn)
        button_layout.addStretch()  # 添加弹性空间
        
        layout.addLayout(button_layout)
        param_group.setLayout(layout)
        
        # 连接GroupBox的toggled信号来控制表格的可见性
        param_group.toggled.connect(self.on_param_group_toggled)
        
        return param_group

    def on_param_group_toggled(self, checked):
        """处理PID参数配置GroupBox的切换状态"""
        if checked:
            # 展开时显示表格和按钮
            self.param_table.setVisible(True)
            self.send_all_pid_params_btn.setVisible(True)
        else:
            # 折叠时隐藏表格和按钮
            self.param_table.setVisible(False)
            self.send_all_pid_params_btn.setVisible(False)

    def set_all_pid_params(self):
        """下发所有PID参数"""
        logging.info("向设备发送所有PID参数。")
        for name, field in self.param_inputs.items():
            self.set_pid_param(name, field.text())
        QMessageBox.information(self, f"PID参数下发完成", f"已将所有PID参数配置下发到设备。")

    def init_ui(self):
        layout = QVBoxLayout()
        
        # PID参数配置表格
        self.pid_param_group = self.create_pid_param_table()
        layout.addWidget(self.pid_param_group)

        # 基本控制功能
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始采集")
        self.save_btn = QPushButton("保存数据")
        self.clear_btn = QPushButton("清空数据")

        self.start_btn.clicked.connect(self.on_start_button_clicked)
        self.clear_btn.clicked.connect(self.flush_buffer)
        self.save_btn.clicked.connect(self.save_data)
        self.save_btn.clicked.connect(self.save_image)

        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.save_btn)
        control_layout.addWidget(self.clear_btn)

        # 显示设置
        control_layout.addWidget(QLabel("屏幕显示时长（s）:"))
        self.length_input = QLineEdit(str(self.display_length))
        self.length_input.setFixedWidth(100)
        control_layout.addWidget(self.length_input)

        # 显示模式选择
        control_layout.addWidget(QLabel("显示模式:"))
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems(["显示电压", "显示磁场"])
        self.display_mode_combo.setCurrentIndex(0)  # 默认显示电压
        control_layout.addWidget(self.display_mode_combo)

        layout.addLayout(control_layout)

        # 采集设置
        acq_layout = QHBoxLayout()
        
        # 定时开始采集
        acq_layout.addWidget(QLabel("定时开始时间:"))
        self.scheduled_time = QDateTimeEdit()
        self.scheduled_time.setDateTime(QDateTime.currentDateTime())
        self.scheduled_time.setCalendarPopup(True)
        self.scheduled_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        acq_layout.addWidget(self.scheduled_time)

        # 采集模式选择
        acq_layout.addWidget(QLabel("采集模式:"))
        self.acq_mode_combo = QComboBox()
        self.acq_mode_combo.addItems(["定时长采集", "不限制时长采集"])
        self.acq_mode_combo.setCurrentIndex(0)  # 默认选择定时长采集
        acq_layout.addWidget(self.acq_mode_combo)

        # 去趋势模式
        acq_layout.addWidget(QLabel("去趋势模式："))
        self.acq_trend_remove_checkbox = QComboBox()
        self.acq_trend_remove_checkbox.addItems(["关闭", "线性去基线", "直流去基线"])
        self.acq_trend_remove_checkbox.setCurrentIndex(0)  # 默认关闭
        acq_layout.addWidget(self.acq_trend_remove_checkbox)

        acq_layout.addWidget(QLabel("CH1初始反馈频率(MHz)："))
        self.ch1_init_feedback_freq = QLineEdit(str(2850))
        acq_layout.addWidget(self.ch1_init_feedback_freq)
        acq_layout.addWidget(QLabel("CH2初始反馈频率(MHz)："))
        self.ch2_init_feedback_freq = QLineEdit(str(2920))
        acq_layout.addWidget(self.ch2_init_feedback_freq)
        layout.addLayout(acq_layout)

        # INSERT_YOUR_CODE
        # 增加两个CheckBox，是否开启对应通道PID，默认选择开启
        self.ch1_pid_enable_checkbox = QCheckBox("开启CH1 PID")
        self.ch1_pid_enable_checkbox.setChecked(True)
        acq_layout.addWidget(self.ch1_pid_enable_checkbox)

        self.ch2_pid_enable_checkbox = QCheckBox("开启CH2 PID")
        self.ch2_pid_enable_checkbox.setChecked(True)
        acq_layout.addWidget(self.ch2_pid_enable_checkbox)

        # 统计信息显示
        self.stats_label = QLabel("CH1误差最大值: --   CH1误差最小值: --   CH1误差均值: --\n"
                                  "CH2误差最大值: --   CH2误差最小值: --   CH2误差均值: --")
        layout.addWidget(self.stats_label)

        self.label_coord = QLabel("X: -- , Y: --")
        layout.addWidget(self.label_coord)

        # 创建图表
        self.create_plots()
        layout.addLayout(self.plot_layout)

        self.setLayout(layout)

    def create_plots(self):
        """创建图表"""
        # 创建6张图的布局
        plot_layout = QGridLayout()
        
        # CH1-Error图
        self.plot_ch1_error = pg.PlotWidget(title="CH1-Error")
        self.plot_ch1_error.showGrid(x=True, y=True)
        self.plot_ch1_error.setLabel("left", "Error", units="V")
        self.plot_ch1_error.setLabel("bottom", "Time", units="s")
        self.curve_ch1_error = self.plot_ch1_error.plot(pen='r', name="CH1 Error")
        self.plot_ch1_error.addLegend()
        self.plot_ch1_error.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch1_error))
        
        # CH1-Feedback图
        self.plot_ch1_feedback = pg.PlotWidget(title="CH1-Feedback")
        self.plot_ch1_feedback.showGrid(x=True, y=True)
        self.plot_ch1_feedback.setLabel("left", "Feedback", units="Hz")
        self.plot_ch1_feedback.setLabel("bottom", "Time", units="s")
        self.curve_ch1_feedback = self.plot_ch1_feedback.plot(pen='r', name="CH1 Feedback")
        self.plot_ch1_feedback.addLegend()
        self.plot_ch1_feedback.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch1_feedback))
        
        # CH1-R/X/Y图
        self.plot_ch1_rxy = pg.PlotWidget(title="CH1-R/X/Y")
        self.plot_ch1_rxy.showGrid(x=True, y=True)
        self.plot_ch1_rxy.setLabel("left", "Amplitude", units="V")
        self.plot_ch1_rxy.setLabel("bottom", "Time", units="s")
        self.curve_ch1_r = self.plot_ch1_rxy.plot(pen='r', name="CH1-R")
        self.curve_ch1_x = self.plot_ch1_rxy.plot(pen='g', name="CH1-X")
        self.curve_ch1_y = self.plot_ch1_rxy.plot(pen='b', name="CH1-Y")
        self.plot_ch1_rxy.addLegend()
        self.plot_ch1_rxy.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch1_rxy))
        
        # CH2-Error图
        self.plot_ch2_error = pg.PlotWidget(title="CH2-Error")
        self.plot_ch2_error.showGrid(x=True, y=True)
        self.plot_ch2_error.setLabel("left", "Error", units="V")
        self.plot_ch2_error.setLabel("bottom", "Time", units="s")
        self.curve_ch2_error = self.plot_ch2_error.plot(pen='b', name="CH2 Error")
        self.plot_ch2_error.addLegend()
        self.plot_ch2_error.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch2_error))
        
        # CH2-Feedback图
        self.plot_ch2_feedback = pg.PlotWidget(title="CH2-Feedback")
        self.plot_ch2_feedback.showGrid(x=True, y=True)
        self.plot_ch2_feedback.setLabel("left", "Feedback", units="Hz")
        self.plot_ch2_feedback.setLabel("bottom", "Time", units="s")
        self.curve_ch2_feedback = self.plot_ch2_feedback.plot(pen='b', name="CH2 Feedback")
        self.plot_ch2_feedback.addLegend()
        self.plot_ch2_feedback.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch2_feedback))
        
        # CH2-R/X/Y图
        self.plot_ch2_rxy = pg.PlotWidget(title="CH2-R/X/Y")
        self.plot_ch2_rxy.showGrid(x=True, y=True)
        self.plot_ch2_rxy.setLabel("left", "Amplitude", units="V")
        self.plot_ch2_rxy.setLabel("bottom", "Time", units="s")
        self.curve_ch2_r = self.plot_ch2_rxy.plot(pen='r', name="CH2-R")
        self.curve_ch2_x = self.plot_ch2_rxy.plot(pen='g', name="CH2-X")
        self.curve_ch2_y = self.plot_ch2_rxy.plot(pen='b', name="CH2-Y")
        self.plot_ch2_rxy.addLegend()
        self.plot_ch2_rxy.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch2_rxy))
        
        # 将6张图排列成2行3列的布局
        plot_layout.addWidget(self.plot_ch1_error, 0, 0)
        plot_layout.addWidget(self.plot_ch1_feedback, 0, 1)
        plot_layout.addWidget(self.plot_ch1_rxy, 0, 2)
        plot_layout.addWidget(self.plot_ch2_error, 1, 0)
        plot_layout.addWidget(self.plot_ch2_feedback, 1, 1)
        plot_layout.addWidget(self.plot_ch2_rxy, 1, 2)
        
        # 保存布局供后续使用
        self.plot_layout = plot_layout

    def get_start_time(self):
        '''获取定时开始时间，单位为秒'''
        return self.scheduled_time.dateTime().toSecsSinceEpoch()

    def on_start_button_clicked(self):
        state = self.state_manager.current_state()
        if state == DevState.PID_RUNNING:
            self.start_btn.setText("开始采集")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()
        elif state == DevState.IDLE:
            self.flush_buffer()
            self.init_start_time = time.time()
            self.start_btn.setText("停止采集")
            self.state_manager.set_state(DevState.PID_RUNNING)
            self.vm.start()

    def update_display(self, mac_time, time_data, data1R, data1X, data1Y, data1Error, data1Feedback,
                      data2R, data2X, data2Y, data2Error, data2Feedback, dataFluoDC, dataLaserDC):
        """更新显示"""
        # 扩展数据缓存
        self.full_data1R.extend(data1R)
        self.full_data1X.extend(data1X)
        self.full_data1Y.extend(data1Y)
        self.full_data1Error.extend(data1Error)
        self.full_data1Feedback.extend(data1Feedback)
        self.full_data2R.extend(data2R)
        self.full_data2X.extend(data2X)
        self.full_data2Y.extend(data2Y)
        self.full_data2Error.extend(data2Error)
        self.full_data2Feedback.extend(data2Feedback)
        self.full_dataFluoDC.extend(dataFluoDC)
        self.full_dataLaserDC.extend(dataLaserDC)
        self.full_time_data.extend(time_data.tolist())
        self.full_mac_time.extend(mac_time.tolist())

        try:
            self.display_length = int(float(self.length_input.text()) * self.vm.model.pid_sample_rate)
        except:
            pass

        acq_trend_remove_checkbox = self.acq_trend_remove_checkbox.currentIndex()
        mag_view_mode = self.display_mode_combo.currentIndex() # 0=电压 1=磁场
        nv_eff_gyromagnetic_ratio = self.parent.param_config['nv_eff_gyromagnetic_ratio']['value']

        # 裁剪显示窗口数据
        timewindow = np.array(self.full_time_data[-self.display_length:]) - self.init_start_time

        # 处理数据
        window1_error = self.full_data1Error[-self.display_length:]
        window2_error = self.full_data2Error[-self.display_length:]
        if acq_trend_remove_checkbox == 1: # 移除线性基线
            # window1_error = detrend(self.full_data1Error[-self.display_length:])
            # window2_error = detrend(self.full_data2Error[-self.display_length:])
            window1_feedback = detrend(self.full_data1Feedback[-self.display_length:])
            window2_feedback = detrend(self.full_data2Feedback[-self.display_length:])
        elif acq_trend_remove_checkbox == 2: # 移除直流基线
            window1_feedback = np.array(self.full_data1Feedback[-self.display_length:])
            window1_feedback = window1_feedback - np.mean(window1_feedback)
            window2_feedback = np.array(self.full_data2Feedback[-self.display_length:])
            window2_feedback = window2_feedback - np.mean(window2_feedback)
        else:
            window1_feedback = np.array(self.full_data1Feedback[-self.display_length:])
            window2_feedback = np.array(self.full_data2Feedback[-self.display_length:])

        # 更新统计信息
        mean_val1 = np.mean(window1_feedback)
        std_val1 = np.std(window1_feedback)
        mean_val2 = np.mean(window2_feedback)
        std_val2 = np.std(window2_feedback)
        std_err_val1 = np.std(window1_error)
        std_err_val2 = np.std(window2_error)
        vpp_val1 = np.ptp(window1_error)
        vpp_val2 = np.ptp(window2_error)


        diff_data = (window1_feedback - window2_feedback) / 2
        comm_data = (window1_feedback + window2_feedback)/2
        std_diff = np.std(diff_data)
        std_comm = np.std(comm_data)
        vpp_diff = np.ptp(diff_data)
        vpp_comm = np.ptp(comm_data)


        eff_gyro = self.parent.param_config['nv_eff_gyromagnetic_ratio']['value']
        temp_coe = 74e3 # Hz/K

        self.stats_label.setText(f"[CH1] 反馈值频率标准差: {std_val1/1e3:.3f}kHz 反馈值均值: {mean_val1/1e3:.3f}kHz 误差值标准差: {std_err_val1 * 1e3:.6f}mV 磁场标准差：{std_val1 / eff_gyro * 1e12:.3f} pT 磁场峰峰值：{vpp_val1 / eff_gyro * 1e12:.3f}\n"
                                 f"[CH2] 反馈值频率标准差: {std_val2/1e3:.3f}kHz 反馈值均值: {mean_val2/1e3:.3f}kHz 误差值标准差: {std_err_val2 * 1e3:.6f}mV 磁场标准差：{std_val2 / eff_gyro * 1e12:.3f} pT 磁场峰峰值：{vpp_val2 / eff_gyro * 1e12:.3f}\n"
                                 f"[差分计算]（磁场） 差分频率标准差：{std_diff/1e3:.3f}kHz  差分磁场标准差：{std_diff/eff_gyro*1e12:.3f}pT 差分磁场峰峰值：{vpp_diff/eff_gyro*1e12:.3f}pT\n"
                                 f"[共模计算]（温度） 共模频率标准差：{std_comm/1e3:.3f}kHz  差分温度标准差：{std_comm/temp_coe:.3f}K 差分温度峰峰值：{vpp_comm/temp_coe:.3f}K"
                                 )
        

        if mag_view_mode == 1:
            # 共振频率差分计算磁场，平均计算零场
            window1_feedback_new = (window1_feedback - window2_feedback) / nv_eff_gyromagnetic_ratio
            window2_feedback_new = (window1_feedback + window2_feedback) / 2

            # 更新
            window1_feedback = window1_feedback_new
            window2_feedback = window2_feedback_new

            self.plot_ch1_feedback.setLabel("left", "磁场", units="T")
            self.plot_ch2_feedback.setLabel("left", "零场", units="Hz")
            self.plot_ch1_feedback.setTitle("差分计算磁场 f+ - f-")
            self.plot_ch2_feedback.setTitle("平均计算零场 (f+ + f-)/2")
        else:
            self.plot_ch1_feedback.setLabel("left", "Feedback", units="Hz")
            self.plot_ch2_feedback.setLabel("left", "Feedback", units="Hz")
            self.plot_ch1_feedback.setTitle("CH1 Feedback")
            self.plot_ch2_feedback.setTitle("CH2 Feedback")
            
    
        # 自动保存检查
        if time.time() - self.vm.model.acq_save_start_time > self.vm.model.auto_save_time_interval:
            self.save_data(ui_mode=False)
            self.vm.model.acq_save_start_time = time.time()
            logging.info(f"自动保存PID数据，保存时间：{time.time()}")

        # 更新图表
        # CH1-Error图
        self.curve_ch1_error.setData(timewindow, np.array(window1_error))
        
        # CH1-Feedback图
        self.curve_ch1_feedback.setData(timewindow, np.array(window1_feedback))

        
        
        # CH1-R/X/Y图
        window1_r = self.full_data1R[-self.display_length:]
        window1_x = self.full_data1X[-self.display_length:]
        window1_y = self.full_data1Y[-self.display_length:]
        self.curve_ch1_r.setData(timewindow, np.array(window1_r))
        self.curve_ch1_x.setData(timewindow, np.array(window1_x))
        self.curve_ch1_y.setData(timewindow, np.array(window1_y))
        
        # CH2-Error图
        self.curve_ch2_error.setData(timewindow, np.array(window2_error))
        
        # CH2-Feedback图
        self.curve_ch2_feedback.setData(timewindow, np.array(window2_feedback))
        
        # CH2-R/X/Y图
        window2_r = self.full_data2R[-self.display_length:]
        window2_x = self.full_data2X[-self.display_length:]
        window2_y = self.full_data2Y[-self.display_length:]
        self.curve_ch2_r.setData(timewindow, np.array(window2_r))
        self.curve_ch2_x.setData(timewindow, np.array(window2_x))
        self.curve_ch2_y.setData(timewindow, np.array(window2_y))


    def on_mouse_moved(self, pos, plot):
        vb = plot.getViewBox()
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        self.label_coord.setText(f"X: {x:.1f}, Y: {y:.6f}")

    def save_data(self, ui_mode=False):
        """保存PID数据"""
        path = self.vm.model.save_dir + gettimestr() + '_pid_data.csv'
        ch1_latest_feedback, ch2_latest_feedbck = 0, 0
        if path:
            arr = np.column_stack((
                self.full_mac_time, self.full_time_data,
                self.full_data1R, self.full_data1X, self.full_data1Y, self.full_data1Error, self.full_data1Feedback,
                self.full_data2R, self.full_data2X, self.full_data2Y, self.full_data2Error, self.full_data2Feedback,
                self.full_dataFluoDC, self.full_dataLaserDC
            ))
            if len(self.full_data1Feedback) > 0:
                ch1_latest_feedback = self.full_data1Feedback[-1]
            if len(self.full_data2Feedback) > 0:
                ch2_latest_feedback = self.full_data2Feedback[-1]
            np.savetxt(path, arr, delimiter=",",
                      header=f"%采样率={self.parent.param_config['lockin_sample_rate']['value']}Hz\n"
                            f"%等效旋磁比：{self.parent.param_config['nv_eff_gyromagnetic_ratio']['value']}Hz/T\n"
                            f"%CH1初始反馈频率：{self.ch1_init_feedback_freq.text()}MHz\n"
                            f"%CH2初始反馈频率：{self.ch2_init_feedback_freq.text()}MHz\n"
                            f"%PID运算抽取率：{self.parent.param_config['lockin_pid_ex_ratio']['value']}\n"
                            f"%PID读回抽取率：{self.parent.param_config['lockin_pid_rd_ratio']['value']}\n"
                            f"%PID模式数据格式：机器时间戳(s), 计算时间戳(s), "
                            f"%CH1-R(V), CH1-X(V), CH1-Y(V), CH1-Error(V), CH1-Feedback(Hz), "
                            f"%CH2-R(V), CH2-X(V), CH2-Y(V), CH2-Error(V), CH2-Feedback(Hz), "
                            f"%Fluo-DC(V), Laser-DC(V)",
                      comments='% ')
            self.flush_buffer()
            if ui_mode:
                QMessageBox.information(self, "保存成功", f"PID模式数据已保存为 {path}")
            logging.info(f"保存成功，PID模式数据已保存为 {path}\n"
                         f"CH1当前反馈频率：{ch1_latest_feedback/1e6:.3f}MHz\n"
                         f"CH2当前反馈频率：{ch2_latest_feedback/1e6:.3f}MHz")

    def save_image(self):
        """保存图像"""
        time_str = gettimestr()
        path_ch1_error = self.save_dir + time_str + '_pid_ch1_error.png'
        path_ch1_feedback = self.save_dir + time_str + '_pid_ch1_feedback.png'
        path_ch1_rxy = self.save_dir + time_str + '_pid_ch1_rxy.png'
        path_ch2_error = self.save_dir + time_str + '_pid_ch2_error.png'
        path_ch2_feedback = self.save_dir + time_str + '_pid_ch2_feedback.png'
        path_ch2_rxy = self.save_dir + time_str + '_pid_ch2_rxy.png'
        
        exporter_ch1_error = ImageExporter(self.plot_ch1_error.plotItem)
        exporter_ch1_feedback = ImageExporter(self.plot_ch1_feedback.plotItem)
        exporter_ch1_rxy = ImageExporter(self.plot_ch1_rxy.plotItem)
        exporter_ch2_error = ImageExporter(self.plot_ch2_error.plotItem)
        exporter_ch2_feedback = ImageExporter(self.plot_ch2_feedback.plotItem)
        exporter_ch2_rxy = ImageExporter(self.plot_ch2_rxy.plotItem)
        
        exporter_ch1_error.export(path_ch1_error)
        exporter_ch1_feedback.export(path_ch1_feedback)
        exporter_ch1_rxy.export(path_ch1_rxy)
        exporter_ch2_error.export(path_ch2_error)
        exporter_ch2_feedback.export(path_ch2_feedback)
        exporter_ch2_rxy.export(path_ch2_rxy)

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()
