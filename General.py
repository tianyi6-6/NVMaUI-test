import logging
import sys
import configparser
import os

# EXP_CONFIG = "config/exp_config.ini"
SYSTEM_CONFIG = "config/system_config.ini"

# Setup logging to file
# log_filename = "log/experiment_log.txt"
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s',
#                     handlers=[logging.FileHandler(log_filename, mode='a', encoding='utf-8'), logging.StreamHandler(sys.stdout)])

class Virtual_Device:
    def __init__(self, *args, **kwargs):
        pass

    def set_param(self, *args, **kwargs):
        # print(f'虚拟设备设置参数：{args[1]}')
        return args[1]

    def set_all_params(self, *args, **kwargs):
        pass

    def set_dev(self, *args, **kwargs):
        pass

    def error_check(self, data_num, *args, **kwargs):
        return True, data_num, data_num

    def close_device(self, *args, **kwargs):
        pass

    def close(self, *args, **kwargs):
        pass

def load_config(path):
    print(f'读取日志文件：{path}')
    config = configparser.ConfigParser()
    config.read(path, encoding='utf-8')
    return config

def gettimestr():
    import time
    return time.strftime('%Y-%m-%d %H_%M_%S', time.localtime(time.time()))

def create_dir(path):
    if not os.path.exists(path):
        os.mkdir(path)
    return path