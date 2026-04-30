"""初始化设备节点：一级分类 + 二级分类 + 三级参数项。"""

import re
import logging

from workflow_extension.node_registry import NodeParamSpec, NodePortSpec, NodeRegistry, NodeSpec


def _extract_numeric(value, default=0.0):
    if value is None:
        return default
    matched = re.search(r"[\d.]+", str(value))
    if not matched:
        return default
    return float(matched.group())


def _make_param(category, key, editor, current_value, valid_range, *, options=None, minimum=0.0, maximum=999999.0, step=1.0, unit=""):
    return NodeParamSpec(
        key=key,
        label=key,
        editor=editor,
        options=options or [],
        minimum=minimum,
        maximum=maximum,
        step=step,
        category=category,
        subcategory=key,
        device_param=True,
        current_value=current_value,
        valid_range=valid_range,
        unit=unit,
    )


def _exec_device_connect(context, node, inputs):
    app = context.get("app")
    dev = getattr(app, "dev", None) if app is not None else None
    connected = bool(app and dev is not None and hasattr(dev, "IIR_play"))
    if app is not None and not connected and hasattr(app, "connect_dev"):
        logging.info("工作流初始化设备节点：当前不是实际采集设备，尝试自动连接设备。")
        app.connect_dev()
        dev = getattr(app, "dev", None)
        connected = bool(dev is not None and hasattr(dev, "IIR_play"))
    if not connected:
        return {
            "connected": False,
            "message": "未连接实际采集设备，请先连接设备",
            "device_config": {},
            "components": {"lockin": False, "laser": False, "microwave": False, "memory": False},
        }

    try:
        if hasattr(app, "param_inputs") and hasattr(app, "set_param"):
            logging.info("工作流初始化设备节点：开始下发所有设备配置。")
            for name, field in app.param_inputs.items():
                app.set_param(name, field.text(), delay_flag=True)
            if hasattr(app, "device_param_buttons"):
                for button in app.device_param_buttons.values():
                    button.click()
            if hasattr(app, "config_sent_signal"):
                app.config_sent_signal.emit(True)
            logging.info("工作流初始化设备节点：设备配置下发完成。")
    except Exception as exc:
        logging.error(f"工作流初始化设备节点：设备配置下发失败: {exc}")
        return {
            "connected": False,
            "message": f"设备配置下发失败: {exc}",
            "device_config": {},
            "components": {"lockin": False, "laser": False, "microwave": False, "memory": False},
        }

    params = node.params
    device_config = {
        "lockin": {
            "lia_time_constant": params.get("LIA时间常数", "100ms"),
            "lia_sampling_rate": params.get("LIA采样率", "1000Hz"),
            "modulation_freq1": params.get("调制频率1", "1kHz"),
            "modulation_freq2": params.get("调制频率2", "10kHz"),
            "square_wave_phase1": params.get("方波调制相位1", "0°"),
            "square_wave_phase2": params.get("方波调制相位2", "90°"),
            "square_wave_phase3": params.get("方波调制相位3", "180°"),
            "square_wave_phase4": params.get("方波调制相位4", "270°"),
            "fluorescence_demod_phase1": params.get("荧光路解调相位1", "0°"),
            "fluorescence_demod_phase2": params.get("荧光路解调相位2", "90°"),
            "laser_demod_phase1": params.get("激光路解调相位1", "0°"),
            "laser_demod_phase2": params.get("激光路解调相位2", "90°"),
            "fluorescence_ad_bias": params.get("荧光路AD偏置", "0V"),
            "laser_ad_bias": params.get("激光路AD偏置", "0V"),
        },
        "laser": {
            "laser_current": params.get("激光器电流", 50.0),
        },
        "microwave": {
            "ch1_power": params.get("CH1微波功率", "0dBm"),
            "ch2_power": params.get("CH2微波功率", "0dBm"),
            "ch1_frequency": params.get("CH1微波频率", "5.1GHz"),
            "ch2_frequency": params.get("CH2微波频率", "5.2GHz"),
            "ch1_modulation_depth": params.get("CH1微波调制深度", 50.0),
            "ch2_modulation_depth": params.get("CH2微波调制深度", 50.0),
            "iir_coefficient": params.get("IIR系数", 1.0),
            "daq_coefficient": params.get("DAQ系数", 1.0),
            "dc_daq_coefficient": params.get("直流DAQ系数", 1.0),
            "ch1_iir_coefficient": params.get("通道1-IIR电压转磁场系数", 1.0),
            "ch2_iir_coefficient": params.get("通道2-IIR电压转磁场系数", 1.0),
            "dual_mode_coefficient": params.get("双微波模式IIR电压转磁场系数", 1.0),
            "ch1_zero_position": params.get("微波通道1一阶微分谱零点位置", 0.5),
            "ch2_zero_position": params.get("微波通道2一阶微分谱零点位置", 0.5),
            "gyromagnetic_ratio": params.get("等效旋磁比", 28.0),
            "ch1_slope": params.get("微波通道1一阶微分谱斜率", 1.0),
            "ch2_slope": params.get("微波通道2一阶微分谱斜率", 1.0),
            "dc_daq_sampling_rate": params.get("直流DAQ采样率", "1000Hz"),
            "daq_decimation_rate": params.get("DAQ运算抽取率", 10),
            "daq_acquisition_time": params.get("DAQ数据采集时间", 1.0),
            "iir_acquisition_time": params.get("IIR数据采集时间", 1.0),
            "modulation_depth_coefficient": params.get("微波调制深度系数", 1.0),
            "motor_speed": params.get("超声电机转速", 1000),
            "motor_direction": params.get("超声电机转动方向", "0"),
        },
        "memory": {
            "nonlinear_correction_time": params.get("非线性区自动校正时间", 60.0),
            "ch1_warning_voltage": params.get("IIR通道1非线性区预警电压阈值", 2.5),
            "ch2_warning_voltage": params.get("IIR通道2非线性区预警电压阈值", 2.5),
            "pid_ch1_p": params.get("锁相PID通道1-P参数", 1.0),
            "pid_ch1_i": params.get("锁相PID通道1-I参数", 0.1),
            "pid_ch1_d": params.get("锁相PID通道1-D参数", 0.01),
            "pid_ch2_p": params.get("锁相PID通道2-P参数", 1.0),
            "pid_ch2_i": params.get("锁相PID通道2-I参数", 0.1),
            "pid_laser_d": params.get("锁相PID-激光通道-D参数", 0.01),
            "pid_laser_t": params.get("锁相PID-激光通道-T参数", 0.1),
            "pid_decimation_rate": params.get("PID运算抽取率", 10),
            "pid_readback_rate": params.get("PID读回抽取率", 10),
            "nonlinear_reset_ratio": params.get("非线性区重设比例", 0.9),
            "dual_microwave_gain": params.get("双微波磁场增益系数", 1.0),
        },
    }

    return {
        "connected": True,
        "message": "设备初始化配置完成",
        "device_config": device_config,
        "components": {"lockin": True, "laser": True, "microwave": True, "memory": True},
    }


def register_device_init_nodes(registry: NodeRegistry):
    lockin_params = [
        _make_param("锁相放大器", "LIA时间常数", "float", "0.1s", "0.0-10.0", minimum=0, maximum=10, step=0.1, unit="s"),
        _make_param("锁相放大器", "LIA采样率", "float", "50.0Hz", "1-100000", minimum=1, maximum=100000, step=1, unit="Hz"),
        _make_param("锁相放大器", "调制频率1", "float", "11373.976Hz", "0.0-1000000.0", minimum=0, maximum=1000000, step=1, unit="Hz"),
        _make_param("锁相放大器", "调制频率2", "float", "11373.976Hz", "0.0-1000000.0", minimum=0, maximum=1000000, step=1, unit="Hz"),
        _make_param("锁相放大器", "方波调制相位1", "float", "0.0°", "0.0-360.0", minimum=0, maximum=360, step=1, unit="deg"),
        _make_param("锁相放大器", "方波调制相位2", "float", "0.0°", "0.0-360.0", minimum=0, maximum=360, step=1, unit="deg"),
        _make_param("锁相放大器", "方波调制相位3", "float", "0.0°", "0.0-360.0", minimum=0, maximum=360, step=1, unit="deg"),
        _make_param("锁相放大器", "方波调制相位4", "float", "0.0°", "0.0-360.0", minimum=0, maximum=360, step=1, unit="deg"),
        _make_param("锁相放大器", "荧光路解调相位1", "float", "158.0°", "0.0-360.0", minimum=0, maximum=360, step=1, unit="deg"),
        _make_param("锁相放大器", "荧光路解调相位2", "float", "158.0°", "0.0-360.0", minimum=0, maximum=360, step=1, unit="deg"),
        _make_param("锁相放大器", "激光路解调相位1", "float", "158.0°", "0.0-360.0", minimum=0, maximum=360, step=1, unit="deg"),
        _make_param("锁相放大器", "激光路解调相位2", "float", "158.0°", "0.0-360.0", minimum=0, maximum=360, step=1, unit="deg"),
        _make_param("锁相放大器", "荧光路AD偏置", "int", "0", "-32768-32767", minimum=-32768, maximum=32767, step=1),
        _make_param("锁相放大器", "激光路AD偏置", "int", "0", "-32768-32767", minimum=-32768, maximum=32767, step=1),
    ]

    laser_params = [
        _make_param("激光器", "激光器电流", "float", "0.8A", "0.0-2.0", minimum=0, maximum=2, step=0.1, unit="A"),
    ]

    microwave_params = [
        _make_param("微波源", "CH1微波功率", "int", "16dBm", "0-30", minimum=0, maximum=30, step=1, unit="dBm"),
        _make_param("微波源", "CH2微波功率", "int", "0dBm", "0-30", minimum=0, maximum=30, step=1, unit="dBm"),
        _make_param("微波源", "CH1微波频率", "int", "2907000000Hz", "2600000000-3100000000", minimum=2600000000, maximum=3100000000, step=1000000, unit="Hz"),
        _make_param("微波源", "CH2微波频率", "int", "2600000000Hz", "2600000000-3100000000", minimum=2600000000, maximum=3100000000, step=1000000, unit="Hz"),
        _make_param("微波源", "CH1微波调制深度", "int", "15", "0-30", minimum=0, maximum=30, step=1),
        _make_param("微波源", "CH2微波调制深度", "int", "15", "0-30", minimum=0, maximum=30, step=1),
        _make_param("微波源", "微波调制深度系数", "float", "0.5MHz", "0.0-100", minimum=0, maximum=100, step=0.1, unit="MHz"),
        _make_param("微波源", "IIR系数", "float", "1.0V", "0.0-100.0", minimum=0, maximum=100, step=0.1, unit="V"),
        _make_param("微波源", "DAQ系数", "float", "1.0V", "0.0-100.0", minimum=0, maximum=100, step=0.1, unit="V"),
        _make_param("微波源", "直流DAQ系数", "float", "1.0V", "0.0-100.0", minimum=0, maximum=100, step=0.1, unit="V"),
        _make_param("微波源", "通道1-IIR电压转磁场系数", "float", "2.100754e-06T/V", "0-1e20", minimum=0, maximum=1e-5, step=1e-8, unit="T/V"),
        _make_param("微波源", "通道2-IIR电压转磁场系数", "float", "2.100754e-06T/V", "0-1e20", minimum=0, maximum=1e-5, step=1e-8, unit="T/V"),
        _make_param("微波源", "双微波模式IIR电压转磁场系数", "float", "2.100754e-06T/V", "0-1e20", minimum=0, maximum=1e-5, step=1e-8, unit="T/V"),
        _make_param("微波源", "微波通道1一阶微分谱零点位置", "float", "2899011184.6533003Hz", "2600000000-3100000000", minimum=2600000000, maximum=3100000000, step=1, unit="Hz"),
        _make_param("微波源", "微波通道2一阶微分谱零点位置", "float", "2899421000.0Hz", "2600000000-3100000000", minimum=2600000000, maximum=3100000000, step=1, unit="Hz"),
        _make_param("微波源", "等效旋磁比", "float", "3.5495e13Hz/T", "0-1e16", minimum=1e10, maximum=1e16, step=1e10, unit="Hz/T"),
        _make_param("微波源", "微波通道1一阶微分谱斜率", "float", "3.437e-08V/Hz", "-1-1", minimum=-1, maximum=1, step=1e-9, unit="V/Hz"),
        _make_param("微波源", "微波通道2一阶微分谱斜率", "float", "3.437e-08V/Hz", "-1-1", minimum=-1, maximum=1, step=1e-9, unit="V/Hz"),
        _make_param("微波源", "直流DAQ采样率", "int", "125Hz", "125-125", minimum=125, maximum=125, step=1, unit="Hz"),
        _make_param("微波源", "DAQ运算抽取率", "int", "2499", "0-25000000", minimum=0, maximum=25000000, step=1),
        _make_param("微波源", "DAQ数据采集时间", "float", "1.0s", "0-1000", minimum=0, maximum=1000, step=0.1, unit="s"),
        _make_param("微波源", "IIR数据采集时间", "float", "1.0s", "0-1000", minimum=0, maximum=1000, step=0.1, unit="s"),
        _make_param("微波源", "超声电机转速", "int", "100°/s", "50-240", minimum=50, maximum=240, step=1, unit="°/s"),
        _make_param("微波源", "超声电机转动方向", "select", "2", "0-2", options=["0", "1", "2"]),
    ]

    memory_params = [
        _make_param("设备内存", "非线性区自动校正时间", "float", "120.0s", "30-3600", minimum=30, maximum=3600, step=1, unit="s"),
        _make_param("设备内存", "IIR通道1非线性区预警电压阈值", "float", "0.03V", "0-1", minimum=0, maximum=1, step=0.01, unit="V"),
        _make_param("设备内存", "IIR通道2非线性区预警电压阈值", "float", "0.03V", "0-1", minimum=0, maximum=1, step=0.01, unit="V"),
        _make_param("设备内存", "锁相PID通道1-P参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID通道1-I参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID通道1-D参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID通道1-T参数", "float", "1", "0-1000", minimum=0, maximum=1000, step=1),
        _make_param("设备内存", "锁相PID通道2-P参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID通道2-I参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID通道2-D参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID通道2-T参数", "float", "1", "0-1000", minimum=0, maximum=1000, step=1),
        _make_param("设备内存", "锁相PID-激光通道-P参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID-激光通道-I参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID-激光通道-D参数", "float", "-0.001", "-1-0", minimum=-1, maximum=0, step=0.001),
        _make_param("设备内存", "锁相PID-激光通道-T参数", "float", "1", "0-1000", minimum=0, maximum=1000, step=1),
        _make_param("设备内存", "PID运算抽取率", "int", "499999", "0-25000000", minimum=0, maximum=25000000, step=1),
        _make_param("设备内存", "PID读回抽取率", "int", "0", "0-25000000", minimum=0, maximum=25000000, step=1),
        _make_param("设备内存", "非线性区重设比例", "float", "1", "0.1-1", minimum=0.5, maximum=2.0, step=0.1),
        _make_param("设备内存", "双微波磁场增益系数", "float", "1.5", "0-10", minimum=0.1, maximum=3.0, step=0.1),
    ]

    all_params = lockin_params + laser_params + microwave_params + memory_params
    default_params = {}
    for param in all_params:
        if param.editor == "float":
            default_params[param.key] = _extract_numeric(param.current_value, 0.0)
        elif param.editor == "int":
            default_params[param.key] = int(_extract_numeric(param.current_value, 0))
        elif param.options:
            default_params[param.key] = param.current_value if param.current_value else param.options[0]
        else:
            default_params[param.key] = param.current_value

    registry.register(
        NodeSpec(
            node_type="device.connect",
            title="初始化设备节点",
            category="设备",
            default_params=default_params,
            input_ports=[NodePortSpec("device_config", "dict")],
            output_ports=[NodePortSpec("device_out", "device")],
            param_specs=all_params,
            executor=_exec_device_connect,
        )
    )
