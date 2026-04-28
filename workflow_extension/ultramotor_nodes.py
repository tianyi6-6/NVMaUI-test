"""
超声电机状态专用节点

本模块提供了超声电机状态相关的专用节点，包括：
- 超声电机状态节点：读取和控制超声电机状态
"""

# encoding=utf-8
import logging
from workflow_extension.node_registry import NodeSpec, NodePortSpec, NodeParamSpec


def _exec_ultramotor_status(context, node, inputs):
    try:
        app = context.get("app")
        if app is None:
            raise ValueError("未找到应用上下文 app，无法执行超声电机状态读取")
        if not hasattr(app, "ultramotor"):
            raise ValueError("应用上下文缺少 ultramotor 接口，无法执行超声电机状态读取")

        motor_speed = int(node.params.get("motor_speed", 1000))
        target_angle = float(node.params.get("target_angle", 0.0))
        motor_direction = str(node.params.get("motor_direction", "正转"))

        if motor_speed < 0 or motor_speed > 10000:
            raise ValueError("超声电机转速必须在0-10000范围内")
        if target_angle < 0.0 or target_angle > 360.0:
            raise ValueError("超声电机角度必须在0-360度范围内")

        # 获取当前超声电机状态
        current_angle = app.ultramotor.get_angle()

        # 根据转动方向设置电机旋转
        direction_flag = True  # 默认正转
        if motor_direction == "反转":
            direction_flag = False
        elif motor_direction == "自动":
            # 自动判断转动方向
            current_angle = app.ultramotor.get_angle()
            forward_angle = (current_angle - target_angle) % 360
            direction_flag = forward_angle > 180

        # 旋转电机到目标角度
        app.ultramotor.rotate_motor(motor_speed, target_angle, direction=direction_flag)

        # 等待电机停止
        while app.ultramotor.is_run():
            import time
            time.sleep(0.01)

        # 获取最终角度和运行状态
        final_angle = app.ultramotor.get_angle()
        is_running = app.ultramotor.is_run()

        # 更新状态
        app.ultramotor.update_status()

        logging.info(
            f"超声电机状态: 转速={motor_speed}rpm, 目标角度={target_angle}°, 转动方向={motor_direction}, "
            f"当前角度={final_angle}°, 运行状态={'运行中' if is_running else '停止'}"
        )

        return {
            "motor_speed": motor_speed,
            "target_angle": target_angle,
            "motor_direction": motor_direction,
            "current_angle": final_angle,
            "is_running": is_running,
        }
    except Exception as e:
        logging.error(f"超声电机状态读取失败: {e}")
        return {"error": str(e)}


def register_ultramotor_nodes(registry):
    """注册超声电机状态相关节点"""
    registry.register(
        NodeSpec(
            node_type="ultramotor.status",
            title="超声电机状态",
            category="设备",
            default_params={
                "motor_speed": 1000,
                "target_angle": 0.0,
                "motor_direction": "正转"
            },
            input_ports=[NodePortSpec("device_in", "device"), NodePortSpec("trigger", "trigger")],
            output_ports=[
                NodePortSpec("current_angle", "float"),
                NodePortSpec("is_running", "bool"),
                NodePortSpec("motor_speed", "int"),
                NodePortSpec("motor_direction", "str")
            ],
            param_specs=[
                NodeParamSpec("motor_speed", "超声电机转速(rpm)", editor="int", minimum=0, maximum=10000, step=100),
                NodeParamSpec("target_angle", "设置超声电机角度(°)", editor="float", minimum=0.0, maximum=360.0, step=0.1),
                NodeParamSpec("motor_direction", "转动方向", editor="select", options=["正转", "反转", "自动"]),
            ],
            executor=_exec_ultramotor_status,
        )
    )
