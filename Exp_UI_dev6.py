# encoding=utf-8
"""
样机2启动程序
"""
import sys
from PySide6.QtWidgets import QApplication
from Exp_UI import ExperimentApp

if __name__ == '__main__':

    app = QApplication(sys.argv)
    
    # 样机2的配置参数
    device_name = "样机4 (WR06-02)"
    exp_config_path = "config/exp_config_dev6.ini"
    sys_config_path = "config/system_config_dev6.ini"
    lockin_port = r"interface\Lockin\usblib\module_64\libusb-1.0.dll"  # TCP/IP通信
    ultramotor_port = "COM12"  # RS485-串口通信
    log_path = "log/experiment_log_dev6.txt"
    
    # 创建并显示主窗口
    window = ExperimentApp(
        device_name=device_name,
        exp_config_path=exp_config_path,
        sys_config_path=sys_config_path,
        lockin_port=lockin_port,
        ultramotor_port=ultramotor_port,
        log_path=log_path
    )
    window.show()
    sys.exit(app.exec())
