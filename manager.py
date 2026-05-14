import enum
from PySide6.QtCore import QTimer, Qt,QDateTime, QObject, Signal, QThread
import logging

class DevState(enum.Enum):
    # 半双工工作模式
    INIT = enum.auto() # 程序初次启动
    OFFLINE = enum.auto() # USB设备未连接
    IDLE = enum.auto() # USB设备成功连接，处于未工作状态
    MONITOR = enum.auto() # 正在执行隔一段时间的监视模式，在其他状态的间隙中进行，优先级较低
    EXP_RUNNING = enum.auto() # 正在执行封装好的实验，设备被占用，此时
    DAQ_RUNNING = enum.auto() # 正在进行DAQ模式采集，设备被占用
    IIR_RUNNING = enum.auto() # 正在进行IIR模式采集，设备被占用
    PID_RUNNING = enum.auto() # 正在进行PID模式采集，设备被占用
    DC_RUNNING = enum.auto() # 正在进行DC模式采集，设备被占用
    CONFIGURING = enum.auto() # 正在下发设备配置指令，设备被占用
    ERROR = enum.auto() # 实验出现故障，进入ERROR状态。
    STOPPING = enum.auto() # 正在终止所有实验，即将但尚未转入IDLE状态。

class DevStateManager(QObject):
    state_changed = Signal(DevState)
    def __init__(self):
        super().__init__()
        self._state = DevState.INIT

    def set_state(self, new_state: DevState):
        if self._state != new_state:
            logging.debug(f"系统切换状态：从 [{self._state.name}] 进入 [{new_state.name}]。")
            self._state = new_state
            self.state_changed.emit(new_state)

    def current_state(self):
        return self._state