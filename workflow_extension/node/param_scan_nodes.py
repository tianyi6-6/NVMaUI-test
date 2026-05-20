"""
参数扫描优化节点

本模块提供参数扫描和自动优化功能，包括：
- 参数扫描节点：执行激光器电流和微波功率的二维参数扫描
- 参数优化节点：根据扫描数据自动推荐最优参数组合
- 数据评估节点：评估扫描数据的质量指标

这些节点专门用于实验参数的自动优化和数据采集。
"""

import time
import numpy as np
from typing import Dict, List, Tuple
from PySide6.QtCore import QCoreApplication

from workflow_extension.node_registry import NodeSpec, NodePortSpec, NodeParamSpec
from workflow_extension.logger import get_logger
from manager import DevState

_log = get_logger("ParamScan")


def _exec_param_scan(context, node, inputs):
    """
    参数扫描节点执行器
    
    执行激光器电流和CH1微波功率的二维参数扫描，采集CW谱数据并保存扫描结果。
    
    Args:
        context (Dict[str, Any]): 执行上下文，包含应用实例和设备接口
        node (WorkflowNodeModel): 节点模型实例，包含扫描参数配置
        inputs (List[Any]): 输入数据列表
        
    Returns:
        Dict[str, Any]: 包含扫描数据和最优参数建议的字典
    """
    try:
        app = context.get("app")
        if app is None:
            raise ValueError("未找到应用上下文 app，无法执行参数扫描")
        if not hasattr(app, "set_param") or not hasattr(app, "dev"):
            raise ValueError("应用上下文缺少 set_param 或 dev 接口")
        if app.dev is None:
            raise ValueError("设备未连接，请先在设备管理页连接设备")
        if not hasattr(app.dev, "IIR_play"):
            raise ValueError("当前设备不是实际采集设备")

        laser_start = float(node.params.get("laser_start", 0.5))
        laser_end = float(node.params.get("laser_end", 1.0))
        laser_step = float(node.params.get("laser_step", 0.1))
        
        power_start = int(node.params.get("power_start", 0))
        power_end = int(node.params.get("power_end", 30))
        power_step = int(node.params.get("power_step", 2))
        
        mw_start_freq = float(node.params.get("mw_start_freq", 2800.0))
        mw_end_freq = float(node.params.get("mw_end_freq", 2950.0))
        mw_step_freq = float(node.params.get("mw_step_freq", 5.0))
        single_point_count = int(node.params.get("single_point_count", 10))

        if laser_step <= 0 or laser_end < laser_start:
            raise ValueError("激光器电流扫描范围无效")
        if power_step <= 0 or power_end < power_start:
            raise ValueError("微波功率扫描范围无效")
        if mw_step_freq <= 0 or mw_end_freq < mw_start_freq:
            raise ValueError("微波频率扫描范围无效")

        laser_currents = np.arange(laser_start, laser_end + laser_step, laser_step)
        powers = np.arange(power_start, power_end + power_step, power_step)
        mw_freqs = np.arange(mw_start_freq, mw_end_freq + mw_step_freq, mw_step_freq) * 1e6

        _log.info(
            "参数扫描开始: 激光器电流=[%s, %s]A (步长=%sA), "
            "CH1微波功率=[%s, %s]dBm (步长=%sdBm), "
            "微波频率=[%s, %s]MHz (步长=%sMHz)",
            laser_start, laser_end, laser_step,
            power_start, power_end, power_step,
            mw_start_freq, mw_end_freq, mw_step_freq
        )

        param_config = getattr(app, "param_config", {})
        ch1_init_power = param_config.get("mw_ch1_power", {}).get("value")
        laser_init_current = param_config.get("laser_current", {}).get("value")

        scan_results = []
        scan_summary = []
        
        workflow_tab = context.get("workflow_tab")
        state_manager = getattr(app, "state_manager", None)
        if state_manager is not None:
            state_manager.set_state(DevState.EXP_RUNNING)

        try:
            for laser_current in laser_currents:
                # 检查停止请求
                if context.get("stop_requested", lambda: False)():
                    _log.info("工作流执行已停止")
                    break
                
                app.set_param(name="laser_current", value=str(laser_current), ui_flag=False, delay_flag=False)
                time.sleep(0.5)

                for power in powers:
                    # 检查停止请求
                    if context.get("stop_requested", lambda: False)():
                        _log.info("工作流执行已停止")
                        break
                    
                    QCoreApplication.processEvents()
                    
                    app.set_param(name="mw_ch1_power", value=str(power), ui_flag=False, delay_flag=False)
                    time.sleep(0.3)

                    ch1_x_data = []
                    ch1_y_data = []

                    for freq_hz in mw_freqs:
                        # 检查停止请求
                        if context.get("stop_requested", lambda: False)():
                            break
                        
                        app.set_param(name="mw_ch1_freq", value=str(freq_hz), ui_flag=False, delay_flag=False)
                        
                        iir_data = app.dev.IIR_play(data_num=single_point_count)
                        iir_1x = float(np.mean(iir_data[1]))
                        iir_1y = float(np.mean(iir_data[2]))
                        
                        ch1_x_data.append(iir_1x)
                        ch1_y_data.append(iir_1y)

                    result = {
                        "laser_current": laser_current,
                        "mw_power": power,
                        "mw_freqs": mw_freqs,
                        "ch1_x": ch1_x_data,
                        "ch1_y": ch1_y_data,
                        "timestamp": time.time()
                    }
                    scan_results.append(result)

                    peak_x = np.max(ch1_x_data)
                    peak_y = np.max(ch1_y_data)
                    noise_x = np.std(ch1_x_data)
                    snr_x = peak_x / noise_x if noise_x > 0 else 0
                    
                    summary_item = {
                        "laser_current": laser_current,
                        "mw_power": power,
                        "peak_x": peak_x,
                        "peak_y": peak_y,
                        "snr_x": snr_x,
                        "noise_x": noise_x
                    }
                    scan_summary.append(summary_item)

                    _log.info(
                        "扫描点: 激光器电流=%.2fA, 微波功率=%ddBm, 峰值X=%.4fV, SNR=%.2f",
                        laser_current, power, peak_x, snr_x
                    )

                    if workflow_tab and hasattr(workflow_tab, 'plot_curve_top_main'):
                        # 更新workflow_tab的内部状态变量
                        workflow_tab._plot_x = np.array(list(mw_freqs))
                        workflow_tab._plot_y = np.array(list(ch1_x_data))
                        workflow_tab._plot_upper_aux = np.array(list(ch1_y_data))
                        workflow_tab._plot_lower_main = np.array([])
                        workflow_tab._plot_lower_aux = np.array([])
                        # 应用cw绘图模式并刷新曲线
                        workflow_tab._apply_plot_mode("cw")
                        QCoreApplication.processEvents()
                
                # 如果停止请求也会break外层循环
                if context.get("stop_requested", lambda: False)():
                    break

        finally:
            if ch1_init_power is not None:
                app.set_param(name="mw_ch1_power", value=ch1_init_power, ui_flag=False, delay_flag=False)
            if laser_init_current is not None:
                app.set_param(name="laser_current", value=laser_init_current, ui_flag=False, delay_flag=False)
            if state_manager is not None:
                state_manager.set_state(DevState.IDLE)

        _log.info("参数扫描完成: 共扫描 %d 个参数组合", len(scan_results))

        return {
            "scan_results": scan_results,
            "scan_summary": scan_summary,
            "laser_currents": laser_currents.tolist(),
            "powers": powers.tolist(),
            "mw_freqs": mw_freqs.tolist(),
            "scan_points": len(scan_results),
            "param_ranges": {
                "laser_current": {"start": laser_start, "end": laser_end, "step": laser_step},
                "mw_power": {"start": power_start, "end": power_end, "step": power_step},
                "mw_freq": {"start": mw_start_freq, "end": mw_end_freq, "step": mw_step_freq}
            }
        }

    except Exception as e:
        _log.error("参数扫描失败: %s", e)
        return {"error": str(e)}


def _exec_param_optimize(context, node, inputs):
    """
    参数优化节点执行器
    
    根据参数扫描数据自动推荐最优参数组合，基于信噪比、峰值等指标进行评估。
    
    Args:
        context (Dict[str, Any]): 执行上下文
        node (WorkflowNodeModel): 节点模型实例
        inputs (Dict[str, Any]): 输入数据，包含扫描结果
        
    Returns:
        Dict[str, Any]: 包含最优参数推荐和评估指标的字典
    """
    try:
        scan_summary = inputs.get("scan_summary")
        if scan_summary is None or not isinstance(scan_summary, list):
            raise ValueError("输入数据中缺少 scan_summary 或格式不正确")

        optimize_method = node.params.get("optimize_method", "snr")

        if optimize_method == "snr":
            best_result = max(scan_summary, key=lambda x: x["snr_x"])
        elif optimize_method == "peak":
            best_result = max(scan_summary, key=lambda x: x["peak_x"])
        elif optimize_method == "peak_snr":
            best_result = max(scan_summary, key=lambda x: x["peak_x"] * x["snr_x"])
        else:
            raise ValueError(f"未知的优化方法: {optimize_method}")

        laser_current_best = best_result["laser_current"]
        mw_power_best = best_result["mw_power"]

        avg_noise = np.mean([item["noise_x"] for item in scan_summary])
        avg_peak = np.mean([item["peak_x"] for item in scan_summary])
        avg_snr = np.mean([item["snr_x"] for item in scan_summary])

        _log.info(
            "参数优化完成: 最优激光器电流=%.2fA, 最优微波功率=%ddBm, "
            "峰值=%.4fV, SNR=%.2f",
            laser_current_best, mw_power_best, best_result["peak_x"], best_result["snr_x"]
        )

        app = context.get("app")
        if app and hasattr(app, "set_param"):
            apply_optimal = node.params.get("apply_optimal", False)
            if apply_optimal:
                app.set_param(name="laser_current", value=str(laser_current_best), ui_flag=True, delay_flag=True)
                app.set_param(name="mw_ch1_power", value=str(mw_power_best), ui_flag=True, delay_flag=True)
                _log.info("已自动应用最优参数到设备")

        return {
            "optimized": True,
            "optimize_method": optimize_method,
            "optimal_params": {
                "laser_current": laser_current_best,
                "mw_ch1_power": mw_power_best
            },
            "optimal_metrics": {
                "peak_x": best_result["peak_x"],
                "peak_y": best_result["peak_y"],
                "snr_x": best_result["snr_x"],
                "noise_x": best_result["noise_x"]
            },
            "overall_metrics": {
                "avg_peak": avg_peak,
                "avg_snr": avg_snr,
                "avg_noise": avg_noise,
                "total_scan_points": len(scan_summary)
            },
            "scan_summary": scan_summary
        }

    except Exception as e:
        _log.error("参数优化失败: %s", e)
        return {"error": str(e)}


def _exec_data_evaluate(context, node, inputs):
    """
    数据评估节点执行器
    
    对扫描数据进行质量评估，计算各项指标并生成评估报告。
    
    Args:
        context (Dict[str, Any]): 执行上下文
        node (WorkflowNodeModel): 节点模型实例
        inputs (Dict[str, Any]): 输入数据
        
    Returns:
        Dict[str, Any]: 包含评估指标和报告的字典
    """
    try:
        scan_results = inputs.get("scan_results")
        if scan_results is None or not isinstance(scan_results, list):
            raise ValueError("输入数据中缺少 scan_results 或格式不正确")

        metrics = []
        
        for result in scan_results:
            ch1_x = np.array(result["ch1_x"])
            ch1_y = np.array(result["ch1_y"])
            
            peak_x = np.max(ch1_x)
            peak_y = np.max(ch1_y)
            mean_x = np.mean(ch1_x)
            std_x = np.std(ch1_x)
            snr_x = peak_x / std_x if std_x > 0 else 0
            
            max_idx = np.argmax(ch1_x)
            peak_freq = result["mw_freqs"][max_idx]
            
            fwhm = _calculate_fwhm(result["mw_freqs"], ch1_x)
            
            metrics.append({
                "laser_current": result["laser_current"],
                "mw_power": result["mw_power"],
                "peak_x": peak_x,
                "peak_y": peak_y,
                "mean_x": mean_x,
                "std_x": std_x,
                "snr_x": snr_x,
                "peak_freq_hz": peak_freq,
                "fwhm_hz": fwhm
            })

        metrics_array = np.array([m["snr_x"] for m in metrics])
        best_idx = np.argmax(metrics_array)
        best_metric = metrics[best_idx]

        _log.info("数据评估完成: 共评估 %d 个扫描点", len(metrics))

        return {
            "evaluated": True,
            "metrics": metrics,
            "best_metric": best_metric,
            "summary": {
                "total_points": len(metrics),
                "avg_snr": np.mean([m["snr_x"] for m in metrics]),
                "max_snr": np.max([m["snr_x"] for m in metrics]),
                "min_snr": np.min([m["snr_x"] for m in metrics]),
                "avg_peak": np.mean([m["peak_x"] for m in metrics]),
                "avg_fwhm": np.mean([m["fwhm_hz"] for m in metrics])
            }
        }

    except Exception as e:
        _log.error("数据评估失败: %s", e)
        return {"error": str(e)}


def _calculate_fwhm(freqs, data):
    """计算数据的半高全宽(FWHM)"""
    try:
        max_val = np.max(data)
        half_max = max_val / 2
        
        indices = np.where(data >= half_max)[0]
        if len(indices) < 2:
            return 0.0
        
        left_idx = indices[0]
        right_idx = indices[-1]
        
        return freqs[right_idx] - freqs[left_idx]
    except:
        return 0.0


def register_param_scan_nodes(registry):
    """注册参数扫描优化相关节点"""
    
    registry.register(
        NodeSpec(
            node_type="param_scan.two_dimensional",
            title="二维参数扫描",
            category="参数扫描优化",
            default_params={
                "laser_start": "0.5",
                "laser_end": "1.0",
                "laser_step": "0.1",
                "power_start": 0,
                "power_end": 30,
                "power_step": 2,
                "mw_start_freq": "2800.0",
                "mw_end_freq": "2950.0",
                "mw_step_freq": "5.0",
                "single_point_count": 10
            },
            input_ports=[NodePortSpec("device_in", "device")],
            output_ports=[
                NodePortSpec("scan_results", "dict"),
                NodePortSpec("scan_summary", "dict")
            ],
            param_specs=[
                NodeParamSpec("laser_start", "激光器电流起始值(A)", editor="float", minimum=0.0, maximum=2.0, step=0.01, unit="A"),
                NodeParamSpec("laser_end", "激光器电流结束值(A)", editor="float", minimum=0.0, maximum=2.0, step=0.01, unit="A"),
                NodeParamSpec("laser_step", "激光器电流步长(A)", editor="float", minimum=0.01, maximum=0.5, step=0.01, unit="A"),
                NodeParamSpec("power_start", "CH1微波功率起始值(dBm)", editor="int", minimum=0, maximum=30, step=1, unit="dBm"),
                NodeParamSpec("power_end", "CH1微波功率结束值(dBm)", editor="int", minimum=0, maximum=30, step=1, unit="dBm"),
                NodeParamSpec("power_step", "CH1微波功率步长(dBm)", editor="int", minimum=1, maximum=10, step=1, unit="dBm"),
                NodeParamSpec("mw_start_freq", "微波起始频率(MHz)", editor="float", minimum=2600.0, maximum=3100.0, step=1.0, unit="MHz"),
                NodeParamSpec("mw_end_freq", "微波结束频率(MHz)", editor="float", minimum=2600.0, maximum=3100.0, step=1.0, unit="MHz"),
                NodeParamSpec("mw_step_freq", "微波频率步长(MHz)", editor="float", minimum=0.1, maximum=50.0, step=0.1, unit="MHz"),
                NodeParamSpec("single_point_count", "单点CW采集累加次数", editor="int", minimum=1, maximum=1000, step=1),
            ],
            executor=_exec_param_scan,
        )
    )

    registry.register(
        NodeSpec(
            node_type="param_scan.optimize",
            title="参数优化",
            category="参数扫描优化",
            default_params={
                "optimize_method": "snr",
                "apply_optimal": False
            },
            input_ports=[
                NodePortSpec("scan_summary", "dict"),
                NodePortSpec("scan_results", "dict")
            ],
            output_ports=[NodePortSpec("optimal_params", "dict")],
            param_specs=[
                NodeParamSpec("optimize_method", "优化方法", editor="select", options=["snr", "peak", "peak_snr"],
                              subcategory="优化方法"),
                NodeParamSpec("apply_optimal", "自动应用最优参数", editor="bool"),
            ],
            executor=_exec_param_optimize,
        )
    )

    registry.register(
        NodeSpec(
            node_type="param_scan.evaluate",
            title="数据评估",
            category="参数扫描优化",
            default_params={},
            input_ports=[NodePortSpec("scan_results", "dict")],
            output_ports=[NodePortSpec("metrics", "dict")],
            param_specs=[],
            executor=_exec_data_evaluate,
        )
    )