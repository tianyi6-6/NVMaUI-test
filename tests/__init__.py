"""
工作流系统测试模块

本模块包含工作流系统的完整测试套件，包括：
- 单元测试：节点执行器、注册机制、序列化测试
- 集成测试：工作流执行、UI交互、性能测试
- 测试工具：pytest配置、性能分析工具
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 测试配置
TEST_CONFIG = {
    "test_data_dir": project_root / "tests" / "data",
    "temp_dir": project_root / "tests" / "temp",
    "mock_devices": True,
    "performance_threshold": {
        "node_execution": 1.0,  # 秒
        "workflow_execution": 10.0,  # 秒
        "ui_response": 0.1,  # 秒
    }
}
