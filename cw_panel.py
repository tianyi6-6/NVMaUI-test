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


# ----------------- Model -----------------
class OscilloscopeCWModel(QObject):
    # data_updated = Signal(np.ndarray)
    data_updated = Signal(np.float64, np.float64, np.float64, np.float64, np.float64)
    measurement_finished = Signal()  # 添加测量完成信号

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.main_ui = self.parent.parent.parent
        self.dev = self.parent.parent.parent.dev
        self.ch1_init_freq = None
        self.running = False

    def get_cw_params(self):
        start_mw_freq = float(self.parent.parent.start_freq_input.text()) * 1e6 # MHz to Hz
        stop_mw_freq = float(self.parent.parent.end_freq_input.text()) * 1e6 # MHz to Hz
        step_mw_freq = float(self.parent.parent.step_freq_input.text()) * 1e6 # MHz to Hz
        return start_mw_freq, stop_mw_freq, step_mw_freq

    def cal_max_slope(self, x, y, cal_pnum=5):
        """
        Calculate the max slope of spectra.
        :param x:
        :param y:
        :param cal_pnum: fitting number of points.
        :return:
        """
        if cal_pnum > len(x):
            return 0, 0, 0, 0
        x = np.array(x)
        y = np.array(y)
        cal_pnum = int(cal_pnum)
        slope_result = []
        for i in range(len(x) - cal_pnum):
            # for i in range(sp + 1, ep + 1):
            slope, intercept, r_value, p_value, std_err = linregress(x[i:i + cal_pnum],
                                                                                 y[i:i + cal_pnum])
            slope_result.append(slope)
        slope_result_abs = np.abs(slope_result)
        max_ind = slope_result_abs.argmax()
        ind2 = int(max_ind + cal_pnum / 2)

        # slope,
        return slope_result[int(max_ind)], x[ind2], y[ind2]

    def cal_phase_angle(self, x, y):
        r = np.sqrt(np.array(x) ** 2 + np.array(y) ** 2)
        r_max_id = np.argmax(r)
        return np.rad2deg(np.arctan2(y[r_max_id], x[r_max_id]))

    def calculate_spectrum_parameters(self, freq_range, x_data, y_data, fit_length_mhz, interp_step_mhz, span_range=None):
        """
        计算谱线参数：零点位置、最大幅度点位置、斜率、线宽、幅度
        :param freq_range: 频率范围 [start_freq, end_freq] in Hz
        :param x_data: X通道数据
        :param y_data: Y通道数据
        :param fit_length_mhz: 线性拟合频率区间长度 (MHz)
        :param interp_step_mhz: 插值后频率步进 (MHz)
        :param span_range: span区间范围 [start_freq, end_freq] in Hz，如果为None则使用全部数据
        :return: 计算结果字典
        """
        if len(x_data) < 3 or len(y_data) < 3:
            return None
            
        # 转换为numpy数组
        freq_array = np.array(freq_range)
        x_array = np.array(x_data)
        y_array = np.array(y_data)
        
        # 如果指定了span区间，只使用区间内的数据
        if span_range is not None:
            start_freq, end_freq = span_range
            mask = (freq_array >= start_freq) & (freq_array <= end_freq)
            freq_array = freq_array[mask]
            x_array = x_array[mask]
            y_array = y_array[mask]
            
            if len(freq_array) < 3:
                return None
        
        # 首先进行插值，提高数据精度
        if len(freq_array) >= 3:
            # 创建插值函数
            freq_interp = np.arange(freq_array[0], freq_array[-1], interp_step_mhz * 1e6)
            print(f'插值后点数: {len(freq_interp)}')
            if len(freq_interp) > 0:
                x_interp_func = interp1d(freq_array, x_array, kind='cubic', bounds_error=False, fill_value='extrapolate')
                y_interp_func = interp1d(freq_array, y_array, kind='cubic', bounds_error=False, fill_value='extrapolate')
                
                x_interp = x_interp_func(freq_interp)
                y_interp = y_interp_func(freq_interp)
                
                # 使用插值后的数据进行所有计算
                freq_calc = freq_interp
                x_calc = x_interp
                y_calc = y_interp
        else:
            logging.info(f"插值失败，使用原始数据进行计算")
            return {
                'zero_point_freq': 0,
                'zero_point_value': 0,
                'max_amplitude_freq': 0,
                'max_amplitude_value': 0,
                'min_amplitude_freq': 0,
                'min_amplitude_value': 0,
                'slope': 0,
                'resonance_freq': 0,
                'linewidth': 0,
                'amplitude': 0,
                'fit_length_mhz': fit_length_mhz,
            }
        
        # 计算幅度（统一使用X通道）
        magnitude = x_calc  # 使用X通道值
        
        # 找到最大幅度点
        max_amp_idx = np.argmax(magnitude)
        max_amp_freq = freq_calc[max_amp_idx]
        max_amp_value = magnitude[max_amp_idx]
        

        min_amp_idx = np.argmin(magnitude)
        min_amp_freq = freq_calc[min_amp_idx]
        min_amp_value = magnitude[min_amp_idx]

        # 找到零点位置（在最大幅度点和最小幅度点中间的区间寻找）
        # 确定最大和最小幅度点的位置，找到它们之间的区间
        start_idx = min(max_amp_idx, min_amp_idx)
        end_idx = max(max_amp_idx, min_amp_idx)
        
        # 在区间内寻找幅度绝对值最小的点作为零点
        interval_magnitude = magnitude[start_idx:end_idx+1]
        interval_indices = np.arange(start_idx, end_idx+1)
        zero_amp_idx_in_interval = np.argmin(np.abs(interval_magnitude))
        zero_amp_idx = interval_indices[zero_amp_idx_in_interval]
        zero_amp_freq = freq_calc[zero_amp_idx]
        zero_amp_value = magnitude[zero_amp_idx]
        
        # 计算线宽（FWHM - Full Width at Half Maximum），使用X通道
        # half_max = (max_amp_value + min_amp_value) / 2
        # 找到幅度大于半最大值的所有点
        # above_half = magnitude > half_max
        # if np.sum(above_half) > 1:
            # 找到第一个和最后一个超过半最大值的点
            # half_indices = np.where(above_half)[0]
            # fwhm_start_idx = half_indices[0]
            # fwhm_end_idx = half_indices[-1]
            # linewidth = freq_calc[fwhm_end_idx] - freq_calc[fwhm_start_idx]
        # else:
            # 如果无法计算FWHM，使用最大幅度点和最小幅度点的频率差作为线宽
        linewidth = abs(max_amp_freq - min_amp_freq)
        
        # 线性拟合计算斜率
        fit_length_points = int(fit_length_mhz * 1e6 / (freq_calc[1] - freq_calc[0]))
        if fit_length_points > len(freq_calc):
            logging.info(f"线性拟合频率区间长度大于数据长度，使用一半数据长度进行拟合")
            fit_length_points = len(freq_calc) // 2
        
        
        slope, res_freq, res_value = self.cal_max_slope(freq_calc, x_calc, fit_length_points)
        
        result = {
            'zero_point_freq': zero_amp_freq,
            'zero_point_value': zero_amp_value,
            'max_amplitude_freq': max_amp_freq,
            'max_amplitude_value': max_amp_value,
            'min_amplitude_freq': min_amp_freq,
            'min_amplitude_value': min_amp_value,
            'slope': slope,
            'resonance_freq': res_freq,
            'resonance_value': res_value,
            'linewidth': linewidth,
            'amplitude': max_amp_value - min_amp_value,
            'r_amplitude': np.amax(np.abs(magnitude)),
            'fit_length_mhz': fit_length_mhz,
        }
        
        return result

    def start(self):
        self.running = True
        # init_start_time = time.time()
        # todo: 替换为分条件采集
        start_mw_freq, stop_mw_freq, step_mw_freq = self.get_cw_params()
        mw_channel = int(self.parent.parent.mw_channel_combo.currentIndex())
        logging.info(f"微波通道选择: CH{mw_channel + 1}")
        current_mw_freq = start_mw_freq
        mw_list = []
        iir_1x_list = []
        iir_2x_list = []
        iir_1y_list = []
        iir_2y_list = []
        single_point_num = int(self.parent.parent.single_point_num_input.text())
        self.ch1_init_freq = self.main_ui.param_config["mw_ch1_freq"]["value"]
        self.ch2_init_freq = self.main_ui.param_config["mw_ch2_freq"]["value"]
        
        self.ch1_init_fm_sens = self.main_ui.param_config["mw_ch1_fm_sens"]["value"]
        self.ch2_init_fm_sens = self.main_ui.param_config["mw_ch2_fm_sens"]["value"]

        self.ch1_init_power = self.main_ui.param_config["mw_ch1_power"]["value"]
        self.ch2_init_power = self.main_ui.param_config["mw_ch2_power"]["value"]

        # 将实验中不用到的通道设成非共振状态
        if mw_channel == 0:
            self.main_ui.set_param(name="mw_ch2_fm_sens", value=0, ui_flag=False, delay_flag=False)
            self.main_ui.set_param(name="mw_ch2_power", value=0, ui_flag=False, delay_flag=False)
            self.main_ui.set_param(name="mw_ch2_freq", value=2.6e9, ui_flag=False, delay_flag=False)
        else:
            self.main_ui.set_param(name="mw_ch1_fm_sens", value=0, ui_flag=False, delay_flag=False)
            self.main_ui.set_param(name="mw_ch1_power", value=0, ui_flag=False, delay_flag=False)
            self.main_ui.set_param(name="mw_ch1_freq", value=2.6e9, ui_flag=False, delay_flag=False)

        while self.running and current_mw_freq <= stop_mw_freq:
            mw_list.append(current_mw_freq)
            if mw_channel == 0:
                self.main_ui.set_param(name="mw_ch1_freq", value=str(current_mw_freq), ui_flag=False, delay_flag=False)
            else:
                self.main_ui.set_param(name="mw_ch2_freq", value=str(current_mw_freq), ui_flag=False, delay_flag=False)
            # print(f'开始采集CW数据')
            iir_data = self.parent.parent.parent.dev.IIR_play(
                data_num=single_point_num)
            # print(f'结束采集CW数据')
            iir_1x = np.mean(iir_data[1])
            iir_1y = np.mean(iir_data[2])
            iir_2x = np.mean(iir_data[7])
            iir_2y = np.mean(iir_data[8])

            iir_1x_list.append(iir_1x)
            iir_2x_list.append(iir_2x)
            iir_1y_list.append(iir_1y)
            iir_2y_list.append(iir_2y)

            # print('[CH1-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[1]), np.mean(IIR_data[1])))
            # print('[CH1-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[2]), np.mean(IIR_data[2])))
            # print('[CH1-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[7]), np.mean(IIR_data[7])))
            # print('[CH1-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[8]), np.mean(IIR_data[8])))

             # print('[CH2-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[4]), np.mean(IIR_data[4])))
            # print('[CH2-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[5]), np.mean(IIR_data[5])))
            # print('[CH2-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[10]), np.mean(IIR_data[10])))
            # print('[CH2-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[11]), np.mean(IIR_data[11])))

            self.data_updated.emit(current_mw_freq, iir_1x, iir_1y, iir_2x, iir_2y)
            current_mw_freq += step_mw_freq
            # QThread.sleep(self.acq_interval)

        slope1, res_freq1, res_value1 = self.cal_max_slope(mw_list, iir_1x_list)
        slope2, res_freq2, res_value2 = self.cal_max_slope(mw_list, iir_2x_list)

        phase_ch1 = self.cal_phase_angle(iir_1x_list, iir_1y_list)
        phase_ch2 = self.cal_phase_angle(iir_2x_list, iir_2y_list)

        logging.info(f"CH1 斜率：{slope1:.3e}V/Hz 共振频率：{res_freq1:.1f}Hz 谱线相位：{phase_ch1:.3f}° 最大X幅度：{np.max(iir_1x_list) * 1e3:.3f}mV 最大幅度频点：{mw_list[np.argmax(iir_1x_list)]:.1f}Hz")
        logging.info(f"CH2 斜率：{slope2:.3e}V/Hz 共振频率：{res_freq2:.1f}Hz 谱线相位：{phase_ch2:.3f}° 最大X幅度：{np.max(iir_2x_list) * 1e3:.3f}mV 最大幅度频点：{mw_list[np.argmax(iir_2x_list)]:.1f}Hz")
        
        # 发送测量完成信号
        self.measurement_finished.emit()
        self.stop()


    def stop(self):
        logging.info("结束CW谱数据采集。")
        self.running = False


# ----------------- ViewModel -----------------
class OscilloscopeCWViewModel(QObject):
    data_ready = Signal(np.float64, np.float64, np.float64, np.float64, np.float64)
    measurement_completed = Signal()  # 添加测量完成信号

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = OscilloscopeCWModel(self)
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
class OscilloscopeCWPanel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        if hasattr(self.parent, 'save_dir_cw'):
            self.save_dir = self.parent.save_dir_cw
        else:
            self.save_dir = './'
        self.setWindowTitle("CW谱数据采集")
        self.resize(1000, 600)

        self.state_manager = parent.state_manager
        self.state_manager.state_changed.connect(self.on_state_changed)

        self.vm = OscilloscopeCWViewModel(self)
        self.vm.data_ready.connect(self.update_display)
        self.vm.measurement_completed.connect(self.on_measurement_completed)  # 连接测量完成信号

        self.mw_freq = []
        self.ch1_x = []
        self.ch1_y = []
        self.ch2_x = []
        self.ch2_y = []
        
        # 谱线计算相关变量
        self.spectrum_calc_enabled = False
        
        # 辅助线相关变量
        self.auxiliary_lines_ch1 = []
        self.auxiliary_lines_ch2 = []
        
        # 状态跟踪变量
        self.ch1_cw_updated = False
        self.ch2_cw_updated = False

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
        self.ch1_x = []  # 无限缓存
        self.ch1_y = []  # 无限缓存
        self.ch2_x = []  # 无限缓存
        self.ch2_y = []  # 无限缓存
        
        # 重置CW谱更新状态
        self.ch1_cw_updated = False
        self.ch2_cw_updated = False

        
        # 清除辅助线
        self.clear_auxiliary_lines()
        
        # 重置span区间到默认范围
        if self.spectrum_calc_enabled:
            start_freq = float(self.start_freq_input.text()) * 1e6
            end_freq = float(self.end_freq_input.text()) * 1e6
            self.span_ch1.setRegion([start_freq, end_freq])
            self.span_ch2.setRegion([start_freq, end_freq])

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

                # 增加微波通道选择下拉框
        freq_layout.addWidget(QLabel("微波通道选择:"))
        self.mw_channel_combo = QComboBox()
        self.mw_channel_combo.addItems(["微波通道1", "微波通道2"])
        self.mw_channel_combo.setCurrentIndex(0)  # 默认选择通道1
        freq_layout.addWidget(self.mw_channel_combo)

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

        # 谱线参数计算GroupBox
        self.spectrum_calc_groupbox = QGroupBox("谱线参数计算")
        self.spectrum_calc_checkbox = QCheckBox("启用谱线参数计算")
        self.spectrum_calc_checkbox.setChecked(False)
        self.spectrum_calc_checkbox.toggled.connect(self.on_spectrum_calc_toggled)
        
        # 参数设置容器
        self.spectrum_calc_content = QWidget()
        spectrum_calc_layout = QVBoxLayout()
        
        # 参数设置
        param_layout = QHBoxLayout()
        
        param_layout.addWidget(QLabel("线性拟合频率区间长度(MHz):"))
        self.fit_length_input = QLineEdit()
        self.fit_length_input.setText('3')
        self.fit_length_input.setFixedWidth(100)
        param_layout.addWidget(self.fit_length_input)
        
        param_layout.addWidget(QLabel("插值后频率步进(MHz):"))
        self.interp_step_input = QLineEdit()
        self.interp_step_input.setText('0.01')
        self.interp_step_input.setFixedWidth(100)
        param_layout.addWidget(self.interp_step_input)
        
        # 添加CH1和CH2分开的计算按钮
        self.calc_ch1_btn = QPushButton("计算CH1谱线参数")
        self.calc_ch1_btn.clicked.connect(lambda: self.calculate_spectrum_parameters_channel(1))
        self.calc_ch1_btn.setEnabled(False)  # 初始禁用
        param_layout.addWidget(self.calc_ch1_btn)
        
        self.calc_ch2_btn = QPushButton("计算CH2谱线参数")
        self.calc_ch2_btn.clicked.connect(lambda: self.calculate_spectrum_parameters_channel(2))
        self.calc_ch2_btn.setEnabled(False)  # 初始禁用
        param_layout.addWidget(self.calc_ch2_btn)
        
        spectrum_calc_layout.addLayout(param_layout)
        self.spectrum_calc_content.setLayout(spectrum_calc_layout)
        
        # 外层GroupBox布局
        outer_spectrum_layout = QVBoxLayout()
        outer_spectrum_layout.addWidget(self.spectrum_calc_checkbox)
        self.span_ch1_label = QLabel("CH1谱线参数计算区间:")
        outer_spectrum_layout.addWidget(self.span_ch1_label)
        self.span_ch2_label = QLabel("CH2谱线参数计算区间:")
        outer_spectrum_layout.addWidget(self.span_ch2_label)
        outer_spectrum_layout.addWidget(self.spectrum_calc_content)
        self.spectrum_calc_groupbox.setLayout(outer_spectrum_layout)
        
        # 初始状态设置为折叠
        self.spectrum_calc_content.setVisible(False)
        
        layout.addLayout(control_layout)
        layout.addWidget(self.spectrum_calc_groupbox)

        self.label_coord = QLabel("X: -- , Y: --")
        layout.addWidget(self.label_coord)

        # 时域图 CH1 & CH2
        self.plot_ch1 = pg.PlotWidget(title="CH1 CW谱")
        self.plot_ch1.showGrid(x=True, y=True)
        self.plot_ch2 = pg.PlotWidget(title="CH2 CW谱")
        self.plot_ch2.showGrid(x=True, y=True)

        self.plot_ch1.setLabel("left", "Voltage", units="V")
        self.plot_ch1.setLabel("bottom", "Frequency", units="Hz")

        self.plot_ch2.setLabel("left", "Voltage", units="V")
        self.plot_ch2.setLabel("bottom", "Frequency", units="Hz")

        # 添加legend
        self.plot_ch1.addLegend()
        self.plot_ch2.addLegend()

        self.curve_ch1 = self.plot_ch1.plot(pen='b', name='CH1-X')
        self.curve_ch3 = self.plot_ch1.plot(pen='r', name='CH1-Y')


        self.curve_ch2 = self.plot_ch2.plot(pen='y', name='CH2-X')

        self.curve_ch4 = self.plot_ch2.plot(pen='g', name='CH2-Y')

        # 添加可拖动的span区间
        self.span_ch1 = pg.LinearRegionItem()
        self.span_ch1.setZValue(10)
        self.span_ch1.setVisible(False)  # 初始不可见
        self.plot_ch1.addItem(self.span_ch1)

        self.span_ch2 = pg.LinearRegionItem()
        self.span_ch2.setZValue(10)
        self.span_ch2.setVisible(False)  # 初始不可见
        self.plot_ch2.addItem(self.span_ch2)
        
        # 移除span变化信号连接，改为按钮触发
        self.span_ch1.sigRegionChanged.connect(self.on_span_changed)
        self.span_ch2.sigRegionChanged.connect(self.on_span_changed)

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
            # self.save_data()
            # self.reset_mw_params()
        elif state == DevState.IDLE:
            self.init_start_time = time.time()
            self.flush_buffer()
            self.start_btn.setText("停止采集")
            self.state_manager.set_state(DevState.EXP_RUNNING)
            self.vm.start()

    def on_measurement_completed(self):
        """测量完成时的回调函数，在主线程中执行"""
        self.start_btn.setText("开始采集")
        self.state_manager.set_state(DevState.IDLE)
        self.vm.stop()
        self.save_data()
        self.reset_mw_params()

    def reset_mw_params(self):
        # 避免采集结束后微波参数被修改，和主UI保持一致
        logging.info("重设微波参数到初始值")
        self.parent.set_param(name="mw_ch1_freq", value=self.vm.model.ch1_init_freq, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch2_freq", value=self.vm.model.ch2_init_freq, ui_flag=True, delay_flag=False)

        self.parent.set_param(name="mw_ch1_fm_sens", value=self.vm.model.ch1_init_fm_sens, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch2_fm_sens", value=self.vm.model.ch2_init_fm_sens, ui_flag=True, delay_flag=False)

        # 最后一次参数设置直接下发到底层，delay_flag=False
        self.parent.set_param(name="mw_ch1_power", value=self.vm.model.ch1_init_power, ui_flag=True, delay_flag=False)
        self.parent.set_param(name="mw_ch2_power", value=self.vm.model.ch2_init_power, ui_flag=True, delay_flag=False)

    def update_display(self, mwf, iir_1x, iir_1y, iir_2x, iir_2y):
        self.mw_freq.append(mwf)
        self.ch1_x.append(iir_1x)
        self.ch1_y.append(iir_1y)
        self.ch2_x.append(iir_2x)
        self.ch2_y.append(iir_2y)

        self.curve_ch1.setData(self.mw_freq, self.ch1_x)
        self.curve_ch2.setData(self.mw_freq, self.ch2_x)

        self.curve_ch3.setData(self.mw_freq, self.ch1_y)
        self.curve_ch4.setData(self.mw_freq, self.ch2_y)

        # 发送CW谱更新状态信号
        # if not self.ch1_cw_updated and len(self.ch1_x) > 0:
        #     self.ch1_cw_updated = True
        #     if hasattr(self.parent, 'ch1_cw_updated_signal'):
        #         self.parent.ch1_cw_updated_signal.emit(True)
        #
        # if not self.ch2_cw_updated and len(self.ch2_x) > 0:
        #     self.ch2_cw_updated = True
        #     if hasattr(self.parent, 'ch2_cw_updated_signal'):
        #         self.parent.ch2_cw_updated_signal.emit(True)

        # 移除自动触发计算，改为按钮触发
        # if self.spectrum_calc_enabled:
        #     self.calculate_spectrum_parameters()

        # 启用计算按钮（如果有数据且启用了谱线计算）
        if self.spectrum_calc_enabled and len(self.mw_freq) > 0:
            self.calc_ch1_btn.setEnabled(True)
            self.calc_ch2_btn.setEnabled(True)

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
        path = self.save_dir + gettimestr() + '_cw.csv'
        if path:
            arr = np.column_stack((self.mw_freq, self.ch1_x, self.ch1_y, self.ch2_x, self.ch2_y))
            np.savetxt(path, arr, delimiter=",",
                       header=f"%IIR模式增益系数={self.parent.param_config['lockin_iir_gain']['value']} V\n"
                              f"%单点CW采集累加次数={self.single_point_num_input.text()}\n"
                              f"%微波通道选择={self.mw_channel_combo.currentText()}\n"
                              f"%激光器电流={self.parent.param_config['laser_power']['value']} A\n"
                              f"%微波CH1功率={self.parent.param_config['mw_ch1_power']['value']} dBm\n"
                              f"%微波CH2功率={self.parent.param_config['mw_ch2_power']['value']} dBm\n"
                              f"%微波CH1调制深度={self.parent.param_config['mw_ch1_fm_sens']['value']}\n"
                              f"%微波CH2调制深度={self.parent.param_config['mw_ch2_fm_sens']['value']}\n"
                              f"%CH1调制频率={self.parent.param_config['lockin_modu_freq1']['value']} Hz\n"
                              f"%CH2调制频率={self.parent.param_config['lockin_modu_freq2']['value']} Hz\n"
                              f"%MW Freq (Hz), CH1-X(Hz), CH1-Y(Hz), CH2-X(Hz), CH2-Y(Hz)\n",
                       comments='% ')
            self.parent.save_exp_config(self.save_dir)
            self.save_image()
            QMessageBox.information(self, "保存成功", f"IIR模式数据已保存为 {path}")

    def save_image(self):
        time_str = gettimestr()
        path_ch1 = self.save_dir + time_str + '_cw_ch1.png'
        path_ch2 = self.save_dir + time_str + '_cw_ch2.png'
        # path, _ = QFileDialog.getSaveFileName(self, "保存图像", "plot.png", "PNG Files (*.png)")
        exporter_ch1 = ImageExporter(self.plot_ch1.plotItem)
        exporter_ch2 = ImageExporter(self.plot_ch2.plotItem)
        exporter_ch1.export(path_ch1)
        exporter_ch2.export(path_ch2)

    def on_spectrum_calc_toggled(self, checked):
        """谱线参数计算复选框状态改变处理"""
        self.spectrum_calc_enabled = checked
        self.spectrum_calc_content.setVisible(checked)
        
        # 设置span区间可见性
        self.span_ch1.setVisible(checked)
        self.span_ch2.setVisible(checked)
        
        # 启用/禁用计算按钮
        has_data = len(self.mw_freq) > 0
        self.calc_ch1_btn.setEnabled(checked and has_data)
        self.calc_ch2_btn.setEnabled(checked and has_data)
        
        if checked and len(self.mw_freq) > 2:
            # 设置span区间默认范围
            # start_freq = float(self.start_freq_input.text()) * 1e6
            # end_freq = float(self.end_freq_input.text()) * 1e6
            start_freq = self.mw_freq[0]
            end_freq = self.mw_freq[-1]
            self.span_ch1.setRegion([start_freq, end_freq])
            self.span_ch2.setRegion([start_freq, end_freq])
            
            # 移除自动触发计算
            # self.calculate_spectrum_parameters()

    def update_calc_region_text(self):
        if self.spectrum_calc_enabled:
            span_ch1 = self.span_ch1.getRegion()
            span_ch2 = self.span_ch2.getRegion()
            self.span_ch1_label.setText(f"CH1计算区域区间: {span_ch1[0]/1e6:.3f}MHz - {span_ch1[1]/1e6:.3f}MHz (区间长度：{span_ch1[1]/1e6-span_ch1[0]/1e6:.3f}MHz)")
            self.span_ch2_label.setText(f"CH2计算区域区间: {span_ch2[0]/1e6:.3f}MHz - {span_ch2[1]/1e6:.3f}MHz (区间长度：{span_ch2[1]/1e6-span_ch2[0]/1e6:.3f}MHz)")

    def on_span_changed(self):
        """span区间改变时触发谱线计算"""
        # if self.spectrum_calc_enabled:
            # self.calculate_spectrum_parameters()
        self.update_calc_region_text()

    def clear_auxiliary_lines(self):
        """清除所有辅助线"""
        # 清除CH1辅助线
        for line in self.auxiliary_lines_ch1:
            self.plot_ch1.removeItem(line)
        self.auxiliary_lines_ch1.clear()
        
        # 清除CH2辅助线
        for line in self.auxiliary_lines_ch2:
            self.plot_ch2.removeItem(line)
        self.auxiliary_lines_ch2.clear()

    def draw_auxiliary_lines(self, ch1_result, ch2_result):
        """绘制辅助线"""
        # 清除之前的辅助线
        self.clear_auxiliary_lines()
        
        if ch1_result:
            # CH1幅度辅助线（水平线）
            max_amp_line_ch1 = pg.InfiniteLine(pos=ch1_result['max_amplitude_value'], 
                                             angle=0, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
            min_amp_line_ch1 = pg.InfiniteLine(pos=ch1_result['min_amplitude_value'], 
                                             angle=0, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
            
            # CH1线宽辅助线（竖直线）
            max_freq_line_ch1 = pg.InfiniteLine(pos=ch1_result['max_amplitude_freq'], 
                                              angle=90, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            min_freq_line_ch1 = pg.InfiniteLine(pos=ch1_result['min_amplitude_freq'], 
                                              angle=90, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            
            # CH1斜率辅助线（在谱线上绘制直线斜率）
            if len(self.mw_freq) > 1:
                # 计算斜率线的两个点
                slope = ch1_result['slope']
                res_freq = ch1_result['resonance_freq']
                res_value = ch1_result['resonance_value']
                
                # 在共振频率附近取一段区间绘制斜率线
                fit_length = ch1_result['fit_length_mhz'] * 1e6
                start_freq = res_freq - fit_length / 2
                end_freq = res_freq + fit_length / 2
                
                print(f'画图时 斜率={slope}V/Hz  共振频率={res_freq:.3f}Hz  共振值={res_value:.3f}  拟合长度={fit_length:.3f}Hz  起始频率={start_freq:.3f}Hz  终止频率={end_freq:.3f}Hz')
                slope_x = [start_freq, end_freq]

                print(f'画图幅度 {res_value - slope * (start_freq - res_freq)}, {res_value + slope * (end_freq - res_freq)}')
                slope_y = [res_value - slope * (start_freq - res_freq),
                          res_value + slope * (end_freq - res_freq)]
                
                slope_line_ch1 = pg.PlotDataItem(x=slope_x, y=slope_y, 
                                               pen=pg.mkPen('orange', width=2, style=Qt.DashLine))
                
                self.plot_ch1.addItem(slope_line_ch1)
                self.auxiliary_lines_ch1.append(slope_line_ch1)
            
            # 添加辅助线到图表
            self.plot_ch1.addItem(max_amp_line_ch1)
            self.plot_ch1.addItem(min_amp_line_ch1)
            self.plot_ch1.addItem(max_freq_line_ch1)
            self.plot_ch1.addItem(min_freq_line_ch1)
            
            self.auxiliary_lines_ch1.extend([max_amp_line_ch1, min_amp_line_ch1, max_freq_line_ch1, min_freq_line_ch1])
        
        if ch2_result:
            # CH2幅度辅助线（水平线）
            max_amp_line_ch2 = pg.InfiniteLine(pos=ch2_result['max_amplitude_value'], 
                                             angle=0, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
            min_amp_line_ch2 = pg.InfiniteLine(pos=ch2_result['zero_point_value'], 
                                             angle=0, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
            
            # CH2线宽辅助线（竖直线）
            max_freq_line_ch2 = pg.InfiniteLine(pos=ch2_result['max_amplitude_freq'], 
                                              angle=90, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            min_freq_line_ch2 = pg.InfiniteLine(pos=ch2_result['zero_point_freq'], 
                                              angle=90, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            
            # CH2斜率辅助线（在谱线上绘制直线斜率）
            if len(self.mw_freq) > 1:
                # 计算斜率线的两个点
                slope = ch2_result['slope']
                res_freq = ch2_result['resonance_freq']
                res_value = ch2_result['resonance_value']
                
                # 在共振频率附近取一段区间绘制斜率线
                fit_length_mhz = ch2_result['fit_length_mhz']
                start_freq = res_freq - fit_length_mhz * 1e6 / 2
                end_freq = res_freq + fit_length_mhz * 1e6 / 2
                
                print(f'CH2 画图时 斜率={slope}V/Hz  共振频率={res_freq:.3f}MHz  共振值={res_value:.3f}  拟合长度={fit_length_mhz}MHz  起始频率={start_freq:.3f}MHz  终止频率={end_freq:.3f}MHz')
                slope_x = [start_freq, end_freq]
                slope_y = [res_value - slope * (start_freq - res_freq),
                          res_value + slope * (end_freq - res_freq)]
                
                slope_line_ch2 = pg.PlotDataItem(x=slope_x, y=slope_y, 
                                               pen=pg.mkPen('orange', width=2, style=Qt.DashLine))
                
                self.plot_ch2.addItem(slope_line_ch2)
                self.auxiliary_lines_ch2.append(slope_line_ch2)
            
            # 添加辅助线到图表
            self.plot_ch2.addItem(max_amp_line_ch2)
            self.plot_ch2.addItem(min_amp_line_ch2)
            self.plot_ch2.addItem(max_freq_line_ch2)
            self.plot_ch2.addItem(min_freq_line_ch2)
            
            self.auxiliary_lines_ch2.extend([max_amp_line_ch2, min_amp_line_ch2, max_freq_line_ch2, min_freq_line_ch2])

    def calculate_spectrum_parameters_channel(self, channel):
        """执行指定通道的谱线参数计算"""
        if not self.spectrum_calc_enabled or len(self.mw_freq) < 3:
            return
            
        try:
            # 获取参数
            fit_length_mhz = float(self.fit_length_input.text())
            interp_step_mhz = float(self.interp_step_input.text())
            
            # 获取span区间范围
            if channel == 1:
                span_range = self.span_ch1.getRegion()
                x_data = self.ch1_x
                y_data = self.ch1_y
                channel_name = "CH1"
                
            else:
                span_range = self.span_ch2.getRegion()
                x_data = self.ch2_x
                y_data = self.ch2_y
                channel_name = "CH2"

            # 计算指定通道参数
            result = self.vm.model.calculate_spectrum_parameters(
                self.mw_freq, x_data, y_data, fit_length_mhz, interp_step_mhz, span_range
            )

            # 输出计算结果
            if result:
                eff_gyro = self.parent.param_config['nv_eff_gyromagnetic_ratio']['value']
                logging.info(f"※提示：更新斜率值到参数表中，从而保证电压-磁场转换系数实时性和准确性。\n\n"
                             f"[{channel_name} - 谱线参数计算]\n"
                             f"谱线零点频率: {result['zero_point_freq']/1e6:.3f}MHz\n"
                           f"最大斜率点频率: {result['resonance_freq']/1e6:.3f}MHz\n"
                           f"最大幅度点频率: {result['max_amplitude_freq']/1e6:.3f}MHz\n"
                           f"斜率: {result['slope']:.3e}V/Hz\n"
                           f"推算转换系数：{1 / (eff_gyro * result['slope']):.6e} T/V\n"
                           f"线宽: {result['linewidth']/1e6:.3f}MHz\n"
                           f"幅度峰峰值: {result['amplitude']:.3f}V\n"
                           f"幅度最大绝对值: {result['r_amplitude']:.3f}V\n"
                             )

                logging.info(f"※将{channel_name}斜率参数、谱线零点参数更新到系统设备中")
                # 更新最新系统斜率/谱线零点
                self.parent.set_param(f"nv_cw_slope_ch{channel}", result['slope'])
                self.parent.set_param(f"nv_res_freq_ch{channel}", result['zero_point_freq'])

                logging.info(f"※将{channel_name}非线性区幅度预警参数更新到系统设备中，取幅度最大绝对值的<60%>作为预警比例（{1e3 * result['r_amplitude']:.2f}mV）")
                self.parent.set_param(f"nv_linear_auto_adjust_warning_voltage_ch{channel}", result['r_amplitude'] * 0.60)



                # 绘制辅助线（只绘制对应通道的）
                if channel == 1:
                    self.draw_auxiliary_lines_channel(result, None)
                    if hasattr(self.parent, 'ch1_cw_updated_signal'):
                        self.parent.ch1_cw_updated_signal.emit(True)
                else:
                    self.draw_auxiliary_lines_channel(None, result)

                    if hasattr(self.parent, 'ch2_cw_updated_signal'):
                        self.parent.ch2_cw_updated_signal.emit(True)
                           
        except Exception as e:
            logging.error(f"{channel_name}谱线参数计算错误: {str(e)}, {traceback.print_exc()}")

    def clear_auxiliary_line_channel(self, channel):
        """清除指定通道的辅助线"""
        if channel == 1:
            for line in self.auxiliary_lines_ch1:
                self.plot_ch1.removeItem(line)
            self.auxiliary_lines_ch1.clear()
        else:
            for line in self.auxiliary_lines_ch2:
                self.plot_ch2.removeItem(line)
            self.auxiliary_lines_ch2.clear()

    def draw_auxiliary_lines_channel(self, ch1_result, ch2_result):
        """绘制指定通道的辅助线"""
        # 清除之前的辅助线
        
        if ch1_result:
            self.clear_auxiliary_line_channel(1)
            # CH1幅度辅助线（水平线）
            max_amp_line_ch1 = pg.InfiniteLine(pos=ch1_result['r_amplitude'] * 0.7,
                                             angle=0, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            min_amp_line_ch1 = pg.InfiniteLine(pos=-ch1_result['r_amplitude'] * 0.7,
                                             angle=0, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            #
            # CH1线宽辅助线（竖直线）
            max_freq_line_ch1 = pg.InfiniteLine(pos=ch1_result['max_amplitude_freq'], 
                                              angle=90, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            min_freq_line_ch1 = pg.InfiniteLine(pos=ch1_result['min_amplitude_freq'],
                                              angle=90, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            zero_freq_line_ch1 = pg.InfiniteLine(pos=ch1_result['zero_point_freq'],
                                                angle=90, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
            
            # CH1斜率辅助线（在谱线上绘制直线斜率）
            if len(self.mw_freq) > 1:
                # 计算斜率线的两个点
                slope = ch1_result['slope']
                res_freq = ch1_result['resonance_freq']
                res_value = ch1_result['resonance_value']
                
                # 在共振频率附近取一段区间绘制斜率线
                fit_length = ch1_result['fit_length_mhz'] * 1e6
                start_freq = res_freq  - fit_length / 2
                end_freq = res_freq  + fit_length / 2
                
                slope_x = [start_freq, end_freq]
                slope_y = [res_value - slope * (res_freq - start_freq),
                          res_value + slope * (end_freq - res_freq)]
                
                # print(f'CH1 画图时 斜率={slope}V/Hz  共振频率={res_freq:.3f}Hz  共振值={res_value:.3f}  拟合长度={fit_length:.3f}Hz  起始频率={start_freq:.3f}Hz  终止频率={end_freq:.3f}Hz')
                # print(f'画图幅度 {res_value - slope * (start_freq - res_freq)}, {res_value + slope * (end_freq - res_freq)}')

                slope_line_ch1 = pg.PlotDataItem(x=slope_x, y=slope_y, 
                                               pen=pg.mkPen('orange', width=2, style=Qt.DashLine))
                
                self.plot_ch1.addItem(slope_line_ch1)
                self.auxiliary_lines_ch1.append(slope_line_ch1)
            
            # 添加辅助线到图表
            # self.plot_ch1.addItem(max_amp_line_ch1) 
            # self.plot_ch1.addItem(min_amp_line_ch1)
            self.plot_ch1.addItem(max_freq_line_ch1)
            self.plot_ch1.addItem(min_freq_line_ch1)
            self.plot_ch1.addItem(zero_freq_line_ch1)
            self.plot_ch1.addItem(max_amp_line_ch1)
            self.plot_ch1.addItem(min_amp_line_ch1)

            self.auxiliary_lines_ch1.extend([max_freq_line_ch1, min_freq_line_ch1, zero_freq_line_ch1, max_amp_line_ch1, min_amp_line_ch1])
        
        if ch2_result:
            self.clear_auxiliary_line_channel(2)
            # CH2幅度辅助线（水平线）
            max_amp_line_ch2 = pg.InfiniteLine(pos=ch2_result['r_amplitude'] * 0.7,
                                               angle=0, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            min_amp_line_ch2 = pg.InfiniteLine(pos=-ch2_result['r_amplitude'] * 0.7,
                                               angle=0, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            
            # CH2线宽辅助线（竖直线）
            max_freq_line_ch2 = pg.InfiniteLine(pos=ch2_result['max_amplitude_freq'], 
                                              angle=90, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            min_freq_line_ch2 = pg.InfiniteLine(pos=ch2_result['min_amplitude_freq'],
                                              angle=90, pen=pg.mkPen('g', width=2, style=Qt.DashLine))
            zero_freq_line_ch2 = pg.InfiniteLine(pos=ch2_result['zero_point_freq'],
                                                angle=90, pen=pg.mkPen('r', width=2, style=Qt.DashLine))

            # CH2斜率辅助线（在谱线上绘制直线斜率）
            if len(self.mw_freq) > 1:
                # 计算斜率线的两个点
                slope = ch2_result['slope']
                res_freq = ch2_result['resonance_freq']
                res_value = ch2_result['resonance_value']
                
                # 在共振频率附近取一段区间绘制斜率线
                fit_length = ch2_result['fit_length_mhz'] * 1e6
                start_freq = res_freq  - fit_length / 2
                end_freq = res_freq  + fit_length / 2
                
                slope_x = [start_freq, end_freq]
                slope_y = [res_value - slope * (res_freq - start_freq),
                          res_value + slope * (end_freq - res_freq)]
                
                slope_line_ch2 = pg.PlotDataItem(x=slope_x, y=slope_y, 
                                               pen=pg.mkPen('orange', width=2, style=Qt.DashLine))
                
                self.plot_ch2.addItem(slope_line_ch2)
                self.auxiliary_lines_ch2.append(slope_line_ch2)
            
            # 添加辅助线到图表
            # self.plot_ch2.addItem(max_amp_line_ch2)
            # self.plot_ch2.addItem(min_amp_line_ch2)
            self.plot_ch2.addItem(max_freq_line_ch2)
            self.plot_ch2.addItem(min_freq_line_ch2)
            self.plot_ch2.addItem(zero_freq_line_ch2)
            self.plot_ch2.addItem(max_amp_line_ch2)
            self.plot_ch2.addItem(min_amp_line_ch2)

            self.auxiliary_lines_ch2.extend([max_freq_line_ch2, min_freq_line_ch2, zero_freq_line_ch2, max_amp_line_ch2, min_amp_line_ch2])
    #
    # def calculate_spectrum_parameters(self):
    #     """执行谱线参数计算（同时计算CH1和CH2）"""
    #     if not self.spectrum_calc_enabled or len(self.mw_freq) < 3:
    #         return
    #
    #     try:
    #         # 获取参数
    #         fit_length_mhz = float(self.fit_length_input.text())
    #         interp_step_mhz = float(self.interp_step_input.text())
    #
    #         # 获取span区间范围
    #         span_range_ch1 = self.span_ch1.getRegion()
    #         span_range_ch2 = self.span_ch2.getRegion()
    #
    #
    #         # 计算CH1参数
    #         ch1_result = self.vm.model.calculate_spectrum_parameters(
    #             self.mw_freq, self.ch1_x, self.ch1_y, fit_length_mhz, interp_step_mhz, span_range_ch1
    #         )
    #
    #         # 计算CH2参数
    #         ch2_result = self.vm.model.calculate_spectrum_parameters(
    #             self.mw_freq, self.ch2_x, self.ch2_y, fit_length_mhz, interp_step_mhz, span_range_ch2
    #         )
    #         eff_gyro = self.parent.param_config['nv_eff_gyromagnetic_ratio']['value']
    #
    #         # 输出计算结果
    #         if ch1_result:
    #             logging.info(f"※提示：更新斜率值到参数表中，从而保证电压-磁场转换系数实时性和准确性。\nCH1谱线参数 - 零点位置: {ch1_result['zero_point_freq']/1e6:.3f}MHz, "
    #                        f"最大幅度点: {ch1_result['max_amplitude_freq']/1e6:.3f}MHz, "
    #                        f"斜率: {ch1_result['slope']:.3e}V/Hz, "
    #                        f"推算转换系数：{1 / (eff_gyro * ch1_result['slope']):.6e} T/V， "
    #                        f"共振频率: {ch1_result['resonance_freq']/1e6:.3f}MHz, "
    #                        f"线宽: {ch1_result['linewidth']/1e6:.3f}MHz, "
    #                        f"幅度: {ch1_result['amplitude']:.3f}V")
    #
    #         if ch2_result:
    #             logging.info(f"※提示：更新斜率值到参数表中，从而保证电压-磁场转换系数实时性和准确性。\nCH2谱线参数 - 零点位置: {ch2_result['zero_point_freq']/1e6:.3f}MHz, "
    #                        f"最大幅度点: {ch2_result['max_amplitude_freq']/1e6:.3f}MHz, "
    #                        f"斜率: {ch2_result['slope']:.3e}V/Hz, "
    #                        f"推算转换系数：{1 / (eff_gyro * ch2_result['slope']):.6e} T/V， "
    #                        f"共振频率: {ch2_result['resonance_freq']/1e6:.3f}MHz, "
    #                        f"线宽: {ch2_result['linewidth']/1e6:.3f}MHz, "
    #                        f"幅度: {ch2_result['amplitude']:.3f}V")
    #
    #         # 绘制辅助线
    #         self.draw_auxiliary_lines(ch1_result, ch2_result)
    #
    #     except Exception as e:
    #         logging.error(f"谱线参数计算错误: {str(e)}")

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()
