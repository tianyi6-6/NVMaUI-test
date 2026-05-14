# encoding=utf-8
import time
import numpy as np
import PySide6.QtGui as QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox,QCheckBox,QComboBox,QDateTimeEdit,
    QGroupBox, QGridLayout
)
from PySide6.QtCore import QDateTime, QTimer, QThread, QObject, Signal
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from manager import *
from scipy.signal import detrend
import os
from data_process_tools import *


def gettimestr():
    import time
    return time.strftime('%Y-%m-%d %H_%M_%S', time.localtime(time.time()))

# ----------------- Timer Thread -----------------
class TimerThread(QThread):
    timer_finished = Signal()
    
    def __init__(self, target_time):
        super().__init__()
        self.target_time = target_time
        self._cancelled = False
        
    def run(self):
        while time.time() < self.target_time and not self._cancelled:
            time.sleep(0.001)  # 1ms检查间隔
        if not self._cancelled:
            self.timer_finished.emit()
    
    def cancel(self):
        self._cancelled = True

# ----------------- Model -----------------
class OscilloscopeIIRDCModel(QObject):
    # data_updated = Signal(np.ndarray)
    data_updated = Signal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray)
    reset_mw_param_signal = Signal()  # 新增：重置微波参数信号

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.panel_ui = parent.parent
        self.main_ui = parent.parent.parent
        self.running = False
        self.sample_rate = self.parent.parent.parent.param_config["lockin_sample_rate"]['value']
        self.sample_interval = 1 / self.sample_rate
        self.acq_time = 0.5 # 采集时长，单位为秒
        self.auto_save_time_interval = 300 # 自动保存时间间隔，单位为秒
        self.save_dir = None
        self.acq_save_start_time = None
        self.is_run = False
        self.ch1_init_freq = None
        self.ch2_init_freq = None

        self.ch1_init_fm_sens = None
        self.ch2_init_fm_sens = None

        self.ch1_init_power = None
        self.ch2_init_power = None

    def start(self):
        self.is_run = True
        logging.info(f"定时计时到达，准备开始进行IIR模式数据采集。定时保存时间间隔：{self.auto_save_time_interval} s")
        self.running = True
        self.panel_ui.flush_buffer()

        # 获取初始化微波参数
        self.ch1_init_freq = self.main_ui.param_config["mw_ch1_freq"]["value"]
        self.ch2_init_freq = self.main_ui.param_config["mw_ch2_freq"]["value"]

        self.ch1_init_fm_sens = self.main_ui.param_config["mw_ch1_fm_sens"]["value"]
        self.ch2_init_fm_sens = self.main_ui.param_config["mw_ch2_fm_sens"]["value"]

        self.ch1_init_power = self.main_ui.param_config["mw_ch1_power"]["value"]
        self.ch2_init_power = self.main_ui.param_config["mw_ch2_power"]["value"]

        ch1_res_freq = self.main_ui.param_config["nv_res_freq_ch1"]["value"]
        ch2_res_freq = self.main_ui.param_config["nv_res_freq_ch2"]["value"]

        # 获取微波工作模式
        # 0:不操作微波, 1: CH1单路微波, 2: CH2单路微波, 3: 双路微波, 4: 非共振状态
        mw_mode = self.panel_ui.mw_mode_combo.currentIndex()
        if mw_mode == 0:
            logging.info("进入IIR采集 - 微波模式: 不改变微波状态")
        elif mw_mode == 1:
            logging.info(f"进入IIR采集 - 微波模式: CH1单路微波，MW1设置到共振频率[{ch1_res_freq} Hz]上")
            self.main_ui.set_param("mw_ch2_freq", 2.6e9, ui_flag=False, delay_flag=False)
            self.main_ui.set_param("mw_ch2_fm_sens", 0, ui_flag=False, delay_flag=False)
            self.main_ui.set_param("mw_ch1_freq", ch1_res_freq, ui_flag=False, delay_flag=False)
        elif mw_mode == 2:
            logging.info(f"进入IIR采集 - 微波模式: CH2单路微波，MW1设置到共振频率[{ch2_res_freq} Hz]上")
            self.main_ui.set_param("mw_ch1_freq", 2.6e9, ui_flag=False, delay_flag=False)
            self.main_ui.set_param("mw_ch1_fm_sens", 0, ui_flag=False, delay_flag=False)
            self.main_ui.set_param("mw_ch2_freq", ch2_res_freq, ui_flag=False, delay_flag=False)
        elif mw_mode == 3:
            logging.info(f"进入IIR采集 - 微波模式: 双路微波，MW1设置到共振频率[{ch1_res_freq} Hz]且MW2设置到共振频率[{ch2_res_freq} Hz]上")
            self.main_ui.set_param("mw_ch1_freq", ch1_res_freq, ui_flag=False, delay_flag=True)
            self.main_ui.set_param("mw_ch2_freq", ch2_res_freq, ui_flag=False, delay_flag=False)
        elif mw_mode == 4:
            logging.info("进入IIR采集 - 微波模式: 非共振状态，两路微波频率都设置到2.6GHz处")
            self.main_ui.set_param("mw_ch1_freq", 2.6e9, ui_flag=False, delay_flag=False)
            self.main_ui.set_param("mw_ch2_freq", 2.6e9, ui_flag=False, delay_flag=False)
        

        init_start_time = time.time()
        # init_start_time = self.parent.get_start_time()
        self.acq_save_start_time = time.time()
        N = 0
        # todo: 替换为分条件采集
        self.save_dir = self.parent.parent.save_dir + f'IIR_data_{gettimestr()}/'
        if not os.path.exists(self.save_dir):
            os.mkdir(self.save_dir)
        self.parent.parent.parent.save_exp_config(self.save_dir)
        self.parent.parent.parent.dev.start_infinite_iir_acq() # 开始无限采集模式

        while self.running:
            # todo: 加入模拟采集数据，以及采样率、深度更新设置
            # data1 = np.random.normal(size=self.acq_pts)
            # data2 = np.random.normal(size=self.acq_pts) * 0.5
            start_time = time.time()
            try:
                iir_data = self.parent.parent.parent.dev.get_infinite_iir_points(data_num=int(self.sample_rate * self.acq_time))
            except:
                # self.parent.stop()
                break
            stop_time = time.time()
            mac_time = np.linspace(start_time, stop_time, len(iir_data[1]))
            # print('[CH1-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[1]), np.mean(IIR_data[1])))
            # print('[CH1-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[2]), np.mean(IIR_data[2])))
            # print('[CH1-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[7]), np.mean(IIR_data[7])))
            # print('[CH1-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[8]), np.mean(IIR_data[8])))

            # print('[CH2-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[4]), np.mean(IIR_data[4])))
            # print('[CH2-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[5]), np.mean(IIR_data[5])))
            # print('[CH2-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[10]), np.mean(IIR_data[10])))
            # print('[CH2-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[11]), np.mean(IIR_data[11])))
            # data1: Fluo-1X, data2: Laser-1X, data3: Fluo-DC, data4: Laser-DC, data5: Fluo-1Y, data6: Laser-1Y, data7: Fluo-2X, data8: Laser-2X, data9: Fluo-2Y, data10: Laser-2Y
            data1 = iir_data[1] # Fluo-1X
            data2 = iir_data[4] # Laser-1X
            
            data3 = iir_data[12] # Fluo - DC
            data4 = iir_data[13] # Laser - DC
            
            data5 = iir_data[2] # Fluo-1Y
            data6 = iir_data[5] # Laser-1Y

            data7 = iir_data[7] # Fluo-2X
            data8 = iir_data[10] # Laser-2X
            data9 = iir_data[8] # Fluo-2Y
            data10 = iir_data[11] # Laser-2Y
            
            N_new = len(data1)

            time_data = np.linspace(init_start_time + N * self.sample_interval, 
                                    init_start_time + (N + N_new) * self.sample_interval, 
                                    len(data1), 
                                    endpoint=False)

            N += N_new

            self.data_updated.emit(mac_time, time_data, data1, data2, data3, data4, data5, data6, data7, data8, data9, data10)
            # QThread.sleep(self.acq_interval)
        self.is_run = False

    def stop(self, reset_mw_param_flag=True):
        logging.info("结束IIR模式数据采集。")
        self.running = False
        while self.is_run:
            time.sleep(0.001)
        self.parent.parent.parent.dev.stop_infinite_iir_acq()
        self.parent.parent.save_data()
        # 发送重置微波参数信号
        if reset_mw_param_flag:
            self.reset_mw_param_signal.emit()

    def set_sample_rate(self, rate):
        self.sample_rate = rate
        self.sample_interval = 1.0 / rate
    
    def set_auto_save_time_interval(self, interval):
        self.auto_save_time_interval = interval

# ----------------- ViewModel -----------------
class OscilloscopeIIRDCViewModel(QObject):
    data_ready = Signal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray)
    reset_mw_param_requested = Signal()  # 新增：重置微波参数请求信号

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.model = OscilloscopeIIRDCModel(self)
        self.thread = QThread()
        self.model.moveToThread(self.thread)

        self.thread.started.connect(self.model.start)
        self.model.data_updated.connect(self.data_ready)
        self.model.reset_mw_param_signal.connect(self.reset_mw_param_requested)  # 连接重置信号
        self.start_time = None
        
        # 添加定时器线程
        self.timer_thread = None

    def get_start_time(self):
        return self.start_time

    def start(self):
        target_start_time = self.parent.get_start_time()
        self.start_time = target_start_time
        
        # 如果目标时间已经过去，直接开始
        if time.time() >= target_start_time:
            if not self.thread.isRunning():
                self.thread.start()
            return
            
        # 创建定时器线程
        self.timer_thread = TimerThread(target_start_time)
        self.timer_thread.timer_finished.connect(self._on_timer_finished)
        self.timer_thread.start()
        
        # 通知UI更新状态
        if hasattr(self.parent, 'on_timer_started'):
            self.parent.on_timer_started()

    def _on_timer_finished(self):
        """定时器完成时的回调"""
        if not self.thread.isRunning():
            self.thread.start()
        self.timer_thread = None
        # 通知UI更新按钮状态
        if hasattr(self.parent, 'on_timer_finished'):
            self.parent.on_timer_finished()

    def save_data(self, ui_mode=False):
        self.parent.save_data(ui_mode)

    def stop(self, reset_mw_param_flag=True):
        # 取消定时器线程
        if self.timer_thread and self.timer_thread.isRunning():
            self.timer_thread.cancel()
            self.timer_thread.wait()
            self.timer_thread = None
            
        # 停止数据采集线程
        self.model.stop(reset_mw_param_flag)
        self.thread.quit()
        self.thread.wait()

    def change_sample_rate(self, rate):
        self.model.set_sample_rate(rate)
    
    def change_auto_save_time_interval(self, interval):
        self.model.set_auto_save_time_interval(interval)


# ----------------- View -----------------
class OscilloscopeIIRDCPanel(QWidget):
    reset_linear_region_signal = Signal()
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

        self.vm = OscilloscopeIIRDCViewModel(self)
        self.vm.data_ready.connect(self.update_display)
        self.vm.reset_mw_param_requested.connect(self.reset_mw_param)  # 连接重置信号
        self.reset_linear_region_signal.connect(self.reset_linear_region) # 重置线性区

        # 数据缓存
        self.full_data1 = []  # 无限缓存
        self.full_data2 = []
        self.full_data3 = []
        self.full_data4 = []
        self.full_data5 = []
        self.full_data6 = []
        self.full_data7 = []
        self.full_data8 = []
        self.full_data9 = []
        self.full_data10 = []
        self.full_time_data = []
        self.full_mac_time = []
        
        # 新增：记录已保存的数据长度，避免重叠保存
        self.saved_data_length = 0
        
        self.init_start_time = time.time()
        
        self.acq_time = 60
        self.display_length = 1000  # 屏幕显示长度（可调）
        
        # 新增：微波模式相关变量
        self.mw_mode = 0  # 0:不操作微波, 1: CH1单路微波, 2: CH2单路微波, 3: 双路微波, 4: 非共振状态
        
        # 新增：通道显示相关变量
        self.show_ch1 = True
        self.show_ch2 = True
        
        # 新增：参考路相消相关变量
        self.reference_cancellation_enabled = False  # 0: 不启动, 1: 启动
        
        # 新增：实时滤波相关变量
        self.realtime_filter_enabled = True
        self.filter_mode = 0  # 0: 带通, 1: 高通, 2: 低通
        self.filter_type = 0  # 滤波器种类
        self.filter_start_freq = 1e-3
        self.filter_stop_freq = 0.5
        self.filter_avg_pts = 50 # 平均滤波点数
        
        # 新增：非线性区自动校正相关变量
        self.nonlinear_threshold_mv = 100.0  # 非线性区识别阈值幅度(mV)
        self.nonlinear_duration_s = 60.0  # 非线性区持续判定时间(s)
        self.nonlinear_auto_correction_enabled = False  # 非线性区自动校正功能开关
        
        self.init_ui()

    def on_state_changed(self, state):
        if state == DevState.OFFLINE:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
            self.mw_mode_combo.setEnabled(True)  # 锁定微波模式选择
        elif state == DevState.IDLE:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
            self.mw_mode_combo.setEnabled(True)  # 解锁微波模式选择
        elif state == DevState.IIR_RUNNING:
            self.start_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
            self.mw_mode_combo.setEnabled(False)  # 锁定微波模式选择
        else:
            self.start_btn.setEnabled(False)
            self.save_btn.setEnabled(True)
            self.mw_mode_combo.setEnabled(True)  # 锁定微波模式选择

    def flush_buffer(self):
        self.full_data1 = []  # 无限缓存
        self.full_data2 = []
        self.full_data3 = []
        self.full_data4 = []
        self.full_data5 = []
        self.full_data6 = []
        self.full_data7 = []
        self.full_data8 = []
        self.full_data9 = []
        self.full_data10 = []
        self.full_time_data = []
        self.full_mac_time = []
        self.saved_data_length = 0  # 重置已保存数据长度
        self.init_start_time = time.time()

    def handle_linear_auto_adjust_change(self):
        if self.linear_auto_adjust_combo.currentIndex() == 0:
            self.linear_auto_adjust_flag = 0 # 关闭
        else:
            self.linear_auto_adjust_flag = 1 # 开启，自动校正

    def handle_mw_mode_change(self):
        """处理微波模式变化"""
        self.mw_mode = self.mw_mode_combo.currentIndex()
        logging.info(f"微波模式已切换为: {self.mw_mode_combo.currentText()}")

    def handle_channel_display_change(self):
        """处理通道显示开关变化"""
        self.show_ch1 = self.ch1_display_checkbox.isChecked()
        self.show_ch2 = self.ch2_display_checkbox.isChecked()
        # self.update_channel_visibility()

    def handle_reference_cancellation_change(self):
        """处理参考路相消开关变化"""
        self.reference_cancellation_enabled = self.reference_cancellation_combo.currentIndex()
        # logging.info(f"参考路相消: {'启动' if self.reference_cancellation_enabled == 1 else '不启动'}")

    def handle_realtime_filter_change(self):
        """处理实时滤波开关变化"""
        self.realtime_filter_enabled = self.realtime_filter_checkbox.isChecked()
        # self.update_filter_controls_visibility()
        # logging.info(f"实时滤波: {'开启' if self.realtime_filter_enabled else '关闭'}")

    def update_filter_controls_visibility(self):
        """更新滤波控件可见性"""
        visible = self.realtime_filter_enabled
        self.filter_mode_combo.setVisible(visible)
        self.filter_type_combo.setVisible(visible)
        self.filter_mode_qlabel.setVisible(visible)
        self.filter_type_qlabel.setVisible(visible)
        self.filter_start_freq_qlabel.setVisible(visible)
        self.filter_start_freq_input.setVisible(visible)
        self.filter_stop_freq_qlabel.setVisible(visible)
        self.filter_stop_freq_input.setVisible(visible)

    def handle_filter_mode_change(self):
        """处理滤波模式变化"""
        self.filter_mode = self.filter_mode_combo.currentIndex()
        # logging.info(f"滤波模式: {self.filter_mode_combo.currentText()}")

    def handle_filter_type_change(self):
        """处理滤波器种类变化"""
        self.filter_type = self.filter_type_combo.currentIndex()
        # logging.info(f"滤波器种类: {self.filter_type_combo.currentText()}")

    def handle_nonlinear_threshold_change(self):
        """处理非线性区识别阈值变化"""
        try:
            self.nonlinear_threshold_mv = float(self.nonlinear_threshold_input.text())
            # logging.info(f"非线性区识别阈值: {self.nonlinear_threshold_mv} mV")
        except ValueError:
            logging.warning("非线性区识别阈值输入无效，使用默认值")
    
    def handle_nonlinear_duration_change(self):
        """处理非线性区持续判定时间变化"""
        try:
            self.nonlinear_duration_s = float(self.nonlinear_duration_input.text())
            # logging.info(f"非线性区持续判定时间: {self.nonlinear_duration_s} s")
        except ValueError:
            logging.warning("非线性区持续判定时间输入无效，使用默认值")
    
    def handle_nonlinear_auto_correction_change(self):
        """处理非线性区自动校正功能开关变化"""
        self.nonlinear_auto_correction_enabled = self.nonlinear_auto_correction_checkbox.isChecked()
        logging.info(f"非线性区自动校正: {'开启' if self.nonlinear_auto_correction_enabled else '关闭'}")
    
    def handle_display_settings_toggle(self, checked):
        """处理显示设置GroupBox折叠/展开状态变化"""
        if checked:
            # 展开：显示所有显示设置控件
            self.ch1_display_checkbox.setVisible(True)
            self.ch2_display_checkbox.setVisible(True)
            self.reference_cancellation_combo.setVisible(True)
            # self.length_input.setVisible(True)
            self.volt_to_mag_mode_combo.setVisible(True)
            self.volt_or_mag_view_mode_combo.setVisible(True)
            # self.acq_trend_remove_checkbox.setVisible(True)
            self.filter_group.setVisible(True)
            self.nonlinear_group.setVisible(True)
            self.time_or_freq_switch_combo.setVisible(True)
            # 显示标签
            for i in range(self.display_settings_layout.count()):
                widget = self.display_settings_layout.itemAt(i).widget()
                if isinstance(widget, QLabel):
                    widget.setVisible(True)
            # logging.info("显示设置已展开")
        else:
            # 折叠：隐藏所有显示设置控件
            self.filter_group.setVisible(False)
            self.nonlinear_group.setVisible(False)
            self.ch1_display_checkbox.setVisible(False)
            self.ch2_display_checkbox.setVisible(False)
            self.reference_cancellation_combo.setVisible(False)
            # self.length_input.setVisible(False)
            self.volt_to_mag_mode_combo.setVisible(False)
            self.volt_or_mag_view_mode_combo.setVisible(False)
            # self.acq_trend_remove_checkbox.setVisible(False)
            self.time_or_freq_switch_combo.setVisible(False)

            # 隐藏标签
            for i in range(self.display_settings_layout.count()):
                widget = self.display_settings_layout.itemAt(i).widget()
                if isinstance(widget, QLabel):
                    widget.setVisible(False)
            # logging.info("显示设置已折叠")

    def reset_linear_region(self):
        """重置线性区"""
        logging.info("触发线性区重设功能")
        if not self.vm.model.is_run:
            logging.info("当前实验未运行，重置线性区操作无效")
            return
        if len(self.full_data1) < 100 or len(self.full_data7) < 100:
            logging.info("当前实验数据数量不足，重置线性区操作无效")
            return
        
        ch1_signal = np.mean(self.full_data1[-100:])
        ch2_signal = np.mean(self.full_data7[-100:])
        
        # 获取当前实验微波模式与参数
        # "不操作微波", "CH1单路微波", "CH2单路微波",   "双路微波"
        mw_mode = self.mw_mode_combo.currentIndex()
        # "基于斜率预测", "扫描重设微波参数"
        nonlinear_correction_mode = self.nonlinear_correction_mode_combo.currentIndex()

        non_linear_reset_ratio = self.parent.param_config["non_linear_reset_ratio"]["value"]
        ch1_res_freq = self.parent.param_config["nv_res_freq_ch1"]["value"]
        ch2_res_freq = self.parent.param_config["nv_res_freq_ch2"]["value"]
        ch1_slope = self.parent.param_config["nv_cw_slope_ch1"]["value"]
        ch2_slope = self.parent.param_config["nv_cw_slope_ch2"]["value"]
        lockin_modu_freq1 = self.parent.param_config["lockin_modu_freq1"]["value"]
        lockin_modu_freq2 = self.parent.param_config["lockin_modu_freq2"]["value"]
        double_modu_freq_flag = (lockin_modu_freq1 == lockin_modu_freq2)

        # 步骤一、检查微波工作模式
        if mw_mode == 0:
            logging.info("当前实验微波模式为[不操作微波]，不进行微波参数重设")
            return 
        elif mw_mode == 1:
            logging.info("当前实验微波模式为[CH1单路微波]，重设CH1微波参数")
            # TODO:完善实验方法
        elif mw_mode == 2:
            logging.info("当前实验微波模式为[CH2单路微波]，重设CH2微波参数")
            # TODO:完善实验方法
        elif mw_mode == 3:
            if double_modu_freq_flag:
                logging.info("当前实验微波模式为[双路微波 - 同频]，重设两路微波参数")
            else:
                logging.info("当前实验微波模式为[双路微波 - 双频]，重设两路微波参数")
            # TODO:完善实验方法
        elif mw_mode == 4:
            logging.info("当前实验微波模式为[非共振状态]，不进行微波参数重设")
            return
        
        # 步骤二、停止当前实验
        self.vm.stop(reset_mw_param_flag=False)

        # 步骤三、开始重设微波
        if nonlinear_correction_mode == 0:
            if mw_mode == 1:
                updated_ch1_res_freq = ch1_res_freq - non_linear_reset_ratio * ch1_signal / ch1_slope # 根据斜率预测刷新
                logging.info(f"重置CH1微波参数: 当前设置共振频率{ch1_res_freq/1e6:.1f}MHz，斜率{ch1_slope:.3e}V/Hz，信号{1e3 * ch1_signal:.1f}mV， 预测共振频率{updated_ch1_res_freq/1e6:.1f}MHz")
                self.parent.set_param(name="nv_res_freq_ch1", value=updated_ch1_res_freq, ui_flag=True, delay_flag=False)
            elif mw_mode == 2:
                updated_ch2_res_freq = ch2_res_freq - non_linear_reset_ratio * ch2_signal / ch2_slope # 根据斜率预测刷新
                logging.info(f"重置CH2微波参数: 当前设置共振频率{ch2_res_freq/1e6:.1f}MHz, 斜率{ch2_slope:.3e}V/Hz，信号{1e3 * ch2_signal:.1f}mV，预测共振频率{updated_ch2_res_freq/1e6:.1f}MHz")
                self.parent.set_param(name="nv_res_freq_ch2", value=updated_ch2_res_freq, ui_flag=True, delay_flag=False)
            elif mw_mode == 3:
                if double_modu_freq_flag:
                    updated_ch1_res_freq = ch1_res_freq - non_linear_reset_ratio * ch1_signal / ch1_slope # 根据斜率预测刷新
                    updated_ch2_res_freq = ch2_res_freq - non_linear_reset_ratio* ch2_signal / ch2_slope # 根据斜率预测刷新
                    logging.info(f"[双频调制双微波模式] 同时重置两路微波参数：\n"
                                 f"[CH1] 当前设置共振频率{ch1_res_freq/1e6:.1f}MHz, 斜率{ch1_slope:.3e}V/Hz，信号{ch1_signal * 1e3:.1f}mV, 预测共振频率{updated_ch1_res_freq/1e6:.1f}MHz\n"
                                 f"[CH2] 当前设置共振频率{ch2_res_freq/1e6:.1f}MHz, 斜率{ch2_slope:.3e}V/Hz，信号{ch2_signal * 1e3:.1f}mV, 预测共振频率{updated_ch2_res_freq/1e6:.1f}MHz")
                    self.parent.set_param(name="nv_res_freq_ch1", value=updated_ch1_res_freq, ui_flag=True, delay_flag=False)
                    self.parent.set_param(name="nv_res_freq_ch2", value=updated_ch2_res_freq, ui_flag=True, delay_flag=False)
                else:
                    logging.info(f"[同频调制双微波模式] 双微波参数不支持通过线性斜率预测刷新，转为扫描重设模式，默认通过CH1进行校正。")

                    # 关闭通道2微波，测量通道1信号
                    self.parent.set_param(name="mw_ch2_freq", value=2.6e9, ui_flag=True, delay_flag=False)
                    self.parent.set_param(name="mw_ch1_freq", value=ch1_res_freq, ui_flag=True, delay_flag=False)
                    time.sleep(1)
                    ch1_signal_singlemw = self.parent.dev.IIR_play(data_num=100)[1]
                    
                    self.parent.set_param(name="mw_ch1_freq", value=2.6e9, ui_flag=True, delay_flag=False)
                    self.parent.set_param(name="mw_ch2_freq", value=ch2_res_freq, ui_flag=True, delay_flag=False)
                    time.sleep(1)
                    ch2_signal_singlemw = self.parent.dev.IIR_play(data_num=100)[7]

                    updated_ch1_res_freq = ch1_res_freq - non_linear_reset_ratio * ch1_signal_singlemw / ch1_slope # 根据斜率预测刷新
                    updated_ch2_res_freq = ch2_res_freq - non_linear_reset_ratio *ch2_signal_singlemw / ch2_slope # 根据斜率预测刷新

                    # 重置双微波参数
                    self.parent.set_param(name="nv_res_freq_ch1", value=updated_ch1_res_freq, ui_flag=True, delay_flag=False)
                    self.parent.set_param(name="nv_res_freq_ch2", value=updated_ch2_res_freq, ui_flag=True, delay_flag=False)


        if nonlinear_correction_mode == 1:
            # 扫描重设微波参数
            if mw_mode == 1:
                logging.info(f"[CH1单路微波] 扫描重设微波参数 （※功能尚未实现）")
            elif mw_mode == 2:
                logging.info(f"[CH2单路微波] 扫描重设微波参数 （※功能尚未实现）")
                pass
            elif mw_mode == 3:
                logging.info(f"[双路微波] 扫描重设微波参数（※功能尚未实现）")


        # 步骤三、重新启动当前实验
        self.flush_buffer()
        self.vm.start()


    def reset_mw_param(self):
        """重置微波参数方法"""
        try:
            # 这里添加重置微波参数的具体实现
            # 例如：重置设备状态、恢复默认参数等
            logging.info("正在重置微波参数...")
            self.parent.set_param(name="mw_ch1_freq", value=self.vm.model.ch1_init_freq, ui_flag=True, delay_flag=True)
            self.parent.set_param(name="mw_ch2_freq", value=self.vm.model.ch2_init_freq, ui_flag=True, delay_flag=True)

            self.parent.set_param(name="mw_ch1_fm_sens", value=self.vm.model.ch1_init_fm_sens, ui_flag=True, delay_flag=True)
            self.parent.set_param(name="mw_ch2_fm_sens", value=self.vm.model.ch2_init_fm_sens, ui_flag=True, delay_flag=True)

            # 最后一次参数设置直接下发到底层，delay_flag=False
            self.parent.set_param(name="mw_ch1_power", value=self.vm.model.ch1_init_power, ui_flag=True, delay_flag=False)
            self.parent.set_param(name="mw_ch2_power", value=self.vm.model.ch2_init_power, ui_flag=True, delay_flag=False)
        except Exception as e:
            logging.error(f"重置微波参数时发生错误: {e}")

    def init_ui(self):
        layout = QVBoxLayout()
        
        # 采集设置GroupBox
        acq_settings_group = QGroupBox("采集设置")
        acq_settings_layout = QGridLayout()
        
        # 基本开始/结束采集功能
        self.start_btn = QPushButton("开始采集")
        self.save_btn = QPushButton("保存数据")
        self.clear_btn = QPushButton("清空数据")

        self.start_btn.clicked.connect(self.on_start_button_clicked)
        self.clear_btn.clicked.connect(self.flush_buffer)
        self.save_btn.clicked.connect(self.save_data)
        self.save_btn.clicked.connect(self.save_image)

        acq_settings_layout.addWidget(self.start_btn, 0, 0)
        acq_settings_layout.addWidget(self.save_btn, 0, 1)
        acq_settings_layout.addWidget(self.clear_btn, 0, 2)

        self.allow_save_checkbox = QCheckBox("数据定时自动保存开关\n※保存时清空当前数据")
        self.allow_save_checkbox.setChecked(True)
        acq_settings_layout.addWidget(self.allow_save_checkbox, 0, 3)

        # 微波模式选择
        acq_settings_layout.addWidget(QLabel("微波模式:"), 0, 6)
        self.mw_mode_combo = QComboBox()
        self.mw_mode_combo.addItems(["不操作微波", "CH1单路微波", "CH2单路微波", "双路微波", "非共振状态"])
        self.mw_mode_combo.setCurrentIndex(1)
        self.mw_mode_combo.currentIndexChanged.connect(self.handle_mw_mode_change)
        acq_settings_layout.addWidget(self.mw_mode_combo, 0, 7)

        # 定时开始采集
        acq_settings_layout.addWidget(QLabel("定时开始时间:"), 0, 4)
        self.scheduled_time = QDateTimeEdit()
        self.scheduled_time.setDateTime(QDateTime.currentDateTime())
        self.scheduled_time.setCalendarPopup(True)
        self.scheduled_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        acq_settings_layout.addWidget(self.scheduled_time, 0, 5)

        acq_settings_group.setLayout(acq_settings_layout)
        layout.addWidget(acq_settings_group)

        # 显示设置GroupBox
        display_settings_group = QGroupBox("显示与控制设置")
        display_settings_group.setCheckable(True)  # 使GroupBox可点击
        display_settings_group.toggled.connect(self.handle_display_settings_toggle)  # 连接折叠/展开信号
        display_settings_layout = QGridLayout()
        self.display_settings_layout = display_settings_layout  # 保存引用以便折叠/展开时使用
        
        # 通道显示开关
        display_settings_layout.addWidget(QLabel("通道显示:"), 1, 0)
        self.ch1_display_checkbox = QCheckBox("CH1")
        self.ch2_display_checkbox = QCheckBox("CH2")
        self.ch1_display_checkbox.setChecked(True)
        self.ch2_display_checkbox.setChecked(False)
        self.ch1_display_checkbox.stateChanged.connect(self.handle_channel_display_change)
        self.ch2_display_checkbox.stateChanged.connect(self.handle_channel_display_change)
        display_settings_layout.addWidget(self.ch1_display_checkbox, 1, 1)
        display_settings_layout.addWidget(self.ch2_display_checkbox, 1, 2)

        # 参考路相消开关
        display_settings_layout.addWidget(QLabel("参考路相消:"), 1, 3)
        self.reference_cancellation_combo = QComboBox()
        self.reference_cancellation_combo.addItems(["不启动参考路相消", "启动参考路相消"])
        self.reference_cancellation_combo.setCurrentIndex(0)
        self.reference_cancellation_combo.currentIndexChanged.connect(self.handle_reference_cancellation_change)
        display_settings_layout.addWidget(self.reference_cancellation_combo, 1, 4, 1, 2)

        # 时域/频域切换
        display_settings_layout.addWidget(QLabel("时域/频域切换:"), 1, 6)
        self.time_or_freq_switch_combo = QComboBox()
        self.time_or_freq_switch_combo.addItems(["时域", "频域-ASD", "频域-FFT"])
        self.time_or_freq_switch_combo.setCurrentIndex(0)
        display_settings_layout.addWidget(self.time_or_freq_switch_combo, 1, 7, 1, 1)

        # 屏幕显示时长
        acq_settings_layout.addWidget(QLabel("屏幕显示时长（s）:"), 0, 8)
        self.length_input = QLineEdit(str(self.display_length))
        self.length_input.setFixedWidth(100)
        acq_settings_layout.addWidget(self.length_input, 0, 9, 1, 2)
        # display_settings_layout.addWidget(self.length_input, 0, 1)

        # 磁场-电压转换系数计算模式
        display_settings_layout.addWidget(QLabel("磁场-电压转换系数计算模式:"), 0, 0)
        self.volt_to_mag_mode_combo = QComboBox()
        self.volt_to_mag_mode_combo.addItems(["基于CW谱/等效旋磁比", "基于直接标定系数"])
        self.volt_to_mag_mode_combo.setCurrentIndex(0)  # 默认基于CW谱/等效旋磁比计算
        self.volt_to_mag_mode_combo.currentIndexChanged.connect(self.handle_volt_to_mag_mode_change)
        display_settings_layout.addWidget(self.volt_to_mag_mode_combo, 0, 1, 1, 1)

        # 磁场/电压显示模式
        display_settings_layout.addWidget(QLabel("磁场/电压显示模式:"), 0, 2)
        self.volt_or_mag_view_mode_combo = QComboBox()
        self.volt_or_mag_view_mode_combo.addItems(["显示电压", "显示磁场"])
        self.volt_or_mag_view_mode_combo.setCurrentIndex(0)  # 默认基于CW谱计算
        display_settings_layout.addWidget(self.volt_or_mag_view_mode_combo, 0, 3, 1, 1)

        # 磁场/电压显示模式
        display_settings_layout.addWidget(QLabel("反向显示模式:"), 0, 4)
        self.invert_view_combo = QCheckBox()
        self.invert_view_combo.setChecked(False)
        display_settings_layout.addWidget(self.invert_view_combo, 0, 5, 1, 1)

        # 去趋势模式
        acq_settings_layout.addWidget(QLabel("去趋势模式:"), 0, 11)
        self.acq_trend_remove_checkbox = QComboBox()
        self.acq_trend_remove_checkbox.addItems(["关闭", "线性去基线", "直流去基线", "二次函数去基线"])
        self.acq_trend_remove_checkbox.setCurrentIndex(0)  # 默认关闭
        acq_settings_layout.addWidget(self.acq_trend_remove_checkbox, 0, 12, 1, 2)

        display_settings_group.setLayout(display_settings_layout)
        layout.addWidget(display_settings_group)

        # 新增：实时滤波GroupBox
        self.filter_group = QGroupBox("实时滤波")
        filter_layout = QGridLayout()
        
        self.realtime_filter_checkbox = QCheckBox("开启实时滤波")
        # self.realtime_filter_checkbox.stateChanged.connect(self.handle_realtime_filter_change)
        acq_settings_layout.addWidget(self.realtime_filter_checkbox, 0, 14, 1, 1)

        self.filter_mode_qlabel = QLabel("滤波模式:")
        filter_layout.addWidget(self.filter_mode_qlabel, 1, 0)
        self.filter_mode_combo = QComboBox()
        self.filter_mode_combo.addItems(["带通", "高通", "低通", "平均"])
        self.filter_mode_combo.setCurrentIndex(3)
        self.filter_mode_combo.currentIndexChanged.connect(self.handle_filter_mode_change)
        filter_layout.addWidget(self.filter_mode_combo, 1, 1)
        
        self.filter_type_qlabel = QLabel("滤波器种类:")
        filter_layout.addWidget(self.filter_type_qlabel, 1, 2)
        self.filter_type_combo = QComboBox()
        self.filter_type_combo.addItems(["Butterworth"])
        self.filter_type_combo.currentIndexChanged.connect(self.handle_filter_type_change)
        filter_layout.addWidget(self.filter_type_combo, 1, 3)
        
        self.filter_start_freq_qlabel = QLabel("起始频率 (Hz):")
        self.filter_start_freq_input = QLineEdit(str(self.filter_start_freq))
        self.filter_start_freq_input.setFixedWidth(100)
        filter_layout.addWidget(self.filter_start_freq_qlabel, 1, 4)
        filter_layout.addWidget(self.filter_start_freq_input, 1, 5)
        
        self.filter_stop_freq_qlabel = QLabel("截止频率 (Hz):")
        self.filter_stop_freq_input = QLineEdit(str(self.filter_stop_freq))
        self.filter_stop_freq_input.setFixedWidth(100)
        filter_layout.addWidget(self.filter_stop_freq_qlabel, 1, 6)
        filter_layout.addWidget(self.filter_stop_freq_input, 1, 7)

        self.filter_avg_pts_qlabel = QLabel("平均点数:")
        self.filter_avg_pts_input = QLineEdit(str(self.filter_avg_pts))
        self.filter_avg_pts_input.setFixedWidth(100)
        filter_layout.addWidget(self.filter_avg_pts_qlabel, 1, 8)
        filter_layout.addWidget(self.filter_avg_pts_input, 1, 9)
        
        self.filter_group.setLayout(filter_layout)

        
        # 初始化滤波控件可见性
        self.update_filter_controls_visibility()

        # 采集模式设置GroupBox
        # acq_mode_group = QGroupBox("采集模式设置")
        # acq_mode_layout = QGridLayout()
        
        # 采集模式选择
        # acq_mode_layout.addWidget(QLabel("采集模式:"), 0, 0)
        # self.acq_mode_combo = QComboBox()
        # self.acq_mode_combo.addItems(["定时长采集", "不限制时长采集"])
        # self.acq_mode_combo.setCurrentIndex(0)  # 默认选择定时长采集
        # acq_mode_layout.addWidget(self.acq_mode_combo, 0, 1, 1, 2)

        # acq_mode_group.setLayout(acq_mode_layout)
        # layout.addWidget(acq_mode_group)
        display_settings_layout.addWidget(self.filter_group, 6, 0, 1, display_settings_layout.columnCount())

        # 新增：非线性区自动校正设置GroupBox
        self.nonlinear_group = QGroupBox("非线性区自动校正设置")
        nonlinear_layout = QGridLayout()
        
        # 非线性区识别阈值幅度
        # nonlinear_layout.addWidget(QLabel("非线性区识别阈值幅度 (mV):"), 0, 0)
        # self.nonlinear_threshold_input = QLineEdit(str(self.nonlinear_threshold_mv))
        # self.nonlinear_threshold_input.setFixedWidth(100)
        # self.nonlinear_threshold_input.textChanged.connect(self.handle_nonlinear_threshold_change)
        # nonlinear_layout.addWidget(self.nonlinear_threshold_input, 0, 1)
        
        # 非线性区持续判定时间
        # nonlinear_layout.addWidget(QLabel("非线性区持续判定时间 (s):"), 0, 2)
        # self.nonlinear_duration_input = QLineEdit(str(self.nonlinear_duration_s))
        # self.nonlinear_duration_input.setFixedWidth(100)
        # self.nonlinear_duration_input.textChanged.connect(self.handle_nonlinear_duration_change)
        # nonlinear_layout.addWidget(self.nonlinear_duration_input, 0, 3)
        
        # 非线性区校正模式
        nonlinear_layout.addWidget(QLabel("非线性区校正模式:"), 0, 0)
        self.nonlinear_correction_mode_combo = QComboBox()
        self.nonlinear_correction_mode_combo.addItems(["基于斜率预测", "扫描重设微波参数"])
        self.nonlinear_correction_mode_combo.setCurrentIndex(0)
        nonlinear_layout.addWidget(self.nonlinear_correction_mode_combo, 0, 1)

        # 非线性区自动校正功能开关
        self.nonlinear_auto_correction_checkbox = QCheckBox("非线性区自动校正功能")
        self.nonlinear_auto_correction_checkbox.setChecked(self.nonlinear_auto_correction_enabled)
        self.nonlinear_auto_correction_checkbox.stateChanged.connect(self.handle_nonlinear_auto_correction_change)
        nonlinear_layout.addWidget(self.nonlinear_auto_correction_checkbox, 0, 2)

        # 非线性区手动校正按钮
        self.nonlinear_manual_correction_button = QPushButton("※强制手动校正非线性区")
        self.nonlinear_manual_correction_button.clicked.connect(self.reset_linear_region)
        nonlinear_layout.addWidget(self.nonlinear_manual_correction_button, 0, 3)

        self.nonlinear_group.setLayout(nonlinear_layout)
        display_settings_layout.addWidget(self.nonlinear_group, 7, 0, 1, display_settings_layout.columnCount())

        display_settings_group.setChecked(False)  # 默认不展开


        self.stats_label = QLabel("CH1最大值: --   CH1最小值: --   CH1均值: --\n"
                                  "CH2最大值: --   CH2最小值: --   CH2均值: --")
        layout.addWidget(self.stats_label)

        self.label_coord = QLabel("X: -- , Y: --")
        layout.addWidget(self.label_coord)

        # 时域图 CH1 & CH2
        self.plot_ch1 = pg.PlotWidget(title="IIR通道时域波形")
        self.plot_ch1.showGrid(x=True, y=True)
        self.plot_ch2 = pg.PlotWidget(title="直流通道时域波形")
        self.plot_ch2.showGrid(x=True, y=True)

        self.plot_ch1.setLabel("left", "Voltage", units="V")
        self.plot_ch1.setLabel("bottom", "Time", units="s")

        self.plot_ch2.setLabel("left", "Voltage", units="V")
        self.plot_ch2.setLabel("bottom", "Time", units="s")

        self.curve_ch1 = self.plot_ch1.plot(pen='y', name='CH1')
        self.curve_ch1_freq2 = self.plot_ch1.plot(pen='b', name='CH2')
        self.curve_ch2 = self.plot_ch2.plot(pen='r', name='荧光')
        self.curve_ch2_laser = self.plot_ch2.plot(pen='g', name='激光')

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

    def on_timer_finished(self):
        """定时器完成时的回调，更新按钮状态"""
        self.start_btn.setText("停止采集")

    def on_timer_started(self):
        """定时器开始时的回调，更新按钮状态"""
        self.start_btn.setText("取消定时")

    def on_start_button_clicked(self):
        state = self.state_manager.current_state()
        
        # 检查是否在等待定时开始
        if self.vm.timer_thread and self.vm.timer_thread.isRunning():
            # 取消定时
            self.start_btn.setText("开始采集")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()
            return
            
        if state == DevState.IIR_RUNNING:
            self.start_btn.setText("开始采集")
            self.state_manager.set_state(DevState.IDLE)
            self.vm.stop()

        elif state == DevState.IDLE:
            self.start_btn.setText("停止采集")
            self.flush_buffer()
            self.vm.model.ch1_init_freq = None
            self.vm.model.ch2_init_freq = None
            self.vm.model.ch1_init_fm_sens = None
            self.vm.model.ch2_init_fm_sens = None
            self.vm.model.ch1_init_power = None
            self.vm.model.ch2_init_power = None
            self.init_start_time = time.time()
            # self.flush_buffer()
            self.state_manager.set_state(DevState.IIR_RUNNING)
            self.vm.start()

    def update_display_length(self):
        val = int(self.length_input.text())
        self.display_length = val

    def update_display(self, mac_time, time_data, data1, data2, data3, data4, data5, data6, data7, data8, data9, data10):
        # data1: Fluo-1X, data2: Laser-1X, data3: Fluo-DC, data4: Laser-DC, data5: Fluo-1Y, data6: Laser-1Y, data7: Fluo-2X, data8: Laser-2X, data9: Fluo-2Y, data10: Laser-2Y
        self.full_data1.extend(data1)
        self.full_data2.extend(data2)
        self.full_data3.extend(data3)
        self.full_data4.extend(data4)
        self.full_data5.extend(data5)
        self.full_data6.extend(data6)
        self.full_data7.extend(data7)
        self.full_data8.extend(data8)
        self.full_data9.extend(data9)
        self.full_data10.extend(data10)
        self.full_time_data.extend(time_data.tolist())
        self.full_mac_time.extend(mac_time.tolist())



        try:
            # print('显示长度：', self.display_length)
            self.display_length = int(float(self.length_input.text()) * self.parent.param_config['lockin_sample_rate']['value'])
        except:
            pass

        acq_trend_remove_checkbox = self.acq_trend_remove_checkbox.currentIndex()
        ch1_display_flag = self.ch1_display_checkbox.isChecked()
        ch2_display_flag = self.ch2_display_checkbox.isChecked()

        # 裁剪显示窗口数据
        timewindow = np.array(self.full_time_data[-self.display_length:]) - self.init_start_time

        # 步骤0：设置显示模式
        mag_conversion_mode = self.volt_to_mag_mode_combo.currentIndex()  # 0=基于CW谱/等效旋磁比，1=基于直接标定系数


        conversion_coe = 1 # 默认，1：1转换
        time_or_freq_switch = self.time_or_freq_switch_combo.currentIndex()
        view_mode = self.volt_or_mag_view_mode_combo.currentIndex() # 0=显示电压，1=显示磁场

        mag_coe_cw_ch1 = 1 / (self.parent.param_config['nv_eff_gyromagnetic_ratio']['value'] * self.parent.param_config['nv_cw_slope_ch1']['value'])
        mag_coe_cw_ch2 = 1 / (self.parent.param_config['nv_eff_gyromagnetic_ratio']['value'] * self.parent.param_config['nv_cw_slope_ch2']['value'])

        mag_coe_fixed_ch1 = self.parent.param_config['nv_volt_to_tesla_coe_ch1']['value']
        mag_coe_fixed_ch2 = self.parent.param_config['nv_volt_to_tesla_coe_ch2']['value']

        mag_coe_1 = mag_coe_cw_ch1
        mag_coe_2 = mag_coe_cw_ch1
        if mag_conversion_mode == 1:
            mag_coe_1 = mag_coe_fixed_ch1
            mag_coe_2 = mag_coe_fixed_ch2

        if time_or_freq_switch == 0:
            self.plot_ch1.setLabel("bottom", "时间", units="s")
            self.plot_ch2.setLabel("bottom", "时间", units="s")
        else:
            self.plot_ch1.setLabel("bottom", "频率", units="Hz")
            self.plot_ch2.setLabel("bottom", "时间", units="s")

        units_volt = ["V", "V/Hz^1/2", "V"]
        units_mag = ["T", "T/Hz^1/2", "T"]
        mw_mode = self.mw_mode_combo.currentIndex()
        if view_mode == 1:
            self.plot_ch1.setLabel("left", "磁场", units=units_mag[time_or_freq_switch])
            # self.plot_ch2.setLabel("left", "磁场", units="V")
            # self.plot_ch2.setLabel("bottom", "时间", units="s")
            self.plot_ch2.setLabel("left", "电压", units=units_volt[time_or_freq_switch])
            self.plot_ch2.setLabel("bottom", "时间", units="s")
            if mw_mode == 1 or mw_mode == 2:
                if mag_conversion_mode == 0:
                    conversion_coe_1 = 1 / (self.parent.param_config['nv_eff_gyromagnetic_ratio']['value'] * self.parent.param_config['nv_cw_slope_ch1']['value'])
                    conversion_coe_2 = 1 / (self.parent.param_config['nv_eff_gyromagnetic_ratio']['value'] * self.parent.param_config['nv_cw_slope_ch2']['value'])
                else:
                    conversion_coe_1 = self.parent.param_config['nv_volt_to_tesla_coe_ch1']['value']
                    conversion_coe_2 = self.parent.param_config['nv_volt_to_tesla_coe_ch2']['value']
            elif mw_mode == 3: # 双微波
                conversion_coe_1 = 1 / (self.parent.param_config['nv_eff_gyromagnetic_ratio']['value'] * self.parent.param_config['nv_cw_slope_ch1']['value'] * self.parent.param_config['double_mw_amp_ratio']['value'])
                conversion_coe_2 = 1 / (self.parent.param_config['nv_eff_gyromagnetic_ratio']['value'] * self.parent.param_config['nv_cw_slope_ch2']['value'] * self.parent.param_config['double_mw_amp_ratio']['value'])
        else:
            self.plot_ch1.setLabel("left", "电压", units=units_volt[time_or_freq_switch])
            self.plot_ch2.setLabel("left", "电压", units=units_volt[time_or_freq_switch])
            conversion_coe_1 = 1
            conversion_coe_2 = 1

        # 步骤1：去趋势
        if acq_trend_remove_checkbox == 1:
            window1_1x = detrend(self.full_data1[-self.display_length:])
            window1_2x = detrend(self.full_data7[-self.display_length:])
            window1_ref_1x = detrend(self.full_data2[-self.display_length:])
            window1_ref_2x = detrend(self.full_data8[-self.display_length:])
            window2 = detrend(self.full_data3[-self.display_length:])
            window2_ref = detrend(self.full_data4[-self.display_length:])
        elif acq_trend_remove_checkbox == 2:
            window1_1x = np.array(self.full_data1[-self.display_length:]) - np.mean(self.full_data1[-self.display_length:])
            window1_2x = np.array(self.full_data7[-self.display_length:]) - np.mean(self.full_data7[-self.display_length:])
            window1_ref_1x = np.array(self.full_data2[-self.display_length:]) - np.mean(self.full_data2[-self.display_length:])
            window1_ref_2x = np.array(self.full_data8[-self.display_length:]) - np.mean(self.full_data8[-self.display_length:])
            window2 = np.array(self.full_data3[-self.display_length:]) - np.mean(self.full_data3[-self.display_length:])
            window2_ref = np.array(self.full_data4[-self.display_length:]) - np.mean(self.full_data4[-self.display_length:])
        elif acq_trend_remove_checkbox == 3:
            window1_1x = poly_detrend(timewindow, self.full_data1[-self.display_length:], deg=2)
            window1_2x = poly_detrend(timewindow, self.full_data7[-self.display_length:], deg=2)
            window1_ref_1x = poly_detrend(timewindow, self.full_data2[-self.display_length:], deg=2)
            window1_ref_2x = poly_detrend(timewindow, self.full_data8[-self.display_length:], deg=2)

            window2 = np.array(self.full_data3[-self.display_length:]) - np.mean(self.full_data3[-self.display_length:])
            window2_ref = np.array(self.full_data4[-self.display_length:]) - np.mean(self.full_data4[-self.display_length:])
        else:
            window1_1x = np.array(self.full_data1[-self.display_length:])
            window1_2x = np.array(self.full_data7[-self.display_length:])
            window1_ref_1x = np.array(self.full_data2[-self.display_length:])
            window1_ref_2x = np.array(self.full_data8[-self.display_length:])
            window2 = np.array(self.full_data3[-self.display_length:])
            window2_ref = np.array(self.full_data4[-self.display_length:])  
        # window3 = self.full_data4[-self.display_length:]

        if self.invert_view_combo.isChecked():
            window1_1x = - window1_1x
            window1_2x = - window1_2x
        # 步骤2：执行相消
        reference_cancellation_label = ''
        if self.reference_cancellation_combo.currentIndex() == 1:
            print('启动参考路相消功能')
            optcoe_ch1, opt_noise_ch1, raw_noise_ch1 = get_optimize_coe(window1_1x, window1_ref_1x)
            optcoe_ch2, opt_noise_ch2, raw_noise_ch2 = get_optimize_coe(window1_2x, window1_ref_2x)
            reference_cancellation_label += f'CH1相消能力：{raw_noise_ch1/opt_noise_ch1:.2f}, CH2相消能力：{raw_noise_ch2/opt_noise_ch2:.2f}\n'
            window1_1x = window1_1x - optcoe_ch1 * window1_ref_1x
            window1_2x = window1_2x - optcoe_ch2 * window1_ref_2x

        # 步骤3：实时滤波
        filter_label = ''
        sample_rate = self.parent.param_config['lockin_sample_rate']['value']

        if self.realtime_filter_checkbox.isChecked():
            print('启动实时滤波功能')
            filter_option = self.filter_mode_combo.currentIndex() # 0=带通滤波，1=低通滤波，2=高通滤波
            valid_filter = True
            try:
                filter_start_freq = float(self.filter_start_freq_input.text())
                filter_end_freq = float(self.filter_stop_freq_input.text())
                if filter_start_freq >0 and filter_end_freq >0 and filter_start_freq < filter_end_freq:
                    valid_filter = True
                else:
                    valid_filter = False
            except:
                valid_filter = False
            if valid_filter:
                N = len(window1_1x)

                if filter_option == 0: # 带通滤波
                    min_samples_needed = int(sample_rate / filter_start_freq * 2)
                    if N < min_samples_needed:
                        print(f"数据长度不足，无法进行带通滤波。需要至少 {min_samples_needed} 个样本（当前 {N} 个样本）")
                        window1_1x = lowpass_filter(window1_1x, sample_rate, filter_end_freq)
                        window1_2x = lowpass_filter(window1_2x, sample_rate, filter_end_freq)
                        filter_label += f'低通滤波：{filter_end_freq}Hz\n'
                    else:
                        window1_1x = bandpass_filter(window1_1x, sample_rate, filter_start_freq, filter_end_freq)
                        window1_2x = bandpass_filter(window1_2x, sample_rate, filter_start_freq, filter_end_freq)
                        filter_label += f'带通滤波：{filter_start_freq}Hz - {filter_end_freq}Hz\n'
                elif filter_option == 1: # 低通滤波
                    window1_1x = lowpass_filter(window1_1x, sample_rate, filter_end_freq)
                    window1_2x = lowpass_filter(window1_2x, sample_rate, filter_end_freq)
                    filter_label += f'低通滤波：{filter_end_freq}Hz\n'
                elif filter_option == 2: # 高通滤波
                    min_samples_needed = int(sample_rate / filter_start_freq * 2)
                    if N < min_samples_needed:
                        print(f"数据长度不足，无法进行高通滤波。需要至少 {min_samples_needed} 个样本（当前 {N} 个样本）")
                    else:
                        window1_1x = highpass_filter(window1_1x, sample_rate, filter_start_freq)
                        window1_2x = highpass_filter(window1_2x, sample_rate, filter_start_freq)
                        filter_label += f'高通滤波：{filter_start_freq}Hz\n'
                elif filter_option == 3: # 平均滤波
                    try:
                        filter_avg_pts = int(self.filter_avg_pts_input.text())
                        window1_1x = moving_average_filter(window1_1x, filter_avg_pts)
                        window1_2x = moving_average_filter(window1_2x, filter_avg_pts)
                        filter_label += f'平均滤波：{filter_avg_pts}点\n'
                    except:
                        window1_1x = moving_average_filter(window1_1x, 5)
                        window1_2x = moving_average_filter(window1_2x, 5)
                        filter_label += f'平均滤波：5点\n'

        # 计算统计量
        stats_results = {
            "ch1_std_volt": np.std(window1_1x),
            "ch2_std_volt": np.std(window1_2x),
            "ch1_std_mag": np.std(window1_1x) * mag_coe_1,
            "ch2_std_mag": np.std(window1_2x) * mag_coe_2,
            "ch1_ptp_volt": np.ptp(window1_1x),
            "ch2_ptp_volt": np.ptp(window1_2x),
            "ch1_ptp_mag": np.ptp(window1_1x) * mag_coe_1,
            "ch2_ptp_mag": np.ptp(window1_2x) * mag_coe_2,
            "filter_label": filter_label,
            "reference_cancellation_label": reference_cancellation_label,
            "ch1_avg_volt": np.mean(self.full_data1[-self.display_length:]),
            "ch2_avg_volt": np.mean(self.full_data7[-self.display_length:]),
        }

        if self.allow_save_checkbox.isChecked() and time.time() - self.vm.model.acq_save_start_time > self.vm.model.auto_save_time_interval:
            self.save_data(ui_mode=False)
            self.vm.model.acq_save_start_time = time.time()
            logging.info(f"自动保存数据，保存时间：{time.time()}")

        # print(f"数据显示长度：{self.display_length}, data1长度：{len(self.full_data1)}, data2长度：{len(self.full_data2)}, 时间长度：{len(timewindow)}")
        if not ch1_display_flag:
            self.curve_ch1.hide()
        else:
            self.curve_ch1.show()

        if not ch2_display_flag:
            self.curve_ch1_freq2.hide()
        else:
            self.curve_ch1_freq2.show()

        if time_or_freq_switch == 1:
            # ASD
            f, window1_1x = cal_ASD(window1_1x, sample_rate)
            f, window1_2x = cal_ASD(window1_2x, sample_rate)
            self.curve_ch1.setData(f, np.array(window1_1x) * conversion_coe_1)
            self.curve_ch1_freq2.setData(f, np.array(window1_2x) * conversion_coe_2)
            self.curve_ch2.setData(timewindow, np.array(window2))
            self.curve_ch2_laser.setData(timewindow, np.array(window2_ref))
        elif time_or_freq_switch == 2:
            # FFT
            f, window1_1x = cal_FFT(window1_1x, sample_rate)
            f, window1_2x = cal_FFT(window1_2x, sample_rate)
            self.curve_ch1.setData(f, np.array(window1_1x) * conversion_coe_1)
            self.curve_ch1_freq2.setData(f, np.array(window1_2x) * conversion_coe_2)
            self.curve_ch2.setData(timewindow, np.array(window2))
            self.curve_ch2_laser.setData(timewindow, np.array(window2_ref))
        elif time_or_freq_switch == 0:
            self.curve_ch1.setData(timewindow, np.array(window1_1x) * conversion_coe_1)
            self.curve_ch1_freq2.setData(timewindow, np.array(window1_2x) * conversion_coe_2)
            self.curve_ch2.setData(timewindow, np.array(window2))
            self.curve_ch2_laser.setData(timewindow, np.array(window2_ref))
        # self.curve_ch3.setData(timewindow, np.array(window3))

        self.update_stats_label(stats_results)

        # 检查是否需要自动校正非线性区
        if self.nonlinear_auto_correction_checkbox.isChecked():

            nonlinear_identify_time = self.parent.param_config['nv_linear_auto_adjust_time']['value']
            nonlinear_identify_time_samples = int(nonlinear_identify_time * sample_rate)

            if len(self.full_data1) >= nonlinear_identify_time_samples:


                nonlinear_threshold_ch1 = self.parent.param_config['nv_linear_auto_adjust_warning_voltage_ch1']['value']
                nonlinear_threshold_ch2 = self.parent.param_config['nv_linear_auto_adjust_warning_voltage_ch2']['value']

                min_val1 = np.amin(np.abs(self.full_data1[-nonlinear_identify_time_samples:]))
                min_val2 = np.amin(np.abs(self.full_data7[-nonlinear_identify_time_samples:]))

                ch1_correct_flag = (min_val1 > nonlinear_threshold_ch1)
                ch2_correct_flag = (min_val2 > nonlinear_threshold_ch2)

                lockin_modu_freq1 = self.parent.param_config["lockin_modu_freq1"]["value"]
                lockin_modu_freq2 = self.parent.param_config["lockin_modu_freq2"]["value"]
                double_modu_freq_flag = (lockin_modu_freq1 == lockin_modu_freq2)
                

                if mw_mode == 1 and ch1_correct_flag:
                    logging.info(f"[CH1] 识别到非线性区持续时间大于{nonlinear_identify_time:.1f}s，设置阈值{1e3 * nonlinear_threshold_ch1:.1f}mV, 当前持续值为{min_val1 * 1e3:.1f}mV, 开始自动校正非线性区")
                    self.reset_linear_region()
                elif mw_mode == 2 and ch2_correct_flag:
                    logging.info(f"[CH2] 识别到非线性区持续时间大于{nonlinear_identify_time:.1f}s，设置阈值{1e3 * nonlinear_threshold_ch2:.1f}mV, 当前持续值为{min_val2 * 1e3:.1f}mV, 开始自动校正非线性区")
                    self.reset_linear_region()
                elif mw_mode == 3 and (ch1_correct_flag or ch2_correct_flag):
                    logging.info(f"[双频微波] 识别到非线性区持续时间大于{nonlinear_identify_time:.1f}s\n[CH1]设置阈值{1e3 * nonlinear_threshold_ch1:.1f}mV, 当前持续值为{min_val1 * 1e3:.1f}mV\n[CH2] 设置阈值{1e3 * nonlinear_threshold_ch2:.1f}mV, 当前持续值为{min_val2 * 1e3:.1f}mV\n开始自动校正非线性区")
                    self.reset_linear_region()


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

    def update_stats_label(self, results):
        self.stats_label.setText(
            f"[CH1]: 电压标准差: {1e3 * results['ch1_std_volt']:.2f}mV  磁场标准差: {1e12 * results['ch1_std_mag']:.2f}pT  磁场峰峰值：{1e12 * results['ch1_ptp_mag']:.2f}pT  电压均值：{1e3 * results['ch1_avg_volt']:.2f}mV\n"
            f"[CH2]: 电压标准差: {1e3 * results['ch2_std_volt']:.2f}mV  磁场标准差: {1e12 * results['ch2_std_mag']:.2f}pT  磁场峰峰值：{1e12 * results['ch2_ptp_mag']:.2f}pT  电压均值：{1e3 * results['ch2_avg_volt']:.2f}mV\n"
            f"{results['filter_label']}"
            f"{results['reference_cancellation_label']}")

    def on_mouse_moved(self, pos, plot):
        vb = plot.getViewBox()
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        self.label_coord.setText(f"X: {x:.1f}, Y: {y:.3f}")

    def save_data(self, ui_mode=False):
        # path, _ = QFileDialog.getSaveFileName(self, "保存数据", "osc_data.csv", "CSV Files (*.csv)")
        path = self.vm.model.save_dir + gettimestr() + '_iir_noise.csv'
        # if path and len(self.full_data1) > 0:
        #     # 只保存新数据，避免重叠
        #     new_data_start = self.saved_data_length
        #     new_data_end = len(self.full_data1)
        #
        #     if new_data_end > new_data_start:  # 有新数据需要保存
        #         # 提取新数据
        #         new_mac_time = self.full_mac_time[new_data_start:new_data_end]
        #         new_time_data = self.full_time_data[new_data_start:new_data_end]
        #         new_data1 = self.full_data1[new_data_start:new_data_end]
        #         new_data2 = self.full_data2[new_data_start:new_data_end]
        #         new_data3 = self.full_data3[new_data_start:new_data_end]
        #         new_data4 = self.full_data4[new_data_start:new_data_end]
        #         new_data5 = self.full_data5[new_data_start:new_data_end]
        #         new_data6 = self.full_data6[new_data_start:new_data_end]
        #         new_data7 = self.full_data7[new_data_start:new_data_end]
        #         new_data8 = self.full_data8[new_data_start:new_data_end]
        #         new_data9 = self.full_data9[new_data_start:new_data_end]
        #         new_data10 = self.full_data10[new_data_start:new_data_end]
        #
        #         arr = np.column_stack((new_mac_time, new_time_data, new_data1, new_data2, new_data5, new_data6, new_data7, new_data8, new_data9, new_data10, new_data3, new_data4))
        #         np.savetxt(path, arr, delimiter=",", header=f"%采样率={self.parent.param_config['lockin_sample_rate']['value']}Hz\n"
        #                           f"%CH1磁场-电压转换系数（未更新，手动指定）={self.parent.param_config['nv_volt_to_tesla_coe_ch1']['value']} T/V\n"
        #                           f"%CH2磁场-电压转换系数（未更新，手动指定）={self.parent.param_config['nv_volt_to_tesla_coe_ch2']['value']} T/V\n"
        #                           f"%等效旋磁比={self.parent.param_config['nv_eff_gyromagnetic_ratio']['value']} Hz/T\n"
        #                           f"%CH1一阶微分谱斜率={self.parent.param_config['nv_cw_slope_ch1']['value']} V/Hz\n"
        #                           f"%CH2一阶微分谱斜率={self.parent.param_config['nv_cw_slope_ch2']['value']} V/Hz\n"
        #                           f"%CH1当前微波设置频率={self.parent.param_config['mw_ch1_freq']['value']:.1f}Hz\n"
        #                           f"%CH2当前微波设置频率={self.parent.param_config['mw_ch2_freq']['value']:.1f}Hz\n"
        #                           f"%微波工作模式：{self.mw_mode_combo.currentText()}\n"
        #                           f"%设置定时采集启动时间={self.get_start_time()}\n"
        #                           f"%IIR模式增益系数={self.parent.param_config['lockin_iir_gain']['value']} V\n"
        #                           f"%机器时间戳(s), 计算时间戳(s), 荧光-CH1-X-Freq1(V), 激光-CH2-X-Freq1(V), 荧光-CH1-Y-Freq1(V), 激光-CH2-Y-Freq1(V), 荧光-CH1-X-Freq2(V), 激光-CH2-X-Freq2(V), 荧光-CH1-Y-Freq2(V), 激光-CH2-Y-Freq2(V),荧光直流-CH1-DC (V), 激光直流-CH2-DC (V)",
        #                    comments='% ')
        #
        #
        #
        #
        #         # 保留最近的数据用于连续显示，避免显示中断
        #         keep_length = min(len(self.full_data1), int(7200 *self.parent.param_config['lockin_sample_rate']['value'] ))  # 保留2h
        #
        #         # 更新已保存数据长度
        #         self.saved_data_length = new_data_end
        #
        #         if keep_length > 0:
        #             self.full_data1 = self.full_data1[-keep_length:]
        #             self.full_data2 = self.full_data2[-keep_length:]
        #             self.full_data3 = self.full_data3[-keep_length:]
        #             self.full_data4 = self.full_data4[-keep_length:]
        #             self.full_data5 = self.full_data5[-keep_length:]
        #             self.full_data6 = self.full_data6[-keep_length:]
        #             self.full_data7 = self.full_data7[-keep_length:]
        #             self.full_data8 = self.full_data8[-keep_length:]
        #             self.full_data9 = self.full_data9[-keep_length:]
        #             self.full_data10 = self.full_data10[-keep_length:]
        #             self.full_time_data = self.full_time_data[-keep_length:]
        #             self.full_mac_time = self.full_mac_time[-keep_length:]
        #
        #             # 调整已保存数据长度记录
        #             self.saved_data_length = max(0, self.saved_data_length - (len(self.full_data1) - keep_length))
        #
        #             logging.info(f"保存后保留最近 {keep_length} 个数据点用于连续显示")
        #
        #         if ui_mode:
        #             QMessageBox.information(self, "保存成功", f"IIR模式数据已保存为 {path}")
        #         logging.info(f"保存成功，IIR模式数据已保存为 {path}，保存了 {new_data_end - new_data_start} 个新数据点")
        #     else:
        #         logging.info("没有新数据需要保存")
        if path and len(self.full_data1) > 0:
            arr = np.column_stack(
                (self.full_mac_time, self.full_time_data, self.full_data1, self.full_data2, self.full_data3, self.full_data4, self.full_data5, self.full_data6,
                 self.full_data7, self.full_data8, self.full_data9, self.full_data10))
            np.savetxt(path, arr, delimiter=",",
                       header=f"%采样率={self.parent.param_config['lockin_sample_rate']['value']}Hz\n"
                              f"%CH1磁场-电压转换系数（未更新，手动指定）={self.parent.param_config['nv_volt_to_tesla_coe_ch1']['value']} T/V\n"
                              f"%CH2磁场-电压转换系数（未更新，手动指定）={self.parent.param_config['nv_volt_to_tesla_coe_ch2']['value']} T/V\n"
                              f"%等效旋磁比={self.parent.param_config['nv_eff_gyromagnetic_ratio']['value']} Hz/T\n"
                              f"%CH1一阶微分谱斜率={self.parent.param_config['nv_cw_slope_ch1']['value']} V/Hz\n"
                              f"%CH2一阶微分谱斜率={self.parent.param_config['nv_cw_slope_ch2']['value']} V/Hz\n"
                              f"%CH1当前微波设置频率={self.parent.param_config['mw_ch1_freq']['value']:.1f}Hz\n"
                              f"%CH2当前微波设置频率={self.parent.param_config['mw_ch2_freq']['value']:.1f}Hz\n"
                              f"%微波工作模式：{self.mw_mode_combo.currentText()}\n"
                              f"%设置定时采集启动时间={self.get_start_time()}\n"
                              f"%IIR模式增益系数={self.parent.param_config['lockin_iir_gain']['value']} V\n"
                              f"%机器时间戳(s), 计算时间戳(s), 荧光-CH1-X-Freq1(V), 激光-CH2-X-Freq1(V), 荧光-CH1-Y-Freq1(V), 激光-CH2-Y-Freq1(V), 荧光-CH1-X-Freq2(V), 激光-CH2-X-Freq2(V), 荧光-CH1-Y-Freq2(V), 激光-CH2-Y-Freq2(V),荧光直流-CH1-DC (V), 激光直流-CH2-DC (V)",
                       comments='% ')
            self.flush_buffer()
            if ui_mode:
                QMessageBox.information(self, "保存成功", f"IIR模式数据已保存为 {path}")
                logging.info(f"保存成功，IIR模式数据已保存为 {path}")
        else:
            logging.info("没有新数据需要保存")

    def save_image(self):
        time_str = gettimestr()
        path_ch1 = self.save_dir + time_str + '_iir_fluo.png'
        path_ch2 = self.save_dir + time_str + '_dc_fluo.png'
        # path, _ = QFileDialog.getSaveFileName(self, "保存图像", "plot.png", "PNG Files (*.png)")
        exporter_ch1 = ImageExporter(self.plot_ch1.plotItem)
        exporter_ch2 = ImageExporter(self.plot_ch2.plotItem)
        exporter_ch1.export(path_ch1)
        exporter_ch2.export(path_ch2)

    def closeEvent(self, event):
        self.vm.stop()
        event.accept()
