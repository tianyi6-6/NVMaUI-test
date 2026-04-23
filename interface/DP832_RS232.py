# coding=UTF-8
import serial
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
    def __init__(self, port, baudrate=9600, debug=False):
        """
        初始化并连接到 DP832 电源设备。
        :param port: 串口名称，如 "COM1" 或 "/dev/ttyUSB0"
        :param baudrate: 波特率，默认9600
        :param debug: 是否开启调试信息输出
        """
        self.debug = debug
        self.device = None
        self.port = port
        self.baudrate = baudrate
        self._connect()

    def _connect(self):
        try:
            self.device = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0
            )
            self.device.flushInput()
            self.device.flushOutput()
            idn = self.query("*IDN?")
            print(f"[INFO] Connected to device: {idn}")
        except Exception:
            traceback.print_exc()
            raise RuntimeError("Failed to open serial device.")

    def query(self, cmd):
        if self.debug:
            print(f"[QUERY] {cmd}")
        self.device.write((cmd + '\n').encode('ascii'))
        response = self.device.readline().decode('ascii').strip()
        if self.debug:
            print(f"[RESPONSE] {response}")
        return response

    def write(self, cmd):
        if self.debug:
            print(f"[WRITE] {cmd}")
        self.device.write((cmd + '\n').encode('ascii'))

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

    def close(self):
        if self.device:
            self.device.close()

class UniTUDP3320Controller:
    def __init__(self, port: str, baudrate: int = 9600, debug: bool = False):
        """
        初始化并连接到 UNI-T UDP3320 电源设备。
        :param port: 串口名称，如 "COM1" 或 "/dev/ttyUSB0"
        :param baudrate: 波特率，默认9600
        :param debug: 是否输出调试信息
        """
        self.port = port
        self.baudrate = baudrate
        self.debug = debug
        self.device = None
        self._connect()

    def _connect(self):
        try:
            self.device = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0
            )
            self.device.flushInput()
            self.device.flushOutput()
            idn = self.query("*IDN?")
            print(f"[INFO] Connected to device: {idn}")
        except Exception:
            traceback.print_exc()
            raise RuntimeError("Failed to connect to UDP3320.")

    def write(self, cmd: str):
        if self.debug:
            print(f"[WRITE] {cmd}")
        self.device.write((cmd + '\n').encode('ascii'))

    def query(self, cmd: str) -> str:
        if self.debug:
            print(f"[QUERY] {cmd}")
        self.device.write((cmd + '\n').encode('ascii'))
        response = self.device.readline().decode('ascii').strip()
        if self.debug:
            print(f"[RESPONSE] {response}")
        return response

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
    import serial.tools.list_ports
    
    # 列出所有可用的串口
    ports = serial.tools.list_ports.comports()
    print('Available serial ports:')
    for port in ports:
        print(f'  {port.device}: {port.description}')
    
    # 示例用法（需要根据实际串口名称修改）
    power = RigolDP832Controller(port='COM23', baudrate=9600, debug=True)

    power.set_voltage(1, 5.0)

    # 设置通道1电流限制为1A
    power.set_current(1, 1.0)

    # 开启通道1输出
    power.set_output(1, True)

    for i in range(3):
        print(f'[Dev1] Voltage:{power.get_voltage(i + 1)}')