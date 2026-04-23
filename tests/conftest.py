"""
pytest配置文件

提供测试夹具和全局配置，确保测试环境的一致性。
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock
import logging

# 禁用日志输出，保持测试输出清洁
logging.basicConfig(level=logging.CRITICAL)


@pytest.fixture
def temp_dir():
    """临时目录夹具"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture
def mock_app():
    """模拟应用实例夹具"""
    app = Mock()
    app.dev = Mock()
    app.dev.is_connected = True
    app.dev.get_status = Mock(return_value="ready")
    return app


@pytest.fixture
def test_context(mock_app):
    """测试上下文夹具"""
    return {
        "app": mock_app,
        "plot_callback": Mock(),
        "test_mode": True
    }


@pytest.fixture
def sample_node():
    """示例节点夹具"""
    from workflow_extension.models import WorkflowNodeModel
    return WorkflowNodeModel(
        node_id="test_node_1",
        node_type="test.type",
        title="测试节点",
        position=(100.0, 100.0),
        params={"param1": "value1", "param2": 42}
    )


@pytest.fixture
def sample_graph():
    """示例工作流图夹具"""
    from workflow_extension.models import WorkflowGraphModel, WorkflowNodeModel, WorkflowEdgeModel
    
    nodes = [
        WorkflowNodeModel(
            node_id="node_1",
            node_type="data.source",
            title="数据源",
            position=(50.0, 50.0),
            params={}
        ),
        WorkflowNodeModel(
            node_id="node_2", 
            node_type="logic.delay",
            title="延时",
            position=(200.0, 50.0),
            params={"delay_ms": 100}
        )
    ]
    
    edges = [
        WorkflowEdgeModel(
            from_node="node_1",
            to_node="node_2",
            from_port="out",
            to_port="in"
        )
    ]
    
    return WorkflowGraphModel(
        name="测试工作流",
        nodes=nodes,
        edges=edges
    )


@pytest.fixture
def node_registry():
    """节点注册表夹具"""
    from workflow_extension.node_registry import NodeRegistry
    from workflow_extension.builtins import register_builtin_nodes
    
    registry = NodeRegistry()
    register_builtin_nodes(registry)
    return registry


@pytest.fixture
def workflow_executor(node_registry):
    """工作流执行器夹具"""
    from workflow_extension.engine import WorkflowExecutor
    return WorkflowExecutor(node_registry)


# 性能测试夹具
@pytest.fixture
def performance_monitor():
    """性能监控夹具"""
    import time
    import threading
    
    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.checkpoints = []
        
        def start(self):
            self.start_time = time.time()
            self.checkpoints = []
        
        def checkpoint(self, name):
            if self.start_time:
                elapsed = time.time() - self.start_time
                self.checkpoints.append((name, elapsed))
        
        def stop(self):
            self.end_time = time.time()
        
        def get_duration(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
    
    return PerformanceMonitor()


# 标记定义
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.ui = pytest.mark.ui
pytest.mark.slow = pytest.mark.slow
