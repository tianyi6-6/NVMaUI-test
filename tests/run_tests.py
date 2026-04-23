#!/usr/bin/env python3
"""
测试运行脚本

提供便捷的测试运行接口，支持：
- 运行所有测试
- 运行特定类型的测试
- 生成测试报告
- 性能分析
"""

import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime


def run_pytest(args, coverage=False, html_report=False):
    """运行pytest测试"""
    cmd = ["python", "-m", "pytest"]
    
    # 添加覆盖率参数
    if coverage:
        cmd.extend([
            "--cov=workflow_extension",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-report=xml"
        ])
    
    # 添加HTML报告
    if html_report:
        cmd.append("--html=test_report.html")
        cmd.append("--self-contained-html")
    
    # 添加用户参数
    cmd.extend(args)
    
    print(f"执行命令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, cwd=Path(__file__).parent)
        return result.returncode
    except Exception as e:
        print(f"测试执行失败: {e}")
        return 1


def run_performance_tests():
    """运行性能测试"""
    print("运行性能测试...")
    
    cmd = [
        "python", "-m", "pytest",
        "-m", "performance",
        "-v",
        "--tb=short",
        "--durations=10"
    ]
    
    return run_pytest(cmd)


def run_unit_tests():
    """运行单元测试"""
    print("运行单元测试...")
    
    cmd = [
        "python", "-m", "pytest",
        "-m", "unit",
        "-v",
        "--tb=short"
    ]
    
    return run_pytest(cmd)


def run_integration_tests():
    """运行集成测试"""
    print("运行集成测试...")
    
    cmd = [
        "python", "-m", "pytest",
        "-m", "integration",
        "-v",
        "--tb=short"
    ]
    
    return run_pytest(cmd)


def run_ui_tests():
    """运行UI测试"""
    print("运行UI测试...")
    
    cmd = [
        "python", "-m", "pytest",
        "-m", "ui",
        "-v",
        "--tb=short"
    ]
    
    return run_pytest(cmd)


def generate_test_report():
    """生成测试报告"""
    print("生成测试报告...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"test_report_{timestamp}.html"
    
    cmd = [
        "python", "-m", "pytest",
        "--html", report_file,
        "--self-contained-html",
        "--tb=short",
        "-v"
    ]
    
    return run_pytest(cmd)


def run_quick_tests():
    """运行快速测试（排除慢速测试）"""
    print("运行快速测试...")
    
    cmd = [
        "python", "-m", "pytest",
        "-v",
        "--tb=short",
        "-m", "not slow"
    ]
    
    return run_pytest(cmd)


def check_test_environment():
    """检查测试环境"""
    print("检查测试环境...")
    
    # 检查Python版本
    python_version = sys.version
    print(f"Python版本: {python_version}")
    
    # 检查必要的包
    required_packages = ["pytest", "PySide6", "psutil"]
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} 已安装")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package} 未安装")
    
    if missing_packages:
        print(f"\n缺少必要的包: {', '.join(missing_packages)}")
        print("请运行: pip install " + " ".join(missing_packages))
        return False
    
    # 检查测试文件
    test_dir = Path(__file__).parent
    test_files = list(test_dir.glob("test_*.py"))
    
    print(f"找到 {len(test_files)} 个测试文件:")
    for test_file in test_files:
        print(f"  - {test_file.name}")
    
    return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="工作流系统测试运行器")
    
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="检查测试环境"
    )
    
    parser.add_argument(
        "--unit",
        action="store_true",
        help="运行单元测试"
    )
    
    parser.add_argument(
        "--integration",
        action="store_true",
        help="运行集成测试"
    )
    
    parser.add_argument(
        "--ui",
        action="store_true",
        help="运行UI测试"
    )
    
    parser.add_argument(
        "--performance",
        action="store_true",
        help="运行性能测试"
    )
    
    parser.add_argument(
        "--quick",
        action="store_true",
        help="运行快速测试（排除慢速测试）"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="运行所有测试"
    )
    
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="生成覆盖率报告"
    )
    
    parser.add_argument(
        "--html-report",
        action="store_true",
        help="生成HTML测试报告"
    )
    
    parser.add_argument(
        "--report",
        action="store_true",
        help="生成详细测试报告"
    )
    
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="传递给pytest的额外参数"
    )
    
    args = parser.parse_args()
    
    # 检查环境
    if args.check_env:
        if not check_test_environment():
            sys.exit(1)
        return
    
    # 如果没有指定任何操作，显示帮助
    if not any([
        args.unit, args.integration, args.ui, args.performance,
        args.quick, args.all, args.report
    ]):
        parser.print_help()
        return
    
    # 切换到测试目录
    test_dir = Path(__file__).parent
    import os
    os.chdir(test_dir)
    
    # 执行相应的测试
    exit_code = 0
    
    if args.all:
        print("运行所有测试...")
        exit_code = run_pytest(
            args.pytest_args,
            coverage=args.coverage,
            html_report=args.html_report
        )
    elif args.unit:
        exit_code = run_unit_tests()
    elif args.integration:
        exit_code = run_integration_tests()
    elif args.ui:
        exit_code = run_ui_tests()
    elif args.performance:
        exit_code = run_performance_tests()
    elif args.quick:
        exit_code = run_quick_tests()
    
    # 生成报告
    if args.report and exit_code == 0:
        exit_code = generate_test_report()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
