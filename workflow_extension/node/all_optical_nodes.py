"""
全光谱数据采集专用节点

本模块提供了全光谱数据采集的专用节点，包括：
- 全光谱采集节点：执行全角度扫描和数据采集
"""

# encoding=utf-8
import time
import numpy as np
from workflow_extension.node_registry import NodeSpec, NodePortSpec, NodeParamSpec
from workflow_extension.logger import get_logger

_log = get_logger("AllOptical")


def _exec_all_optical_acquire(context, node, inputs):
    try:
        app = context.get("app")
        if app is None:
            raise ValueError("未找到应用上下文 app，无法执行全光谱真实采集")
        if not hasattr(app, "dev") or not hasattr(app, "ultramotor"):
            raise ValueError("应用上下文缺少 dev 或 ultramotor 接口，无法执行全光谱真实采集")

        start_motor_angle = float(node.params.get("start_motor_angle", 0.1))
        stop_motor_angle = float(node.params.get("stop_motor_angle", 359.9))
        step_motor_angle = float(node.params.get("step_motor_angle", 2.0))

        if step_motor_angle <= 0:
            raise ValueError("步进角度必须大于0")
        if stop_motor_angle < start_motor_angle:
            raise ValueError("结束角度必须大于等于起始角度")

        motor_angle_list = []
        fluo_dc_list = []
        laser_dc_list = []
        callback = context.get("plot_callback")
        workflow_tab = context.get("workflow_tab")

        speed = 100
        current_motor_angle = start_motor_angle

        while current_motor_angle <= stop_motor_angle:
            current_angle = app.ultramotor.get_angle()
            forward_angle = (current_angle - current_motor_angle) % 360
            _log.debug("当前角度：%s, 目标角度：%s, 判断正转所需：%s", current_angle, current_motor_angle, forward_angle)

            motor_direction_flag = forward_angle > 180
            app.ultramotor.rotate_motor(speed, current_motor_angle, direction=motor_direction_flag)

            while app.ultramotor.is_run():
                time.sleep(0.01)

            real_motor_angle = app.ultramotor.get_angle()
            motor_angle_list.append(real_motor_angle)

            auxdaq_data = app.dev.auxDAQ_play(data_num=50)
            fluo_dc = float(np.mean(auxdaq_data[0]))
            laser_dc = float(np.mean(auxdaq_data[1]))
            fluo_dc_list.append(fluo_dc)
            laser_dc_list.append(laser_dc)

            _log.debug("设置角度：%s° 测量角度：%s°", current_motor_angle, real_motor_angle)

            if callback:
                callback({"x": real_motor_angle, "y": fluo_dc, "y2": laser_dc})

            # 实时更新工作流双图显示
            if workflow_tab and hasattr(workflow_tab, 'plot_curve_top_main'):
                workflow_tab._plot_x = np.array([real_motor_angle])
                workflow_tab._plot_y = np.array([fluo_dc])
                workflow_tab._plot_lower_main = np.array([laser_dc])
                workflow_tab._plot_upper_aux = np.array([])
                workflow_tab._plot_lower_aux = np.array([])
                workflow_tab.plot_curve_top_main.setData(workflow_tab._plot_x, workflow_tab._plot_y)
                workflow_tab.plot_curve_bottom_main.setData(workflow_tab._plot_x, workflow_tab._plot_lower_main)
                # 处理UI事件，保持界面响应
                from PySide6.QtCore import QCoreApplication
                QCoreApplication.processEvents()

            current_motor_angle += step_motor_angle

        _log.info(
            "全光谱采集完成: 起始角度=%s°, 结束角度=%s°, "
            "步进角度=%s°, 点数=%s",
            start_motor_angle, stop_motor_angle,
            step_motor_angle, len(motor_angle_list)
        )

        return {
            "data_type": "all_optical",
            "motor_angle": motor_angle_list,
            "fluo_dc": fluo_dc_list,
            "laser_dc": laser_dc_list,
            "point_count": len(motor_angle_list),
        }
    except Exception as e:
        _log.error("全光谱采集失败: %s", e)
        return {"error": str(e)}


def register_all_optical_nodes(registry):
    """注册全光谱数据采集相关节点"""
    registry.register(
        NodeSpec(
            node_type="all_optical.acquire",
            title="全光谱采集",
            category="全光谱数据采集",
            default_params={
                "start_motor_angle": "0.1",
                "stop_motor_angle": "359.9",
                "step_motor_angle": "2.0"
            },
            input_ports=[NodePortSpec("device_in", "device")],
            output_ports=[
                NodePortSpec("data", "dict")
            ],
            param_specs=[
                NodeParamSpec("start_motor_angle", "起始角度(°)", editor="float", minimum=0.0, maximum=360.0, step=0.1),
                NodeParamSpec("stop_motor_angle", "结束角度(°)", editor="float", minimum=0.0, maximum=360.0, step=0.1),
                NodeParamSpec("step_motor_angle", "步进角度(°)", editor="float", minimum=0.01, maximum=360.0, step=0.1),
            ],
            executor=_exec_all_optical_acquire,
        )
    )
