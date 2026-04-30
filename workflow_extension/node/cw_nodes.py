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
from manager import DevState
from workflow_extension.node_registry import NodeSpec, NodePortSpec, NodeParamSpec


def _exec_cw_spectrum_acquire(context, node, inputs):
    try:
        app = context.get("app")
        if app is None:
            raise ValueError("未找到应用上下文 app，无法执行CW谱真实采集")
        if not hasattr(app, "set_param") or not hasattr(app, "dev"):
            raise ValueError("应用上下文缺少 set_param 或 dev 接口，无法执行CW谱真实采集")
        if app.dev is None:
            raise ValueError("设备未连接，请先在设备管理页连接设备")
        if not hasattr(app.dev, "IIR_play"):
            raise ValueError("当前设备不是实际采集设备，请先连接锁相放大器设备")

        mw_channel = str(node.params.get("mw_channel", "微波通道1"))
        start_freq = float(node.params.get("start_freq_mhz", 2800.0))
        end_freq = float(node.params.get("end_freq_mhz", 2950.0))
        step_freq = float(node.params.get("step_freq_mhz", 2.0))
        single_point_count = int(node.params.get("single_point_count", 10))

        if step_freq <= 0:
            raise ValueError("步进频率必须大于0")
        if end_freq < start_freq:
            raise ValueError("结束频率必须大于等于起始频率")
        if single_point_count <= 0:
            raise ValueError("单点CW采集累加次数必须大于0")

        start_freq_hz = start_freq * 1e6
        end_freq_hz = end_freq * 1e6
        step_freq_hz = step_freq * 1e6
        if start_freq_hz > end_freq_hz:
            raise ValueError("频率扫描范围无有效点")

        param_config = getattr(app, "param_config", {})
        ch1_init_freq = param_config.get("mw_ch1_freq", {}).get("value")
        ch2_init_freq = param_config.get("mw_ch2_freq", {}).get("value")
        ch1_init_fm_sens = param_config.get("mw_ch1_fm_sens", {}).get("value")
        ch2_init_fm_sens = param_config.get("mw_ch2_fm_sens", {}).get("value")
        ch1_init_power = param_config.get("mw_ch1_power", {}).get("value")
        ch2_init_power = param_config.get("mw_ch2_power", {}).get("value")

        mw_freq = []
        ch1_x = []
        ch1_y = []
        ch2_x = []
        ch2_y = []
        callback = context.get("plot_callback")
        workflow_tab = context.get("workflow_tab")
        state_manager = getattr(app, "state_manager", None)
        if state_manager is not None:
            state_manager.set_state(DevState.EXP_RUNNING)

        active_channel_index = 0 if mw_channel == "微波通道1" else 1
        if active_channel_index == 0:
            app.set_param(name="mw_ch2_fm_sens", value=0, ui_flag=False, delay_flag=False)
            app.set_param(name="mw_ch2_power", value=0, ui_flag=False, delay_flag=False)
            app.set_param(name="mw_ch2_freq", value=2.6e9, ui_flag=False, delay_flag=False)
        else:
            app.set_param(name="mw_ch1_fm_sens", value=0, ui_flag=False, delay_flag=False)
            app.set_param(name="mw_ch1_power", value=0, ui_flag=False, delay_flag=False)
            app.set_param(name="mw_ch1_freq", value=2.6e9, ui_flag=False, delay_flag=False)

        current_freq_hz = start_freq_hz
        try:
            while current_freq_hz <= end_freq_hz:
                if active_channel_index == 0:
                    app.set_param(name="mw_ch1_freq", value=str(current_freq_hz), ui_flag=False, delay_flag=False)
                else:
                    app.set_param(name="mw_ch2_freq", value=str(current_freq_hz), ui_flag=False, delay_flag=False)

                iir_data = app.dev.IIR_play(data_num=single_point_count)
                iir_1x = float(np.mean(iir_data[1]))
                iir_1y = float(np.mean(iir_data[2]))
                iir_2x = float(np.mean(iir_data[7]))
                iir_2y = float(np.mean(iir_data[8]))

                mw_freq.append(current_freq_hz)
                ch1_x.append(iir_1x)
                ch1_y.append(iir_1y)
                ch2_x.append(iir_2x)
                ch2_y.append(iir_2y)

                if callback:
                    callback({"x": current_freq_hz, "y": iir_1x, "y2": iir_2x})

                # 实时更新工作流双图显示
                if workflow_tab and hasattr(workflow_tab, 'plot_curve_top_main'):
                    # 创建numpy数组副本用于绘图，不影响原始列表
                    plot_x = np.array(mw_freq)
                    plot_y = np.array(ch1_x)
                    plot_upper_aux = np.array(ch1_y)
                    plot_lower_main = np.array(ch2_x)
                    plot_lower_aux = np.array(ch2_y)
                    workflow_tab.plot_curve_top_main.setData(plot_x, plot_y)
                    workflow_tab.plot_curve_top_aux.setData(plot_x, plot_upper_aux)
                    workflow_tab.plot_curve_bottom_main.setData(plot_x, plot_lower_main)
                    workflow_tab.plot_curve_bottom_aux.setData(plot_x, plot_lower_aux)
                    # 处理UI事件，保持界面响应
                    from PySide6.QtCore import QCoreApplication
                    QCoreApplication.processEvents()
                current_freq_hz += step_freq_hz
        finally:
            if ch1_init_freq is not None:
                app.set_param(name="mw_ch1_freq", value=ch1_init_freq, ui_flag=False, delay_flag=False)
            if ch2_init_freq is not None:
                app.set_param(name="mw_ch2_freq", value=ch2_init_freq, ui_flag=False, delay_flag=False)
            if ch1_init_fm_sens is not None:
                app.set_param(name="mw_ch1_fm_sens", value=ch1_init_fm_sens, ui_flag=False, delay_flag=False)
            if ch2_init_fm_sens is not None:
                app.set_param(name="mw_ch2_fm_sens", value=ch2_init_fm_sens, ui_flag=False, delay_flag=False)
            if ch1_init_power is not None:
                app.set_param(name="mw_ch1_power", value=ch1_init_power, ui_flag=False, delay_flag=False)
            if ch2_init_power is not None:
                app.set_param(name="mw_ch2_power", value=ch2_init_power, ui_flag=False, delay_flag=False)
            if state_manager is not None:
                state_manager.set_state(DevState.IDLE)

        logging.info(
            f"CW谱采集: 通道={mw_channel}, 起始频率={start_freq}MHz, 结束频率={end_freq}MHz, "
            f"步进频率={step_freq}MHz, 单点累加次数={single_point_count}, 点数={len(mw_freq)}"
        )

        return {
            "data_type": "cw",
            "mw_channel": mw_channel,
            "mw_freq": mw_freq,
            "ch1_x": ch1_x,
            "ch1_y": ch1_y,
            "ch2_x": ch2_x,
            "ch2_y": ch2_y,
            "single_point_count": single_point_count,
            "point_count": int(len(mw_freq)),
        }
    except Exception as e:
        logging.error(f"CW谱采集失败: {e}")
        return {"error": str(e)}


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
    registry.register(
        NodeSpec(
            node_type="cw.spectrum_acquire",
            title="CW谱采集",
            category="CW谱数据采集",
            default_params={
                "mw_channel": "微波通道1",
                "start_freq_mhz": 2800.0,
                "end_freq_mhz": 2950.0,
                "step_freq_mhz": 2.0,
                "single_point_count": 10
            },
            input_ports=[NodePortSpec("device_in", "device")],
            output_ports=[
                NodePortSpec("data", "dict")
            ],
            param_specs=[
                NodeParamSpec("mw_channel", "微波通道选择", editor="select", options=["微波通道1", "微波通道2"]),
                NodeParamSpec("start_freq_mhz", "起始频率(MHz)", editor="float", minimum=1.0, maximum=10000.0, step=1.0),
                NodeParamSpec("end_freq_mhz", "结束频率(MHz)", editor="float", minimum=1.0, maximum=10000.0, step=1.0),
                NodeParamSpec("step_freq_mhz", "步进频率(MHz)", editor="float", minimum=0.001, maximum=1000.0, step=0.1),
                NodeParamSpec("single_point_count", "单点CW采集累加次数", editor="int", minimum=1, maximum=100000, step=1),
            ],
            executor=_exec_cw_spectrum_acquire,
        )
    )
