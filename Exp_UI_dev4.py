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
    device_name = "样机4 (WR05-01)"
    exp_config_path = "config/exp_config_dev4.ini"
    sys_config_path = "config/system_config_dev4.ini"
    lockin_port = "192.168.3.101:5005"  # TCP/IP通信
    ultramotor_port = "COM14"  # RS485-串口通信
    log_path = "log/experiment_log_dev4.txt"
    
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
