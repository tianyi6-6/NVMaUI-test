#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
非线性区检测功能测试脚本
"""

import numpy as np
import time
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_nonlinear_detection():
    """测试非线性区检测功能"""
    
    # 模拟信号数据
    sample_rate = 1000  # 1kHz采样率
    duration = 10  # 10秒数据
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # 模拟正常信号（小幅度）
    normal_signal = 0.05 * np.sin(2 * np.pi * 1 * t) + 0.01 * np.random.randn(len(t))
    
    # 模拟非线性区信号（大幅度）
    nonlinear_signal = 0.2 * np.sin(2 * np.pi * 1 * t) + 0.05 * np.random.randn(len(t))
    
    # 测试参数
    threshold_mv = 100.0  # 100mV阈值
    duration_s = 3.0  # 3秒持续时间
    
    print("=== 非线性区检测功能测试 ===")
    print(f"阈值: {threshold_mv} mV")
    print(f"持续时间: {duration_s} s")
    print(f"采样率: {sample_rate} Hz")
    print(f"数据长度: {len(t)} 点")
    print()
    
    # 测试正常信号
    print("1. 测试正常信号（不应触发检测）")
    test_signal_detection(normal_signal, threshold_mv, duration_s, sample_rate)
    print()
    
    # 测试非线性信号
    print("2. 测试非线性信号（应触发检测）")
    test_signal_detection(nonlinear_signal, threshold_mv, duration_s, sample_rate)
    print()
    
    # 测试斜率计算
    print("3. 测试斜率计算功能")
    test_slope_calculation()

def test_signal_detection(signal, threshold_mv, duration_s, sample_rate):
    """测试信号检测功能"""
    threshold_v = threshold_mv / 1000.0  # 转换为V
    
    # 检查信号是否超过阈值
    exceeded_mask = np.abs(signal) >= threshold_v
    exceeded_count = np.sum(exceeded_mask)
    exceeded_ratio = exceeded_count / len(signal)
    
    print(f"   信号最大值: {np.max(np.abs(signal)):.6f} V")
    print(f"   超过阈值点数: {exceeded_count} / {len(signal)} ({exceeded_ratio:.2%})")
    
    if exceeded_ratio > 0.5:  # 如果超过50%的点都超过阈值
        print(f"   ✅ 检测到非线性区信号")
        
        # 模拟持续时间检测
        consecutive_exceeded = 0
        max_consecutive = 0
        for exceeded in exceeded_mask:
            if exceeded:
                consecutive_exceeded += 1
                max_consecutive = max(max_consecutive, consecutive_exceeded)
            else:
                consecutive_exceeded = 0
        
        consecutive_time = max_consecutive / sample_rate
        print(f"   最长连续超过阈值时间: {consecutive_time:.2f} s")
        
        if consecutive_time >= duration_s:
            print(f"   ✅ 持续时间达到阈值，应触发重设")
        else:
            print(f"   ❌ 持续时间不足，不触发重设")
    else:
        print(f"   ❌ 未检测到非线性区信号")

def test_slope_calculation():
    """测试斜率计算功能"""
    from scipy.stats import linregress
    
    # 模拟带趋势的信号
    t = np.linspace(0, 10, 1000)
    signal = 0.1 * t + 0.05 * np.random.randn(len(t))  # 线性趋势 + 噪声
    
    # 计算斜率
    slope, intercept, r_value, p_value, std_err = linregress(t, signal)
    
    print(f"   信号斜率: {slope:.6f}")
    print(f"   截距: {intercept:.6f}")
    print(f"   相关系数: {r_value:.6f}")
    print(f"   零点频率偏移: {-intercept/slope:.6f} Hz" if abs(slope) > 1e-6 else "   斜率太小，无法计算零点")

if __name__ == "__main__":
    test_nonlinear_detection() 