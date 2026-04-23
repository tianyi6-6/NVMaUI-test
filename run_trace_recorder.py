#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
航迹信息记录器启动脚本
"""

import sys
import os

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from trace_line_info_recorder import main
    main()
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保已安装PySide6: pip install PySide6")
    sys.exit(1)
except Exception as e:
    print(f"运行错误: {e}")
    sys.exit(1) 