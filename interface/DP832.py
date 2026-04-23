# coding=UTF-8
import pyvisa
import traceback
import time

class SimuDCPowerController:
    def __init__(self, *args, **kwargs):
        self.channels = 3
        self.max_current = [3.0, 3.0, 3.0]
        self.max_voltage = [30.0, 30.0, 30.0]
        self.voltage = [24.0, 24.0, 24.0]
        self.current = [1.0, 1.0, 1.0]
        self.state_on = [False, False, False]

    def _connect(self):
        pass

    def set_voltage(self, ch, volt):
        self.voltage[ch - 1] = volt

    def set_max_current(self, ch, curr):
        self.max_current[ch - 1] = curr

    def get_voltage(self, ch):
        return self.voltage[ch - 1]

    def set_output(self, ch, flag):
        self.state_on[ch - 1] = flag
        if flag:
            self.current[ch - 1] = 1.0

    def get_output(self, ch):
        return self.state_on[ch - 1]

    def get_current(self, ch):
        return self.current[ch - 1]

class RigolDP832Controller:
    def __init__(self, resource_name, debug=False):
        """
        初始化并连接到 DP832 电源设备。
        :param resource_name: VISA 格式的设备名，如 "USB0::0x1AB1::0x0E11::DP8E214200280::INSTR"
        :param debug: 是否开启调试信息输出
        """
        self.debug = debug
        self.device = None
        self.resource_name = resource_name
        self.rm = pyvisa.ResourceManager()
        self._connect()

    def _connect(self):
        try:
            self.device = self.rm.open_resource(self.resource_name)
            self.device.timeout = 1000
            self.device.clear()
            idn = self.query("*IDN?")
            print(f"[INFO] Connected to device: {idn}")
        except Exception:
            traceback.print_exc()
            raise RuntimeError("Failed to open VISA device.")

    def query(self, cmd):
        if self.debug:
            print(f"[QUERY] {cmd}")
        return self.device.query(cmd)

    def write(self, cmd):
        if self.debug:
            print(f"[WRITE] {cmd}")
        self.device.write(cmd)

    def do_command(self, command, hide_params=False):
        if hide_params:
            header, _ = command.split(" ", 1)
            self.write(header)
        else:
            self.write(command)

    # ===========================
    # Public API
    # ===========================

    def set_voltage(self, ch, volt):
        self.write(f":INST CH{ch}")
        self.write(f":VOLT {volt:.4f}")

    def get_voltage(self, ch):
        return float(self.query(f":MEAS:VOLT? CH{ch}"))

    def set_current(self, ch, curr):
        self.write(f":INST CH{ch}")
        self.write(f":CURR {curr:.4f}")

    def get_current(self, ch):
        return float(self.query(f":MEAS:CURR? CH{ch}"))

    def set_output(self, ch, flag):
        self.write(f":INST CH{ch}")
        self.write(f":OUTP CH{ch},{'ON' if flag else 'OFF'}")

class UniTUDP3320Controller:
    def __init__(self, resource_name: str, debug: bool = False):
        """
        初始化并连接到 UNI-T UDP3320 电源设备。
        :param resource_name: VISA 资源名，例如 "USB0::0xXXXX::0xYYYY::SERIAL::INSTR"
        :param debug: 是否输出调试信息
        """
        self.resource_name = resource_name
        self.debug = debug
        self.device = None
        self.rm = pyvisa.ResourceManager()
        self._connect()

    def _connect(self):
        try:
            self.device = self.rm.open_resource(self.resource_name)
            self.device.timeout = 1000
            self.device.clear()
            idn = self.query("*IDN?")
            print(f"[INFO] Connected to device: {idn}")
        except Exception:
            traceback.print_exc()
            raise RuntimeError("Failed to connect to UDP3320.")

    def write(self, cmd: str):
        if self.debug:
            print(f"[WRITE] {cmd}")
        self.device.write(cmd)

    def query(self, cmd: str) -> str:
        if self.debug:
            print(f"[QUERY] {cmd}")
        return self.device.query(cmd).strip()

    def set_voltage(self, volt: float):
        """设置输出电压（单位：V）"""
        self.write(f"VOLT {volt:.3f}")

    def set_current(self, curr: float):
        """设置输出电流限制（单位：A）"""
        self.write(f"CURR {curr:.3f}")

    def get_voltage(self) -> float:
        """读取实际输出电压"""
        return float(self.query("MEAS:VOLT?"))

    def get_current(self) -> float:
        """读取实际输出电流"""
        return float(self.query("MEAS:CURR?"))

    def output_on(self):
        self.write("OUTP ON")

    def output_off(self):
        self.write("OUTP OFF")

    def set_output(self, flag: bool):
        self.write("OUTP ON" if flag else "OUTP OFF")

    def close(self):
        if self.device:
            self.device.close()

if __name__ == '__main__':
    # print(pyvisa.log_to_screen())  # 显示详细日志
    rm = pyvisa.ResourceManager()
    print('all devices:', rm.list_resources())
    # exit()
    # 'USB0::0x1AB1::0x0E11::DP8C263102708::INSTR'
    # 'USB0::0x0483::0x5740::ADP3524510002::INSTR'
    # 'USB0::0x1AB1::0x0E11::DP8C263202820::INSTR'

    dev1 = RigolDP832Controller(resource_name='USB0::0x1AB1::0x0E11::DP8C263202813::INSTR')

    dev1.set_voltage(1, 5)
    dev1.set_current(1, 3)

    dev1.set_output(1, False)

    time.sleep(2)

    # dev1 = RigolDP832Controller(resource_name='USB0::0x1AB1::0x0E11::DP8C263202820::INSTR')
    for i in range(3):
        print(f'[Dev1] State:{dev1.get_voltage(i + 1)}')