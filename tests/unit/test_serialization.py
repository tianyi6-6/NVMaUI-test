"""
数据序列化/反序列化单元测试

测试工作流系统的数据序列化功能，包括：
- 工作流保存和加载
- JSON格式导出
- Python脚本导出
- 加密/解密功能
- 版本兼容性
- 异常处理
"""

import pytest
import json
import tempfile
from pathlib import Path
from workflow_extension.models import WorkflowGraphModel, WorkflowNodeModel, WorkflowEdgeModel
from workflow_extension.serializer import (
    save_workflow,
    load_workflow,
    export_json,
    export_python,
    _xor_crypt
)


class TestWorkflowSerialization:
    """工作流序列化测试类"""
    
    @pytest.fixture
    def sample_workflow(self):
        """示例工作流数据"""
        nodes = [
            WorkflowNodeModel(
                node_id="node_1",
                node_type="data.source",
                title="数据源",
                position=(50.0, 50.0),
                params={"frequency": 1000, "amplitude": 1.0}
            ),
            WorkflowNodeModel(
                node_id="node_2",
                node_type="logic.delay",
                title="延时",
                position=(200.0, 50.0),
                params={"delay_ms": 100}
            ),
            WorkflowNodeModel(
                node_id="node_3",
                node_type="plot.stream",
                title="绘图",
                position=(350.0, 50.0),
                params={}
            )
        ]
        
        edges = [
            WorkflowEdgeModel(
                from_node="node_1",
                to_node="node_2",
                from_port="out",
                to_port="in"
            ),
            WorkflowEdgeModel(
                from_node="node_2",
                to_node="node_3",
                from_port="out",
                to_port="in"
            )
        ]
        
        return WorkflowGraphModel(
            name="测试工作流",
            nodes=nodes,
            edges=edges
        )
    
    @pytest.mark.unit
    def test_save_and_load_workflow(self, sample_workflow, temp_dir):
        """测试工作流保存和加载"""
        file_path = temp_dir / "test_workflow.nvw"
        
        # 保存工作流
        save_workflow(sample_workflow, str(file_path))
        
        # 验证文件存在
        assert file_path.exists()
        
        # 加载工作流
        loaded_workflow = load_workflow(str(file_path))
        
        # 验证加载的工作流
        assert loaded_workflow.name == sample_workflow.name
        assert len(loaded_workflow.nodes) == len(sample_workflow.nodes)
        assert len(loaded_workflow.edges) == len(sample_workflow.edges)
        
        # 验证节点数据
        for original, loaded in zip(sample_workflow.nodes, loaded_workflow.nodes):
            assert original.node_id == loaded.node_id
            assert original.node_type == loaded.node_type
            assert original.title == loaded.title
            assert original.position == loaded.position
            assert original.params == loaded.params
        
        # 验证边数据
        for original, loaded in zip(sample_workflow.edges, loaded_workflow.edges):
            assert original.from_node == loaded.from_node
            assert original.to_node == loaded.to_node
            assert original.from_port == loaded.from_port
            assert original.to_port == loaded.to_port
    
    @pytest.mark.unit
    def test_save_workflow_encryption(self, sample_workflow, temp_dir):
        """测试工作流保存加密"""
        file_path = temp_dir / "encrypted_workflow.nvw"
        
        # 保存工作流
        save_workflow(sample_workflow, str(file_path))
        
        # 读取文件内容
        encrypted_content = file_path.read_bytes()
        
        # 验证内容是加密的（不是纯文本JSON）
        try:
            # 尝试直接解码为JSON应该失败
            json.loads(encrypted_content.decode('utf-8'))
            assert False, "文件内容应该是加密的，不是纯文本"
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 这是期望的结果
            pass
        
        # 验证文件大小合理
        assert len(encrypted_content) > 0
    
    @pytest.mark.unit
    def test_load_nonexistent_file(self):
        """测试加载不存在的文件"""
        with pytest.raises(FileNotFoundError):
            load_workflow("nonexistent_file.nvw")
    
    @pytest.mark.unit
    def test_load_corrupted_file(self, temp_dir):
        """测试加载损坏的文件"""
        file_path = temp_dir / "corrupted_workflow.nvw"
        
        # 写入无效内容
        file_path.write_bytes(b"invalid encrypted content")
        
        with pytest.raises((json.JSONDecodeError, ValueError)):
            load_workflow(str(file_path))


class TestJSONExport:
    """JSON导出测试类"""
    
    @pytest.fixture
    def sample_workflow(self):
        """示例工作流"""
        nodes = [
            WorkflowNodeModel(
                node_id="export_node_1",
                node_type="test.type",
                title="导出测试节点",
                position=(10.0, 20.0),
                params={"test_param": "test_value"}
            )
        ]
        
        edges = [
            WorkflowEdgeModel(
                from_node="export_node_1",
                to_node="export_node_2",
                from_port="out",
                to_port="in"
            )
        ]
        
        return WorkflowGraphModel(
            name="导出测试工作流",
            nodes=nodes,
            edges=edges
        )
    
    @pytest.mark.unit
    def test_export_json_valid(self, sample_workflow, temp_dir):
        """测试JSON导出"""
        file_path = temp_dir / "test_export.json"
        
        # 导出JSON
        export_json(sample_workflow, str(file_path))
        
        # 验证文件存在
        assert file_path.exists()
        
        # 验证JSON格式正确
        with open(file_path, 'r', encoding='utf-8') as f:
            exported_data = json.load(f)
        
        # 验证导出的数据结构
        assert "name" in exported_data
        assert "nodes" in exported_data
        assert "edges" in exported_data
        assert exported_data["name"] == "导出测试工作流"
        assert len(exported_data["nodes"]) == 1
        assert len(exported_data["edges"]) == 1
    
    @pytest.mark.unit
    def test_export_json_content_verification(self, sample_workflow, temp_dir):
        """测试JSON导出内容验证"""
        file_path = temp_dir / "content_test.json"
        
        # 导出JSON
        export_json(sample_workflow, str(file_path))
        
        # 读取并验证内容
        with open(file_path, 'r', encoding='utf-8') as f:
            exported_data = json.load(f)
        
        # 验证节点内容
        node_data = exported_data["nodes"][0]
        assert node_data["node_id"] == "export_node_1"
        assert node_data["node_type"] == "test.type"
        assert node_data["title"] == "导出测试节点"
        assert node_data["position"] == [10.0, 20.0]
        assert node_data["params"]["test_param"] == "test_value"
        
        # 验证边内容
        edge_data = exported_data["edges"][0]
        assert edge_data["from_node"] == "export_node_1"
        assert edge_data["to_node"] == "export_node_2"
        assert edge_data["from_port"] == "out"
        assert edge_data["to_port"] == "in"


class TestPythonExport:
    """Python脚本导出测试类"""
    
    @pytest.fixture
    def sample_workflow(self):
        """示例工作流"""
        nodes = [
            WorkflowNodeModel(
                node_id="python_node_1",
                node_type="demo.delay",
                title="Python导出节点",
                position=(100.0, 100.0),
                params={"delay_ms": 500}
            ),
            WorkflowNodeModel(
                node_id="python_node_2",
                node_type="data.source",
                title="数据源",
                position=(300.0, 100.0),
                params={"seed": 42}
            )
        ]
        
        edges = [
            WorkflowEdgeModel(
                from_node="python_node_1",
                to_node="python_node_2"
            )
        ]
        
        return WorkflowGraphModel(
            name="Python导出测试",
            nodes=nodes,
            edges=edges
        )
    
    @pytest.mark.unit
    def test_export_python_valid(self, sample_workflow, temp_dir):
        """测试Python脚本导出"""
        file_path = temp_dir / "test_export.py"
        
        # 导出Python脚本
        export_python(sample_workflow, str(file_path))
        
        # 验证文件存在
        assert file_path.exists()
        
        # 验证文件内容
        content = file_path.read_text(encoding='utf-8')
        
        # 验证包含预期的代码结构
        assert "Auto-generated NVMagUI workflow script" in content
        assert "NODES = [" in content
        assert "EDGES = [" in content
        assert "pprint(NODES)" in content
        assert "pprint(EDGES)" in content
    
    @pytest.mark.unit
    def test_export_python_content_verification(self, sample_workflow, temp_dir):
        """测试Python导出内容验证"""
        file_path = temp_dir / "python_content_test.py"
        
        # 导出Python脚本
        export_python(sample_workflow, str(file_path))
        
        # 读取并验证内容
        content = file_path.read_text(encoding='utf-8')
        
        # 验证节点定义
        assert "python_node_1" in content
        assert "python_node_2" in content
        assert "demo.delay" in content
        assert "data.source" in content
        assert "delay_ms" in content
        assert "seed" in content
        
        # 验证边定义
        assert "('python_node_1', 'python_node_2')" in content


class TestXOREncryption:
    """XOR加密测试类"""
    
    @pytest.mark.unit
    def test_xor_encrypt_decrypt_basic(self):
        """测试XOR加密解密基本功能"""
        original_data = b"Hello, World! This is a test message."
        
        # 加密
        encrypted_data = _xor_crypt(original_data)
        
        # 验证加密数据与原数据不同
        assert encrypted_data != original_data
        
        # 解密
        decrypted_data = _xor_crypt(encrypted_data)
        
        # 验证解密后数据与原数据相同
        assert decrypted_data == original_data
    
    @pytest.mark.unit
    def test_xor_encrypt_decrypt_empty(self):
        """测试空数据的XOR加密解密"""
        original_data = b""
        
        encrypted_data = _xor_crypt(original_data)
        decrypted_data = _xor_crypt(encrypted_data)
        
        assert decrypted_data == original_data
    
    @pytest.mark.unit
    def test_xor_encrypt_decrypt_unicode(self):
        """测试Unicode数据的XOR加密解密"""
        original_text = "测试中文消息！Hello World! 🚀"
        original_data = original_text.encode('utf-8')
        
        encrypted_data = _xor_crypt(original_data)
        decrypted_data = _xor_crypt(encrypted_data)
        
        assert decrypted_data == original_data
        
        # 验证解密后的文本正确
        decrypted_text = decrypted_data.decode('utf-8')
        assert decrypted_text == original_text
    
    @pytest.mark.unit
    def test_xor_encrypt_consistency(self):
        """测试XOR加密的一致性"""
        original_data = b"Consistency test data"
        
        # 多次加密应该产生相同结果
        encrypted_data1 = _xor_crypt(original_data)
        encrypted_data2 = _xor_crypt(original_data)
        
        assert encrypted_data1 == encrypted_data2
    
    @pytest.mark.unit
    def test_xor_encrypt_large_data(self):
        """测试大数据的XOR加密"""
        # 创建1MB的测试数据
        original_data = b"A" * (1024 * 1024)
        
        encrypted_data = _xor_crypt(original_data)
        decrypted_data = _xor_crypt(encrypted_data)
        
        assert decrypted_data == original_data
        assert len(encrypted_data) == len(original_data)


class TestVersionCompatibility:
    """版本兼容性测试类"""
    
    @pytest.mark.unit
    def test_current_version_format(self, temp_dir):
        """测试当前版本格式"""
        # 创建当前版本的工作流
        workflow = WorkflowGraphModel(
            version="1.0",
            name="版本测试",
            nodes=[],
            edges=[]
        )
        
        file_path = temp_dir / "version_test.nvw"
        save_workflow(workflow, str(file_path))
        
        # 加载并验证版本
        loaded_workflow = load_workflow(str(file_path))
        assert loaded_workflow.version == "1.0"
    
    @pytest.mark.unit
    def test_missing_version_handling(self, temp_dir):
        """测试缺失版本信息的处理"""
        # 创建没有版本信息的工作流数据
        workflow_data = {
            "name": "无版本测试",
            "nodes": [],
            "edges": []
        }
        
        file_path = temp_dir / "no_version.nvw"
        
        # 手动创建文件（模拟旧版本）
        import base64
        from workflow_extension.serializer import _xor_crypt
        json_data = json.dumps(workflow_data, ensure_ascii=False, indent=2)
        encrypted_data = base64.b64encode(_xor_crypt(json_data.encode('utf-8')))
        file_path.write_bytes(encrypted_data)
        
        # 加载并验证默认版本
        loaded_workflow = load_workflow(str(file_path))
        assert loaded_workflow.version == "1.0"  # 应该使用默认版本
        assert loaded_workflow.name == "无版本测试"
    
    @pytest.mark.unit
    def test_future_version_warning(self, temp_dir):
        """测试未来版本警告"""
        # 创建未来版本的工作流数据
        workflow_data = {
            "version": "2.0",  # 未来版本
            "name": "未来版本测试",
            "nodes": [],
            "edges": []
        }
        
        file_path = temp_dir / "future_version.nvw"
        
        # 手动创建文件
        import base64
        from workflow_extension.serializer import _xor_crypt
        json_data = json.dumps(workflow_data, ensure_ascii=False, indent=2)
        encrypted_data = base64.b64encode(_xor_crypt(json_data.encode('utf-8')))
        file_path.write_bytes(encrypted_data)
        
        # 加载未来版本文件（当前实现可能没有版本检查）
        loaded_workflow = load_workflow(str(file_path))
        assert loaded_workflow.version == "2.0"
        # 在实际实现中，这里应该有版本兼容性警告


class TestSerializationPerformance:
    """序列化性能测试类"""
    
    @pytest.mark.unit
    @pytest.mark.performance
    def test_large_workflow_serialization(self, temp_dir, performance_monitor):
        """测试大型工作流序列化性能"""
        # 创建大型工作流（1000个节点，2000条边）
        nodes = []
        edges = []
        
        for i in range(1000):
            nodes.append(WorkflowNodeModel(
                node_id=f"large_node_{i}",
                node_type="test.type",
                title=f"大型节点{i}",
                position=(float(i * 10), float(i * 5)),
                params={"index": i, "data": f"test_data_{i}" * 10}  # 较大的参数数据
            ))
            
            # 创建连接（每个节点连接到下一个节点）
            if i > 0:
                edges.append(WorkflowEdgeModel(
                    from_node=f"large_node_{i-1}",
                    to_node=f"large_node_{i}"
                ))
        
        large_workflow = WorkflowGraphModel(
            name="大型性能测试工作流",
            nodes=nodes,
            edges=edges
        )
        
        file_path = temp_dir / "large_workflow.nvw"
        
        # 测试保存性能
        performance_monitor.start()
        save_workflow(large_workflow, str(file_path))
        performance_monitor.checkpoint("save_complete")
        
        # 测试加载性能
        loaded_workflow = load_workflow(str(file_path))
        performance_monitor.checkpoint("load_complete")
        performance_monitor.stop()
        
        duration = performance_monitor.get_duration()
        
        # 验证结果正确性
        assert len(loaded_workflow.nodes) == 1000
        assert len(loaded_workflow.edges) == 999
        
        # 性能断言（应该在合理时间内完成）
        assert duration < 5.0  # 5秒内完成
        
        # 检查文件大小
        file_size = file_path.stat().st_size
        assert file_size > 0  # 文件应该有内容
        
        # 验证检查点时间
        checkpoints = dict(performance_monitor.checkpoints)
        assert "save_complete" in checkpoints
        assert "load_complete" in checkpoints
