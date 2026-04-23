import serial
import logging
import time
from serial.tools import list_ports
from functools import reduce
from PySide6.QtCore import QObject, Signal

# ---------- 配置日志 ----------
# logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
# logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# ---------- 协议常量 ----------
HEADER = b'\xEB\x90'
HEADER_RECV = b'\x90\xEB'
CMD_ROTATE = b'\x11'
CMD_STATUS = b'\x33'
CMD_STOP = b'\x22'
DIR_FORWARD = b'\x55'
DIR_REVERSE = b'\xAA'
FRAME_LENGTH = 11

STATUS1_MAP = {
    0x01: "运行中",
    0x02: "定位成功",
    0x03: "停车成功",
    0xFF: "故障"
}

STATUS2_MAP = {
    0x00: "正常",
    0x11: "热敏电阻短路",
    0x12: "热敏电阻开路"
}


# ---------- 协议封装 ----------
def calculate_checksum(frame: bytes) -> int:
    return reduce(lambda x, y: x ^ y, frame[2:10], 0)

def build_rotate_command(speed: int, angle: float, direction: bool) -> bytes:
    angle_val = int(angle * 1000)
    direction_byte = DIR_FORWARD if direction else DIR_REVERSE
    frame = HEADER + CMD_ROTATE + angle_val.to_bytes(3, 'big') + speed.to_bytes(2, 'big') + direction_byte + b'\x00'
    return frame + bytes([calculate_checksum(frame)])

def build_status_query() -> bytes:
    frame = HEADER + CMD_STATUS + b'\x00' * 7
    return frame + bytes([calculate_checksum(frame)])

def build_stop_query() -> bytes:
    frame = HEADER + CMD_STOP + b'\x00' * 7
    return frame + bytes([calculate_checksum(frame)])

def parse_status_response(resp: bytes) -> dict:
    if len(resp) != FRAME_LENGTH or not resp.startswith(HEADER_RECV + b'\x55'):
        raise ValueError("返回格式错误或帧头无效")
    angle = int.from_bytes(resp[3:6], 'big') / 1000
    speed = int.from_bytes(resp[6:8], 'big') / 100
    status1 = STATUS1_MAP.get(resp[8], f"未知状态({resp[8]:#04x})")
    status2 = STATUS2_MAP.get(resp[9], f"未知状态({resp[9]:#04x})")
    return {"angle": angle, "speed": speed, "status1": status1, "status2": status2}

class Ultramotor_Backend(QObject):
    status_updated = Signal(dict)       # 更新角度、速度、状态信息
    # error_occurred = Signal(str)        # 错误信息输出
    log_message = Signal(str)           # 原始串口信息或日志打印

    def __init__(self, port=None):
        super().__init__()
        self.port = port
        self._is_connect = False
        self.current_angle = 0

    def is_connect(self):
        return self._is_connect

    def connect_motor(self):
        try:
            self.motor = USM20Motor(self.port)
            self.log_message.emit("超声电机连接成功")
            self._is_connect = True
            return True
        except Exception as e:
            self.motor = None
            # self.error_occurred.emit(f"初始化失败: {str(e)}")
            self.log_message.emit(f"超声电机初始化失败: {str(e)}")
            self._is_connect = False
            return False

    def disconnect_motor(self):
        if self.motor is not None and self.motor.conn is not None:
            self.motor.conn.close()
        self.motor = None
        self._is_connect = False
        return True

    def stop_motor(self):
        if not self.motor:
            # self.error_occurred.emit("超声电机未初始化")
            self.log_message.emit("超声电机未初始化")
            return
        try:
            self.log_message.emit(f"超声电机开始停机")
            status = self.motor.stop()
            self.status_updated.emit(status)
        except Exception as e:
            # self.error_occurred.emit(f"超声电机转动失败: {str(e)}")
            self.log_message.emit(f"超声电机停机失败: {str(e)}")

    def rotate_motor(self, speed: int, angle: float, direction: bool = True):
        if not self.motor:
            # self.error_occurred.emit("超声电机未初始化")
            self.log_message.emit("超声电机未初始化")
            return
        try:
            self.log_message.emit(f"超声电机开始转动：speed={speed}, angle={angle}, direction={'正' if direction else '反'}")
            self.motor.rotate(speed, angle, direction)
            # self.status_updated.emit(status)
        except Exception as e:
            # self.error_occurred.emit(f"超声电机转动失败: {str(e)}")
            self.log_message.emit(f"超声电机转动失败: {str(e)}")

    def is_run(self):
        if not self.motor:
            # self.error_occurred.emit("超声电机未初始化")
            self.log_message.emit("超声电机未初始化")
            return
        try:
            status = self.motor.query_status()
            self.status_updated.emit(status)
            print()
            return "运行中" == status['status1']
        except Exception as e:
            # self.error_occurred.emit(f"超声电机状态获取失败: {str(e)}")
            self.log_message.emit(f"超声电机状态获取失败: {str(e)}")
            return False

    def get_angle(self):
        if not self.motor:
            # self.error_occurred.emit("超声电机未初始化")
            self.log_message.emit("超声电机未初始化")
            return
        try:
            status = self.motor.query_status()
            self.current_angle = status['angle']
            self.status_updated.emit(status)
            return self.current_angle
        except Exception as e:
            # self.error_occurred.emit(f"超声电机状态获取失败: {str(e)}")
            self.log_message.emit(f"超声电机状态获取失败: {str(e)}")
            return 0
    def update_status(self):
        if not self.motor:
            # self.error_occurred.emit("超声电机未初始化")
            self.log_message.emit("超声电机未初始化")
            return
        try:
            status = self.motor.query_status()
            self.current_angle = status['angle']
            self.status_updated.emit(status)
        except Exception as e:
            # self.error_occurred.emit(f"超声电机状态获取失败: {str(e)}")
            self.log_message.emit(f"超声电机状态获取失败: {str(e)}")

    def shutdown(self):
        if self.motor:
            self.motor.close()
            self.motor = None
            self.log_message.emit("串口已关闭")

# ---------- 串口封装 ----------
class SerialConnection:
    def __init__(self, port: str, baudrate: int = 19200, timeout: float = 1.0):
        self.port = port
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)

    def send(self, data: bytes):
        self.ser.write(data)
        logging.debug(f">> {data.hex()}")

    def receive(self, length: int = FRAME_LENGTH) -> bytes:
        data = self.ser.read(length)
        logging.debug(f"<< {data.hex()}")
        return data

    def close(self):
        self.ser.close()


# ---------- 主控类 ----------
class USM20Motor:
    def __init__(self, port: str = None):
        if not port:
            port = self._find_motor_port()
        if not port:
            raise IOError("未找到超声电机串口")
        logging.info(f"使用串口：{port}")
        self.conn = SerialConnection(port)

    def _find_motor_port(self):
        for port in list_ports.comports():
            print(f'All Ports: HWID={port.hwid}')
            # if "VID:PID=0403:6001" in port.hwid and "B001" in port.hwid:
            if "VID:PID=0403:6001" in port.hwid:
                print(f'Find Ultra Motor!.')
                return port.device
        return None

    def rotate(self, speed: int, angle: float, direction: bool = True):
        cmd = build_rotate_command(speed, angle, direction)
        self.conn.send(cmd)
        # time.sleep(angle / speed + 0.1)
        # return self.query_status()

    def stop(self):
        cmd = build_stop_query()
        self.conn.send(cmd)

    def query_status(self):
        cmd = build_status_query()
        self.conn.send(cmd)
        resp = self.conn.receive()
        return parse_status_response(resp)

    def close(self):
        self.conn.close()


# ---------- 测试入口 ----------
if __name__ == '__main__':
    import sys
    argv = sys.argv[1:]
    motor = USM20Motor()  # 自动查找设备
    result = motor.rotate(speed=50, angle=float(argv[0]), direction=True)
    logging.info(f"状态查询：{result}")
    motor.close()
