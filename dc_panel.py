# encoding=utf-8
import time
import numpy as np
import PySide6.QtGui as QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox,QComboBox,QCheckBox,
)
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from manager import *
from General import *


# ----------------- Model -----------------
class OscilloscopeDCModel(QObject):
    # data_updated = Signal(np.ndarray)
    data_updated = Signal(np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, parent, buffer_size=1024):
        super().__init__()
        self.parent = parent
        self.running = False
        self.sample_rate = 125
        self.acq_interval = 1
        self.sample_interval = 1.0 / self.sample_rate
        self.acq_time = 0.5 # 单次采集
        self.buffer_size = buffer_size
        self.acq_pts = int(self.sample_rate * self.acq_interval)

    def start(self):
        logging.info("开始进行DC模式数据采集。")
        self.running = True
        # init_start_time = time.time()
        while self.running:
            start_time = time.time()
            # todo: 加入模拟采集数据，以及采样率、深度更新设置
            # data1 = np.random.normal(size=self.acq_pts)
            # data2 = np.random.normal(size=self.acq_pts) * 0.5
            data1, data2 = self.parent.parent.dev.auxDAQ_play(data_num=int(self.sample_rate * self.acq_time))
            stop_time = time.time()
            time_data = np.linspace(start_time, stop_time, len(data1))
            self.data_updated.emit(time_data, data1, data2)
            # QThread.sleep(self.acq_interval)

    def stop(self):
        logging.info("结束DC模式数据采集。")
        self.running = False

    def set_sample_rate(self, rate):
        self.sample_rate = rate
        self.sample_interval = 1.0 / rate


# ----------------- ViewModel -----------------
class OscilloscopeDCViewModel(QObject):
    data_ready = Signal(np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = OscilloscopeDCModel(parent)
        self.thread = QThread()
        self.model.moveToThread(self.thread)

        self.thread.started.connect(self.model.start)
        self.model.data_updated.connect(self.data_ready)

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
class OscilloscopeDCPanel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setWindowTitle("DC 示波器")
        self.resize(1000, 600)

        self.state_manager = parent.state_manager
        self.state_manager.state_changed.connect(self.on_state_changed)

        self.vm = OscilloscopeDCViewModel(self)
        self.vm.data_ready.connect(self.update_display)

        self.full_data1 = []  # 无限缓存
        self.full_data2 = []
        self.full_time_data = []

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
        elif state == DevState.DC_RUNNING:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
        elif state == DevState.DAQ_RUNNING:
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

        self.start_btn = QPushButton("开始采集")
        self.save_btn = QPushButton("保存数据")
        self.clear_btn = QPushButton("清空数据")

        # self.start_btn.clicked.connect(self.flush_buffer)
        self.start_btn.clicked.connect(self.on_start_button_clicked)
        self.clear_btn.clicked.connect(self.flush_buffer)
        self.save_btn.clicked.connect(self.save_data)
        self.save_btn.clicked.connect(self.save_image)

        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.save_btn)
        control_layout.addWidget(self.clear_btn)

        control_layout.addWidget(QLabel("屏幕显示长度（点）:"))

       

        self.length_input = QLineEdit(str(self.display_length))
        self.length_input.setFixedWidth(100)
        self.length_input.setValidator(QtGui.QIntValidator(100, 1000000))
        # self.length_input.editingFinished.connect(self.update_display_length)
        control_layout.addWidget(self.length_input)

        layout.addLayout(control_layout)

        self.stats_label = QLabel("CH1最大值: --   CH1最小值: --   CH1均值: --\n"
                                  "CH2最大值: --   CH2最小值: --   CH2均值: --")
        layout.addWidget(self.stats_label)

        self.label_coord = QLabel("X: -- , Y: --")
        layout.addWidget(self.label_coord)

        # 时域图 CH1 & CH2
        self.plot_ch1 = pg.PlotWidget(title="CH1 DC通道时域波形")
        self.plot_ch1.showGrid(x=True, y=True)
        self.plot_ch2 = pg.PlotWidget(title="CH2 DC通道时域波形")
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

    def on_start_button_clicked(self):
        state = self.state_manager.current_state()
        if state == DevState.DC_RUNNING:
            self.start_btn.setText("开始采集")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()
        elif state == DevState.IDLE:
            self.init_start_time = time.time()
            # self.flush_buffer()
            self.start_btn.setText("停止采集")
            self.state_manager.set_state(DevState.DC_RUNNING)
            self.vm.start()

    def update_display_length(self):
        val = int(self.length_input.text())
        self.display_length = val

    def update_display(self, time_data, data1, data2):
        self.full_data1.extend(data1.tolist())
        self.full_data2.extend(data2.tolist())
        self.full_time_data.extend(time_data.tolist())

        try:
            self.display_length = int(self.length_input.text())
        except:
            pass

        # 裁剪显示窗口数据
        timewindow = np.array(self.full_time_data[-self.display_length:]) - self.init_start_time
        window1 = self.full_data1[-self.display_length:]
        window2 = self.full_data2[-self.display_length:]

        # print(f"数据显示长度：{self.display_length}, data1长度：{len(self.full_data1)}, data2长度：{len(self.full_data2)}, 时间长度：{len(timewindow)}")
        self.curve_ch1.setData(timewindow, window1)
        self.curve_ch2.setData(timewindow, window2)

        # 统计量
        max_val1 = np.max(window1)
        min_val1 = np.min(window1)
        mean_val1 = np.mean(window1)

        max_val2 = np.max(window2)
        min_val2 = np.min(window2)
        mean_val2 = np.mean(window2)
        self.stats_label.setText(f"CH1最大值: {max_val1:.4f}  CH1最小值: {min_val1:.4f}  CH1均值: {mean_val1:.4f}\n"
                                 f"CH2最大值: {max_val2:.4f}  CH2最小值: {min_val2:.4f}  CH2均值: {mean_val2:.4f}\n")

    def on_mouse_moved(self, pos, plot):
        vb = plot.getViewBox()
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        self.label_coord.setText(f"X: {x:.1f}, Y: {y:.3f}")

    def save_data(self):
        # path, _ = QFileDialog.getSaveFileName(self, "保存数据", "osc_data.csv", "CSV Files (*.csv)")
        path = self.parent.save_dir_osc_dc + gettimestr() + '_osc_dc.csv'
        if path:
            arr = np.column_stack((self.full_time_data, self.full_data1, self.full_data2))
            np.savetxt(path, arr, delimiter=",", header=f"%采样率={self.parent.param_config['auxdaq_sample_rate']['value']}Hz\n"
                              f"%直流DAQ模式增益系数={self.parent.param_config['lockin_dc_daq_gain']['value']}\n"
                              f"%Time (s), CH1(Hz), CH2(Hz)",
                       comments='% ')
            QMessageBox.information(self, "保存成功", f"DAQ模式数据已保存为 {path}")

    def save_image(self):
        time_str = gettimestr()
        path_ch1 = self.parent.save_dir_osc_dc + time_str + '_osc_dc_ch1.png'
        path_ch2 = self.parent.save_dir_osc_dc + time_str + '_osc_dc_ch2.png'
        # path, _ = QFileDialog.getSaveFileName(self, "保存图像", "plot.png", "PNG Files (*.png)")
        exporter_ch1 = ImageExporter(self.plot_ch1.plotItem)
        exporter_ch2 = ImageExporter(self.plot_ch2.plotItem)
        exporter_ch1.export(path_ch1)
        exporter_ch2.export(path_ch2)

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()
