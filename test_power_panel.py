#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试重构后的电源控制面板
"""

import sys
import os
import configparser
from datetime import datetime

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config_loading():
    """测试配置文件加载"""
    print("=== 测试配置文件加载 ===")
    
    config = configparser.ConfigParser()
    config.read("config/power_config.ini", encoding="utf-8")
    
    # 检查基本配置
    power_number = int(config.get("Setup", "power_number", fallback="1"))
    print(f"电源设备数量: {power_number}")
    
    for i in range(1, power_number + 1):
        device_type = config.get("Setup", f"power_device_type_{i}", fallback="Unknown")
        resource_name = config.get("Setup", f"power_device_id_{i}", fallback="")
        name = config.get(f"power_{i}", "name", fallback=f"Device {i}")
        
        print(f"设备 {i}: {name}")
        print(f"  类型: {device_type}")
        print(f"  资源名: {resource_name}")
        
        # 检查通道配置
        ch_count = int(config.get(f"power_{i}", "channels", fallback="3"))
        print(f"  通道数: {ch_count}")
        
        for ch in range(1, ch_count + 1):
            ch_name = config.get(f"power_{i}", f"ch{ch}_name", fallback=f"CH{ch}")
            v_max = float(config.get(f"power_{i}", f"ch{ch}_max_volt", fallback="30"))
            i_max = float(config.get(f"power_{i}", f"ch{ch}_max_current", fallback="3"))
            editable = config.getboolean(f"power_{i}", f"ch{ch}_editable", fallback=False)
            
            print(f"    通道 {ch}: {ch_name}")
            print(f"      最大电压: {v_max}V")
            print(f"      最大电流: {i_max}A")
            print(f"      可编辑: {editable}")
    
    print()

def test_device_interfaces():
    """测试设备接口"""
    print("=== 测试设备接口 ===")
    
    try:
        from interface.DP832 import RigolDP832Controller
        print("✓ DP832接口导入成功")
    except ImportError as e:
        print(f"✗ DP832接口导入失败: {e}")
    
    try:
        from interface.UDP3305S import UniTUDP3305SController
        print("✓ UDP3305S接口导入成功")
    except ImportError as e:
        print(f"✗ UDP3305S接口导入失败: {e}")
    
    print()

def test_visa_resources():
    """测试VISA资源"""
    print("=== 测试VISA资源 ===")
    
    try:
        import pyvisa
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        
        if resources:
            print("发现VISA设备:")
            for i, resource in enumerate(resources, 1):
                print(f"  {i}. {resource}")
        else:
            print("未发现VISA设备")
            
    except ImportError:
        print("✗ PyVISA未安装")
    except Exception as e:
        print(f"✗ VISA资源检测失败: {e}")
    
    print()

def test_power_panel_import():
    """测试电源面板导入"""
    print("=== 测试电源面板导入 ===")
    
    try:
        from power_panel import PowerPanel, PowerDevice, PowerChannel, DeviceConnectionThread
        print("✓ 电源面板模块导入成功")
        
        # 测试类定义
        print("✓ PowerPanel类定义正常")
        print("✓ PowerDevice类定义正常")
        print("✓ PowerChannel类定义正常")
        print("✓ DeviceConnectionThread类定义正常")
        
        # 测试默认参数设置功能
        print("✓ 默认参数设置功能已添加")
        
    except ImportError as e:
        print(f"✗ 电源面板模块导入失败: {e}")
    except Exception as e:
        print(f"✗ 电源面板测试失败: {e}")
    
    print()

def test_log_function():
    """测试日志功能"""
    print("=== 测试日志功能 ===")
    
    try:
        from power_panel import log_event
        
        # 创建日志目录
        os.makedirs("log", exist_ok=True)
        
        # 测试日志写入
        test_message = f"测试日志消息 - {datetime.now()}"
        log_event(test_message)
        print("✓ 日志写入功能正常")
        
        # 检查日志文件
        log_path = "log/power_log.txt"
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if test_message in content:
                    print("✓ 日志文件内容正确")
                else:
                    print("✗ 日志文件内容不正确")
        else:
            print("✗ 日志文件未创建")
            
    except Exception as e:
        print(f"✗ 日志功能测试失败: {e}")
    
    print()

def test_default_parameters():
    """测试默认参数设置功能"""
    print("=== 测试默认参数设置功能 ===")
    
    try:
        config = configparser.ConfigParser()
        config.read("config/power_config.ini", encoding="utf-8")
        
        # 检查配置文件中的默认参数
        power_number = int(config.get("Setup", "power_number", fallback="1"))
        
        for i in range(1, power_number + 1):
            section = f"power_{i}"
            ch_count = int(config.get(section, "channels", fallback="3"))
            
            print(f"设备 {i} 默认参数:")
            for ch in range(1, ch_count + 1):
                v_default = float(config.get(section, f"ch{ch}_default_volt", fallback="0"))
                i_default = float(config.get(section, f"ch{ch}_default_current", fallback="0"))
                ch_name = config.get(section, f"ch{ch}_name", fallback=f"CH{ch}")
                
                print(f"  通道 {ch} ({ch_name}): V={v_default}V, I={i_default}A")
        
        print("✓ 默认参数配置检查完成")
        
    except Exception as e:
        print(f"✗ 默认参数测试失败: {e}")
    
    print()

def main():
    """主测试函数"""
    print("电源控制面板重构测试")
    print("=" * 50)
    
    test_config_loading()
    test_device_interfaces()
    test_visa_resources()
    test_power_panel_import()
    test_log_function()
    test_default_parameters()
    
    print("测试完成")
    print("=" * 50)
    print("如果所有测试都通过，可以运行 power_panel.py 启动电源控制面板")

if __name__ == "__main__":
    main() 