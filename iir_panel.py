# encoding=utf-8
import time
import numpy as np
import PySide6.QtGui as QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox,QCheckBox,QComboBox,QDateTimeEdit
)
from PySide6.QtCore import QDateTime, QTimer
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from manager import *
from General import *



# ----------------- Model -----------------
class OscilloscopeIIRModel(QObject):
    # data_updated = Signal(np.ndarray)
    data_updated = Signal(np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.running = False
        self.sample_rate = self.parent.parent.parent.param_config["lockin_sample_rate"]['value']
        self.sample_interval = 1 / self.sample_rate
        self.acq_time = 0.5 # 采集时长，单位为秒

    
    def start(self):
        logging.info("定时计时到达，准备开始进行IIR模式数据采集。")
        self.running = True
        # init_start_time = time.time()
        init_start_time = self.parent.get_start_time()
        N = 0
        # todo: 替换为分条件采集
        self.parent.parent.parent.dev.start_infinite_iir_acq() # 开始无限采集模式
        while self.running:
            # todo: 加入模拟采集数据，以及采样率、深度更新设置
            # data1 = np.random.normal(size=self.acq_pts)
            # data2 = np.random.normal(size=self.acq_pts) * 0.5
            try:
                iir_data = self.parent.parent.parent.dev.get_infinite_iir_points(data_num=int(self.sample_rate * self.acq_time))
            except:
                self.parent.stop()
                break
            # print('[CH1-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[1]), np.mean(IIR_data[1])))
            # print('[CH1-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[2]), np.mean(IIR_data[2])))
            # print('[CH1-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[7]), np.mean(IIR_data[7])))
            # print('[CH1-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[8]), np.mean(IIR_data[8])))

            # print('[CH2-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[4]), np.mean(IIR_data[4])))
            # print('[CH2-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[5]), np.mean(IIR_data[5])))
            # print('[CH2-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[10]), np.mean(IIR_data[10])))
            # print('[CH2-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[11]), np.mean(IIR_data[11])))
            data1 = iir_data[1] # Fluo-1X
            data2 = iir_data[7] # Fluo-2X
            N_new = len(data1)

            time_data = np.linspace(init_start_time + N * self.sample_interval, 
                                    init_start_time + (N + N_new) * self.sample_interval, 
                                    len(data1), 
                                    endpoint=False)
            
            N += N_new

            self.data_updated.emit(time_data, data1, data2)
            # QThread.sleep(self.acq_interval)

    def stop(self):
        logging.info("结束IIR模式数据采集。")
        self.parent.parent.parent.dev.stop_infinite_iir_acq()
        self.running = False

    def set_sample_rate(self, rate):
        self.sample_rate = rate
        self.sample_interval = 1.0 / rate

# ----------------- ViewModel -----------------
class OscilloscopeIIRViewModel(QObject):
    data_ready = Signal(np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = OscilloscopeIIRModel(self)
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
                time.sleep(0.001) # 等待定时开始时间
            self.thread.start()

    def stop(self):
        self.model.stop()
        self.thread.quit()
        self.thread.wait()

    def change_sample_rate(self, rate):
        self.model.set_sample_rate(rate)


# ----------------- View -----------------
class OscilloscopeIIRPanel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        if hasattr(self.parent, 'save_dir_iir'):
            self.save_dir = self.parent.save_dir_iir
        else:
            self.save_dir = './'
        self.setWindowTitle("IIR数据采集")
        self.resize(1000, 600)

        self.state_manager = parent.state_manager
        self.state_manager.state_changed.connect(self.on_state_changed)

        self.vm = OscilloscopeIIRViewModel(self)
        self.vm.data_ready.connect(self.update_display)

        self.full_data1 = []  # 无限缓存
        self.full_data2 = []
        self.full_time_data = []

        self.acq_time = 60
        self.display_length = 1000  # 屏幕显示长度（可调）
        self.init_start_time = time.time()
        self.init_ui()

    def on_state_changed(self, state):
        if state == DevState.OFFLINE:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        elif state == DevState.IDLE:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
        elif state == DevState.IIR_RUNNING:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
        elif state == DevState.IIR_RUNNING:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        else:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)

    def flush_buffer(self):
        self.full_data1 = []  # 无限缓存
        self.full_data2 = []
        self.full_time_data = []
        self.init_start_time = time.time()

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

        # 显示切换功能
        # self.unit_mode_checkbox = QCheckBox("显示磁场示值")
        #self.unit_mode_checkbox.stateChanged.connect(self.handle_unit_mode_toggle)
        # control_layout.addWidget(self.unit_mode_checkbox)

        # QCheckBox("启用温度计设备")
        # self.thermometer_device_checkbox.stateChanged.connect(self.handle_thermometer_toggle)

        
        control_layout.addWidget(QLabel("屏幕显示时长（s）:"))
        self.length_input = QLineEdit(str(self.display_length))
        self.length_input.setFixedWidth(100)
        control_layout.addWidget(self.length_input)
        

        # 显示模式选择
        control_layout.addWidget(QLabel("磁场-电压转换系数计算模式:"))
        self.volt_to_mag_mode_combo = QComboBox()
        self.volt_to_mag_mode_combo.addItems(["基于CW谱/等效旋磁比", "基于直接标定系数"])
        self.volt_to_mag_mode_combo.setCurrentIndex(1)  # 默认基于直接标定系数计算
        self.volt_to_mag_mode_combo.currentIndexChanged.connect(self.handle_volt_to_mag_mode_change)
        control_layout.addWidget(self.volt_to_mag_mode_combo)

         # 显示模式选择
        control_layout.addWidget(QLabel("磁场/电压显示模式:"))
        self.volt_or_mag_view_mode_combo = QComboBox()
        self.volt_or_mag_view_mode_combo.addItems(["显示电压", "显示磁场"])
        self.volt_or_mag_view_mode_combo.setCurrentIndex(0)  # 默认基于CW谱计算
        control_layout.addWidget(self.volt_or_mag_view_mode_combo)


        layout.addLayout(control_layout)

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

     

        # 采集时长选择
        acq_layout.addWidget(QLabel("采集时长（秒）:"))
        self.acq_time_input = QLineEdit(str(self.acq_time))
        self.acq_time_input.setFixedWidth(60)
        self.acq_time_input.setValidator(QtGui.QIntValidator(1, 1000000))
        acq_layout.addWidget(self.acq_time_input)

        layout.addLayout(acq_layout)


        self.stats_label = QLabel("CH1最大值: --   CH1最小值: --   CH1均值: --\n"
                                  "CH2最大值: --   CH2最小值: --   CH2均值: --")
        layout.addWidget(self.stats_label)

        self.label_coord = QLabel("X: -- , Y: --")
        layout.addWidget(self.label_coord)

        # 时域图 CH1 & CH2
        self.plot_ch1 = pg.PlotWidget(title="CH1 IIR通道时域波形")
        self.plot_ch1.showGrid(x=True, y=True)
        self.plot_ch2 = pg.PlotWidget(title="CH2 IIR通道时域波形")
        self.plot_ch2.showGrid(x=True, y=True)

        self.plot_ch1.setLabel("left", "Voltage", units="V")
        self.plot_ch1.setLabel("bottom", "Time", units="s")

        self.plot_ch2.setLabel("left", "Voltage", units="V")
        self.plot_ch2.setLabel("bottom", "Time", units="s")

        self.curve_ch1 = self.plot_ch1.plot(pen='b')
        self.curve_ch2 = self.plot_ch2.plot(pen='y')

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
    
    def handle_volt_to_mag_mode_change(self):
        if self.volt_to_mag_mode_combo.currentIndex() == 0:
            self.mag_mode_flag = 0 # 基于CW谱/等效旋磁比
        else:
            self.mag_mode_flag = 1 # 基于直接标定系数

    def handle_unit_mode_toggle(self):
        pass

    def on_start_button_clicked(self):
        state = self.state_manager.current_state()
        if state == DevState.IIR_RUNNING:
            self.start_btn.setText("开始采集")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()
        elif state == DevState.IDLE:
            self.init_start_time = time.time()
            # self.flush_buffer()
            self.start_btn.setText("停止采集")
            self.state_manager.set_state(DevState.IIR_RUNNING)
            self.vm.start()

    def update_display_length(self):
        val = int(self.length_input.text())
        self.display_length = val

    def update_display(self, time_data, data1, data2):
        self.full_data1.extend(data1)
        self.full_data2.extend(data2)
        self.full_time_data.extend(time_data.tolist())

        try:
            # print('显示长度：', self.display_length)
            self.display_length = int(float(self.length_input.text()) * self.parent.param_config['lockin_sample_rate']['value'])
        except:
            pass

        # 裁剪显示窗口数据
        timewindow = np.array(self.full_time_data[-self.display_length:]) - self.init_start_time

        conversion_coe = 1 # 默认，1：1转换
        view_mode = self.volt_or_mag_view_mode_combo.currentIndex() # 0=显示电压，1=显示磁场
        if view_mode == 1:
            self.plot_ch1.setLabel("left", "磁场", units="T")
            self.plot_ch1.setLabel("bottom", "时间", units="s")

            self.plot_ch2.setLabel("left", "磁场", units="V")
            self.plot_ch2.setLabel("bottom", "时间", units="s")
            mag_conversion_mode = self.volt_to_mag_mode_combo.currentIndex() # 0=基于CW谱/等效旋磁比，1=基于直接标定系数
            if mag_conversion_mode == 0:
                conversion_coe = 1 / (self.parent.param_config['nv_eff_gyromagnetic_ratio']['value'] * self.parent.param_config['nv_cw_slope']['value'])
            else:
                conversion_coe = self.parent.param_config['nv_volt_to_tesla_coe']['value']
        else:
            self.plot_ch1.setLabel("left", "电压", units="V")
            self.plot_ch1.setLabel("bottom", "时间", units="s")

            self.plot_ch2.setLabel("left", "电压", units="V")
            self.plot_ch2.setLabel("bottom", "时间", units="s")
            conversion_coe = 1

        window1 = self.full_data1[-self.display_length:]
        window2 = self.full_data2[-self.display_length:]

        # print(f"数据显示长度：{self.display_length}, data1长度：{len(self.full_data1)}, data2长度：{len(self.full_data2)}, 时间长度：{len(timewindow)}")
        self.curve_ch1.setData(timewindow, np.array(window1) * conversion_coe)
        self.curve_ch2.setData(timewindow, np.array(window2) * conversion_coe)

        # if len(window1) >= 50 * 7200:
        #     logging.info(f"容量达到缓存区上限，保存并清空数据，避免占用数据采集进程计算资源：")
        #     self.save_data()
        #     self.flush_buffer()
        # 统计量
        # max_val1 = np.max(window1)
        # min_val1 = np.min(window1)
        # mean_val1 = np.mean(window1)
        #
        # max_val2 = np.max(window2)
        # min_val2 = np.min(window2)
        # mean_val2 = np.mean(window2)
        # self.stats_label.setText(f"CH1最大值: {max_val1:.4f}  CH1最小值: {min_val1:.4f}  CH1均值: {mean_val1:.4f}\n"
        #                          f"CH2最大值: {max_val2:.4f}  CH2最小值: {min_val2:.4f}  CH2均值: {mean_val2:.4f}\n")

    def on_mouse_moved(self, pos, plot):
        vb = plot.getViewBox()
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        self.label_coord.setText(f"X: {x:.1f}, Y: {y:.3f}")

    def save_data(self):
        # path, _ = QFileDialog.getSaveFileName(self, "保存数据", "osc_data.csv", "CSV Files (*.csv)")
        path = self.parent.save_dir + gettimestr() + '_iir_noise.csv'
        if path:
            arr = np.column_stack((self.full_time_data, self.full_data1, self.full_data2))
            np.savetxt(path, arr, delimiter=",")
            QMessageBox.information(self, "保存成功", f"IIR模式数据已保存为 {path}")

    def save_image(self):
        time_str = gettimestr()
        path_ch1 = self.save_dir + time_str + '_iir_ch1.png'
        path_ch2 = self.save_dir + time_str + '_iir_ch2.png'
        # path, _ = QFileDialog.getSaveFileName(self, "保存图像", "plot.png", "PNG Files (*.png)")
        exporter_ch1 = ImageExporter(self.plot_ch1.plotItem)
        exporter_ch2 = ImageExporter(self.plot_ch2.plotItem)
        exporter_ch1.export(path_ch1)
        exporter_ch2.export(path_ch2)

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()
