#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
航迹信息记录器 PyInstaller 打包脚本
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_pyinstaller():
    """检查PyInstaller是否已安装"""
    try:
        import PyInstaller
        print(f"✓ PyInstaller 已安装，版本: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("✗ PyInstaller 未安装")
        print("正在安装 PyInstaller...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("✓ PyInstaller 安装成功")
            return True
        except subprocess.CalledProcessError:
            print("✗ PyInstaller 安装失败")
            return False

def build_executable():
    """构建可执行文件"""
    print("\n=== 开始构建可执行文件 ===")
    
    # 获取当前目录
    current_dir = Path(__file__).parent
    main_script = r"D:\Software Learning\NVMagUI\run_trace_recorder.py"
    
    # if not main_script.exists():
    #     print(f"✗ 主程序文件不存在: {main_script}")
    #     return False
    
    # 构建输出目录
    dist_dir = current_dir / "dist"
    build_dir = current_dir / "build"
    
    # 清理之前的构建文件
    if dist_dir.exists():
        print("清理之前的构建文件...")
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    
    # PyInstaller 命令参数
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name=航迹信息记录器",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=PySide6.QtGui",
        "--clean",
        str(main_script)
    ]
    
    # 如果没有图标文件，移除图标参数
    # if not (current_dir / "icon.ico").exists():
    #     cmd = [arg for arg in cmd if not arg.startswith("--icon")]
    #     print("注意: 未找到 icon.ico 文件，将使用默认图标")
    
    print(f"执行命令: {' '.join(cmd)}")
    
    try:
        # 执行PyInstaller
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print("✓ 构建成功!")
        
        # 检查输出文件
        exe_path = dist_dir / "航迹信息记录器.exe"
        if exe_path.exists():
            file_size = exe_path.stat().st_size / (1024 * 1024)  # MB
            print(f"✓ 可执行文件已生成: {exe_path}")
            print(f"✓ 文件大小: {file_size:.2f} MB")
            
            # 创建数据目录说明
            readme_path = dist_dir / "使用说明.txt"
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write("""航迹信息记录器使用说明

1. 运行程序
   - 双击 "航迹信息记录器.exe" 启动程序

2. 数据保存位置
   - 所有航迹数据将保存在 D:/trace_data 目录下
   - 程序会自动创建该目录

3. 文件格式
   - 主航迹信息: trace_YYYYMMDD_HHMMSS.csv
   - 航迹点详情: trace_points_YYYYMMDD_HHMMSS.csv

4. 注意事项
   - 确保D盘有足够空间存储数据
   - 程序需要网络连接（首次运行可能需要下载依赖）

5. 技术支持
   - 详细使用说明请参考 README_trace_recorder.md
""")
            print(f"✓ 使用说明已生成: {readme_path}")
            
            return True
        else:
            print("✗ 可执行文件生成失败")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"✗ 构建失败: {e}")
        print(f"错误输出: {e.stderr}")
        return False

def create_icon():
    """创建简单的图标文件（可选）"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # 创建一个简单的图标
        size = (256, 256)
        img = Image.new('RGBA', size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        
        # 绘制简单的图标
        draw.ellipse([50, 50, 206, 206], fill=(76, 175, 80, 255), outline=(56, 142, 60, 255), width=3)
        draw.text((128, 128), "航", fill=(255, 255, 255, 255), anchor="mm")
        
        # 保存为ICO文件
        icon_path = Path(__file__).parent / "icon.ico"
        img.save(icon_path, format='ICO', sizes=[(256, 256)])
        print(f"✓ 图标文件已创建: {icon_path}")
        return True
    except ImportError:
        print("注意: PIL未安装，跳过图标创建")
        return False
    except Exception as e:
        print(f"图标创建失败: {e}")
        return False

def main():
    """主函数"""
    print("=== 航迹信息记录器打包工具 ===")
    print(f"当前目录: {Path(__file__).parent}")
    
    # 检查PyInstaller
    if not check_pyinstaller():
        print("请手动安装 PyInstaller: pip install pyinstaller")
        return
    
    # 尝试创建图标
    # create_icon()
    
    # 构建可执行文件
    if build_executable():
        print("\n=== 打包完成 ===")
        print("可执行文件位置: dist/航迹信息记录器.exe")
        print("使用说明位置: dist/使用说明.txt")
        print("\n提示:")
        print("1. 将整个 dist 文件夹复制到目标机器即可使用")
        print("2. 确保目标机器有足够的磁盘空间")
        print("3. 首次运行可能需要较长时间")
    else:
        print("\n=== 打包失败 ===")
        print("请检查错误信息并重试")

if __name__ == "__main__":
    main() 