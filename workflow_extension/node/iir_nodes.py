"""
IIR谱数据采集专用节点

本模块提供了IIR谱数据采集的专用节点，包括：
- IIR谱采集节点：执行IIR模式数据采集
"""

# encoding=utf-8
import time
import numpy as np
import logging
from workflow_extension.node_registry import NodeSpec, NodePortSpec, NodeParamSpec


def _exec_iir_acquire(context, node, inputs):
    try:
        app = context.get("app")
        if app is None:
            raise ValueError("未找到应用上下文 app，无法执行IIR谱真实采集")
        if not hasattr(app, "dev"):
            raise ValueError("应用上下文缺少 dev 接口，无法执行IIR谱真实采集")

        acq_time = float(node.params.get("acq_time", 0.5))
        acq_mode = str(node.params.get("acq_mode", "定时长采集"))

        if acq_time <= 0:
            raise ValueError("采集时长必须大于0")

        param_config = getattr(app, "param_config", {})
        sample_rate = param_config.get("lockin_sample_rate", {}).get("value", 1000.0)
        if sample_rate <= 0:
            sample_rate = 1000.0

        sample_interval = 1.0 / sample_rate
        time_data = []
        ch1_data = []
        ch2_data = []
        callback = context.get("plot_callback")
        workflow_tab = context.get("workflow_tab")

        init_start_time = time.time()
        N = 0

        app.dev.start_infinite_iir_acq()

        try:
            if acq_mode == "定时长采集":
                total_samples = int(sample_rate * acq_time)
                collected_samples = 0

                while collected_samples < total_samples:
                    try:
                        iir_data = app.dev.get_infinite_iir_points(data_num=min(int(sample_rate * acq_time), total_samples - collected_samples))
                    except:
                        break

                    data1 = iir_data[1]
                    data2 = iir_data[7]
                    N_new = len(data1)

                    new_time_data = np.linspace(
                        init_start_time + N * sample_interval,
                        init_start_time + (N + N_new) * sample_interval,
                        len(data1),
                        endpoint=False
                    )

                    N += N_new
                    collected_samples += N_new

                    time_data.extend(new_time_data.tolist())
                    ch1_data.extend(data1.tolist())
                    ch2_data.extend(data2.tolist())

                    if callback and len(time_data) > 0:
                        callback({"x": time_data[-1], "y": ch1_data[-1], "y2": ch2_data[-1]})

                    # 实时更新工作流双图显示
                    if workflow_tab and hasattr(workflow_tab, 'plot_curve_top_main'):
                        workflow_tab._plot_x = np.array(time_data[-100:])  # 显示最近100个点
                        workflow_tab._plot_y = np.array(ch1_data[-100:])
                        workflow_tab._plot_lower_main = np.array(ch2_data[-100:])
                        workflow_tab._plot_upper_aux = np.array([])
                        workflow_tab._plot_lower_aux = np.array([])
                        workflow_tab.plot_curve_top_main.setData(workflow_tab._plot_x, workflow_tab._plot_y)
                        workflow_tab.plot_curve_bottom_main.setData(workflow_tab._plot_x, workflow_tab._plot_lower_main)
                        # 处理UI事件，保持界面响应
                        from PySide6.QtCore import QCoreApplication
                        QCoreApplication.processEvents()

            else:
                while True:
                    try:
                        iir_data = app.dev.get_infinite_iir_points(data_num=int(sample_rate * acq_time))
                    except:
                        break

                    data1 = iir_data[1]
                    data2 = iir_data[7]
                    N_new = len(data1)

                    new_time_data = np.linspace(
                        init_start_time + N * sample_interval,
                        init_start_time + (N + N_new) * sample_interval,
                        len(data1),
                        endpoint=False
                    )

                    N += N_new

                    time_data.extend(new_time_data.tolist())
                    ch1_data.extend(data1.tolist())
                    ch2_data.extend(data2.tolist())

                    if callback and len(time_data) > 0:
                        callback({"x": time_data[-1], "y": ch1_data[-1], "y2": ch2_data[-1]})

                    # 实时更新工作流双图显示
                    if workflow_tab and hasattr(workflow_tab, 'plot_curve_top_main'):
                        workflow_tab._plot_x = np.array(time_data[-100:])  # 显示最近100个点
                        workflow_tab._plot_y = np.array(ch1_data[-100:])
                        workflow_tab._plot_lower_main = np.array(ch2_data[-100:])
                        workflow_tab._plot_upper_aux = np.array([])
                        workflow_tab._plot_lower_aux = np.array([])
                        workflow_tab.plot_curve_top_main.setData(workflow_tab._plot_x, workflow_tab._plot_y)
                        workflow_tab.plot_curve_bottom_main.setData(workflow_tab._plot_x, workflow_tab._plot_lower_main)
                        # 处理UI事件，保持界面响应
                        from PySide6.QtCore import QCoreApplication
                        QCoreApplication.processEvents()

                    if not context.get("running", True):
                        break
        finally:
            app.dev.stop_infinite_iir_acq()

        logging.info(
            f"IIR谱采集: 采集时长={acq_time}s, 采样率={sample_rate}Hz, 点数={len(time_data)}"
        )

        return {
            "data_type": "iir",
            "time": time_data,
            "ch1": ch1_data,
            "ch2": ch2_data,
            "sample_rate": sample_rate,
            "point_count": len(time_data),
        }
    except Exception as e:
        logging.error(f"IIR谱采集失败: {e}")
        return {"error": str(e)}


def register_iir_nodes(registry):
    """注册IIR谱数据采集相关节点"""
    registry.register(
        NodeSpec(
            node_type="iir.acquire",
            title="IIR谱采集",
            category="IIR谱数据采集",
            default_params={
                "acq_time": 0.5,
                "display_length": 1000,
                "mw_mode": "不操作微波",
                "trend_remove_mode": "关闭",
                "realtime_filter_enabled": False
            },
            input_ports=[NodePortSpec("device_in", "device")],
            output_ports=[
                NodePortSpec("data", "dict")
            ],
            param_specs=[
                NodeParamSpec("acq_time", "采集时长(秒)", editor="float", minimum=0.1, maximum=10000.0, step=0.1),
                NodeParamSpec("display_length", "屏幕显示时长(s)", editor="int", minimum=1, maximum=1000000, step=1),
                NodeParamSpec("mw_mode", "微波模式", editor="select", options=["不操作微波", "CH1单路微波", "CH2单路微波", "双路微波", "非共振状态"]),
                NodeParamSpec("trend_remove_mode", "去趋势模式", editor="select", options=["关闭", "线性去基线", "直流去基线", "二次函数去基线"]),
                NodeParamSpec("realtime_filter_enabled", "开启实时滤波", editor="bool"),
            ],
            executor=_exec_iir_acquire,
        )
    )
