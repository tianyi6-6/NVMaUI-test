"""
程序介绍：通过串口通讯，可发送和接收电机指令，具体指令见电机文档
control_motor(100, 90)函数参数分别为速度（100左右）和角度【0，360）
注：这里角度并不是转动角度，而是和0°的相对位置。
"""
import struct

import serial
import time

class USM20:
    def __init__(self, port=None, baudrate=19200, timeout=1):
        """
        超声电机初始化
        设备识别码：DNVCS-Motor-usm20-0001
        Motor_usm20
        :param port: 端口号 str None None "COM1"
        :param baudrate: 波特率 int between [1,1E7] 19200
        :param timeout: 访问延时 float between [0,100] 1
        """
        if (not port):
            port = self.find_motor()
        try:
            self.Serial = serial.Serial(port, baudrate=baudrate, bytesize=8, parity='N', stopbits=1, timeout=timeout)
        except PermissionError:
            print("超声电机串口已被占用")
        self.status1_dic = {b'\x01' : "运行中", b'\x02' : "定位成功", b'\x03' : "停车成功", b'\xFF' : "故障"}
        self.status2_dic = {b'\x00' : "正常", b'\x11' : "热敏电阻短路", b'\x12' : "热敏电阻开路"}

    def find_motor(self):
        from serial.tools import list_ports
        ports = list_ports.comports()
        for port in ports:
            if "USB VID:PID=0403:6001 SER=B001" in port.hwid:
                return port.device
        return None

    # 定义校验位计算函数
    def calculate_checksum(self, data):
        checksum = 0
        for byte in data[2:10]:
            checksum ^= byte
        return checksum

    # 定义发送命令的函数
    def send_command(self, frame):
        self.Serial.write(frame)
        print(f"Sent command frame: {frame.hex()}")

    # 定义接收响应的函数
    def receive_response(self):
        """
        电机遥测
        设备识别码：DNVCS-Motor-usm20-0003
        Motor_usm20
        """
        self.Serial.write(b'\xEB\x90\x33\x00\x00\x00\x00\x00\x00\x00\x33')  # 发送遥测指令
        response = self.Serial.read(11)
        if len(response) == 11:
            print(f"Received response frame: {response.hex()}")
            if(response[:3] == b'\xEB\x90\x55' and self.calculate_checksum(response[:10]) == response[10]):
                angle_bytes = response[3:6]
                angle = ((angle_bytes[0] << 16) | (angle_bytes[1] << 8) | angle_bytes[2]) / 1000
                speed = struct.unpack(">H", response[6:8])[0] / 100
                status1 = self.status1_dic[response[8]]
                status2 = self.status2_dic[response[9]]
                print(f"电机各项状态： \n当前角度 {angle}、 当前速度 {speed}、 运行状态 {status1}、 线路状态 {status2}")
            return response
        else:
            print("Incomplete response received.")
            return None
    # 定义控制电机的函数
    def control_motor(self, speed, angle, direction):
        """
        控制电机
        设备识别码：DNVCS-Motor-usm20-0002
        Motor_usm20
        :param speed: 速度 int in [0,255] 0
        :param angle: 度数 int between [0,360] 0
        :param direction: 正反转，0为反向，其余正向 int in [0,1] 1
        """
        header = b'\xEB\x90'
        cmd = b'\x11'  # 旋转命令
        angle = angle*1000  # 角度倍数为1000
        angle_high = (angle >> 16) & 0xFF
        angle_mid = (angle >> 8) & 0xFF
        angle_low = angle & 0xFF  # 文档中角度为3个字节
        speed_high = (speed >> 8) & 0xFF
        speed_low = speed & 0xFF  # 文档中速度为2个字节
        if(direction):
            direction = b'\x55'  # 0x55正转，0xAA反转
        else:
            direction = b'\xAA'
        nine = b'\x00'  # 9位字节为0x00
        # 字节相加
        frame = header + cmd + bytes([angle_high, angle_mid, angle_low]) + bytes([speed_high, speed_low]) + direction + nine
        # frame = b'\xEB\x90\x11\x02\xBF\x20\x00\x78\x55\x00' #文档的示例指令
        # 校验位计算
        checksum = self.calculate_checksum(frame)
        # 加上校验位
        frame += bytes([checksum])
        # 发送命令
        # print(f"Sent command frame: {frame.hex()}")
        self.send_command(frame)
        time.sleep(1)  # 等待一段时间以便接收响应
        return self.receive_response()

def main():
    motor = USM20()
    # motor.control_motor(100, 90)

if __name__ == "__main__":
    main()