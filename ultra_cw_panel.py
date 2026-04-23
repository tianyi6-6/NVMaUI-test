# encoding=utf-8
import time
import numpy as np
import PySide6.QtGui as QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QCheckBox, QComboBox, QDateTimeEdit
)
from PySide6.QtCore import QDateTime, QTimer
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from manager import *
from General import *
from scipy.stats import linregress


# ----------------- Model -----------------
class OscilloscopeAllOpticalCWModel(QObject):
    # data_updated = Signal(np.ndarray)
    data_updated = Signal(np.float64,  np.float64,  np.float64)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.main_ui = self.parent.parent.parent
        self.dev = self.parent.parent.parent.dev
        self.running = False

    def get_all_optical_cw_params(self):
        start_motor_angle = float(self.parent.parent.start_motor_angle_input.text())
        stop_motor_angle = float(self.parent.parent.end_motor_angle_input.text())
        step_motor_angle = float(self.parent.parent.step_motor_angle_input.text())
        return start_motor_angle, stop_motor_angle, step_motor_angle

    def start(self):
        self.running = True
        # init_start_time = time.time()
        speed = 100
        # todo: 替换为分条件采集
        start_motor_angle, stop_motor_angle, step_motor_angle = self.get_all_optical_cw_params()

        current_motor_angle = start_motor_angle
        motor_angle_list = []
        fluo_dc_list = []
        laser_dc_list = []
        while self.running and current_motor_angle <= stop_motor_angle:
            # motor_angle_list.append(current_motor_angle)

            current_angle = self.parent.parent.parent.ultramotor.get_angle()

            forward_angle = (current_angle - current_motor_angle) % 360
            logging.info(f"当前角度：{current_angle}, 目标角度：{current_motor_angle}, 判断正转所需：{forward_angle}")

            motor_direction_flag = forward_angle > 180
            self.parent.parent.parent.ultramotor.rotate_motor(speed, current_motor_angle, direction=motor_direction_flag)

            while self.parent.parent.parent.ultramotor.is_run():
                time.sleep(0.01)
            real_motor_angle = self.parent.parent.parent.ultramotor.get_angle()
            motor_angle_list.append(real_motor_angle)
            auxdaq_data = self.parent.parent.parent.dev.auxDAQ_play(data_num=50)
            fluo_dc = np.mean(auxdaq_data[0])
            laser_dc = np.mean(auxdaq_data[1])
            fluo_dc_list.append(fluo_dc)
            laser_dc_list.append(laser_dc)

            logging.info(f'设置角度：{current_motor_angle}° 测量角度：{real_motor_angle}°')
            self.data_updated.emit(real_motor_angle, fluo_dc, laser_dc)
            current_motor_angle += step_motor_angle
            # QThread.sleep(self.acq_interval)

        logging.info(f"结束全光谱数据采集。荧光最高点角度：{fluo_dc_list.index(max(fluo_dc_list))} °\n"
                     f"荧光最高点值：{max(fluo_dc_list) * 1000} mV")
        # self.parent.parent.on_start_button_clicked()
        self.stop()


    def stop(self):
        logging.info("结束全光荧光数据采集。")
        self.running = False


# ----------------- ViewModel -----------------
class OscilloscopeAllOpticalCWViewModel(QObject):
    data_ready = Signal(np.float64, np.float64, np.float64)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = OscilloscopeAllOpticalCWModel(self)
        self.thread = QThread()
        self.model.moveToThread(self.thread)

        self.thread.started.connect(self.model.start)
        self.model.data_updated.connect(self.data_ready)
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
class OscilloscopeAllOpticalCWPanel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        if hasattr(self.parent, 'save_dir_all_optical_cw'):
            self.save_dir = self.parent.save_dir_cw
        else:
            self.save_dir = './'
        self.setWindowTitle("全光荧光数据采集")
        self.resize(1000, 600)

        self.state_manager = parent.state_manager
        self.state_manager.state_changed.connect(self.on_state_changed)

        self.vm = OscilloscopeAllOpticalCWViewModel(self)
        self.vm.data_ready.connect(self.update_display)

        self.motor_angle = []
        self.fluo_dc = []
        self.laser_dc = []

        self.init_ui()

    def on_state_changed(self, state):
        if state == DevState.OFFLINE:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        elif state == DevState.IDLE:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
        elif state == DevState.EXP_RUNNING:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
        elif state == DevState.EXP_RUNNING:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        else:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)

    def flush_buffer(self):
        self.motor_angle = []
        self.fluo_dc = []
        self.laser_dc = []

    def init_ui(self):
        layout = QVBoxLayout()
        control_layout = QHBoxLayout()

        # 基本开始/结束采集功能
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

        # 扫描参数设置
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("起始角度(°):"))
        self.start_motor_angle_input = QLineEdit()
        self.start_motor_angle_input.setText('0.1')
        self.start_motor_angle_input.setFixedWidth(100)
        freq_layout.addWidget(self.start_motor_angle_input)

        freq_layout.addWidget(QLabel("结束角度(°):"))
        self.end_motor_angle_input = QLineEdit()
        self.end_motor_angle_input.setText('359.9')
        self.end_motor_angle_input.setFixedWidth(100)
        freq_layout.addWidget(self.end_motor_angle_input)

        freq_layout.addWidget(QLabel("步进角度(°):"))
        self.step_motor_angle_input = QLineEdit()
        self.step_motor_angle_input.setText('2')
        self.step_motor_angle_input.setFixedWidth(100)
        freq_layout.addWidget(self.step_motor_angle_input)

        control_layout.addLayout(freq_layout)

        layout.addLayout(control_layout)

        self.label_coord = QLabel("X: -- , Y: --")
        layout.addWidget(self.label_coord)

        # 时域图 CH1 & CH2
        self.plot_ch1 = pg.PlotWidget(title="CH1 荧光路 直流信号")
        self.plot_ch1.showGrid(x=True, y=True)
        self.plot_ch2 = pg.PlotWidget(title="CH2 激光路 直流信号")
        self.plot_ch2.showGrid(x=True, y=True)

        self.plot_ch1.setLabel("left", "Voltage", units="V")
        self.plot_ch1.setLabel("bottom", "Motor Angle", units="°")

        self.plot_ch2.setLabel("left", "Voltage", units="V")
        self.plot_ch2.setLabel("bottom", "Motor Angle", units="°")

        self.curve_ch1 = self.plot_ch1.plot(pen='b')
        self.curve_ch2 = self.plot_ch2.plot(pen='y')

        # 添加可拖动的span
        # self.span_ch1 = pg.LinearRegionItem()
        # self.span_ch1.setZValue(10)
        # self.plot_ch1.addItem(self.span_ch1)

        # self.span_ch2 = pg.LinearRegionItem()
        # self.span_ch2.setZValue(10)
        # self.plot_ch2.addItem(self.span_ch2)

        self.plot_ch1.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch1))
        self.plot_ch2.scene().sigMouseMoved.connect(lambda pos: self.on_mouse_moved(pos, self.plot_ch2))

        layout.addWidget(self.plot_ch1)
        layout.addWidget(self.plot_ch2)

        self.setLayout(layout)

    def get_start_time(self):
        '''
        获取定时开始时间，单位为秒
        '''
        return self.scheduled_time.dateTime().toSecsSinceEpoch()

    def on_start_button_clicked(self):
        state = self.state_manager.current_state()
        if state == DevState.EXP_RUNNING:
            self.save_data()
            self.start_btn.setText("开始采集")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()
        elif state == DevState.IDLE:
            self.init_start_time = time.time()
            self.flush_buffer()
            self.start_btn.setText("停止采集")
            self.state_manager.set_state(DevState.EXP_RUNNING)
            self.vm.start()

    def update_display(self, motor_angle, fluo_dc, laser_dc):
        self.motor_angle.append(motor_angle)
        self.fluo_dc.append(fluo_dc)
        self.laser_dc.append(laser_dc)

        self.curve_ch1.setData(self.motor_angle, self.fluo_dc)
        self.curve_ch2.setData(self.motor_angle, self.laser_dc)

        # 统计量
        # max_val1 = np.max(self.ch1_x)
        # min_val1 = np.min(self.ch1_x)
        #
        # max_val2 = np.max(self.ch2_x)
        # min_val2 = np.min(self.ch2_x)

    def on_mouse_moved(self, pos, plot):
        vb = plot.getViewBox()
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        self.label_coord.setText(f"X: {x:.1f}, Y: {y:.3f}")

    def save_data(self):
        # path, _ = QFileDialog.getSaveFileName(self, "保存数据", "osc_data.csv", "CSV Files (*.csv)")
        path = self.parent.save_dir + gettimestr() + '_all_optical_cw.csv'
        if path:
            arr = np.column_stack((self.motor_angle, self.fluo_dc))
            np.savetxt(path, arr, delimiter=",",
                       header=f"%Motor Angle (°), Fluo DC (V)\n",
                       comments='% ')
            QMessageBox.information(self, "保存成功", f"全光荧光数据已保存为 {path}")

    def save_image(self):
        time_str = gettimestr()
        path_ch1 = self.save_dir + time_str + '_all_optical_cw_ch1.png'
        path_ch2 = self.save_dir + time_str + '_all_optical_cw_ch2.png'
        # path, _ = QFileDialog.getSaveFileName(self, "保存图像", "plot.png", "PNG Files (*.png)")
        exporter_ch1 = ImageExporter(self.plot_ch1.plotItem)
        exporter_ch2 = ImageExporter(self.plot_ch2.plotItem)
        exporter_ch1.export(path_ch1)
        exporter_ch2.export(path_ch2)

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()
