import math
import random
import time
from typing import Dict

from PySide6.QtCore import QCoreApplication

from workflow_extension.node_registry import NodeParamSpec, NodePortSpec, NodeRegistry, NodeSpec


def _exec_device_connect(context, node, inputs):
    app = context.get("app")
    connected = False
    message = "未连接"
    if app and getattr(app, "dev", None) is not None:
        connected = True
        message = "设备已存在连接实例"
    return {"connected": connected, "message": message}


def _exec_parameter_config(context, node, inputs):
    return {"configured": True, "params": dict(node.params)}


def _exec_delay(context, node, inputs):
    delay_ms = int(float(node.params.get("delay_ms", 500)))
    time.sleep(max(delay_ms, 0) / 1000.0)
    return {"delay_ms": delay_ms}


def _exec_data_source(context, node, inputs):
    value = random.uniform(0, 1)
    ts = time.time()
    return {"x": ts, "y": value}


def _exec_plot_stream(context, node, inputs):
    payload = inputs[-1] if inputs else {}
    callback = context.get("plot_callback")
    if callback:
        callback(payload)
    return payload


def _exec_logic_condition(context, node, inputs):
    threshold = float(node.params.get("threshold", 0.5))
    payload = inputs[-1] if inputs else {}
    val = float(payload.get("y", 0.0))
    return {"passed": val >= threshold, "value": val, "threshold": threshold}


def _exec_demo_start(context, node, inputs):
    seed = int(node.params.get("seed", 42))
    random.seed(seed)
    context["demo_state"] = {
        "left_peak": random.uniform(0.26, 0.34),
        "right_peak": random.uniform(0.66, 0.74),
        "expected_cw": random.uniform(0.44, 0.56),
    }
    return {"seed": seed, "status": "ready"}


def _exec_demo_init_device(context, node, inputs):
    state = context.setdefault("demo_state", {})
    state["device_ready"] = True
    return {
        "lockins": int(node.params.get("lockins", 2)),
        "motors": int(node.params.get("motors", 2)),
        "resonator": str(node.params.get("resonator", "yig")),
    }


def _exec_demo_coarse_scan(context, node, inputs):
    state = context.setdefault("demo_state", {})
    left_peak = state.get("left_peak", 0.3)
    right_peak = state.get("right_peak", 0.7)
    start = float(node.params.get("scan_start", 0.0))
    end = float(node.params.get("scan_end", 1.0))
    points = int(node.params.get("points", 121))
    noise = float(node.params.get("noise", 0.01))
    xs = [start + (end - start) * i / max(points - 1, 1) for i in range(points)]
    ys = []
    callback = context.get("plot_callback")
    for idx, x in enumerate(xs):
        y = (
            0.9 * math.exp(-((x - left_peak) ** 2) / 0.0022)
            + 0.85 * math.exp(-((x - right_peak) ** 2) / 0.0028)
            + random.uniform(-noise, noise)
        )
        ys.append(y)
        if callback and idx % 3 == 0:
            callback({"x": x, "y": y, "series": "coarse"})
            QCoreApplication.processEvents()
    return {"curve_x": xs, "curve_y": ys, "left_peak": left_peak, "right_peak": right_peak}


def _exec_demo_define_left(context, node, inputs):
    coarse = inputs[-1] if inputs else {}
    left_peak = float(coarse.get("left_peak", 0.3))
    width = float(node.params.get("width", 0.08))
    return {"left_range": (max(0.0, left_peak - width), min(1.0, left_peak + width))}


def _exec_demo_define_right(context, node, inputs):
    source = inputs[-1] if inputs else {}
    right_peak = float(source.get("right_peak", context.get("demo_state", {}).get("right_peak", 0.7)))
    width = float(node.params.get("width", 0.08))
    return {"right_range": (max(0.0, right_peak - width), min(1.0, right_peak + width))}


def _exec_demo_fine_scan(context, node, inputs):
    source = inputs[-1] if inputs else {}
    range_key = "left_range" if "left_range" in source else "right_range"
    scan_range = source.get(range_key, (0.45, 0.55))
    peak = context.get("demo_state", {}).get("expected_cw", 0.5)
    steps = int(node.params.get("steps", 45))
    xs = [scan_range[0] + (scan_range[1] - scan_range[0]) * i / max(steps - 1, 1) for i in range(steps)]
    ys = []
    callback = context.get("plot_callback")
    for x in xs:
        y = math.exp(-((x - peak) ** 2) / 0.00025) + random.uniform(-0.012, 0.012)
        ys.append(y)
        if callback:
            callback({"x": x, "y": y, "series": str(node.params.get("series", "fine"))})
            QCoreApplication.processEvents()
    best_idx = max(range(len(ys)), key=lambda i: ys[i]) if ys else 0
    return {"candidate_cw": xs[best_idx], "score": ys[best_idx], "range_key": range_key}


def _exec_demo_select_region(context, node, inputs):
    left = inputs[0] if len(inputs) > 0 else {}
    right = inputs[1] if len(inputs) > 1 else {}
    left_score = float(left.get("score", -1))
    right_score = float(right.get("score", -1))
    chosen = left if left_score >= right_score else right
    region = "left" if chosen is left else "right"
    return {"chosen_region": region, "candidate_cw": chosen.get("candidate_cw"), "score": chosen.get("score")}


def _exec_demo_compute_work_freq(context, node, inputs):
    chosen = inputs[-1] if inputs else {}
    base = float(chosen.get("candidate_cw", 0.5))
    work_freq_hz = float(node.params.get("base_freq_hz", 5.1e9)) + (base - 0.5) * 1.2e8
    return {"work_freq_hz": work_freq_hz, "cw_angle": base}


def _exec_demo_apply_freq(context, node, inputs):
    target = inputs[-1] if inputs else {}
    return {"applied": True, "work_freq_hz": target.get("work_freq_hz"), "sampling_started": True}


def _exec_demo_monitor_drift(context, node, inputs):
    sample_count = int(node.params.get("sample_count", 180))
    expected = context.get("demo_state", {}).get("expected_cw", 0.5)
    callback = context.get("plot_callback")
    drift_values = []
    start = time.time()
    for i in range(sample_count):
        t = i * 0.4
        drift = expected + 0.02 * math.sin(i / 9.0) + random.uniform(-0.003, 0.003)
        drift_values.append(drift)
        if callback:
            callback({"x": t, "y": drift, "series": "drift"})
            callback({"x": t, "y2": expected, "series2": "target"})
            QCoreApplication.processEvents()
        time.sleep(0.01)
    variance = sum((v - expected) ** 2 for v in drift_values) / max(len(drift_values), 1)
    return {"drift_variance": variance, "duration_s": round(time.time() - start, 2)}


def register_builtin_nodes(registry: NodeRegistry):
    registry.register(
        NodeSpec(
            node_type="device.connect",
            title="设备连接",
            category="设备",
            default_params={},
            input_ports=[],
            output_ports=[NodePortSpec("device_out", "device")],
            executor=_exec_device_connect,
        )
    )
    registry.register(
        NodeSpec(
            node_type="device.parameter",
            title="参数配置",
            category="设备",
            default_params={"target": "lockin", "value": "default"},
            input_ports=[NodePortSpec("device_in", "device")],
            output_ports=[NodePortSpec("device_out", "device")],
            param_specs=[
                NodeParamSpec("target", "目标", editor="select", options=["lockin", "microwave", "motor"]),
                NodeParamSpec("value", "值", editor="text"),
            ],
            executor=_exec_parameter_config,
        )
    )
    registry.register(
        NodeSpec(
            node_type="logic.delay",
            title="延时等待",
            category="逻辑",
            default_params={"delay_ms": 500},
            input_ports=[NodePortSpec("in", "any")],
            output_ports=[NodePortSpec("out", "any")],
            param_specs=[NodeParamSpec("delay_ms", "延时(ms)", editor="int", minimum=0, maximum=600000, step=50)],
            executor=_exec_delay,
        )
    )
    registry.register(
        NodeSpec(
            node_type="data.source",
            title="示例数据源",
            category="数据",
            default_params={},
            input_ports=[],
            output_ports=[NodePortSpec("data_out", "signal")],
            executor=_exec_data_source,
        )
    )
    registry.register(
        NodeSpec(
            node_type="plot.stream",
            title="流式绘图",
            category="绘图",
            default_params={"channel": "CH1"},
            input_ports=[NodePortSpec("data_in", "signal")],
            output_ports=[NodePortSpec("data_out", "signal")],
            param_specs=[NodeParamSpec("channel", "通道", editor="select", options=["CH1", "CH2", "CH3"])],
            executor=_exec_plot_stream,
        )
    )
    registry.register(
        NodeSpec(
            node_type="logic.condition",
            title="逻辑判断",
            category="逻辑",
            default_params={"threshold": 0.5},
            input_ports=[NodePortSpec("in", "signal")],
            output_ports=[NodePortSpec("out", "bool")],
            param_specs=[NodeParamSpec("threshold", "阈值", editor="float", minimum=0.0, maximum=10.0, step=0.05)],
            executor=_exec_logic_condition,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.start",
            title="开始",
            category="流程Demo",
            default_params={"seed": 42},
            input_ports=[],
            output_ports=[NodePortSpec("ctx_out", "context")],
            param_specs=[NodeParamSpec("seed", "随机种子", editor="int", minimum=0, maximum=100000, step=1)],
            executor=_exec_demo_start,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.init_device",
            title="初始化设备",
            category="流程Demo",
            default_params={"lockins": 2, "motors": 2, "resonator": "yig"},
            input_ports=[NodePortSpec("ctx_in", "context")],
            output_ports=[NodePortSpec("ctx_out", "context")],
            param_specs=[
                NodeParamSpec("lockins", "锁相数量", editor="int", minimum=1, maximum=8, step=1),
                NodeParamSpec("motors", "电机数量", editor="int", minimum=1, maximum=8, step=1),
                NodeParamSpec("resonator", "谐振器", editor="select", options=["yig", "cavity"]),
            ],
            executor=_exec_demo_init_device,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.coarse_scan",
            title="全光谱扫描",
            category="流程Demo",
            default_params={"scan_start": 0.0, "scan_end": 1.0, "points": 121, "noise": 0.01},
            input_ports=[NodePortSpec("ctx_in", "context")],
            output_ports=[NodePortSpec("scan_out", "scan_curve")],
            param_specs=[
                NodeParamSpec("scan_start", "扫描起点", editor="float", minimum=0.0, maximum=1.0, step=0.01),
                NodeParamSpec("scan_end", "扫描终点", editor="float", minimum=0.0, maximum=1.0, step=0.01),
                NodeParamSpec("points", "采样点", editor="int", minimum=21, maximum=2000, step=10),
                NodeParamSpec("noise", "噪声", editor="float", minimum=0.0, maximum=0.5, step=0.001),
            ],
            executor=_exec_demo_coarse_scan,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.define_left",
            title="定义左侧角度区间",
            category="流程Demo",
            default_params={"width": 0.08},
            input_ports=[NodePortSpec("scan_in", "scan_curve")],
            output_ports=[NodePortSpec("left_out", "range")],
            param_specs=[NodeParamSpec("width", "区间宽度", editor="float", minimum=0.01, maximum=0.4, step=0.01)],
            executor=_exec_demo_define_left,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.left_fine_scan",
            title="执行左区精扫",
            category="流程Demo",
            default_params={"steps": 45, "series": "left_fine"},
            input_ports=[NodePortSpec("range_in", "range")],
            output_ports=[NodePortSpec("result_out", "fine_result")],
            param_specs=[
                NodeParamSpec("steps", "步数", editor="int", minimum=5, maximum=400, step=5),
                NodeParamSpec("series", "序列名", editor="text"),
            ],
            executor=_exec_demo_fine_scan,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.define_right",
            title="定义右侧角度区间",
            category="流程Demo",
            default_params={"width": 0.08},
            input_ports=[NodePortSpec("scan_in", "scan_curve")],
            output_ports=[NodePortSpec("right_out", "range")],
            param_specs=[NodeParamSpec("width", "区间宽度", editor="float", minimum=0.01, maximum=0.4, step=0.01)],
            executor=_exec_demo_define_right,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.right_fine_scan",
            title="执行右区精扫",
            category="流程Demo",
            default_params={"steps": 45, "series": "right_fine"},
            input_ports=[NodePortSpec("range_in", "range")],
            output_ports=[NodePortSpec("result_out", "fine_result")],
            param_specs=[
                NodeParamSpec("steps", "步数", editor="int", minimum=5, maximum=400, step=5),
                NodeParamSpec("series", "序列名", editor="text"),
            ],
            executor=_exec_demo_fine_scan,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.select_region",
            title="确认最优角度",
            category="流程Demo",
            default_params={},
            input_ports=[NodePortSpec("left_in", "fine_result"), NodePortSpec("right_in", "fine_result")],
            output_ports=[NodePortSpec("best_out", "choice")],
            executor=_exec_demo_select_region,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.compute_work_freq",
            title="计算工作点频率",
            category="流程Demo",
            default_params={"base_freq_hz": 5.1e9},
            input_ports=[NodePortSpec("best_in", "choice")],
            output_ports=[NodePortSpec("freq_out", "frequency")],
            param_specs=[
                NodeParamSpec("base_freq_hz", "基准频率", editor="float", minimum=1e6, maximum=20e9, step=1e6)
            ],
            executor=_exec_demo_compute_work_freq,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.apply_work_freq",
            title="设置双路微波并采集",
            category="流程Demo",
            default_params={},
            input_ports=[NodePortSpec("freq_in", "frequency")],
            output_ports=[NodePortSpec("state_out", "sampling_state")],
            executor=_exec_demo_apply_freq,
        )
    )
    registry.register(
        NodeSpec(
            node_type="demo.monitor_drift",
            title="观测误差数据",
            category="流程Demo",
            default_params={"sample_count": 180},
            input_ports=[NodePortSpec("state_in", "sampling_state")],
            output_ports=[NodePortSpec("metrics_out", "metrics")],
            param_specs=[NodeParamSpec("sample_count", "采样数", editor="int", minimum=20, maximum=5000, step=10)],
            executor=_exec_demo_monitor_drift,
        )
    )
