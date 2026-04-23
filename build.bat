@echo off
chcp 65001 >nul
echo ========================================
echo 航迹信息记录器打包工具
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python
    pause
    exit /b 1
)

echo Python环境检查通过
echo.

REM 运行打包脚本
python build_exe.py

echo.
echo 按任意键退出...
pause >nul 