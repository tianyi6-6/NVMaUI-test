# 工作流系统测试框架

本测试框架基于文档第9章测试规范构建，提供完整的测试覆盖，包括单元测试、集成测试、UI测试和性能测试。

## 📁 测试文件结构

```
tests/
├── __init__.py              # 测试模块初始化
├── conftest.py              # pytest配置和夹具
├── pytest.ini              # pytest配置文件
├── README.md                # 本文件
├── run_tests.py             # 测试运行脚本
├── profile_workflow.py      # 性能分析工具
├── test_node_executors.py   # 节点执行器单元测试
├── test_node_registry.py    # 节点注册机制测试
├── test_serialization.py    # 数据序列化测试
├── test_workflow_integration.py  # 工作流集成测试
├── test_ui_interaction.py   # UI交互测试
└── test_performance.py      # 性能测试
```

## 🚀 快速开始

### 环境检查

```bash
python run_tests.py --check-env
```

### 运行所有测试

```bash
python run_tests.py --all
```

### 运行特定类型测试

```bash
# 单元测试
python run_tests.py --unit

# 集成测试
python run_tests.py --integration

# UI测试
python run_tests.py --ui

# 性能测试
python run_tests.py --performance

# 快速测试（排除慢速测试）
python run_tests.py --quick
```

### 生成测试报告

```bash
# HTML报告
python run_tests.py --all --html-report

# 详细报告
python run_tests.py --all --report

# 覆盖率报告
python run_tests.py --all --coverage
```

## 📊 测试分类

### 🏗️ 单元测试 (@pytest.mark.unit)

测试单个组件的功能：

- **节点执行器测试** (`test_node_executors.py`)
  - 内置节点执行器功能测试
  - CW谱节点执行器功能测试
  - 异常处理测试
  - 参数验证测试

- **节点注册机制测试** (`test_node_registry.py`)
  - 节点注册功能测试
  - 节点查询功能测试
  - 节点分组功能测试
  - 重复注册处理测试

- **数据序列化测试** (`test_serialization.py`)
  - 工作流保存和加载测试
  - JSON格式导出测试
  - Python脚本导出测试
  - XOR加密/解密测试
  - 版本兼容性测试

### 🔗 集成测试 (@pytest.mark.integration)

测试组件间的协作：

- **工作流执行测试** (`test_workflow_integration.py`)
  - 简单工作流执行测试
  - 复杂工作流执行测试
  - 错误处理工作流测试
  - 并行执行测试
  - 状态监控测试

### 🎨 UI测试 (@pytest.mark.ui)

测试用户界面交互：

- **UI交互测试** (`test_ui_interaction.py`)
  - 节点拖拽操作测试
  - 连线操作测试
  - 参数编辑测试
  - 画布交互测试
  - 键盘快捷键测试

### ⚡ 性能测试 (@pytest.mark.performance)

测试系统性能指标：

- **性能测试** (`test_performance.py`)
  - 节点执行性能测试
  - 工作流执行性能测试
  - 内存使用性能测试
  - 大规模数据处理性能测试
  - 并发性能测试

## 🛠️ 性能分析

### 使用性能分析工具

```bash
# 分析节点性能
python profile_workflow.py --nodes

# 分析工作流性能
python profile_workflow.py --workflows

# 分析内存使用
python profile_workflow.py --memory

# 执行所有分析
python profile_workflow.py --all

# 指定输出文件
python profile_workflow.py --all --output my_performance_report.txt
```

### 性能基准

当前性能基准（在参考硬件上）：

- **简单节点执行**: < 1ms
- **线性工作流(50节点)**: < 1s
- **并行工作流(10节点)**: < 500ms
- **内存使用增长**: < 50MB
- **序列化(100节点)**: < 500ms

## 📋 测试标记

使用pytest标记来分类和组织测试：

```python
@pytest.mark.unit        # 单元测试
@pytest.mark.integration # 集成测试
@pytest.mark.ui          # UI测试
@pytest.mark.performance # 性能测试
@pytest.mark.slow        # 慢速测试
```

### 运行特定标记的测试

```bash
# 只运行单元测试
pytest -m unit

# 运行单元测试和集成测试
pytest -m "unit or integration"

# 排除慢速测试
pytest -m "not slow"
```

## 🔧 测试夹具

### 常用夹具

- `temp_dir`: 临时目录
- `mock_app`: 模拟应用实例
- `test_context`: 测试上下文
- `sample_node`: 示例节点
- `sample_graph`: 示例工作流图
- `node_registry`: 节点注册表
- `workflow_executor`: 工作流执行器
- `performance_monitor`: 性能监控器

### 使用夹具示例

```python
def test_example(sample_node, test_context):
    """使用夹具的测试示例"""
    result = execute_node(sample_node, test_context)
    assert result is not None
```

## 📈 覆盖率报告

生成代码覆盖率报告：

```bash
# 生成HTML覆盖率报告
python run_tests.py --all --coverage

# 查看报告
# 打开 htmlcov/index.html
```

覆盖率目标：
- **整体覆盖率**: > 80%
- **核心模块覆盖率**: > 90%
- **测试工具覆盖率**: > 70%

## 🐛 调试测试

### 运行单个测试

```bash
# 运行单个测试文件
pytest test_node_executors.py -v

# 运行单个测试函数
pytest test_node_executors.py::TestBuiltinNodeExecutors::test_device_connect_success -v

# 显示详细输出
pytest -v -s
```

### 调试模式

```bash
# 在第一个失败时停止
pytest -x

# 显示本地变量
pytest -l

# 使用pdb调试
pytest --pdb
```

## 📝 编写新测试

### 单元测试模板

```python
import pytest
from workflow_extension.models import WorkflowNodeModel

class TestNewFeature:
    """新功能测试类"""
    
    @pytest.mark.unit
    def test_new_functionality(self, test_context):
        """测试新功能"""
        # 准备测试数据
        node = WorkflowNodeModel(...)
        
        # 执行测试
        result = execute_function(node, test_context)
        
        # 验证结果
        assert result["expected_key"] == "expected_value"
    
    @pytest.mark.unit
    def test_error_handling(self, test_context):
        """测试错误处理"""
        # 准备会导致错误的测试数据
        node = WorkflowNodeModel(...)
        
        # 执行测试
        result = execute_function(node, test_context)
        
        # 验证错误处理
        assert "error" in result
```

### 集成测试模板

```python
import pytest
from workflow_extension.models import WorkflowGraphModel, WorkflowNodeModel, WorkflowEdgeModel

class TestNewIntegration:
    """新集成测试类"""
    
    @pytest.fixture
    def integration_workflow(self):
        """集成测试工作流"""
        nodes = [...]
        edges = [...]
        return WorkflowGraphModel(nodes=nodes, edges=edges)
    
    @pytest.mark.integration
    def test_integration_scenario(self, integration_workflow, executor, test_context):
        """测试集成场景"""
        # 执行工作流
        executor.run(integration_workflow, test_context)
        
        # 验证集成结果
        assert expected_result
```

## 🚨 持续集成

### CI配置示例

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.8
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov pytest-html
    - name: Run tests
      run: |
        cd tests
        python run_tests.py --all --coverage --html-report
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

## 📊 测试报告

测试完成后会生成以下报告：

- `test_report.html`: HTML格式的测试报告
- `htmlcov/`: 代码覆盖率报告
- `performance_report_*.txt`: 性能分析报告

## 🔍 故障排除

### 常见问题

1. **UI测试失败**
   - 确保有可用的显示环境
   - 检查PySide6安装

2. **性能测试不稳定**
   - 在负载较低的机器上运行
   - 多次运行取平均值

3. **内存测试误报**
   - 检查系统内存使用情况
   - 考虑GC时机的影响

### 调试技巧

- 使用 `-v` 标志查看详细输出
- 使用 `--tb=short` 简化错误输出
- 使用 `--lf` 只运行上次失败的测试

## 📚 参考资料

- [pytest官方文档](https://docs.pytest.org/)
- [PySide6测试指南](https://doc.qt.io/qtforpython/testing.html)
- [Python性能分析](https://docs.python.org/3/library/profile.html)

## 🤝 贡献指南

添加新测试时请遵循：

1. 使用适当的测试标记
2. 编写清晰的测试文档
3. 添加必要的测试夹具
4. 确保测试独立性
5. 更新此README文档

---

**测试框架版本**: 1.0  
**最后更新**: 2024-01-XX  
**维护者**: 工作流系统开发团队
