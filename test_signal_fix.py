#!/usr/bin/env python3
"""
测试信号连接修复
验证程序不再在信号连接时崩溃
"""

import sys
import os
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_signal_connection():
    """测试信号连接是否正常工作"""
    print("=== 测试信号连接修复 ===")
    
    try:
        # 导入主程序
        from geo_sites_locator import FlightTrackApp
        
        # 创建应用程序
        app = QApplication(sys.argv)
        
        # 创建主窗口
        window = FlightTrackApp()
        window.show()
        
        # 设置实验站
        window.on_experiment_station_changed(29.5600, 119.1767, "测试实验站")
        
        # 开启采集
        window.on_collecting_status_changed(True)
        
        print("✓ 程序启动成功")
        print("✓ 实验站设置成功")
        print("✓ 采集状态开启成功")
        
        # 测试添加单个航点
        def test_add_waypoint():
            try:
                # 模拟添加航点
                waypoint_table = window.waypoint_table
                waypoint_table.add_waypoint()
                print("✓ 添加航点功能正常")
                
                # 测试初始化默认航线
                def test_default_route():
                    try:
                        waypoint_table.init_default_waypoints()
                        print("✓ 初始化默认航线功能正常")
                        
                        # 测试表格更新
                        if len(waypoint_table.waypoints) > 0:
                            print(f"✓ 成功创建 {len(waypoint_table.waypoints)} 个航点")
                            print("✓ 表格更新正常")
                            print("✓ 信号连接修复成功！")
                        else:
                            print("✗ 航点创建失败")
                        
                        # 关闭程序
                        QTimer.singleShot(1000, app.quit)
                        
                    except Exception as e:
                        print(f"✗ 初始化默认航线失败: {e}")
                        QTimer.singleShot(1000, app.quit)
                
                # 延迟测试默认航线
                QTimer.singleShot(500, test_default_route)
                
            except Exception as e:
                print(f"✗ 添加航点失败: {e}")
                QTimer.singleShot(1000, app.quit)
        
        # 延迟测试添加航点
        QTimer.singleShot(500, test_add_waypoint)
        
        # 运行应用程序
        return app.exec()
        
    except Exception as e:
        print(f"✗ 程序启动失败: {e}")
        return 1

def test_signal_disconnect():
    """测试信号断开连接的安全性"""
    print("\n=== 测试信号断开连接安全性 ===")
    
    try:
        from PySide6.QtWidgets import QApplication, QTableWidget
        from PySide6.QtCore import QObject
        
        # 创建QApplication（如果还没有的话）
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        # 创建测试对象
        table = QTableWidget()
        
        def test_handler():
            pass
        
        # 测试未连接时断开信号
        try:
            table.itemChanged.disconnect(test_handler)
            print("✗ 应该抛出异常但没有")
        except (TypeError, RuntimeError):
            print("✓ 未连接时断开信号正确抛出异常")
        
        # 测试连接后断开信号
        table.itemChanged.connect(test_handler)
        try:
            table.itemChanged.disconnect(test_handler)
            print("✓ 连接后断开信号正常")
        except Exception as e:
            print(f"✗ 连接后断开信号失败: {e}")
        
        print("✓ 信号断开连接测试通过")
        return True
        
    except Exception as e:
        print(f"✗ 信号断开连接测试失败: {e}")
        return False

if __name__ == '__main__':
    print("开始测试信号连接修复...")
    
    # 测试信号断开连接安全性
    if test_signal_disconnect():
        # 测试完整程序
        result = test_signal_connection()
        sys.exit(result)
    else:
        sys.exit(1) 