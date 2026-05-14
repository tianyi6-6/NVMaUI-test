# coding=UTF-8
import pyvisa
import traceback

class UniTUDP3305SController:
    def __init__(self, resource_name, debug=False):
        """
        初始化并连接到 UDP3305S 电源设备。
        :param resource_name: VISA 资源名，例如 "USB0::0xXXXX::0xYYYY::SERIAL::INSTR"
        :param debug: 是否输出调试信息
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
            raise RuntimeError("Failed to connect to UDP3305S.")

    def query(self, cmd):
        if self.debug:
            print(f"[QUERY] {cmd}")
        return self.device.query(cmd).strip()

    def write(self, cmd):
        if self.debug:
            print(f"[WRITE] {cmd}")
        self.device.write(cmd)

    def set_channel(self, ch):
        """设置当前通道"""
        self.write(f":INST:NSEL {ch}")

    # ===========================
    # Public API
    # ===========================

    def set_voltage(self, ch, volt):
        """设置通道电压"""
        self.set_channel(ch)
        self.write(f":SOUR{ch}:VOLT {volt:.3f}")

    def get_voltage(self, ch):
        """读取实际输出电压"""
        return float(self.query(f":MEAS:VOLT? CH{ch}"))

    def set_current(self, ch, curr):
        """设置输出电流限制"""
        self.set_channel(ch)
        self.write(f":SOUR{ch}:CURR {curr:.3f}")

    def get_current(self, ch):
        """读取实际输出电流"""
        return float(self.query(f":MEAS:CURR? CH{ch}"))

    def set_output(self, ch, flag):
        """设置输出开关状态"""
        self.write(f":OUTP CH{ch},{'ON' if flag else 'OFF'}")

    def get_output(self, ch):
        """查询输出开关状态"""
        return self.query(f":OUTP? CH{ch}") == "ON"

    def set_ovp(self, ch, volt):
        """设置过压保护值"""
        self.set_channel(ch)
        self.write(f":SOUR{ch}:VOLT:PROT {volt:.3f}")

    def set_ovp_state(self, ch, flag):
        """设置过压保护开关"""
        self.set_channel(ch)
        self.write(f":SOUR{ch}:VOLT:PROT:STATE {'ON' if flag else 'OFF'}")

    def set_ocp(self, ch, curr):
        """设置过流保护值"""
        self.set_channel(ch)
        self.write(f":SOUR{ch}:CURR:PROT {curr:.3f}")

    def set_ocp_state(self, ch, flag):
        """设置过流保护开关"""
        self.set_channel(ch)
        self.write(f":SOUR{ch}:CURR:PROT:STATE {'ON' if flag else 'OFF'}")

    def get_cvcc_state(self, ch):
        """查询恒压/恒流状态"""
        return self.query(f":OUTP:CVCC? CH{ch}")

    def close(self):
        """关闭连接"""
        if self.device:
            self.device.close()

if __name__ == '__main__':
    # 创建控制器实例
    power = UniTUDP3305SController('USB0::0x0483::0x5740::ADP3524510002::INSTR', debug=True)

    # 设置通道1电压为5V
    power.set_voltage(1, 5.0)

    # 设置通道1电流限制为1A
    power.set_current(1, 1.0)

    # 开启通道1输出
    power.set_output(1, False)

    # 读取通道1电压和电流
    voltage = power.get_voltage(1)
    current = power.get_current(1)
    print(f"Voltage: {voltage}V, Current: {current}A")

    # 关闭连接
    power.close()