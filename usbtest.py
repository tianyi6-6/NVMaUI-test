import ctypes
from ctypes import (
    c_int, c_void_p, c_ubyte, c_ushort, c_uint, c_char_p, POINTER,
    Structure, byref, create_string_buffer, cast
)
import platform
import numpy as np
import time

# 定义常量
LIBUSB_SUCCESS = 0
LIBUSB_ERROR_TIMEOUT = -7
LIBUSB_REQUEST_TYPE_STANDARD = (0x00 << 5)
LIBUSB_RECIPIENT_DEVICE = 0x00

# 定义结构体
class libusb_device_descriptor(Structure):
    _fields_ = [
        ("bLength", c_ubyte),
        ("bDescriptorType", c_ubyte),
        ("bcdUSB", c_ushort),
        ("bDeviceClass", c_ubyte),
        ("bDeviceSubClass", c_ubyte),
        ("bDeviceProtocol", c_ubyte),
        ("bMaxPacketSize0", c_ubyte),
        ("idVendor", c_ushort),
        ("idProduct", c_ushort),
        ("bcdDevice", c_ushort),
        ("iManufacturer", c_ubyte),
        ("iProduct", c_ubyte),
        ("iSerialNumber", c_ubyte),
        ("bNumConfigurations", c_ubyte),
    ]

def num_to_bytes(num, bytenum, high_head=True):
    if high_head:
        return np.array([num], dtype='>u8').tobytes()[-bytenum:]
    else:
        return np.array([num], dtype='<u8').tobytes()[:bytenum]

def bytes_to_num(bytes_):
    return int.from_bytes(bytes_, byteorder='big')

class LibUSBError(Exception):
    """自定义异常类，封装 libusb 错误码"""
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code

class USBController:
    def __init__(self, libusb_path: str):
        # 加载 libusb-1.0 动态库（Linux 路径，Windows 需调整为 libusb-1.0.dll）
        system = platform.system()
        if system == 'Windows':
            libusb_path = libusb_path.replace('.so', '.dll')
        else:
            libusb_path = libusb_path.replace('.dll', '.so')
        self.libusb = ctypes.CDLL(libusb_path)

        self.ctx = c_void_p()  # libusb_context
        self._init_libusb()
        self.read_endpoint = 0x86 # 上位机←设备
        self.write_endpoint = 0x02 # 上位机→设备

        self.bulk_buffer_packet_size = 512 # bulk传输模式的单个包size

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.close_device()

    def _init_libusb(self):
        # 初始化 libusb
        ret = self.libusb.libusb_init(ctypes.byref(self.ctx))
        if ret != LIBUSB_SUCCESS:
            raise LibUSBError("Failed to initialize libusb", ret)

    def get_device_list(self):
        """枚举所有 USB 设备，返回设备信息列表"""
        libusb_device = ctypes.c_void_p
        libusb_device_p = ctypes.POINTER(libusb_device)
        devices = libusb_device_p()
        count = self.libusb.libusb_get_device_list(self.ctx, ctypes.byref(devices))

        if count < 0:
            raise LibUSBError("Failed to get device list", count)

        device_list = []
        for i in range(count):
            dev = devices[i]
            desc = libusb_device_descriptor()
            ret = self.libusb.libusb_get_device_descriptor(dev, byref(desc))
            if ret != LIBUSB_SUCCESS:
                continue  # 忽略无法获取描述符的设备

            bus = self.libusb.libusb_get_bus_number(dev)
            address = self.libusb.libusb_get_device_address(dev)
            device_list.append({
                "bus": bus,
                "address": address,
                "vendor_id": desc.idVendor,
                "product_id": desc.idProduct,
            })

        self.libusb.libusb_free_device_list(devices, 1)  # 释放设备列表
        return device_list

    def open_device(self, vendor_id, product_id):
        """通过 VID/PID 打开设备，返回设备句柄"""
        handle = c_void_p()
        dev_handle = self.libusb.libusb_open_device_with_vid_pid(
            self.ctx, vendor_id, product_id
        )
        if not dev_handle:
            raise LibUSBError("Device not found")
        self.handle = dev_handle
        return dev_handle

    def close_device(self):
        """关闭设备"""
        if self.handle:
            self.libusb.libusb_close(self.handle)
            self.handle = None

    def control_transfer(self, bmRequestType, bRequest, wValue, wIndex, data, timeout=1000):
        """
        发送控制传输请求
        :param bmRequestType: 请求类型
        :param bRequest: 请求码
        :param wValue: 值
        :param wIndex: 索引
        :param data: 要发送/接收的数据（bytes 或 bytearray）
        :param timeout: 超时时间（毫秒）
        :return: 实际传输的字节数
        """
        buffer = create_string_buffer(data) if isinstance(data, (bytes, bytearray)) else None
        buffer_ptr = cast(buffer, c_char_p) if buffer else None
        length = len(data) if buffer else 0

        ret = self.libusb.libusb_control_transfer(
            self.handle,
            bmRequestType,
            bRequest,
            wValue,
            wIndex,
            buffer_ptr,
            length,
            timeout
        )
        if ret < 0:
            raise LibUSBError("Control transfer failed", ret)
        return ret

    def bulk_transfer(self, endpoint, data, timeout=1000):
        """
        批量传输（同步）
        :param endpoint: 端点地址（0x81 等）
        :param data: 数据缓冲区（bytes/bytearray 用于发送，预分配用于接收）
        :param timeout: 超时时间（毫秒）
        :return: (实际传输字节数, 接收的数据)
        """
        length = len(data)
        transferred = c_int()

        # 创建与数据长度相等的缓冲区
        buffer = create_string_buffer(length)

        print(f'信号传输endpoint:{endpoint}')
        # 判断端点类型：IN（读） or OUT（写）
        if endpoint & 0x80 == 0:  # 输出端点，拷贝数据
            print(f'准备输出数据:{data}')
            # 写入端点，准备发送数据内容
            if isinstance(data, (bytes, bytearray)):
                buffer.raw = data
            else:
                raise TypeError("发送数据必须是 bytes 或 bytearray")

        ret = self.libusb.libusb_bulk_transfer(
            self.handle,
            endpoint,
            cast(buffer, c_char_p),
            length,
            byref(transferred),
            timeout
        )
        if ret != LIBUSB_SUCCESS:
            raise LibUSBError("Bulk transfer failed", ret)

        # 如果是输入传输，返回接收到的数据
        return transferred.value, buffer.raw[:transferred.value]

    def send_command(self, command_bytes: bytes):
        self.bulk_transfer(self.write_endpoint, command_bytes)

    def read_response(self, size=512):
        return self.bulk_transfer(self.read_endpoint, bytearray(size))

    def read_data(self, length: int, timeout_sec: float = 5.0) -> bytes:
        """
        连续读取指定长度的 USB 数据，具备高优先级、超时保护、大缓存设计。

        :param length: 期望总读取的字节数（如 1MB）
        :param timeout_sec: 若连续 timeout_sec 秒无任何数据返回，则终止读取
        :param block_size: 每次读取的块大小（推荐与端点最大包长一致）
        :return: 实际接收到的数据（bytes）
        :raises LibUSBError: 如果遇到传输故障
        """
        buffer = bytearray()
        start_time = time.time()
        last_data_time = start_time

        while len(buffer) < length:
            now = time.time()
            # 检查超时（采集中断）
            if now - last_data_time > timeout_sec:
                print(f"[Warning] Timeout: No data received for {timeout_sec} seconds")
                break

            try:
                # 调用 bulk_transfer 尝试读取一块数据
                transferred, data = self.bulk_transfer(
                    endpoint=self.read_endpoint,
                    data=bytearray(self.bulk_buffer_packet_size),
                    timeout=500  # 每次尝试的超时时间，避免阻塞太久
                )
                if transferred > 0:
                    buffer.extend(data[:transferred])
                    last_data_time = time.time()
            except LibUSBError as e:
                if e.error_code == -7:  # Timeout，仅重试
                    continue
                else:
                    raise e  # 其他错误直接中断

        return bytes(buffer)

    def IIR_play(self, data_num):
        data = [[] for i in range(14)]

        self.send_command(b'\x00\x00') # 进入到IDLE状态
        self.send_command(b'\x00\x04')  # 进入到IIR状态

        time.sleep(0.1)
        self.send_command(num_to_bytes(data_num, 4))
        IIR_data = b''
        IIR_data += self.read_data(data_num * 80, timeout_sec=1)  # 80 bytes per frame，读取数据

        for i in range(data_num):
            for j in range(12):
                data_buf = bytes_to_num(IIR_data[80 * i + (j % 14) * 6:  80 * i + (j % 14 + 1) * 6])
                if data_buf > 2 ** 47 - 1:
                    data_buf = (data_buf - 2 ** 48.0) / 2 ** 48.0
                else:
                    data_buf = data_buf / 2 ** 48.0
                data[j].append(data_buf)

            ch1_data = bytes_to_num(IIR_data[80 * i + 72: 80 * i + 76])
            ch2_data = bytes_to_num(IIR_data[80 * i + 76: 80 * i + 80])
            if ch1_data > 2 ** 15 - 1:
                ch1_data_buf = (ch1_data - 2 ** 16.0) / 2 ** 16.0
            else:
                ch1_data_buf = ch1_data / 2 ** 16.0

            if ch2_data > 2 ** 15 - 1:
                ch2_data_buf = (ch2_data - 2 ** 16.0) / 2 ** 16.0
            else:
                ch2_data_buf = ch2_data / 2 ** 16.0
            data[12].append(ch1_data_buf)
            data[13].append(ch2_data_buf)
        return data

    def all_start(self):
        self.send_command(b'\x00\x3C')

    def all_stop(self):
        self.send_command(b'\x00\x3D')

    def error_check(self, data_num):
        # 使用前需要确保系统处于IDLE状态
        self.send_command(b'\x00\x00')
        time.sleep(.1)
        self.send_command(b'\x00\x06')
        time.sleep(.1)

        self.send_command(num_to_bytes(data_num, 4))
        DAQ_data = b''
        DAQ_data += self.read_data(int((data_num) * 2), timeout_sec=0.5)
        print(len(DAQ_data))
        data = []

        for i in range(data_num):
            data_buf = bytes_to_num(DAQ_data[2 * i: 2 * i + 2])
            data.append(data_buf)
            if data_buf != data_num - i:
                print('!!!error!!!')
        print(data)

# ================== 使用示例 ==================
if __name__ == "__main__":
    import sys
    argvs = sys.argv[1:]
    try:
        # with USBController(libusb_path="/home/pi/Program/NVMagUI/interface/Lockin/usblib/module_64/libusb-1.0.so") as usb:
        with USBController(libusb_path="D:/Software Learning/NVMagUI/interface/Lockin/usblib/module_64/libusb-1.0.dll") as usb:
            # 枚举设备
            devices = usb.get_device_list()
            print("Connected USB Devices:")
            for dev in devices:
                print(f"Bus {dev['bus']:03d}, Device {dev['address']:03d}: "
                      f"VID 0x{dev['vendor_id']:04X}, PID 0x{dev['product_id']:04X}")

            # 示例：打开特定设备（替换为实际 VID/PID）
            VID, PID = 0x04b4, 0x00f1
            usb.open_device(VID, PID)
            print("Device opened")

            usb.all_start()

            # usb.IIR_play(data_num=100)

            usb.error_check(data_num=int(argvs[0]))

            usb.close_device()
            print("Device closed")

    except LibUSBError as e:
        print(f"LibUSB Error [{e.error_code}]: {e}")
