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
class OscilloscopeDCCWModel(QObject):
    # data_updated = Signal(np.ndarray)
    data_updated = Signal(np.float64, np.float64, np.float64)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.main_ui = self.parent.parent.parent
        self.dev = self.parent.parent.parent.dev
        self.running = False
        self.ch1_init_modu = None
        self.ch1_init_freq = None

    def get_cw_params(self):
        start_mw_freq = float(self.parent.parent.start_freq_input.text()) * 1e6 # MHz to Hz
        stop_mw_freq = float(self.parent.parent.end_freq_input.text()) * 1e6 # MHz to Hz
        step_mw_freq = float(self.parent.parent.step_freq_input.text()) * 1e6 # MHz to Hz
        return start_mw_freq, stop_mw_freq, step_mw_freq

    def start(self):
        self.running = True
        # init_start_time = time.time()
        # todo: 替换为分条件采集
        start_mw_freq, stop_mw_freq, step_mw_freq = self.get_cw_params()

        current_mw_freq = start_mw_freq
        mw_list = []
        auxdaq_1_list = []
        auxdaq_2_list = []
        single_point_num = int(self.parent.parent.single_point_num_input.text())

        self.ch1_init_modu = self.main_ui.param_config["mw_ch1_fm_sens"]["value"]
        self.ch1_init_freq = self.main_ui.param_config["mw_ch1_freq"]["value"]

        self.main_ui.set_param(name="mw_ch1_fm_sens", value=0, ui_flag=False, delay_flag=False)

        while self.running and current_mw_freq <= stop_mw_freq:
            mw_list.append(current_mw_freq)
            self.main_ui.set_param(name="mw_ch1_freq", value=str(current_mw_freq), ui_flag=False, delay_flag=False)
            # print(f'开始采集CW数据')
            auxdaq_data = self.parent.parent.parent.dev.auxdaq_play(
                data_num=single_point_num)
            # print(f'结束采集CW数据')
            auxdaq_1 = np.mean(auxdaq_data[0])
            auxdaq_2 = np.mean(auxdaq_data[1])
 
            auxdaq_1_list.append(auxdaq_1)
            auxdaq_2_list.append(auxdaq_2)

            # print('[CH1-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[1]), np.mean(IIR_data[1])))
            # print('[CH1-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[2]), np.mean(IIR_data[2])))
            # print('[CH1-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[7]), np.mean(IIR_data[7])))
            # print('[CH1-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[8]), np.mean(IIR_data[8])))

             # print('[CH2-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[4]), np.mean(IIR_data[4])))
            # print('[CH2-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[5]), np.mean(IIR_data[5])))
            # print('[CH2-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[10]), np.mean(IIR_data[10])))
            # print('[CH2-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[11]), np.mean(IIR_data[11])))

            self.data_updated.emit(current_mw_freq, auxdaq_1, auxdaq_2)
            current_mw_freq += step_mw_freq
            # QThread.sleep(self.acq_interval)
        

        self.stop()


    def stop(self):
        logging.info("结束CW谱数据采集。")
        self.running = False


# ----------------- ViewModel -----------------
class OscilloscopeDCCWViewModel(QObject):
    data_ready = Signal(np.float64, np.float64, np.float64)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = OscilloscopeDCCWModel(self)
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
class OscilloscopeDCCWPanel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        if hasattr(self.parent, 'save_dir_cw'):
            self.save_dir = self.parent.save_dir_cw
        else:
            self.save_dir = './'
        self.setWindowTitle("DC-CW谱数据采集")
        self.resize(1000, 600)

        self.state_manager = parent.state_manager
        self.state_manager.state_changed.connect(self.on_state_changed)

        self.vm = OscilloscopeDCCWViewModel(self)
        self.vm.data_ready.connect(self.update_display)

        self.mw_freq = []
        self.ch1_x = []
        self.ch1_y = []
        self.ch2_x = []
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
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
        elif state == DevState.EXP_RUNNING:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        else:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)

    def flush_buffer(self):
        self.mw_freq = []
        self.auxdaq_all_1 = []
        self.auxdaq_all_2 = []

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
        freq_layout.addWidget(QLabel("起始频率(MHz):"))
        self.start_freq_input = QLineEdit()
        self.start_freq_input.setText('2800')
        self.start_freq_input.setFixedWidth(100)
        freq_layout.addWidget(self.start_freq_input)

        freq_layout.addWidget(QLabel("结束频率(MHz):"))
        self.end_freq_input = QLineEdit()
        self.end_freq_input.setText('2950')
        self.end_freq_input.setFixedWidth(100)
        freq_layout.addWidget(self.end_freq_input)

        freq_layout.addWidget(QLabel("步进频率(MHz):"))
        self.step_freq_input = QLineEdit()
        self.step_freq_input.setText('2')
        self.step_freq_input.setFixedWidth(100)
        freq_layout.addWidget(self.step_freq_input)

        # 单点采集累加点数
        self.single_point_num_input = QLineEdit()
        self.single_point_num_input.setText('10')
        self.single_point_num_input.setFixedWidth(100)
        freq_layout.addWidget(QLabel("单点CW采集累加次数:"))
        freq_layout.addWidget(self.single_point_num_input)

        control_layout.addLayout(freq_layout)

        layout.addLayout(control_layout)

        self.label_coord = QLabel("X: -- , Y: --")
        layout.addWidget(self.label_coord)

        # 时域图 CH1 & CH2
        self.plot_ch1 = pg.PlotWidget(title="CH1 荧光 DC-CW谱")
        self.plot_ch1.showGrid(x=True, y=True)
        self.plot_ch2 = pg.PlotWidget(title="CH2 激光 DC-CW谱")
        self.plot_ch2.showGrid(x=True, y=True)

        self.plot_ch1.setLabel("left", "Voltage", units="V")
        self.plot_ch1.setLabel("bottom", "Frequency", units="Hz")

        self.plot_ch2.setLabel("left", "Voltage", units="V")
        self.plot_ch2.setLabel("bottom", "Frequency", units="Hz")

        self.curve_ch1 = self.plot_ch1.plot(pen='b', name='CH1-X')
        self.curve_ch2 = self.plot_ch2.plot(pen='y', name='CH2-X')

        self.curve_ch3 = self.plot_ch1.plot(pen='r', name='CH1-Y')
        self.curve_ch4 = self.plot_ch2.plot(pen='g', name='CH2-Y')

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
            self.start_btn.setText("开始采集")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()
            self.save_data()
            self.reset_mw_params()
        elif state == DevState.IDLE:
            self.init_start_time = time.time()
            self.flush_buffer()
            self.start_btn.setText("停止采集")
            self.state_manager.set_state(DevState.EXP_RUNNING)
            self.vm.start()

    def reset_mw_params(self):
        # 避免采集结束后微波参数被修改，和主UI保持一致
        self.parent.set_param(name="mw_ch1_fm_sens", value=self.vm.model.ch1_init_modu, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch1_freq", value=self.vm.model.ch1_init_freq, ui_flag=True, delay_flag=False)

    def update_display(self, mwf, auxdaq_1, auxdaq_2):
        self.mw_freq.append(mwf)
        self.auxdaq_all_1.append(auxdaq_1)
        self.auxdaq_all_2.append(auxdaq_2)

        self.curve_ch1.setData(self.mw_freq, self.auxdaq_all_1)
        self.curve_ch2.setData(self.mw_freq, self.auxdaq_all_2)

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
        path = self.parent.save_dir + gettimestr() + '_dc_cw.csv'
        if path:
            arr = np.column_stack((self.mw_freq, self.auxdaq_all_1, self.auxdaq_all_2))
            np.savetxt(path, arr, delimiter=",",
                       header=f"%直流采集模式-码值电压转换系数={self.parent.param_config['lockin_dc_daq_gain']['value']} V\n"
                              f"%单点CW采集累加次数={self.single_point_num_input.text()}\n"
                              f"%MW Freq (Hz), CH1-DC(V), CH2-DC(V)\n",
                       comments='% ')
            QMessageBox.information(self, "保存成功", f"DC-CW模式数据已保存为 {path}")

    def save_image(self):
        time_str = gettimestr()
        path_ch1 = self.save_dir + time_str + '_dc_cw_ch1.png'
        path_ch2 = self.save_dir + time_str + '_dc_cw_ch2.png'
        # path, _ = QFileDialog.getSaveFileName(self, "保存图像", "plot.png", "PNG Files (*.png)")
        exporter_ch1 = ImageExporter(self.plot_ch1.plotItem)
        exporter_ch2 = ImageExporter(self.plot_ch2.plotItem)
        exporter_ch1.export(path_ch1)
        exporter_ch2.export(path_ch2)

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()
