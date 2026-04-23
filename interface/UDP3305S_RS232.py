# coding=UTF-8
import serial
import traceback
import time

class UniTUDP3305SController:
    def __init__(self, port, baudrate=9600, debug=False):
        """
        初始化并连接到 UDP3305S 电源设备（RS232通信）。
        :param port: 串口号，例如 "COM1" 或 "/dev/ttyUSB0"
        :param baudrate: 波特率，默认9600
        :param debug: 是否输出调试信息
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
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=1.0
            )
            self.device.flushInput()
            self.device.flushOutput()
            idn = self.query("*IDN?")
            print(f"[INFO] Connected to device: {idn}")
        except Exception:
            traceback.print_exc()
            raise RuntimeError("Failed to connect to UDP3305S.")

    def query(self, cmd):
        """发送查询命令并返回响应"""
        if self.debug:
            print(f"[QUERY] {cmd}")
        
        # 发送命令
        self.device.write((cmd + '\n').encode('ascii'))
        time.sleep(0.1)  # 等待设备响应
        
        # 读取响应
        response = self.device.readline().decode('ascii').strip()
        if self.debug:
            print(f"[RESPONSE] {response}")
        return response

    def write(self, cmd):
        """发送命令（不等待响应）"""
        if self.debug:
            print(f"[WRITE] {cmd}")
        self.device.write((cmd + '\n').encode('ascii'))
        time.sleep(0.05)  # 短暂延时确保命令被处理

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
        if self.device and self.device.is_open:
            self.device.close()

    def __del__(self):
        """析构函数，确保连接被关闭"""
        self.close()

if __name__ == '__main__':
    # 创建控制器实例（使用RS232通信）
    power = UniTUDP3305SController("COM6", baudrate=9600, debug=True)

    # 设置通道1电压为5V
    power.set_voltage(1, 5.0)

    # 设置通道1电流限制为1A
    power.set_current(1, 1.0)

    # 开启通道1输出
    power.set_output(1, False)

    # 读取通道1电压和电流
    while True:
        try:
            voltage = power.get_voltage(1)
            current = power.get_current(1)
            print(f"Voltage: {voltage}V, Current: {current}A")
        except Exception as e:
            print(f"Error: {e}")
            break
        time.sleep(0.1)

    # 关闭连接
    power.close()