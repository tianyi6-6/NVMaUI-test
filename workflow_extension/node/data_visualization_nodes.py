"""
数据可视化节点

本模块提供了数据可视化相关的节点，包括：
- 数据显示节点：将采集数据显示在工作流双图显示面板上
"""

# encoding=utf-8
import logging
import numpy as np
from workflow_extension.node_registry import NodeSpec, NodePortSpec, NodeParamSpec


def _exec_data_display(context, node, inputs):
    try:
        workflow_tab = context.get("workflow_tab")
        if workflow_tab is None:
            raise ValueError("未找到工作流标签页上下文，无法执行数据显示")

        # 获取输入数据（引擎传入的是端口名到数据的映射字典）
        data = inputs.get("data_in", {})
        if not data or isinstance(data, dict) and "error" in data:
            logging.warning(f"数据显示节点未收到有效数据: {data.get('error', '无数据') if isinstance(data, dict) else '无数据'}")
            return {"error": f"上游数据无效: {data.get('error', '无数据') if isinstance(data, dict) else '无数据'}"}

        # 判断数据类型并选择显示模式
        data_type = data.get("data_type", "unknown")

        if data_type == "cw":
            # CW谱数据
            mw_freq = data.get("mw_freq", [])
            ch1_x = data.get("ch1_x", [])
            ch1_y = data.get("ch1_y", [])
            ch2_x = data.get("ch2_x", [])
            ch2_y = data.get("ch2_y", [])

            workflow_tab._plot_x = np.array(mw_freq)
            workflow_tab._plot_y = np.array(ch1_x)
            workflow_tab._plot_upper_aux = np.array(ch1_y)
            workflow_tab._plot_lower_main = np.array(ch2_x)
            workflow_tab._plot_lower_aux = np.array(ch2_y)

            workflow_tab._apply_plot_mode("cw")
            workflow_tab.tab_widget.setCurrentIndex(1)  # 切换到CW谱标签页

            logging.info(f"CW谱数据显示: 频率点数={len(mw_freq)}")

        elif data_type == "all_optical":
            # 全光谱数据
            motor_angle = data.get("motor_angle", [])
            fluo_dc = data.get("fluo_dc", [])
            laser_dc = data.get("laser_dc", [])

            workflow_tab._plot_x = np.array(motor_angle)
            workflow_tab._plot_y = np.array(fluo_dc)
            workflow_tab._plot_lower_main = np.array(laser_dc)
            workflow_tab._plot_upper_aux = np.array([])  # 全光谱只有两个通道
            workflow_tab._plot_lower_aux = np.array([])

            workflow_tab._apply_plot_mode("all_optical")
            workflow_tab.tab_widget.setCurrentIndex(0)  # 切换到全关谱标签页

            logging.info(f"全光谱数据显示: 角度点数={len(motor_angle)}")

        elif data_type == "iir":
            # IIR谱数据
            time_data = data.get("time", [])
            ch1 = data.get("ch1", [])
            ch2 = data.get("ch2", [])

            workflow_tab._plot_x = np.array(time_data)
            workflow_tab._plot_y = np.array(ch1)
            workflow_tab._plot_lower_main = np.array(ch2)
            workflow_tab._plot_upper_aux = np.array([])  # IIR谱只有两个通道
            workflow_tab._plot_lower_aux = np.array([])

            workflow_tab._apply_plot_mode("iir")
            workflow_tab.tab_widget.setCurrentIndex(2)  # 切换到IIR谱标签页

            logging.info(f"IIR谱数据显示: 时间点数={len(time_data)}")

        else:
            logging.warning(f"未知数据类型: {data_type}")
            return {"error": f"未知数据类型: {data_type}"}

        # 更新图表
        if hasattr(workflow_tab, 'plot_curve_top_main'):
            workflow_tab.plot_curve_top_main.setData(workflow_tab._plot_x, workflow_tab._plot_y)

        if hasattr(workflow_tab, 'plot_curve_top_aux') and len(workflow_tab._plot_upper_aux) > 0:
            workflow_tab.plot_curve_top_aux.setData(workflow_tab._plot_x, workflow_tab._plot_upper_aux)

        if hasattr(workflow_tab, 'plot_curve_bottom_main'):
            workflow_tab.plot_curve_bottom_main.setData(workflow_tab._plot_x, workflow_tab._plot_lower_main)

        if hasattr(workflow_tab, 'plot_curve_bottom_aux') and len(workflow_tab._plot_lower_aux) > 0:
            workflow_tab.plot_curve_bottom_aux.setData(workflow_tab._plot_x, workflow_tab._plot_lower_aux)

        return {"status": "success", "data_type": data_type}

    except Exception as e:
        logging.error(f"数据显示失败: {e}")
        return {"error": str(e)}


def register_data_visualization_nodes(registry):
    """注册数据可视化相关节点"""
    registry.register(
        NodeSpec(
            node_type="data.display",
            title="数据显示",
            category="数据可视化",
            default_params={},
            input_ports=[
                NodePortSpec("data_in", "dict")
            ],
            output_ports=[
                NodePortSpec("status", "dict")
            ],
            param_specs=[],
            executor=_exec_data_display,
        )
    )
