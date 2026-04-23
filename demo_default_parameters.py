#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
默认参数设置功能演示
展示设备连接成功后自动设置默认参数的功能
"""

import sys
import os
import configparser
from datetime import datetime

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def show_default_parameters():
    """显示配置文件中的默认参数"""
    print("=== 默认参数配置演示 ===")
    print()
    
    config = configparser.ConfigParser()
    config.read("config/power_config.ini", encoding="utf-8")
    
    power_number = int(config.get("Setup", "power_number", fallback="1"))
    
    for i in range(1, power_number + 1):
        section = f"power_{i}"
        name = config.get(section, "name", fallback=f"Device {i}")
        device_type = config.get("Setup", f"power_device_type_{i}", fallback="Unknown")
        ch_count = int(config.get(section, "channels", fallback="3"))
        
        print(f"设备 {i}: {name} ({device_type})")
        print("-" * 50)
        
        for ch in range(1, ch_count + 1):
            ch_name = config.get(section, f"ch{ch}_name", fallback=f"CH{ch}")
            v_default = float(config.get(section, f"ch{ch}_default_volt", fallback="0"))
            i_default = float(config.get(section, f"ch{ch}_default_current", fallback="0"))
            editable = config.getboolean(section, f"ch{ch}_editable", fallback=False)
            
            print(f"  通道 {ch}: {ch_name}")
            print(f"    默认电压: {v_default}V")
            print(f"    默认电流: {i_default}A")
            print(f"    可编辑: {'是' if editable else '否'}")
            print()
    
    print("=" * 50)

def show_workflow():
    """显示工作流程"""
    print("=== 默认参数设置工作流程 ===")
    print()
    
    steps = [
        "1. 用户勾选'Enable Communication'",
        "2. 系统尝试连接设备",
        "3. 连接成功后触发默认参数设置",
        "4. 从配置文件读取默认电压和电流值",
        "5. 设置设备参数（set_voltage, set_current）",
        "6. 更新UI显示（避免重复触发）",
        "7. 记录操作日志",
        "8. 设备准备就绪，等待用户操作"
    ]
    
    for step in steps:
        print(step)
    
    print()
    print("=" * 50)

def show_benefits():
    """显示功能优势"""
    print("=== 默认参数设置功能优势 ===")
    print()
    
    benefits = [
        "✓ 自动化操作：无需手动设置每个通道",
        "✓ 提高效率：减少重复性操作",
        "✓ 确保安全：使用预配置的安全参数",
        "✓ 一致性：每次启动都使用相同的默认值",
        "✓ 可配置：通过配置文件灵活调整",
        "✓ 智能避免：防止设置过程中的重复触发",
        "✓ 完整日志：记录所有设置操作"
    ]
    
    for benefit in benefits:
        print(benefit)
    
    print()
    print("=" * 50)

def show_usage_example():
    """显示使用示例"""
    print("=== 使用示例 ===")
    print()
    
    print("配置文件示例 (config/power_config.ini):")
    print("""
[power_1]
name = NV磁传感器供电电源
ch1_name = NV磁传感器 - 样机1
ch1_default_volt = 24.0
ch1_default_current = 3.0
ch1_editable = False

[power_2]
name = 超声电机供电电源
ch1_name = 超声电机 - 样机1
ch1_default_volt = 24.0
ch1_default_current = 1.0
ch1_editable = False
""")
    
    print("操作步骤:")
    print("1. 启动程序: python power_panel.py")
    print("2. 勾选'Enable Communication'")
    print("3. 等待连接成功（状态变为'Connected'）")
    print("4. 观察设备自动设置默认参数")
    print("5. 查看日志文件确认设置结果")
    
    print()
    print("=" * 50)

def main():
    """主函数"""
    print("默认参数设置功能演示")
    print("=" * 60)
    print()
    
    show_default_parameters()
    show_workflow()
    show_benefits()
    show_usage_example()
    
    print("演示完成！")
    print("要体验实际功能，请运行: python power_panel.py")

if __name__ == "__main__":
    main() 