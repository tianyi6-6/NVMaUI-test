import ctypes
from ctypes import (
    c_int, c_uint8, c_uint16, c_void_p, POINTER,
    Structure, byref, create_string_buffer, cast
)
import numpy as np

def bytes_to_num(bytes_):
    return int.from_bytes(bytes_, byteorder='big')

def num_to_bytes(num, bytenum, high_head=True):
    if high_head:
        return np.array([num], dtype='>u8').tobytes()[-bytenum:]
    else:
        return np.array([num], dtype='<u8').tobytes()[:bytenum]

class libusb_device_descriptor(Structure):
    _fields_ = [
        ("bLength", c_uint8),
        ("bDescriptorType", c_uint8),
        ("bcdUSB", c_uint16),
        ("bDeviceClass", c_uint8),
        ("bDeviceSubClass", c_uint8),
        ("bDeviceProtocol", c_uint8),
        ("bMaxPacketSize0", c_uint8),
        ("idVendor", c_uint16),
        ("idProduct", c_uint16),
        ("bcdDevice", c_uint16),
        ("iManufacturer", c_uint8),
        ("iProduct", c_uint8),
        ("iSerialNumber", c_uint8),
        ("bNumConfigurations", c_uint8),
    ]

class LibUSBError(Exception):
    """自定义异常类，封装 libusb 错误码"""
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code

LIBUSB_SUCCESS = 0

class USBDevice:
    def __init__(self, libusb_path : str):
        self.libusb = ctypes.CDLL(libusb_path)

        self.read_endpoint = 0x86  # 上位机←设备
        self.write_endpoint = 0x02  # 上位机→设备

        self.bulk_buffer_packet_size = 512

        self.vendor_id = 0x04b4
        self.product_id = 0x00f1

        # 设置函数签名
        self.libusb.libusb_init.argtypes = [POINTER(c_void_p)]
        self.libusb.libusb_get_device_list.argtypes = [c_void_p, POINTER(POINTER(c_void_p))]
        self.libusb.libusb_get_device_list.restype = ctypes.c_ssize_t
        self.libusb.libusb_get_device_descriptor.argtypes = [c_void_p, POINTER(libusb_device_descriptor)]
        self.libusb.libusb_open.argtypes = [c_void_p, POINTER(c_void_p)]
        self.libusb.libusb_open_device_with_vid_pid.argtypes = [c_void_p, c_uint16, c_uint16]
        self.libusb.libusb_open_device_with_vid_pid.restype = c_void_p
        self.libusb.libusb_bulk_transfer.argtypes = [
            c_void_p, c_uint8, c_void_p, c_int, POINTER(c_int), c_uint16
        ]
        self.libusb.libusb_close.argtypes = [c_void_p]
        self.libusb.libusb_free_device_list.argtypes = [POINTER(c_void_p), c_int]
        self.libusb.libusb_exit.argtypes = [c_void_p]

        self.ctx = c_void_p()
        self.handle = None
        if self.libusb.libusb_init(byref(self.ctx)) != LIBUSB_SUCCESS:
            raise RuntimeError("Failed to init libusb")

    def __del__(self):
        if self.handle:
            self.libusb.libusb_close(self.handle)
        if self.ctx:
            self.libusb.libusb_exit(self.ctx)

    def find_and_open(self):
        """查找并打开设备"""
        # 设备打开后，配置和 claim 接口
        devices = POINTER(c_void_p)()
        count = self.libusb.libusb_get_device_list(self.ctx, byref(devices))
        if count < 0:
            raise RuntimeError("Failed to get USB device list")

        found = False
        for i in range(count):
            dev = devices[i]
            desc = libusb_device_descriptor()
            ret = self.libusb.libusb_get_device_descriptor(dev, byref(desc))
            if ret == LIBUSB_SUCCESS and desc.idVendor == self.vendor_id and desc.idProduct == self.product_id:
                found = True
                break

        self.libusb.libusb_free_device_list(devices, 1)

        if not found:
            raise RuntimeError("Device not found")

        self.handle = self.libusb.libusb_open_device_with_vid_pid(self.ctx, self.vendor_id, self.product_id)
        if not self.handle:
            raise RuntimeError("Failed to open device")
        print(f"✅ Device opened: VID=0x{self.vendor_id:04X}, PID=0x{self.product_id:04X}")
        # 设置配置
        self.libusb.libusb_set_configuration.argtypes = [c_void_p, c_int]
        self.libusb.libusb_claim_interface.argtypes = [c_void_p, c_int]

        CONFIG_ID = 1
        INTERFACE_ID = 0
        ret = self.libusb.libusb_set_configuration(self.handle, CONFIG_ID)
        if ret != LIBUSB_SUCCESS:
            raise RuntimeError(f"Failed to set configuration: {ret}")

        # Claim 接口
        ret = self.libusb.libusb_claim_interface(self.handle, INTERFACE_ID)
        if ret != LIBUSB_SUCCESS:
            raise RuntimeError(f"Failed to claim interface: {ret}")

        print(f"✅ Configuration {CONFIG_ID} set and interface {INTERFACE_ID} claimed.")

    def bulk_transfer(self, endpoint, data: bytes, timeout=1000):
        """执行 Bulk OUT 传输"""
        transferred = c_int()
        buf = create_string_buffer(data)
        result = self.libusb.libusb_bulk_transfer(
            self.handle,
            endpoint,  # 如0x02为OUT，0x81为IN
            cast(buf, c_void_p),
            len(data),
            byref(transferred),
            timeout
        )
        if result != LIBUSB_SUCCESS:
            raise RuntimeError(f"Bulk transfer failed with error {result}")
        return transferred.value

    def bulk_write(self, endpoint, data: bytes, timeout=1000):
        """Bulk OUT 传输"""
        transferred = c_int()
        buf = create_string_buffer(data)
        result = self.libusb.libusb_bulk_transfer(
            self.handle,
            endpoint,
            cast(buf, c_void_p),
            len(data),
            byref(transferred),
            timeout
        )
        if result != LIBUSB_SUCCESS:
            raise RuntimeError(f"Bulk OUT transfer failed with error {result}")
        return transferred.value

    def bulk_read(self, endpoint, size: int, timeout=1000):
        """Bulk IN 传输"""
        transferred = c_int()
        buf = create_string_buffer(size)
        result = self.libusb.libusb_bulk_transfer(
            self.handle,
            endpoint,
            cast(buf, c_void_p),
            size,
            byref(transferred),
            timeout
        )
        if result != LIBUSB_SUCCESS:
            raise RuntimeError(f"Bulk IN transfer failed with error {result}")
        return buf.raw[:transferred.value], transferred.value

    def flush_input_buffer(self, max_empty_count=5, timeout_ms=100):
        """
        清空设备端输入缓存（丢弃所有可读数据）

        :param max_empty_count: 连续空读尝试次数，超过则认为已清空
        :param timeout_ms: 每次读取超时时间（毫秒）
        """
        empty_count = 0
        total_flushed = 0
        while empty_count < max_empty_count:
            try:
                chunk, transferred = self.bulk_read(
                    self.read_endpoint,
                    self.bulk_buffer_packet_size,
                    timeout=timeout_ms
                )
                if transferred > 0:
                    total_flushed += transferred
                    empty_count = 0  # 成功读取就重置
                else:
                    empty_count += 1
            except RuntimeError:
                empty_count += 1
        print(f"🧹 Flushed {total_flushed} bytes from device input buffer.")

    def DWritePort(self, command_bytes: bytes):
        self.bulk_write(self.write_endpoint, command_bytes)

    def DReadPort(self, length: int, timeout_sec: float = 1.0) -> bytes:
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
                data, transferred = self.bulk_read(
                    endpoint=self.read_endpoint,
                    size=self.bulk_buffer_packet_size,
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
# ======================
# 示例代码：main 测试
# ======================

if __name__ == "__main__":
    import platform
    import time

    libusb_path = r"interface/Lockin/usblib/module_64/libusb-1.0.so"
    # libusb_path = r"/home/pi/Program/NVMagUI/interface/Lockin/usblib/module_64/libusb-1.0.so"
    system = platform.system()
    if system == 'Windows':
        libusb_path = libusb_path.replace('.so', '.dll')
    else:
        libusb_path = libusb_path.replace('.dll', '.so')
    print(f"当前系统平台：{system}, 路径：{libusb_path}")
    # dev = USBDevice("libusb-1.0.dll")
    dev = USBDevice(libusb_path)
    dev.find_and_open()
    dev.flush_input_buffer()

    # 发送 Bulk OUT 数据
    data_num = 1000

    sent_bytes = dev.DWritePort(b'\x00\x00')
    time.sleep(0.1)
    dev.DWritePort(b'\x00\x06')

    dev.DWritePort(num_to_bytes(data_num, 4))
    DAQ_data = b''
    DAQ_data += dev.DReadPort(int((data_num) * 2))
    data = []

    checked_flag = True
    checked_num = 0
    for i in range(data_num):
        data_buf = bytes_to_num(DAQ_data[2 * i: 2 * i + 2])
        data.append(data_buf)
        if data_buf != data_num - i:
            checked_flag = False
        else:
            checked_num += 1
        print(data_buf)
    print(f'检查：{checked_flag}')

    print(f"✅ Sent {sent_bytes} bytes via bulk transfer.")
