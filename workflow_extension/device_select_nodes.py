"""
设备选择专用节点

本模块提供了设备选择相关的专用节点，包括：
- 选择设备节点：选择并配置实验设备
"""

# encoding=utf-8
import logging
from workflow_extension.node_registry import NodeSpec, NodePortSpec, NodeParamSpec


def _exec_device_select(context, node, inputs):
    try:
        app = context.get("app")
        if app is None:
            raise ValueError("未找到应用上下文 app，无法执行设备选择")

        device_name = str(node.params.get("device_name", "样机1 (WR04-02)"))
        exp_config_path = str(node.params.get("exp_config_path", "config/exp_config_dev1.ini"))
        sys_config_path = str(node.params.get("sys_config_path", "config/system_config_dev1.ini"))
        lockin_port = str(node.params.get("lockin_port", "interface/Lockin/usblib/module_64/libusb-1.0.dll"))
        ultramotor_port = str(node.params.get("ultramotor_port", "COM12"))
        log_path = str(node.params.get("log_path", "log/experiment_log_dev1.txt"))

        logging.info(
            f"设备选择: 设备名称={device_name}, 实验配置={exp_config_path}, "
            f"系统配置={sys_config_path}, 锁相端口={lockin_port}, "
            f"超声电机端口={ultramotor_port}, 日志路径={log_path}"
        )

        # 返回设备配置信息
        return {
            "device_name": device_name,
            "exp_config_path": exp_config_path,
            "sys_config_path": sys_config_path,
            "lockin_port": lockin_port,
            "ultramotor_port": ultramotor_port,
            "log_path": log_path,
        }
    except Exception as e:
        logging.error(f"设备选择失败: {e}")
        return {"error": str(e)}


def register_device_select_nodes(registry):
    """注册设备选择相关节点"""
    registry.register(
        NodeSpec(
            node_type="device.select",
            title="选择设备",
            category="设备",
            default_params={
                "device_name": "样机1 (WR04-02)",
                "exp_config_path": "config/exp_config_dev1.ini",
                "sys_config_path": "config/system_config_dev1.ini",
                "lockin_port": "interface/Lockin/usblib/module_64/libusb-1.0.dll",
                "ultramotor_port": "COM12",
                "log_path": "log/experiment_log_dev1.txt"
            },
            input_ports=[],
            output_ports=[
                NodePortSpec("device_config", "dict"),
                NodePortSpec("device_name", "str"),
                NodePortSpec("exp_config_path", "str"),
                NodePortSpec("sys_config_path", "str"),
                NodePortSpec("lockin_port", "str"),
                NodePortSpec("ultramotor_port", "str"),
                NodePortSpec("log_path", "str")
            ],
            param_specs=[
                NodeParamSpec("device_name", "设备名称", editor="select", options=["样机1 (WR04-02)", "样机2 (WR04-04)", "样机3 (WR05-03)", "样机4 (WR05-01)", "样机4 (WR06-02)"]),
                NodeParamSpec("exp_config_path", "实验配置文件路径", editor="text"),
                NodeParamSpec("sys_config_path", "系统配置文件路径", editor="text"),
                NodeParamSpec("lockin_port", "锁相端口", editor="text"),
                NodeParamSpec("ultramotor_port", "超声电机端口", editor="text"),
                NodeParamSpec("log_path", "日志文件路径", editor="text"),
            ],
            executor=_exec_device_select,
        )
    )
