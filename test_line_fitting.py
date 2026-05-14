#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试拟合直线的异常情况处理
"""

import numpy as np
import math

def test_line_fitting():
    """测试各种异常情况的直线拟合"""
    
    print("=== 测试拟合直线异常情况处理 ===\n")
    
    # 测试1: 垂直直线（所有点经度相同）
    print("测试1: 垂直直线（所有点经度相同）")
    lats_vertical = [29.1, 29.2, 29.3, 29.4]
    lons_vertical = [119.1, 119.1, 119.1, 119.1]  # 所有经度相同
    
    if len(set(lons_vertical)) == 1:
        vertical_lon = lons_vertical[0]
        heading_angle = 90.0
        print(f"  垂直直线，经度: {vertical_lon}")
        print(f"  航向角: {heading_angle}°")
        
        # 模拟实验站
        station_lat = 29.25
        station_lon = 119.2
        distance_to_station = abs(station_lon - vertical_lon) * 111.0 * 1000 * math.cos(math.radians(station_lat))
        print(f"  到实验站距离: {distance_to_station:.1f}m")
    print()
    
    # 测试2: 水平直线（所有点纬度相同）
    print("测试2: 水平直线（所有点纬度相同）")
    lats_horizontal = [29.1, 29.1, 29.1, 29.1]  # 所有纬度相同
    lons_horizontal = [119.1, 119.2, 119.3, 119.4]
    
    if len(set(lats_horizontal)) == 1:
        horizontal_lat = lats_horizontal[0]
        heading_angle = 0.0
        print(f"  水平直线，纬度: {horizontal_lat}")
        print(f"  航向角: {heading_angle}°")
        
        # 模拟实验站
        station_lat = 29.2
        station_lon = 119.25
        distance_to_station = abs(station_lat - horizontal_lat) * 111.0 * 1000
        print(f"  到实验站距离: {distance_to_station:.1f}m")
    print()
    
    # 测试3: 正常直线拟合
    print("测试3: 正常直线拟合")
    lats_normal = [29.1, 29.2, 29.3, 29.4]
    lons_normal = [119.1, 119.2, 119.3, 119.4]
    
    try:
        coeffs = np.polyfit(lons_normal, lats_normal, 1)
        slope = coeffs[0]
        intercept = coeffs[1]
        
        if np.isfinite(slope) and np.isfinite(intercept):
            heading_angle = math.degrees(math.atan(slope))
            if heading_angle < 0:
                heading_angle += 360
            
            print(f"  斜率: {slope:.6f}")
            print(f"  截距: {intercept:.6f}")
            print(f"  航向角: {heading_angle:.1f}°")
            
            # 模拟实验站
            station_lat = 29.25
            station_lon = 119.25
            a = slope
            b = -1
            c = intercept
            
            denominator = math.sqrt(a**2 + b**2)
            if denominator > 1e-10:
                distance_to_line = abs(a * station_lon + b * station_lat + c) / denominator
                distance_to_station = distance_to_line * 111.0 * 1000
                print(f"  到实验站距离: {distance_to_station:.1f}m")
            else:
                print(f"  实验站正好在直线上")
        else:
            print("  拟合失败：斜率或截距为无穷大或NaN")
    except Exception as e:
        print(f"  拟合异常: {e}")
    print()
    
    # 测试4: 实验站正好在直线上
    print("测试4: 实验站正好在直线上")
    lats_line = [29.1, 29.2, 29.3]
    lons_line = [119.1, 119.2, 119.3]
    
    try:
        coeffs = np.polyfit(lons_line, lats_line, 1)
        slope = coeffs[0]
        intercept = coeffs[1]
        
        # 实验站正好在直线上
        station_lat = 29.2  # 直线上的点
        station_lon = 119.2
        
        a = slope
        b = -1
        c = intercept
        
        denominator = math.sqrt(a**2 + b**2)
        if denominator > 1e-10:
            distance_to_line = abs(a * station_lon + b * station_lat + c) / denominator
            distance_to_station = distance_to_line * 111.0 * 1000
            print(f"  到实验站距离: {distance_to_station:.1f}m")
        else:
            print(f"  实验站正好在直线上，距离为0")
    except Exception as e:
        print(f"  拟合异常: {e}")
    print()
    
    # 测试5: 只有两个相同点
    print("测试5: 只有两个相同点")
    lats_same = [29.1, 29.1]
    lons_same = [119.1, 119.1]
    
    if len(set(lats_same)) == 1 and len(set(lons_same)) == 1:
        print("  所有点重合，无法拟合直线")
    else:
        try:
            coeffs = np.polyfit(lons_same, lats_same, 1)
            slope = coeffs[0]
            intercept = coeffs[1]
            print(f"  斜率: {slope}")
            print(f"  截距: {intercept}")
        except Exception as e:
            print(f"  拟合异常: {e}")
    print()
    
    print("=== 测试完成 ===")

if __name__ == "__main__":
    test_line_fitting() 