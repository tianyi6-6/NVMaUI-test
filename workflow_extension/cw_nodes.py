"""
CW谱数据采集专用节点

本模块提供了连续波谱数据采集的专用节点，包括：
- 锁相放大器配置节点：配置锁相放大器参数
- 微波扫频循环节点：执行微波频率扫描
- 微波源配置节点：配置微波源参数
- 锁相数据读取节点：读取锁相放大器数据
- 数据平均处理节点：对采集数据进行平均处理
- CW谱可视化节点：实时显示CW谱数据
- CW谱数据保存节点：保存CW谱数据到文件

这些节点专门用于CW谱实验的数据采集和处理流程。
"""

# encoding=utf-8
import time
import numpy as np
import logging
from PySide6.QtCore import QObject, Signal
from workflow_extension.node_registry import NodeSpec, NodePortSpec, NodeParamSpec


def _exec_lockin_config(context, node, inputs):
    """
    锁相放大器配置节点执行器
    
    配置锁相放大器的关键参数，包括调制频率、采样频率、时间常数和灵敏度。
    在实际应用中会调用硬件API进行设备配置。
    
    Args:
        context (Dict[str, Any]): 执行上下文，包含应用实例和设备接口
        node (WorkflowNodeModel): 节点模型实例，包含锁相参数配置
        inputs (List[Any]): 输入数据列表
        
    Returns:
        Dict[str, Any]: 包含配置状态和参数的字典
    """
    try:
        # 获取锁相放大器参数
        mod_freq = float(node.params.get("mod_freq", 1000))      # 调制频率 (Hz)
        sample_freq = float(node.params.get("sample_freq", 10000))  # 采样频率 (Hz)
        time_constant = float(node.params.get("time_constant", 10))  # 时间常数 (ms)
        sensitivity = float(node.params.get("sensitivity", 1.0))     # 灵敏度 (V)
        
        # 记录配置信息
        logging.info(f"配置锁相放大器: 调制频率={mod_freq}Hz, 采样频率={sample_freq}Hz, "
                     f"时间常数={time_constant}ms, 灵敏度={sensitivity}V")
        
        # 在实际应用中，这里会调用硬件API进行设备配置
        # context['app'].dev.set_lockin_params(mod_freq, sample_freq, time_constant, sensitivity)
        
        return {
            "configured": True,
            "mod_freq": mod_freq,
            "sample_freq": sample_freq,
            "time_constant": time_constant,
            "sensitivity": sensitivity
        }
    except Exception as e:
        logging.error(f"锁相放大器配置失败: {e}")
        return {"configured": False, "error": str(e)}


def _exec_mw_sweep_loop(context, node, inputs):
    """
    微波扫频循环节点执行器
    
    执行微波频率扫描循环，生成频率序列并循环执行子节点进行数据采集。
    支持实时绘图显示扫描过程。
    
    Args:
        context (Dict[str, Any]): 执行上下文，包含绘图回调函数
        node (WorkflowNodeModel): 节点模型实例，包含扫频参数
        inputs (List[Any]): 输入数据列表
        
    Returns:
        Dict[str, Any]: 包含频率数组和采集数据的字典
    """
    try:
        # 获取扫频参数
        start_freq = float(node.params.get("start_freq", 1000))  # 起始频率 (MHz)
        stop_freq = float(node.params.get("stop_freq", 2000))    # 终止频率 (MHz)
        num_points = int(node.params.get("num_points", 100))    # 扫描点数
        
        # 生成线性频率序列
        freq_array = np.linspace(start_freq, stop_freq, num_points)
        
        logging.info(f"微波扫频循环: 起始频率={start_freq}MHz, 终止频率={stop_freq}MHz, 点数={num_points}")
        
        # 初始化采集数据数组
        cw_data = []
        for i, freq in enumerate(freq_array):
            # 设置当前频率到上下文
            context["mw_freq"] = freq
            context["freq_index"] = i
            
            # 在实际工作流引擎中，这里会执行子节点
            # 目前模拟数据采集
            # 模拟锁相放大器数据读取
            point_data = _simulate_lockin_reading(freq, num_points=10)
            cw_data.append(point_data)
            
            # 实时数据更新回调
            if "plot_callback" in context:
                context["plot_callback"]({
                    "x": freq,
                    "y": np.mean(point_data[:, 0]),  # X通道平均值
                    "y2": np.mean(point_data[:, 1]) if point_data.shape[1] > 1 else None,  # Y通道平均值
                    "series": "cw_realtime"
                })
        
        # 转换为numpy数组，形状为 (num_points, 2, sample_points)
        cw_data = np.array(cw_data)
        
        return {
            "mw_freq": freq_array,
            "cw_data": cw_data,
            "num_points": num_points
        }
    except Exception as e:
        logging.error(f"微波扫频循环失败: {e}")
        return {"error": str(e)}


def _exec_mw_source_config(context, node, inputs):
    """
    微波源配置节点执行器
    
    配置微波源的频率、功率和FM灵敏度参数。
    在实际应用中会调用硬件API进行微波源配置。
    
    Args:
        context (Dict[str, Any]): 执行上下文，包含应用实例和设备接口
        node (WorkflowNodeModel): 节点模型实例，包含微波源参数配置
        inputs (List[Any]): 输入数据列表，第一个元素为微波频率
        
    Returns:
        Dict[str, Any]: 包含配置状态和参数的字典
    """
    try:
        # 获取输入频率 (来自扫频循环)
        mw_freq = inputs.get("mw_freq", 1000)  # MHz
        
        # 获取微波源参数
        power = float(node.params.get("power", 0))        # 功率 (dBm)
        fm_sens = float(node.params.get("fm_sens", 1.0))   # FM灵敏度 (V/V)
        
        # 记录配置信息
        logging.info(f"配置微波源: 频率={mw_freq}MHz, 功率={power}dBm, FM灵敏度={fm_sens}")
        
        # 在实际应用中，这里会调用硬件API进行设备配置
        # context['app'].dev.set_mw_params(mw_freq * 1e6, power, fm_sens)
        
        return {
            "configured": True,
            "mw_freq": mw_freq,
            "power": power,
            "fm_sens": fm_sens
        }
    except Exception as e:
        logging.error(f"微波源配置失败: {e}")
        return {"configured": False, "error": str(e)}


def _exec_lockin_read(context, node, inputs):
    """执行锁相放大器数据读取"""
    try:
        # 获取配置参数
        channels = node.params.get("channels", ["input1-x", "input1-y"])
        sample_points = int(node.params.get("sample_points", 10))
        
        # 获取当前频率（从上下文获取）
        current_freq = context.get("mw_freq", 1000)
        
        # 模拟读取锁相放大器数据
        data = _simulate_lockin_reading(current_freq, sample_points, len(channels))
        
        logging.info(f"读取锁相数据: 频率={current_freq}MHz, 通道={channels}, 采样点数={sample_points}")
        
        return {
            "data": data,
            "freq": current_freq,
            "channels": channels,
            "sample_points": sample_points
        }
    except Exception as e:
        logging.error(f"锁相数据读取失败: {e}")
        return {"error": str(e)}


def _exec_data_average(context, node, inputs):
    """执行数据平均处理"""
    try:
        # 获取输入数据
        cw_data = inputs.get("cw_data")
        
        if cw_data is None:
            raise ValueError("未找到输入数据 cw_data")
        
        # 对第三维度求平均
        if len(cw_data.shape) == 3:
            cw_data_avg = np.mean(cw_data, axis=2)  # shape: (num_points, 2)
        else:
            cw_data_avg = cw_data
        
        logging.info(f"数据平均处理: 输入形状={cw_data.shape}, 输出形状={cw_data_avg.shape}")
        
        return {
            "cw_data_avg": cw_data_avg,
            "original_shape": cw_data.shape,
            "processed_shape": cw_data_avg.shape
        }
    except Exception as e:
        logging.error(f"数据平均处理失败: {e}")
        return {"error": str(e)}


def _exec_cw_visualization(context, node, inputs):
    """执行CW谱数据可视化"""
    try:
        # 获取输入数据
        cw_data_avg = inputs.get("cw_data_avg")
        mw_freq = inputs.get("mw_freq")
        
        if cw_data_avg is None or mw_freq is None:
            raise ValueError("未找到输入数据 cw_data_avg 或 mw_freq")
        
        # 获取绘图参数
        plot_title = node.params.get("plot_title", "CW谱")
        x_label = node.params.get("x_label", "频率 (MHz)")
        y_label = node.params.get("y_label", "幅度 (V)")
        show_legend = node.params.get("show_legend", True)
        
        # 实时绘图回调
        if "plot_callback" in context:
            # 绘制X通道数据
            context["plot_callback"]({
                "x": mw_freq,
                "y": cw_data_avg[:, 0],
                "series": "ch_x",
                "title": plot_title,
                "x_label": x_label,
                "y_label": y_label,
                "show_legend": show_legend
            })
            
            # 如果有Y通道数据，也绘制
            if cw_data_avg.shape[1] > 1:
                context["plot_callback"]({
                    "x": mw_freq,
                    "y": cw_data_avg[:, 1],
                    "series": "ch_y",
                    "title": plot_title,
                    "x_label": x_label,
                    "y_label": y_label,
                    "show_legend": show_legend
                })
        
        logging.info(f"CW谱可视化: 数据点数={len(mw_freq)}, 通道数={cw_data_avg.shape[1]}")
        
        return {
            "visualized": True,
            "data_points": len(mw_freq),
            "channels": cw_data_avg.shape[1],
            "plot_title": plot_title
        }
    except Exception as e:
        logging.error(f"CW谱可视化失败: {e}")
        return {"error": str(e)}


def _exec_cw_data_save(context, node, inputs):
    """执行CW谱数据保存"""
    try:
        # 获取输入数据
        cw_data_avg = inputs.get("cw_data_avg")
        mw_freq = inputs.get("mw_freq")
        
        if cw_data_avg is None or mw_freq is None:
            raise ValueError("未找到输入数据 cw_data_avg 或 mw_freq")
        
        # 获取保存参数
        save_path = node.params.get("save_path", "cw_spectrum_data")
        file_format = node.params.get("file_format", "csv")
        
        # 构建完整文件路径
        if not save_path.endswith(('.csv', '.npy', '.txt')):
            save_path = f"{save_path}.{file_format}"
        
        # 保存数据
        if file_format == "csv":
            # 保存为CSV格式
            import pandas as pd
            df = pd.DataFrame({
                'frequency_mhz': mw_freq,
                'channel_x': cw_data_avg[:, 0],
                'channel_y': cw_data_avg[:, 1] if cw_data_avg.shape[1] > 1 else np.zeros(len(mw_freq))
            })
            df.to_csv(save_path, index=False)
        elif file_format == "npy":
            # 保存为numpy格式
            np.save(save_path, {
                'frequency': mw_freq,
                'data': cw_data_avg
            })
        elif file_format == "txt":
            # 保存为文本格式
            with open(save_path, 'w') as f:
                f.write("# Frequency(MHz)\tChannel_X\tChannel_Y\n")
                for i, freq in enumerate(mw_freq):
                    x_val = cw_data_avg[i, 0]
                    y_val = cw_data_avg[i, 1] if cw_data_avg.shape[1] > 1 else 0
                    f.write(f"{freq:.6f}\t{x_val:.6f}\t{y_val:.6f}\n")
        
        logging.info(f"CW谱数据保存: 文件={save_path}, 格式={file_format}")
        
        return {
            "saved": True,
            "file_path": save_path,
            "file_format": file_format,
            "data_shape": cw_data_avg.shape
        }
    except Exception as e:
        logging.error(f"CW谱数据保存失败: {e}")
        return {"error": str(e)}


def _simulate_lockin_reading(freq, sample_points=10, channels=2):
    """模拟锁相放大器数据读取"""
    # 模拟一个简单的共振峰
    center_freq = 1500  # MHz
    linewidth = 100  # MHz
    amplitude = 1.0  # V
    
    # 计算该频率点的幅度
    freq_offset = freq - center_freq
    lorentzian = amplitude / (1 + (2 * freq_offset / linewidth) ** 2)
    
    # 添加噪声
    noise_level = 0.01
    data = np.random.normal(lorentzian, noise_level, (sample_points, channels))
    
    return data


def register_cw_nodes(registry):
    """注册CW谱数据采集相关节点"""
    
    # 1. 参数配置：锁相放大器
    registry.register(
        NodeSpec(
            node_type="cw.lockin_config",
            title="参数配置：锁相放大器",
            category="CW谱数据采集",
            default_params={
                "mod_freq": 1000,
                "sample_freq": 10000,
                "time_constant": 10,
                "sensitivity": 1.0
            },
            input_ports=[NodePortSpec("trigger", "trigger")],
            output_ports=[NodePortSpec("configured", "bool")],
            param_specs=[
                NodeParamSpec("mod_freq", "调制频率 (Hz)", editor="float", minimum=1, maximum=100000),
                NodeParamSpec("sample_freq", "采样频率 (Hz)", editor="float", minimum=100, maximum=1000000),
                NodeParamSpec("time_constant", "时间常数 (ms)", editor="float", minimum=1, maximum=1000),
                NodeParamSpec("sensitivity", "灵敏度 (V)", editor="float", minimum=0.001, maximum=1000),
            ],
            executor=_exec_lockin_config,
        )
    )
    
    # 2. 循环：微波扫频
    registry.register(
        NodeSpec(
            node_type="cw.mw_sweep_loop",
            title="循环：微波扫频",
            category="CW谱数据采集",
            default_params={
                "start_freq": 1000,
                "stop_freq": 2000,
                "num_points": 100
            },
            input_ports=[NodePortSpec("trigger", "trigger")],
            output_ports=[
                NodePortSpec("mw_freq", "array"),
                NodePortSpec("cw_data", "array")
            ],
            param_specs=[
                NodeParamSpec("start_freq", "起始频率 (MHz)", editor="float", minimum=1, maximum=10000),
                NodeParamSpec("stop_freq", "终止频率 (MHz)", editor="float", minimum=1, maximum=10000),
                NodeParamSpec("num_points", "扫描点数", editor="int", minimum=10, maximum=1000),
            ],
            executor=_exec_mw_sweep_loop,
        )
    )
    
    # 3. 参数配置：微波设置
    registry.register(
        NodeSpec(
            node_type="cw.mw_source_config",
            title="参数配置：微波设置",
            category="CW谱数据采集",
            default_params={
                "power": 0,
                "fm_sens": 1.0
            },
            input_ports=[NodePortSpec("mw_freq", "float")],
            output_ports=[NodePortSpec("configured", "bool")],
            param_specs=[
                NodeParamSpec("power", "功率 (dBm)", editor="float", minimum=-30, maximum=30),
                NodeParamSpec("fm_sens", "FM灵敏度", editor="float", minimum=0.1, maximum=10),
            ],
            executor=_exec_mw_source_config,
        )
    )
    
    # 4. 读取数据：锁相扫谱
    registry.register(
        NodeSpec(
            node_type="cw.lockin_read",
            title="读取数据：锁相扫谱",
            category="CW谱数据采集",
            default_params={
                "channels": "input1-x,input1-y",
                "sample_points": 10
            },
            input_ports=[NodePortSpec("trigger", "trigger")],
            output_ports=[NodePortSpec("data", "array")],
            param_specs=[
                NodeParamSpec("channels", "采集通道", editor="text"),
                NodeParamSpec("sample_points", "采样点数", editor="int", minimum=1, maximum=1000),
            ],
            executor=_exec_lockin_read,
        )
    )
    
    # 5. 数据处理：平均
    registry.register(
        NodeSpec(
            node_type="cw.data_average",
            title="数据处理：平均",
            category="CW谱数据采集",
            input_ports=[NodePortSpec("cw_data", "array")],
            output_ports=[NodePortSpec("cw_data_avg", "array")],
            param_specs=[],
            executor=_exec_data_average,
        )
    )
    
    # 6. 数据可视化：CW谱
    registry.register(
        NodeSpec(
            node_type="cw.cw_visualization",
            title="数据可视化：CW谱",
            category="CW谱数据采集",
            default_params={
                "plot_title": "CW谱",
                "x_label": "频率 (MHz)",
                "y_label": "幅度 (V)",
                "show_legend": True
            },
            input_ports=[
                NodePortSpec("cw_data_avg", "array"),
                NodePortSpec("mw_freq", "array")
            ],
            output_ports=[NodePortSpec("visualized", "bool")],
            param_specs=[
                NodeParamSpec("plot_title", "图表标题", editor="text"),
                NodeParamSpec("x_label", "X轴标签", editor="text"),
                NodeParamSpec("y_label", "Y轴标签", editor="text"),
                NodeParamSpec("show_legend", "显示图例", editor="bool"),
            ],
            executor=_exec_cw_visualization,
        )
    )
    
    # 7. 数据保存：CW谱
    registry.register(
        NodeSpec(
            node_type="cw.cw_data_save",
            title="数据保存：CW谱",
            category="CW谱数据采集",
            default_params={
                "save_path": "cw_spectrum_data",
                "file_format": "csv"
            },
            input_ports=[
                NodePortSpec("cw_data_avg", "array"),
                NodePortSpec("mw_freq", "array")
            ],
            output_ports=[NodePortSpec("saved", "bool")],
            param_specs=[
                NodeParamSpec("save_path", "保存路径", editor="text"),
                NodeParamSpec("file_format", "文件格式", editor="select", options=["csv", "npy", "txt"]),
            ],
            executor=_exec_cw_data_save,
        )
    )
