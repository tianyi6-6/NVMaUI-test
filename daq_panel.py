# encoding=utf-8
import numpy as np
import PySide6.QtGui as QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QComboBox,
)
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from manager import *
from General import *
from collections import deque

# ----------------- Model -----------------
class OscilloscopeModel(QObject):
    # data_updated = Signal(np.ndarray)
    data_updated = Signal(np.ndarray, np.ndarray)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.running = False
        self.sample_rate = 10000
        self.sample_interval = 1.0 / self.sample_rate
        self.acq_time = 1

    def start(self):
        logging.info("开始进行DAQ模式数据采集。")
        self.running = True
        while self.running:
            acq_pts = int(self.sample_rate * self.parent.parent.parent.param_config['lockin_daq_time']['value'])
            ext_ratio = self.parent.parent.parent.param_config['lockin_daq_ex_ratio']['value']
            # print(f'采集点数：{acq_pts}, 采集抽取率：{ext_ratio}, 推算采样率：{25e3 / (ext_ratio + 1)} ksps')
            data1, data2 = self.parent.parent.parent.dev.DAQ_play(data_num=acq_pts, extract_ratio=ext_ratio)
            # data1 = np.random.normal(size=self.buffer_size) + np.sin(time_data * 300)
            # data2 = np.random.normal(size=self.buffer_size) * 0.5 + np.sin(time_data * 500)
            self.data_updated.emit(data1, data2)
            # QThread.sleep(1)
            # QThread.msleep(int(self.sample_interval * 1000))

    def stop(self):
        logging.info("结束DAQ模式数据采集。")
        self.running = False

    def set_sample_rate(self, rate):
        self.sample_rate = rate
        self.sample_interval = 1.0 / rate

    def set_acq_time(self, acq_time):
        self.acq_time = acq_time


# ----------------- ViewModel -----------------
class OscilloscopeViewModel(QObject):
    # data_ready = Signal(np.ndarray)
    data_ready = Signal(np.ndarray, np.ndarray)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = OscilloscopeModel(self)
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
class OscilloscopePanel(QWidget):
    rate_map = {
        "10kHz": 10000,
        "20kHz": 20000,
        "50kHz": 50000,
        "100kHz": 100000,
        "200kHz": 200000,
        "500kHz": 500000,
        "1MHz": 1000000,
        "5MHz": 5000000,
        "25MHz": 25000000,
    }

    acq_time_map = {
        "10s":10,
        '5s':5,
        '2s':2,
        '1s':1,
        '100ms':0.1,
        '10ms':0.01,
        '1ms':0.001,
        '100μs':0.0001,
        '10μs':0.00001,
        '1μs':0.000001,
    }

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.state_manager = parent.state_manager
        self.state_manager.state_changed.connect(self.on_state_changed)
        self.setWindowTitle("MVVM 示波器")
        self.resize(1000, 600)

        self.sample_rate_change = None
        self.sample_pts_change = None

        self.avg_count = 1
        self.acq_time = 1
        self.buffers_ch1 = deque(maxlen=self.avg_count)
        self.buffers_ch2 = deque(maxlen=self.avg_count)
        self.buffers_ch1_fft = deque(maxlen=self.avg_count)
        self.buffers_ch2_fft = deque(maxlen=self.avg_count)

        self.vm = OscilloscopeViewModel(self)
        self.vm.data_ready.connect(self.update_data)

        self.update_plot_timer = QTimer()
        self.update_plot_timer.timeout.connect(self.update_display)
        # self.vm.data_ready.connect(self.update_display)

        self.fft_mode = "FFT"

        self.init_ui()

    def on_state_changed(self, state):
        if state == DevState.OFFLINE:
            self.rate_selector.setEnabled(False)
            self.mode_selector.setEnabled(False)
            self.start_btn.setEnabled(False)
            # self.stop_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        elif state == DevState.IDLE:
            self.rate_selector.setEnabled(True)
            self.mode_selector.setEnabled(True)
            self.start_btn.setEnabled(True)
            # self.stop_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
        elif state == DevState.DAQ_RUNNING:
            self.rate_selector.setEnabled(True)
            self.mode_selector.setEnabled(True)
            self.start_btn.setEnabled(True)
            # self.stop_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
        else:
            self.rate_selector.setEnabled(True)
            self.mode_selector.setEnabled(True)
            self.start_btn.setEnabled(False)
            # self.stop_btn.setEnabled(True)
            self.save_btn.setEnabled(True)

    def init_ui(self):
        layout = QVBoxLayout()
        control_layout = QHBoxLayout()

        control_layout.addWidget(QLabel("采样率:"))

        self.rate_selector = QComboBox()
        self.rate_selector.addItems(["10kHz", "20kHz", "50kHz", "100kHz", "200kHz", "500kHz", "1MHz", "5MHz", "25MHz"])

        # todo: 根据实验面板参数设置初始采样率
        init_ex_ratio = self.parent.param_config["lockin_daq_ex_ratio"]["value"]
        init_rate_table = {2499: 0, 1249: 1, 499: 2, 249: 3, 124: 4, 49: 5, 4: 7, 0: 8}
        self.rate_selector.setCurrentIndex(init_rate_table[init_ex_ratio])

        self.rate_selector.currentIndexChanged.connect(self.on_rate_change)
        self.rate_selector.currentIndexChanged.connect(self.update_avg_count)
        control_layout.addWidget(self.rate_selector)

        # control_layout.addWidget(QLabel("单次采集开关:"))
        # init_daq_time = self.parent.param_config["lockin_daq_time"]["value"]
        # control_layout.addWidget()


        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["FFT", "功率谱密度"])
        self.mode_selector.currentIndexChanged.connect(self.on_mode_change)
        self.mode_selector.currentIndexChanged.connect(self.update_avg_count)
        control_layout.addWidget(QLabel("频域模式:"))
        control_layout.addWidget(self.mode_selector)
        self.start_btn = QPushButton("开始示波器")
        # self.stop_btn = QPushButton("停止示波器")
        self.save_btn = QPushButton("保存当前数据")

        # --- 区间输入控件 ---
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("频率区间:"))
        self.freq_start_input = QLineEdit()
        self.freq_start_input.setPlaceholderText("起始 Hz")
        self.freq_start_input.setText("1000")
        self.freq_end_input = QLineEdit()
        self.freq_end_input.setPlaceholderText("结束 Hz")
        self.freq_end_input.setText('2000')

        freq_layout.addWidget(self.freq_start_input)
        freq_layout.addWidget(self.freq_end_input)

        freq_layout.addWidget(QLabel("Hz"))

        # freq_layout.addWidget(self.calc_avg_btn)

        self.start_btn.clicked.connect(self.on_start_btn)
        # self.stop_btn.clicked.connect(self.on_stop_btn)
        self.save_btn.clicked.connect(self.save_data)
        self.save_btn.clicked.connect(self.save_image)

        control_layout.addWidget(self.start_btn)
        # control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(self.save_btn)

        layout.addLayout(freq_layout)
        layout.addLayout(control_layout)
        # 数据面板
        # control_layout.addWidget(QLabel("采样时间:"))
        # self.acq_time_input = QLineEdit()
        # self.acq_time_input.setFixedWidth(60)
        # self.acq_time_input.setText(str(self.acq_time))
        # control_layout.addWidget(self.acq_time_input)
        # control_layout.addWidget(QLabel("s"))

        control_layout.addWidget(QLabel("平均次数:"))
        self.avg_input = QLineEdit("1")
        self.avg_input.setFixedWidth(60)
        self.avg_input.setValidator(QtGui.QIntValidator(1, 100))
        self.avg_input.editingFinished.connect(self.update_avg_count)
        control_layout.addWidget(self.avg_input)

        self.data_label = QLabel("最小噪声: --")
        layout.addWidget(self.data_label)
        self.range_label = QLabel("区间均值: --")
        layout.addWidget(self.range_label)

        self.plot_time = pg.PlotWidget(title="时域波形")
        self.plot_fft = pg.PlotWidget(title="频域图（对数）")
        self.plot_time.showGrid(x=True, y=True)
        self.plot_fft.showGrid(x=True, y=True)
        self.plot_fft.setLogMode(x=False, y=True)

        self.plot_time.addLegend()
        self.plot_fft.addLegend()
        self.plot_time.setLabel("left", "Voltage", units="V")
        self.plot_time.setLabel("bottom", "Samples")
        self.plot_fft.setLabel("left", "Amplitude", units="V")
        self.plot_fft.setLabel("bottom", "Frequency", units="Hz")

        self.curve_time1 = self.plot_time.plot(pen='blue', name="CH1")
        self.curve_time2 = self.plot_time.plot(pen='y', name="CH2")

        self.curve_fft1 = self.plot_fft.plot(pen='blue', name="CH1-Spec")
        self.curve_fft2 = self.plot_fft.plot(pen='y', name="CH2-Spec")

        self.band_avg_line1 = self.plot_fft.plot(pen=pg.mkPen('r', width=1, style=pg.QtCore.Qt.DashLine))
        self.band_avg_line2 = self.plot_fft.plot(pen=pg.mkPen('r', width=1, style=pg.QtCore.Qt.DashLine))

        self.band_min_line1 = self.plot_fft.plot(pen=pg.mkPen('blue', width=1, style=pg.QtCore.Qt.DashLine))
        self.band_max_line1 = self.plot_fft.plot(pen=pg.mkPen('blue', width=1, style=pg.QtCore.Qt.DashLine))
        self.band_min_line2 = self.plot_fft.plot(pen=pg.mkPen('y', width=1, style=pg.QtCore.Qt.DashLine))
        self.band_max_line2 = self.plot_fft.plot(pen=pg.mkPen('y', width=1, style=pg.QtCore.Qt.DashLine))

        self.freq_vline1 = self.plot_fft.plot(pen=pg.mkPen('r', width=1, style=pg.QtCore.Qt.DashLine))
        self.freq_vline2 = self.plot_fft.plot(pen=pg.mkPen('r', width=1, style=pg.QtCore.Qt.DashLine))

        self.label_coord = QLabel("X: -- Hz, Y: --")
        self.plot_fft.scene().sigMouseMoved.connect(self.on_mouse_moved)

        layout.addWidget(self.plot_time)
        layout.addWidget(self.plot_fft)
        layout.addWidget(self.label_coord)

        self.setLayout(layout)

    def on_start_btn(self):
        state = self.state_manager.current_state()
        if state == DevState.DAQ_RUNNING:
            self.start_btn.setText("开始采集")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()
            self.update_plot_timer.stop()
        elif state == DevState.IDLE:
            self.start_btn.setText("停止采集")
            self.state_manager.set_state(DevState.DAQ_RUNNING)
            self.update_avg_count()
            self.vm.start()
            self.update_plot_timer.start(1000)

    def update_avg_count(self):
        self.avg_count = int(self.avg_input.text())
        self.buffers_ch1 = deque(maxlen=self.avg_count)
        self.buffers_ch1_fft = deque(maxlen=self.avg_count)
        self.buffers_ch2 = deque(maxlen=self.avg_count)
        self.buffers_ch2_fft = deque(maxlen=self.avg_count)

    def calculate_band_average(self):
        try:
            f_start = float(self.freq_start_input.text())
            f_end = float(self.freq_end_input.text())
        except ValueError:
            self.range_label.setText("区间均值: 输入无效")
            return

        if f_end <= f_start:
            self.range_label.setText("区间均值: 区间非法")
            return

        if len(self.buffers_ch1) == 0:
            return
        # 重新获取当前频谱数据（从缓存或重新计算）
        spec1 = np.mean(self.buffers_ch1_fft, axis=0)
        spec2 = np.mean(self.buffers_ch2_fft, axis=0)

        freqs1 = np.fft.rfftfreq(len(self.buffers_ch1[0]), d=1.0 / self.vm.model.sample_rate)
        freqs2 = np.fft.rfftfreq(len(self.buffers_ch2[0]), d=1.0 / self.vm.model.sample_rate)

        # 获取频率区间对应索引
        mask1 = (freqs1 >= f_start) & (freqs1 <= f_end)
        mask2 = (freqs2 >= f_start) & (freqs2 <= f_end)
        if not np.any(mask1):
            self.range_label.setText("区间均值: 无数据")
            return

        # 先计算平均fft，再计算均值
        avg1 = np.mean(spec1[mask1])
        avg2 = np.mean(spec2[mask2])

        min1 = np.amin(spec1[mask1])
        min2 = np.amin(spec2[mask2])
        max1 = np.amax(spec1[mask1])
        max2 = np.amax(spec2[mask2])

        full_min1 = np.amin(spec1)
        full_max1 = np.amax(spec1)
        full_min2 = np.amin(spec2)
        full_max2 = np.amax(spec2)
        # min1 = np.amin(self.buffers_ch1_fft[i][mask1], axis=0)
        # min2 = np.amin(self.buffers_ch2_fft[:, mask2], axis=0)

        # max1 = np.amax(self.buffers_ch1_fft[:, mask1], axis=0)
        # max2 = np.amax(self.buffers_ch2_fft[:, mask2], axis=0)

        # 设置横线位置
        self.band_avg_line1.setData([f_start, f_end], [avg1, avg1])
        self.band_avg_line2.setData([f_start, f_end], [avg2, avg2])

        # 峰值频率位置
        peak_freq1 = freqs1[np.argmax(spec1)]
        peak_freq2 = freqs2[np.argmax(spec2)]
        self.freq_vline1.setData([peak_freq1, peak_freq1], [full_min1, full_max1])
        self.freq_vline2.setData([peak_freq2, peak_freq2], [full_min2, full_max2])

        self.band_min_line1.setData([f_start, f_end], [min1, min1])
        self.band_max_line1.setData([f_start, f_end], [max1, max1])
        self.band_min_line2.setData([f_start, f_end], [min2, min2])
        self.band_max_line2.setData([f_start, f_end], [max2, max2])

        # 更新文本
        # self.range_label.setText(f"CH1 区间均值: {avg1:.4e}, CH2 区间均值: {avg2:.4e}")

    def save_image(self):
        time_str = gettimestr()
        path_fft = self.parent.save_dir_osc_ac + time_str + '_osc_ac_freq_spectrum.png'
        path_time = self.parent.save_dir_osc_ac + time_str + '_osc_ac_time_domain.png'
        # path, _ = QFileDialog.getSaveFileName(self, "保存图像", "plot.png", "PNG Files (*.png)")
        exporter_fft = ImageExporter(self.plot_fft.plotItem)
        exporter_time = ImageExporter(self.plot_time.plotItem)
        exporter_fft.export(path_fft)
        exporter_time.export(path_time)

    def on_mode_change(self):
        self.fft_mode = self.mode_selector.currentText()

    def update_data(self, data1, data2):
        # 新读取到的数据
        self.buffers_ch1.append(data1)
        self.buffers_ch2.append(data2)

        # 当前已经采到的数据
        # freqs1 = np.fft.rfftfreq(len(data1), d=1.0 / self.vm.model.sample_rate)
        # freqs2 = np.fft.rfftfreq(len(data2), d=1.0 / self.vm.model.sample_rate)

        fft_data1 = np.fft.rfft(data1)
        fft_data2 = np.fft.rfft(data2)

        if self.fft_mode == "功率谱密度":
            spec1 = (np.abs(fft_data1) ** 2) / (self.vm.model.sample_rate * len(data1))
            spec2 = (np.abs(fft_data2) ** 2) / (self.vm.model.sample_rate * len(data2))
        else:
            spec1 = np.abs(fft_data1)
            spec2 = np.abs(fft_data2)

        # 存入滑动平均缓冲
        self.buffers_ch1_fft.append(spec1)
        self.buffers_ch2_fft.append(spec2)

    def update_display(self):

        # try:
        #     new_acq_time = int(self.acq_time_input)
        #     if new_acq_time != self.acq_time and 0 < new_acq_time < 10:
        #         self.acq_time = new_acq_time
        #         self.update_avg_count()
        # except:
        #     pass

        if len(self.buffers_ch2_fft) == 0:
            return
        freqs1 = np.fft.rfftfreq(len(self.buffers_ch1[0]), d=1.0 / self.vm.model.sample_rate)
        freqs2 = freqs1

        # 滑动平均
        avg_spec1 = np.mean(self.buffers_ch1_fft, axis=0)
        avg_spec2 = np.mean(self.buffers_ch2_fft, axis=0)

        # 频域数据：绘制平均值
        self.curve_fft1.setData(freqs1, avg_spec1)
        self.curve_fft2.setData(freqs2, avg_spec2)

        # 时域数据：绘制最新数据
        self.curve_time1.setData(self.buffers_ch1[-1])
        self.curve_time2.setData(self.buffers_ch2[-1])

        # 统计分析
        peak_freq1_id_list = np.argmax(self.buffers_ch1_fft, axis=1)
        peak_freq2_id_list = np.argmax(self.buffers_ch2_fft, axis=1)

        peak_freq1_list = [freqs1[peak_freq1_id_list[i]] for i in range(len(peak_freq1_id_list))]
        peak_amp1_list = [self.buffers_ch1_fft[i][peak_freq1_id_list[i]] for i in range(len(peak_freq1_id_list))]
        peak_freq2_list = [freqs1[peak_freq2_id_list[i]] for i in range(len(peak_freq1_id_list))]
        peak_amp2_list = [self.buffers_ch2_fft[i][peak_freq2_id_list[i]] for i in range(len(peak_freq1_id_list))]

        # mean1_list = np.mean(self.buffers_ch1_fft, axis=1)
        # mean2_list = np.mean(self.buffers_ch2_fft, axis=1)
        # std1_list = np.std(self.buffers_ch1_fft, axis=1)
        # std2_list = np.std(self.buffers_ch2_fft, axis=1)

        text = (
            f"平均次数：{len(self.buffers_ch1_fft)}/{self.avg_count}\n"
            f"CH1:峰值频率={np.mean(peak_freq1_list):.6e} Hz +- {np.ptp(peak_freq1_list) / 2 / np.mean(peak_freq1_list) * 100 if np.mean(peak_freq1_list) != 0 else 0:.2f} %  (1sigma={np.std(peak_freq1_list) / np.mean(peak_freq1_list) * 100 if np.mean(peak_freq1_list) != 0 else 0:.2f} %)\n"
            f"CH1:峰值幅度={np.mean(peak_amp1_list):.6e} V +- {np.ptp(peak_amp1_list) / 2 / np.mean(peak_amp1_list) * 100 if np.mean(peak_amp1_list) != 0 else 0:.2f} %  (1sigma={np.std(peak_amp1_list) / np.mean(peak_amp1_list) * 100 if np.mean(peak_amp1_list) != 0 else 0:.2f} %)\n"
            # f"CH1:区间内频谱平均值={np.mean(mean1_list):.6e} +- {np.ptp(mean1_list) / 2/ np.mean(mean1_list) * 100:.2f} %  (1sigma={np.std(mean1_list) / np.mean(mean1_list) * 100:.2f} %)\n"
            # f"CH1:区间标准差={np.mean(std1_list):.6e} +- {np.ptp(std1_list) / 2:6e}  (1sigma={np.std(std1_list):6e})\n"

            f"CH2:峰值频率={np.mean(peak_freq2_list):.6e} +- {np.ptp(peak_freq2_list) / 2 / np.mean(peak_freq2_list) * 100 if np.mean(peak_freq2_list) != 0 else 0:.2f} %   (1sigma={np.std(peak_freq2_list) / np.mean(peak_freq2_list) * 100 if np.mean(peak_freq2_list) != 0 else 0:.2f} %)\n"
            f"CH2:峰值幅度={np.mean(peak_amp2_list):.6e} +- {np.ptp(peak_amp2_list) / 2 / np.mean(peak_amp2_list) * 100 if np.mean(peak_amp2_list) != 0 else 0:.2f} %   (1sigma={np.std(peak_amp2_list) / np.mean(peak_amp2_list) * 100 if np.mean(peak_amp2_list) != 0 else 0:.2f} %)\n"
            # f"CH2:区间内频谱平均值={np.mean(mean2_list):.6e} +- {np.ptp(mean2_list) / 2/ np.mean(mean2_list) * 100:.2f} %   (1sigma={np.std(mean2_list) / np.mean(mean2_list) * 100:.2f} %)\n"
            # f"CH2:区间标准差={np.mean(std2_list):.6e} +- {np.ptp(std2_list) / 2:6e}  (1sigma={np.std(std2_list):6e})"
        )
        self.data_label.setText(text)
        self.calculate_band_average()

    def on_rate_change(self):
        text = self.rate_selector.currentText()
        rate = self.rate_map.get(text, 10000)
        self.parent.set_param("lockin_daq_ex_ratio", int(25e6 / rate) - 1)
        self.vm.change_sample_rate(rate)

    def on_mouse_moved(self, pos):
        vb = self.plot_fft.getViewBox()
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        # if x > 0 and y > 0:
        self.label_coord.setText(f"X: {x:.1f} Hz, Y: {y:.2e}")

    def save_data(self):
        path = self.parent.save_dir_osc_ac + gettimestr() + '_osc_ac_fft.csv'
        path_time = self.parent.save_dir_osc_ac + gettimestr() + '_osc_ac_time.csv'

        # arr = np.column_stack((self.data_buffer1, self.data_buffer2))
        if len(self.buffers_ch1) > 0:
            freqs1 = np.fft.rfftfreq(len(self.buffers_ch1[0]), d=1.0 / self.vm.model.sample_rate)
            arr = np.column_stack(
                (freqs1, np.mean(self.buffers_ch1_fft, axis=0), np.mean(self.buffers_ch2_fft, axis=0)))
            np.savetxt(path, arr, delimiter=",",
                       header=f"采样率={self.rate_map.get(self.rate_selector.currentText(), 10000)}Hz\n"
                              f"平均次数={len(self.buffers_ch1)}\n"
                              f"DAQ模式增益系数={self.parent.param_config['lockin_daq_gain']['value']}V\n"
                              f"Freq (Hz), CH1(Hz), CH2(Hz)",
                       comments='% ',
                       )

            savetime = np.linspace(0, len(self.buffers_ch1[0]) / self.vm.model.sample_rate, len(self.buffers_ch1[0]))
            arr = np.column_stack((savetime, self.buffers_ch1[-1], self.buffers_ch2[-1]))
            np.savetxt(path_time, arr, delimiter=",",
                       header=f"采样率={self.rate_map.get(self.rate_selector.currentText(), 10000)}Hz\n"
                              f"采样时间={len(self.buffers_ch1) / self.vm.model.sample_rate}s\n"
                              f"DAQ模式增益系数={self.parent.param_config['lockin_daq_gain']['value']}V\n"
                              f"Freq (Hz), CH1(Hz), CH2(Hz)",
                       comments='% ',
                       )
            # QMessageBox.information(self, "保存成功", f"数据已保存为 {path}")
            logging.info(f"保存成功，DAQ数据已保存为{path}、{path_time}。")

            # arr = np.column_stack()

        else:
            logging.info("无有效数据可保存。")

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()