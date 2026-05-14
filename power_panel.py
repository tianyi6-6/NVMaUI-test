import sys
import os
import configparser
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                 QPushButton, QDoubleSpinBox, QGridLayout, QGroupBox,
                                 QCheckBox, QTextEdit, QMessageBox, QFrame)
from PySide6.QtCore import QTimer, Qt, QThread, Signal as pyqtSignal
from PySide6.QtGui import QFont, QColor, QPalette
from interface.DP832 import RigolDP832Controller
from interface.UDP3305S import UniTUDP3305SController
import pyvisa
import traceback

LOG_PATH = "log/power_log.txt"
CONFIG_PATH = "config/power_config.ini"
os.makedirs("log", exist_ok=True)

def log_event(text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text}\n")

class DeviceConnectionThread(QThread):
    """设备连接线程，避免阻塞UI"""
    connection_result = pyqtSignal(int, bool, str)  # device_index, success, message
    
    def __init__(self, device_index, device_type, resource_name):
        super().__init__()
        self.device_index = device_index
        self.device_type = device_type
        self.resource_name = resource_name
    
    def run(self):
        try:
            if self.device_type == "Rigol-DP832":
                controller = RigolDP832Controller(self.resource_name, debug=False)
                self.connection_result.emit(self.device_index, True, f"DP832 connected successfully")
            elif self.device_type == "UNI-T-UT33C":
                controller = UniTUDP3305SController(self.resource_name, debug=False)
                self.connection_result.emit(self.device_index, True, f"UDP3305S connected successfully")
            else:
                self.connection_result.emit(self.device_index, False, f"Unknown device type: {self.device_type}")
        except Exception as e:
            self.connection_result.emit(self.device_index, False, f"Connection failed: {str(e)}")

class PowerChannel(QWidget):
    def __init__(self, device_id, channel_id, name, v_max, i_max, v_default, i_default, editable, device_controller=None):
        super().__init__()
        self.device_id = device_id
        self.channel_id = channel_id
        self.name = name
        self.device_controller = device_controller
        self.is_connected = False
        self.is_setting_defaults = False  # 标记是否正在设置默认值

        layout = QGridLayout()

        # 标题
        title = QLabel(f"CH{channel_id}: {name}")
        title.setFont(QFont("Arial", 14))
        layout.addWidget(title, 0, 0, 1, 2, alignment=Qt.AlignCenter)

        # 状态指示器
        self.status_frame = QFrame()
        self.status_frame.setFixedSize(20, 20)
        self.status_frame.setStyleSheet("background-color: red; border-radius: 10px;")
        layout.addWidget(self.status_frame, 0, 2, alignment=Qt.AlignRight)

        # 显示标签
        font_big = QFont("Arial", 12)
        self.v_label = QLabel("0.000 V")
        self.i_label = QLabel("0.000 A")
        self.p_label = QLabel("0.000 W")
        for lbl in [self.v_label, self.i_label, self.p_label]:
            lbl.setFont(font_big)
            lbl.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.v_label, 1, 0, 1, 2)
        layout.addWidget(self.i_label, 2, 0, 1, 2)
        layout.addWidget(self.p_label, 3, 0, 1, 2)

        # 设置控件
        self.v_spin = QDoubleSpinBox()
        self.v_spin.setRange(0, v_max)
        self.v_spin.setValue(v_default)
        self.v_spin.setSingleStep(0.001)
        self.v_spin.setSuffix(" V")
        self.v_spin.setEnabled(editable and self.is_connected)
        self.v_spin.valueChanged.connect(self.on_voltage_changed)

        self.i_spin = QDoubleSpinBox()
        self.i_spin.setRange(0, i_max)
        self.i_spin.setValue(i_default)
        self.i_spin.setSingleStep(0.001)
        self.i_spin.setSuffix(" A")
        self.i_spin.setEnabled(editable and self.is_connected)
        self.i_spin.valueChanged.connect(self.on_current_changed)

        layout.addWidget(QLabel("Set:"), 4, 0)
        layout.addWidget(self.v_spin, 4, 1)
        layout.addWidget(self.i_spin, 5, 1)

        # 输出开关
        self.output_btn = QPushButton("ON/OFF")
        self.output_btn.setCheckable(True)
        self.output_btn.clicked.connect(self.toggle_output)
        self.output_btn.setEnabled(self.is_connected)
        self.set_button_color(False)
        layout.addWidget(self.output_btn, 6, 0, 1, 2)

        self.setLayout(layout)

    def set_connection_status(self, connected):
        """设置连接状态"""
        self.is_connected = connected
        self.status_frame.setStyleSheet(
            f"background-color: {'green' if connected else 'red'}; border-radius: 10px;"
        )
        self.v_spin.setEnabled(self.v_spin.isEnabled() and connected)
        self.i_spin.setEnabled(self.i_spin.isEnabled() and connected)
        self.output_btn.setEnabled(connected)

    def on_voltage_changed(self):
        """电压设置改变时的回调"""
        if self.is_connected and self.device_controller and not self.is_setting_defaults:
            try:
                voltage = self.v_spin.value()
                self.device_controller.set_voltage(self.channel_id, voltage)
                msg = f"[Device {self.device_id} CH{self.channel_id}] Voltage set to {voltage:.3f}V"
                print(msg)
                log_event(msg)
            except Exception as e:
                msg = f"[Device {self.device_id} CH{self.channel_id}] Voltage set failed: {str(e)}"
                print(msg)
                log_event(msg)

    def on_current_changed(self):
        """电流设置改变时的回调"""
        if self.is_connected and self.device_controller and not self.is_setting_defaults:
            try:
                current = self.i_spin.value()
                self.device_controller.set_current(self.channel_id, current)
                msg = f"[Device {self.device_id} CH{self.channel_id}] Current set to {current:.3f}A"
                print(msg)
                log_event(msg)
            except Exception as e:
                msg = f"[Device {self.device_id} CH{self.channel_id}] Current set failed: {str(e)}"
                print(msg)
                log_event(msg)

    def set_default_values(self, voltage, current):
        """设置默认值（不触发设备设置）"""
        self.is_setting_defaults = True
        try:
            self.v_spin.setValue(voltage)
            self.i_spin.setValue(current)
        finally:
            self.is_setting_defaults = False

    def toggle_output(self):
        """切换输出状态"""
        if not self.is_connected or not self.device_controller:
            return
            
        try:
            state = self.output_btn.isChecked()
            self.device_controller.set_output(self.channel_id, state)
            self.set_button_color(state)
            msg = f"[Device {self.device_id} CH{self.channel_id}] Output {'ON' if state else 'OFF'}"
            print(msg)
            log_event(msg)
        except Exception as e:
            msg = f"[Device {self.device_id} CH{self.channel_id}] Output toggle failed: {str(e)}"
            print(msg)
            log_event(msg)
            # 恢复按钮状态
            self.output_btn.setChecked(not self.output_btn.isChecked())

    def set_button_color(self, on):
        """设置按钮颜色"""
        pal = self.output_btn.palette()
        pal.setColor(QPalette.Button, QColor("lightgreen" if on else "lightgrey"))
        self.output_btn.setAutoFillBackground(True)
        self.output_btn.setPalette(pal)
        self.output_btn.update()

    def update_readings(self, voltage, current):
        """更新显示读数"""
        power = voltage * current
        self.v_label.setText(f"{voltage:.3f} V")
        self.i_label.setText(f"{current:.3f} A")
        self.p_label.setText(f"{power:.3f} W")

    def read_from_device(self):
        """从设备读取实际值"""
        if not self.is_connected or not self.device_controller:
            return False, 0, 0
            
        try:
            voltage = self.device_controller.get_voltage(self.channel_id)
            current = self.device_controller.get_current(self.channel_id)
            self.update_readings(voltage, current)
            return True, voltage, current
        except Exception as e:
            msg = f"[Device {self.device_id} CH{self.channel_id}] Read failed: {str(e)}"
            print(msg)
            log_event(msg)
            return False, 0, 0

class PowerDevice(QWidget):
    def __init__(self, device_index, config, log_output):
        super().__init__()
        self.setMinimumWidth(900)
        self.device_index = device_index
        self.config = config
        self.log_output = log_output
        self.device_controller = None
        self.connection_thread = None

        section = f"power_{device_index}"
        name = config.get(section, "name", fallback=f"Device {device_index}")
        ch_count = int(config.get(section, "channels", fallback="3"))
        
        # 获取设备类型和资源名
        device_type = config.get("Setup", f"power_device_type_{device_index}", fallback="Unknown")
        resource_name = config.get("Setup", f"power_device_id_{device_index}", fallback="")

        self.enabled_checkbox = QCheckBox("Enable Communication")
        self.enabled_checkbox.setChecked(False)
        self.enabled_checkbox.stateChanged.connect(self.on_communication_toggled)

        # 连接状态标签
        self.connection_label = QLabel("Disconnected")
        self.connection_label.setStyleSheet("color: red; font-weight: bold;")

        group_box = QGroupBox(f"{name} ({device_type})")
        group_box.setFont(QFont("Arial", 11, QFont.Bold))

        group_layout = QHBoxLayout()
        self.channels = []

        for ch in range(1, ch_count + 1):
            ch_name = config.get(section, f"ch{ch}_name", fallback=f"CH{ch}")
            v_max = float(config.get(section, f"ch{ch}_max_volt", fallback="30"))
            i_max = float(config.get(section, f"ch{ch}_max_current", fallback="3"))
            v_def = float(config.get(section, f"ch{ch}_default_volt", fallback="0"))
            i_def = float(config.get(section, f"ch{ch}_default_current", fallback="0"))
            editable = config.getboolean(section, f"ch{ch}_editable", fallback=False)
            ch_widget = PowerChannel(device_index, ch, ch_name, v_max, i_max, v_def, i_def, editable)
            self.channels.append(ch_widget)
            group_layout.addWidget(ch_widget)

        layout = QVBoxLayout()
        
        # 顶部控制栏
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.enabled_checkbox)
        top_layout.addWidget(self.connection_label)
        top_layout.addStretch()
        
        layout.addLayout(top_layout)
        layout.addWidget(group_box)
        group_box.setLayout(group_layout)
        self.setLayout(layout)

        # 保存设备信息
        self.device_type = device_type
        self.resource_name = resource_name

    def on_communication_toggled(self):
        """通信开关切换"""
        if self.enabled_checkbox.isChecked():
            self.connect_device()
        else:
            self.disconnect_device()

    def connect_device(self):
        """连接设备"""
        if not self.resource_name or self.resource_name == "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
            msg = f"[Device {self.device_index}] No valid resource name configured"
            print(msg)
            log_event(msg)
            self.enabled_checkbox.setChecked(False)
            return

        self.connection_thread = DeviceConnectionThread(
            self.device_index, self.device_type, self.resource_name
        )
        self.connection_thread.connection_result.connect(self.on_connection_result)
        self.connection_thread.start()

    def on_connection_result(self, device_index, success, message):
        """连接结果处理"""
        if success:
            try:
                # 创建设备控制器
                if self.device_type == "Rigol-DP832":
                    self.device_controller = RigolDP832Controller(self.resource_name, debug=False)
                elif self.device_type == "UNI-T-UT33C":
                    self.device_controller = UniTUDP3305SController(self.resource_name, debug=False)
                
                # 更新UI状态
                self.connection_label.setText("Connected")
                self.connection_label.setStyleSheet("color: green; font-weight: bold;")
                
                # 更新所有通道状态
                for ch in self.channels:
                    ch.set_connection_status(True)
                    ch.device_controller = self.device_controller
                
                # 连接成功后设置默认参数
                self.set_default_parameters()
                
                msg = f"[Device {self.device_index}] {message}"
                print(msg)
                log_event(msg)
                
            except Exception as e:
                msg = f"[Device {self.device_index}] Controller creation failed: {str(e)}"
                print(msg)
                log_event(msg)
                self.enabled_checkbox.setChecked(False)
        else:
            self.connection_label.setText("Connection Failed")
            self.connection_label.setStyleSheet("color: red; font-weight: bold;")
            msg = f"[Device {self.device_index}] {message}"
            print(msg)
            log_event(msg)
            self.enabled_checkbox.setChecked(False)

    def set_default_parameters(self):
        """设置默认参数"""
        if not self.device_controller:
            return
            
        section = f"power_{self.device_index}"
        
        for ch in self.channels:
            try:
                # 获取默认参数
                v_default = float(self.config.get(section, f"ch{ch.channel_id}_default_volt", fallback="0"))
                i_default = float(self.config.get(section, f"ch{ch.channel_id}_default_current", fallback="0"))
                
                # 设置设备参数
                self.device_controller.set_voltage(ch.channel_id, v_default)
                self.device_controller.set_current(ch.channel_id, i_default)
                
                # 更新UI显示（不触发设备设置）
                ch.set_default_values(v_default, i_default)
                
                msg = f"[Device {self.device_index} CH{ch.channel_id}] Default parameters set: V={v_default:.3f}V, I={i_default:.3f}A"
                print(msg)
                log_event(msg)
                
            except Exception as e:
                msg = f"[Device {self.device_index} CH{ch.channel_id}] Failed to set default parameters: {str(e)}"
                print(msg)
                log_event(msg)

    def disconnect_device(self):
        """断开设备连接"""
        if self.device_controller:
            try:
                self.device_controller.close()
            except:
                pass
            self.device_controller = None

        self.connection_label.setText("Disconnected")
        self.connection_label.setStyleSheet("color: red; font-weight: bold;")
        
        for ch in self.channels:
            ch.set_connection_status(False)
            ch.device_controller = None

        msg = f"[Device {self.device_index}] Disconnected"
        print(msg)
        log_event(msg)

    def update_all_readings(self):
        """更新所有通道读数"""
        if not self.enabled_checkbox.isChecked() or not self.device_controller:
            return
            
        for ch in self.channels:
            success, voltage, current = ch.read_from_device()
            if success:
                log_event(f"[Device {self.device_index} CH{ch.channel_id}] V={voltage:.3f}V I={current:.3f}A")

class PowerPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Power Supply Control")
        self.setMinimumSize(1500, 900)

        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_PATH, encoding="utf-8")

        big_main_layout = QHBoxLayout()
        log_layout = QVBoxLayout()
        main_layout = QVBoxLayout()

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        log_layout.addWidget(QLabel("Power Event Log:"))
        log_layout.addWidget(self.log_box)

        self.devices = []
        power_number = int(self.config.get("Setup", "power_number", fallback="1"))
        for i in range(1, power_number + 1):
            device = PowerDevice(i, self.config, self.log_box)
            self.devices.append(device)
            main_layout.addWidget(device)

        big_main_layout.addLayout(main_layout)
        big_main_layout.addLayout(log_layout)
        self.setLayout(big_main_layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.start(1000)

        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self.refresh_log_view)
        self.log_timer.start(2000)

    def update_status(self):
        """更新状态"""
        for device in self.devices:
            device.update_all_readings()

    def refresh_log_view(self):
        """刷新日志显示"""
        try:
            with open(LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                self.log_box.setPlainText(content)
                self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())
        except Exception as e:
            print("Log load error:", e)

    def closeEvent(self, event):
        """关闭事件处理"""
        for device in self.devices:
            device.disconnect_device()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    panel = PowerPanel()
    panel.show()
    sys.exit(app.exec())
