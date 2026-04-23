# encoding=utf-8
import time
import traceback

import numpy as np
import PySide6.QtGui as QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QCheckBox, QComboBox, QDateTimeEdit,
    QGroupBox
)
from PySide6.QtCore import QDateTime, QTimer, Qt
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from manager import *
from General import *
from scipy.stats import linregress
from scipy.interpolate import interp1d
from data_process_tools import *

# ----------------- Model -----------------
class LaserPhaseOptimizationModel(QObject):
    data_updated = Signal(np.float64, np.float64, np.float64, np.float64, np.float64)
    measurement_finished = Signal()  # 添加测量完成信号

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.main_ui = self.parent.parent.parent
        self.dev = self.parent.parent.parent.dev
        self.ch1_init_freq = None
        self.running = False

    def get_phase_params(self):
        start_phase = float(self.parent.parent.start_phase_input.text())  # 度
        stop_phase = float(self.parent.parent.end_phase_input.text())  # 度
        step_phase = float(self.parent.parent.step_phase_input.text())  # 度
        return start_phase, stop_phase, step_phase

    def cal_phase_angle(self, x, y):
        r = np.sqrt(np.array(x) ** 2 + np.array(y) ** 2)
        r_max_id = np.argmax(r)
        return np.rad2deg(np.arctan2(y[r_max_id], x[r_max_id]))

    def start(self):
        self.running = True
        start_phase, stop_phase, step_phase = self.get_phase_params()
        current_phase = start_phase
        
        phase_list = []

        raw_noise_ch1 = []
        opt_noise_ch1 = []

        raw_noise_ch2 = []
        opt_noise_ch2 = []

        # iir_1x_list = []
        # iir_1y_list = []
        # iir_2x_list = []
        # iir_2y_list = []

        # iir_1x_laser_list = []
        # iir_1y_laser_list = []
        # iir_2x_laser_list = []
        # iir_2y_laser_list = []

        noise_analysis_time = int(self.parent.parent.noise_analysis_time_input.text())
        sample_rate = self.main_ui.param_config["lockin_sample_rate"]["value"]
        single_point_num = int(noise_analysis_time * sample_rate)

        # 保存初始微波参数
        self.ch1_init_freq = self.main_ui.param_config["mw_ch1_freq"]["value"]
        self.ch2_init_freq = self.main_ui.param_config["mw_ch2_freq"]["value"]
        self.ch1_init_fm_sens = self.main_ui.param_config["mw_ch1_fm_sens"]["value"]
        self.ch2_init_fm_sens = self.main_ui.param_config["mw_ch2_fm_sens"]["value"]
        self.ch1_init_power = self.main_ui.param_config["mw_ch1_power"]["value"]
        self.ch2_init_power = self.main_ui.param_config["mw_ch2_power"]["value"]
        self.ch2_init_demod_phase1 = self.main_ui.param_config["lockin_ch2_demod_phase1"]["value"]
        self.ch2_init_demod_phase2 = self.main_ui.param_config["lockin_ch2_demod_phase2"]["value"]

        # 将微波设置到非共振点
        logging.info("将微波设置到非共振点进行激光相位优化")
        self.main_ui.set_param(name="mw_ch1_fm_sens", value=0, ui_flag=False, delay_flag=False)
        self.main_ui.set_param(name="mw_ch2_fm_sens", value=0, ui_flag=False, delay_flag=False)
        self.main_ui.set_param(name="mw_ch1_freq", value=2.6e9, ui_flag=False, delay_flag=False)
        self.main_ui.set_param(name="mw_ch2_freq", value=2.6e9, ui_flag=False, delay_flag=False)

        while self.running and current_phase <= stop_phase:
            phase_list.append(current_phase)
            
            # 设置激光相位（这里需要根据实际的激光相位控制接口进行调整）
            self.main_ui.set_param(name="lockin_ch2_demod_phase1", value=current_phase, ui_flag=False, delay_flag=False)
            self.main_ui.set_param(name="lockin_ch2_demod_phase2", value=current_phase, ui_flag=False, delay_flag=False)
            
            # 采集数据
            iir_data = self.parent.parent.parent.dev.IIR_play(data_num=single_point_num)
            
            # 计算参考路相消后的噪声水平（使用X通道作为噪声水平）
            iir_1x = iir_data[1]
            # iir_1y = iir_data[2]
            iir_2x = iir_data[7]
            # iir_2y = iir_data[8]

            iir_1x_laser = iir_data[4]
            # iir_1y_laser = iir_data[5]

            iir_2x_laser = iir_data[10]
            # iir_2y_laser = iir_data[11]

            _,  opt_noise_1, raw_noise_1 = get_optimize_coe(iir_1x, iir_1x_laser)
            _, opt_noise_2, raw_noise_2 = get_optimize_coe(iir_2x, iir_2x_laser)

            raw_noise_ch1.append(raw_noise_1)
            raw_noise_ch2.append(raw_noise_2)
            opt_noise_ch1.append(opt_noise_1)
            opt_noise_ch2.append(opt_noise_2)


            self.data_updated.emit(current_phase, raw_noise_1, opt_noise_1, raw_noise_2, opt_noise_2)
            current_phase += step_phase

        # 计算最优相位
        if len(phase_list) > 0:
            # 找到噪声最小的相位点
            min_noise_idx_ch1 = np.argmin(np.abs(opt_noise_ch1))
            min_noise_idx_ch2 = np.argmin(np.abs(opt_noise_ch2))
            
            optimal_phase_ch1 = phase_list[min_noise_idx_ch1]
            optimal_phase_ch2 = phase_list[min_noise_idx_ch2]
            
            logging.info(f"CH1 最优激光相位：{optimal_phase_ch1:.2f}° 对应噪声水平：{opt_noise_ch1[min_noise_idx_ch1]:.6f}V 相消倍率：{raw_noise_ch1[min_noise_idx_ch1] / opt_noise_ch1[min_noise_idx_ch1]:.3f}")
            logging.info(f"CH2 最优激光相位：{optimal_phase_ch2:.2f}° 对应噪声水平：{opt_noise_ch2[min_noise_idx_ch2]:.6f}V 相消倍率：{raw_noise_ch2[min_noise_idx_ch2] / opt_noise_ch2[min_noise_idx_ch2]:.3f}")
        
        # 发送测量完成信号
        self.measurement_finished.emit()
        self.stop()

    def stop(self):
        logging.info("结束激光相位优化测量。")
        self.running = False


# ----------------- ViewModel -----------------
class LaserPhaseOptimizationViewModel(QObject):
    data_ready = Signal(np.float64, np.float64, np.float64, np.float64, np.float64)
    measurement_completed = Signal()  # 添加测量完成信号

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = LaserPhaseOptimizationModel(self)
        self.thread = QThread()
        self.model.moveToThread(self.thread)

        self.thread.started.connect(self.model.start)
        self.model.data_updated.connect(self.data_ready)
        self.model.measurement_finished.connect(self.measurement_completed)  # 连接测量完成信号
        self.start_time = None

    def get_start_time(self):
        return self.start_time

    def start(self):
        if not self.thread.isRunning():
            self.thread.start()

    def stop(self):
        self.model.stop()
        self.thread.quit()
        self.thread.wait()

    def change_sample_rate(self, rate):
        self.model.set_sample_rate(rate)

# ----------------- View -----------------
class LaserPhaseOptimizationPanel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        if hasattr(self.parent, 'save_dir_laser_phase'):
            self.save_dir = self.parent.save_dir_laser_phase
        else:
            self.save_dir = './'
        self.setWindowTitle("激光相位优化")
        self.resize(1000, 600)

        self.state_manager = parent.state_manager
        self.state_manager.state_changed.connect(self.on_state_changed)

        self.vm = LaserPhaseOptimizationViewModel(self)
        self.vm.data_ready.connect(self.update_display)
        self.vm.measurement_completed.connect(self.on_measurement_completed)  # 连接测量完成信号

        self.phase_angles = []
        self.ch1_noise = []
        self.ch1_y = []
        self.ch2_noise = []
        self.ch2_y = []

        self.init_ui()

    def on_state_changed(self, state):
        if state == DevState.OFFLINE:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        elif state == DevState.IDLE:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
        elif state == DevState.EXP_RUNNING:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        else:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)

    def flush_buffer(self):
        self.phase_angles = []
        self.ch1_noise = []
        self.ch1_y = []
        self.ch2_noise = []
        self.ch2_y = []

    def init_ui(self):
        layout = QVBoxLayout()
        control_layout = QHBoxLayout()

        # 基本开始/结束采集功能
        self.start_btn = QPushButton("开始优化")
        self.save_btn = QPushButton("保存数据")
        self.clear_btn = QPushButton("清空数据")

        self.start_btn.clicked.connect(self.on_start_button_clicked)
        self.clear_btn.clicked.connect(self.flush_buffer)
        self.save_btn.clicked.connect(self.save_data)
        self.save_btn.clicked.connect(self.save_image)

        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.save_btn)
        control_layout.addWidget(self.clear_btn)

        # 相位扫描参数设置
        phase_layout = QHBoxLayout()

        phase_layout.addWidget(QLabel("起始相位(度):"))
        self.start_phase_input = QLineEdit()
        self.start_phase_input.setText('0')
        self.start_phase_input.setFixedWidth(100)
        phase_layout.addWidget(self.start_phase_input)

        phase_layout.addWidget(QLabel("结束相位(度):"))
        self.end_phase_input = QLineEdit()
        self.end_phase_input.setText('360')
        self.end_phase_input.setFixedWidth(100)
        phase_layout.addWidget(self.end_phase_input)

        phase_layout.addWidget(QLabel("步进相位(度):"))
        self.step_phase_input = QLineEdit()
        self.step_phase_input.setText('5')
        self.step_phase_input.setFixedWidth(100)
        phase_layout.addWidget(self.step_phase_input)

        # 噪声分析时间长度
        self.noise_analysis_time_input = QLineEdit()
        self.noise_analysis_time_input.setText('10')
        self.noise_analysis_time_input.setFixedWidth(100)
        phase_layout.addWidget(QLabel("噪声分析时间长度(s):"))
        phase_layout.addWidget(self.noise_analysis_time_input)  

        control_layout.addLayout(phase_layout)
        layout.addLayout(control_layout)

        self.label_coord = QLabel("X: -- , Y: --")
        layout.addWidget(self.label_coord)

        # 相位优化图 CH1 & CH2
        self.plot_ch1 = pg.PlotWidget(title="CH1 激光相位优化相消")
        self.plot_ch1.showGrid(x=True, y=True)
        self.plot_ch2 = pg.PlotWidget(title="CH2 激光相位优化相消")
        self.plot_ch2.showGrid(x=True, y=True)

        self.plot_ch1.setLabel("left", "噪声水平", units="V")
        self.plot_ch1.setLabel("bottom", "激光相位", units="度")

        self.plot_ch2.setLabel("left", "噪声水平", units="V")
        self.plot_ch2.setLabel("bottom", "激光相位", units="度")

        # 添加legend
        self.plot_ch1.addLegend()
        self.plot_ch2.addLegend()

        self.curve_ch1 = self.plot_ch1.plot(pen='b', name='CH1-相消前-噪声水平')
        self.curve_ch3 = self.plot_ch1.plot(pen='r', name='CH1-相消后-噪声水平')

        self.curve_ch2 = self.plot_ch2.plot(pen='y', name='CH2-相消前-噪声水平')
        self.curve_ch4 = self.plot_ch2.plot(pen='g', name='CH2-相消后-噪声水平')

        self.plot_ch1.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch1))
        self.plot_ch2.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch2))

        layout.addWidget(self.plot_ch1)
        layout.addWidget(self.plot_ch2)

        self.setLayout(layout)

    def on_start_button_clicked(self):
        state = self.state_manager.current_state()
        if state == DevState.EXP_RUNNING:
            self.start_btn.setText("开始优化")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()
        elif state == DevState.IDLE:
            self.init_start_time = time.time()
            self.flush_buffer()
            self.start_btn.setText("停止优化")
            self.state_manager.set_state(DevState.EXP_RUNNING)
            self.vm.start()

    def on_measurement_completed(self):
        """测量完成时的回调函数，在主线程中执行"""
        self.start_btn.setText("开始优化")
        self.state_manager.set_state(DevState.IDLE)
        self.vm.stop()
        self.save_data()
        self.reset_mw_params()

    def reset_mw_params(self):
        # 恢复微波参数到初始值
        logging.info("恢复微波参数到初始值")
        self.parent.set_param(name="mw_ch1_freq", value=self.vm.model.ch1_init_freq, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch2_freq", value=self.vm.model.ch2_init_freq, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch1_fm_sens", value=self.vm.model.ch1_init_fm_sens, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch2_fm_sens", value=self.vm.model.ch2_init_fm_sens, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch1_power", value=self.vm.model.ch1_init_power, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch2_power", value=self.vm.model.ch2_init_power, ui_flag=True, delay_flag=False)
        logging.info("恢复激光解调相位到初始值")
        self.parent.set_param(name="lockin_ch2_demod_phase1", value=self.vm.model.ch2_init_demod_phase1, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="lockin_ch2_demod_phase2", value=self.vm.model.ch2_init_demod_phase2, ui_flag=True, delay_flag=False)

    def update_display(self, phase, iir_1x, iir_1y, iir_2x, iir_2y):
        self.phase_angles.append(phase)
        self.ch1_noise.append(iir_1x)
        self.ch1_y.append(iir_1y)
        self.ch2_noise.append(iir_2x)
        self.ch2_y.append(iir_2y)

        self.curve_ch1.setData(self.phase_angles, self.ch1_noise)
        self.curve_ch2.setData(self.phase_angles, self.ch2_noise)
        self.curve_ch3.setData(self.phase_angles, self.ch1_y)
        self.curve_ch4.setData(self.phase_angles, self.ch2_y)

    def on_mouse_moved(self, pos, plot):
        vb = plot.getViewBox()
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        self.label_coord.setText(f"X: {x:.1f}°, Y: {y:.6f}V")

    def save_data(self):
        path = self.save_dir + gettimestr() + '_laser_phase_optimization.csv'
        if path:
            arr = np.column_stack((self.phase_angles, self.ch1_noise, self.ch1_y, self.ch2_noise, self.ch2_y))
            np.savetxt(path, arr, delimiter=",",
                       header=f"%激光相位优化数据\n"
                              f"%单点采集时长={float(self.noise_analysis_time_input.text())}s\n"
                              f"%激光器电流={self.parent.param_config['laser_power']['value']} A\n"
                              f"%荧光CH1解调相位：{self.parent.param_config['lockin_ch1_demod_phase1']['value']}°\n"
                              f"%荧光CH2解调相位：{self.parent.param_config['lockin_ch1_demod_phase2']['value']}°\n"
                              f"%锁相放大器时间常数：{self.parent.param_config['lockin_tc']['value']}s\n"
                              f"%锁相放大器CH1调制频率：{self.parent.param_config['lockin_modu_freq1']['value']}Hz\n"
                              f"%锁相放大器CH2调制频率：{self.parent.param_config['lockin_modu_freq2']['value']}Hz\n"
                              f"%锁相放大器采样率：{self.parent.param_config['lockin_sample_rate']['value']}Hz\n"
                              f"%扫描激光解调相位(度), CH1-X-降噪前噪声水平(V), CH1-X-降噪后噪声水平(V), CH2-X-降噪前噪声水平(V), CH2-X-降噪后噪声水平(V)\n",
                       comments='% ')
            self.parent.save_exp_config(self.save_dir)
            self.save_image()
            QMessageBox.information(self, "保存成功", f"激光相位优化数据已保存为 {path}")

    def save_image(self):
        time_str = gettimestr()
        path_ch1 = self.save_dir + time_str + '_laser_phase_ch1.png'
        path_ch2 = self.save_dir + time_str + '_laser_phase_ch2.png'
        exporter_ch1 = ImageExporter(self.plot_ch1.plotItem)
        exporter_ch2 = ImageExporter(self.plot_ch2.plotItem)
        exporter_ch1.export(path_ch1)
        exporter_ch2.export(path_ch2)

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()
