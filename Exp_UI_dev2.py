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
    device_name = "样机2 (WR04-04)"
    exp_config_path = "config/exp_config_dev2.ini"
    sys_config_path = "config/system_config_dev2.ini"
    lockin_port = "192.168.3.100:5005"  # TCP/IP通信
    ultramotor_port = "COM4"  # RS485-串口通信
    log_path = "log/experiment_log_dev2.txt"
    
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
