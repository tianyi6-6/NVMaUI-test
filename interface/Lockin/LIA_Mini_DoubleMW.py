# coding=utf-8
import numpy as np
import os
import queue
import time
import matplotlib.pyplot as plt
import threading
import ctypes
from ctypes import (
    c_int, c_void_p, c_ubyte, c_ushort, c_uint,c_uint8,c_uint16, c_char_p, POINTER,
    Structure, byref, create_string_buffer, cast
)
import platform
import re
import logging

def str_to_hexstr(s):
    return ' '.join(['%02x' % b for b in s])

def num_to_bytes_signed(num, bytenum, high_head=True):
    if high_head:
        return np.array([num], dtype='>u8').tobytes()[-bytenum:]
    else:
        return np.array([num], dtype='<u8').tobytes()[:bytenum]

def bytes_to_num(bytes_):
    return int.from_bytes(bytes_, byteorder='big')

def num_to_bytes(num, bytenum, high_head=True):
    if high_head:
        return np.array([num], dtype='>u8').tobytes()[-bytenum:]
    else:
        return np.array([num], dtype='<u8').tobytes()[:bytenum]

def num_to_bytes_new(num: int, bytenum: int, high_head: bool = True) -> bytes:
    return num.to_bytes(bytenum, byteorder='big' if high_head else 'little')

num_to_bytes_old0 = num_to_bytes_new

# 定义常量
LIBUSB_SUCCESS = 0
LIBUSB_ERROR_TIMEOUT = -7
LIBUSB_REQUEST_TYPE_STANDARD = (0x00 << 5)
LIBUSB_RECIPIENT_DEVICE = 0x00

# 定义结构体

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


class USBController:
    def __init__(self, port : str):
        # 加载 libusb-1.0 动态库（Linux 路径，Windows 需调整为 libusb-1.0.dll）
        libusb_path = port
        system = platform.system()
        if system == 'Windows':
            libusb_path = libusb_path.replace('.so', '.dll')
        else:
            libusb_path = libusb_path.replace('.dll', '.so')
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

    def close(self):
        self.close_device()

    def __del__(self):
        if self.handle:
            self.libusb.libusb_close(self.handle)
        if self.ctx:
            self.libusb.libusb_exit(self.ctx)

    def open_device(self, *args, **kwargs):
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

        return True
        print(f"✅ Configuration {CONFIG_ID} set and interface {INTERFACE_ID} claimed.")

    def close_device(self):
        """关闭设备"""
        if self.handle:
            self.libusb.libusb_close(self.handle)
            self.handle = None

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

class USBController_Old:
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

        self.vendor_id = 0x04b4
        self.product_id = 0x00f1

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
        devices = POINTER(c_void_p)()
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

    def open_device(self):
        """通过 VID/PID 打开设备，返回设备句柄"""
        handle = c_void_p()
        dev_handle = self.libusb.libusb_open_device_with_vid_pid(
            self.ctx, self.vendor_id, self.product_id
        )
        if not dev_handle:
            raise LibUSBError("Device not found")
        self.handle = dev_handle

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

        # print(f'信号传输endpoint:{endpoint}')
        # 判断端点类型：IN（读） or OUT（写）
        if endpoint & 0x80 == 0:  # 输出端点，拷贝数据
            # print(f'准备输出数据:{data}')
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

    def DWritePort(self, command_bytes: bytes):
        self.bulk_transfer(self.write_endpoint, command_bytes)

    def read_response(self, size=512):
        return self.bulk_transfer(self.read_endpoint, bytearray(size))

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

class LIA_API(USBController):
    def __init__(self, *args, **kwargs):
        USBController.__init__(self, *args, **kwargs)
        # todo: 注册新设备类型
        self.dev_ctrl = {
            'LIA': self.lia_play,
            'MW': self.mw_play,
            'Laser': self.laser_play,
        }
        self.DAQ_gain = 1.0
        self.LIA_gain = 1.0
        self.auxdaq_gain = 1.0

        self.ADC_sample_rate = 25.0 * np.power(10, 6)
        self.IIR_o_sample_rate = 25.0 * np.power(10, 6)  # orig IIR sample rate unit:Sps
        self.daq_sample_rate = 1.0 * 10 ** 3  # output sample rate unit:Sps
        self.De_fre = {'ch1': 1000, 'ch2': 2200, 'ch3': 3500, 'ch4': 4800}
        self.De_phase = {'ch1': 0.0, 'ch2': 0.0, 'ch3': 0.0, 'ch4': 0.0, 'ch5': 0.0, 'ch6': 0.0, 'ch7': 0.0, 'ch8': 0.0}
        self.Modu_fre = {'ch1': 1000, 'ch2': 2200, 'ch3': 3500, 'ch4': 4800}
        self.Modu_phase = {'ch1': 0, 'ch2': 0, 'ch3': 0, 'ch4': 0}
        self.AD_offset = {'ch1': -0.0, 'ch2': -0.0, 'ch3': -0, 'ch4': -0}
        self.DA_offset = {'ch1': 0.0, 'ch2': 0.0}
        self.mw_para = {'ch1_Fre': 2.6e9, 'ch1_fm_sens': 0, 'ch1_atte': 30,
                        'ch2_Fre': 2.6e9, 'ch2_fm_sens': 0, 'ch2_atte': 30,
                        'ch3_Fre': 2.6e9, 'ch3_fm_sens': 0, 'ch3_atte': 30,
                        'ch4_Fre': 2.6e9, 'ch4_fm_sens': 0, 'ch4_atte': 30,
                        }
        self.laser_para = {'laser_power': 0.0}
        self.sample_rate = 1.0 * 10 ** 3
        self.tc = 0.002
        self.raw_data_queue = queue.Queue(maxsize=5000)
        self.data_queue = queue.Queue(maxsize=5000)

    def mw_play(self):
        '''把实际微波参数写入设备'''
        logging.info("将微波参数写入设备。")
        self.MW_SPI_Ctrl(ch1_Fre_buf=self.mw_para['ch1_Fre'], ch1_modu=self.mw_para['ch1_fm_sens'],
                         ch1_atte=self.mw_para['ch1_atte'],
                         ch2_Fre_buf=self.mw_para['ch2_Fre'], ch2_modu=self.mw_para['ch2_fm_sens'],
                         ch2_atte=self.mw_para['ch2_atte'])

    def laser_play(self):
        '''把实际激光参数写入设备'''
        logging.info("将激光参数写入设备。")
        self.CS_SPI_Ctrl(self.laser_para['laser_power'])

    def lia_play(self):
        '''把实际LIA参数写入设备'''
        logging.info("将锁相放大器参数写入设备。")
        self.all_stop()
        self.play()
        self.all_start()

    def set_dev(self, name):
        if name in self.dev_ctrl.keys():
            self.dev_ctrl[name]()

    def set_param(self, name, value):
        # todo: 暂时想不到太好的方法，手工逐个设置。
        if name == 'laser_power':
            return_value = self.laser_para['laser_power'] = value
        elif name == 'lockin_tc':
            return_value = self.set_tc(value)
        elif name == 'lockin_sample_rate':
            actual_sample_rate, deci_ratio = self.sample_rate_config(value)
            # logging.info(f"设置采样率：{value:.2f} Sps, 实际采样率：{actual_sample_rate:.2f} Sps, 运算抽取比：{deci_ratio}@{self.IIR_o_sample_rate} Sps")
            return_value = round(actual_sample_rate, 3)
        elif re.match(r"^lockin_modu_freq([1-2])$", name):
            ch = int(re.match(r"^lockin_modu_freq([1-2])$", name).group(1))  # 提取通道号
            # 同时设置调制和解调频率
            actual_modu_freq = self.Modu_fre_config(ch, value)
            self.De_fre_config(ch, value)
            # logging.info(f"设置通道[{ch}]调制/解调频率:{value} Hz，实际调制频率：{actual_modu_freq} Hz")
            return_value = round(actual_modu_freq, 3)
        elif re.match(r"^lockin_ch([1-2])_demod_phase([1-2])$", name):
            ch = int(re.match(r"^lockin_ch([1-2])_demod_phase([1-2])$", name).group(1))  # 提取输入通道号
            ch_freq = int(re.match(r"^lockin_ch([1-2])_demod_phase([1-2])$", name).group(2))  # 提取频率源通道号
            self.De_phase_config((ch - 1) * 2 + (ch_freq - 1) + 1, value)
            return_value = value
        elif re.match(r"^lockin_ch([1-2])_ad_offset$", name):
            ch = int(re.match(r"^lockin_ch([1-2])_ad_offset$", name).group(1))  # 提取通道号
            self.AD_offset_config(ch, value)
            return_value = value
        elif re.match(r"^mw_ch([1-2])_power$", name):
            ch = int(re.match(r"^mw_ch([1-2])_power$", name).group(1))  # 提取通道号
            self.mw_para[f'ch{ch}_atte'] = 30 - value
            return_value = value
        elif re.match(r"^mw_ch([1-2])_freq$", name):
            ch = int(re.match(r"^mw_ch([1-2])_freq$", name).group(1))  # 提取通道号
            return_value = self.get_actual_mw_freq(value)
            self.mw_para[f'ch{ch}_Fre'] = return_value
        elif re.match(r"^mw_ch([1-2])_fm_sens$", name):
            ch = int(re.match(r"^mw_ch([1-2])_fm_sens$", name).group(1))  # 提取通道号
            self.mw_para[f'ch{ch}_fm_sens'] = value
            return_value = value
        else:
            return_value = value
        # logging.info(f'设置[{name}], 设置值[{value}]， 返回值[{return_value}]')
        return return_value

    def connect_device(self):
        try:
            return self.USB_START()
        except:
            print('设备连接失败 T_T')
            return False

    def disconnect_device(self):
        self.USB_END()

    def USB_START(self):
        """
        开启USB设备
        设备识别码：DNVCS-API-TotalField-0001
        API-TotalField
        """
        return self.open_device(vendor_id=self.vendor_id, product_id=self.product_id)

    def USB_END(self):
        """
        断开USB设备
        设备识别码：DNVCS-API-TotalField-0002
        API-TotalField
        """
        # 断开连接
        self.close_device()

    def ioconfig(self, io_ch, coup, match, Attenuat, DA_Gain, AD_Gain):
        if io_ch == 1:
            self.DWritePort(b'\x00\xB8')
            time.sleep(.01)
            data = 0
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            self.DWritePort(num_to_bytes(io_ch - 1,
                                         1) + b'\x40\x00\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(0指的IO作为输出IO，1指的是IO作为输入IO)
            time.sleep(.01)
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            for i in range(4):
                if coup['ch' + str(4 - i)] == 'DC':
                    data = data * 4 + 2
                elif coup['ch' + str(4 - i)] == 'AC':
                    data = data * 4 + 1
                else:
                    print('coup config error')
                # print data
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x14' + num_to_bytes(data, 1))
            time.sleep(.01)
            data = 0
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            self.DWritePort(num_to_bytes(io_ch - 1,
                                         1) + b'\x40\x01\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(0指的IO作为输出IO，1指的是IO作为输入IO)
            time.sleep(.01)
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            for i in range(4):
                if match['ch' + str(4 - i)] == '50':
                    data = data * 4 + 2
                elif match['ch' + str(4 - i)] == '1M':
                    data = data * 4 + 1
                else:
                    print('match config error')
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x14' + num_to_bytes(data, 1))
            time.sleep(.01)
        elif io_ch == 2:
            data = 0
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            self.DWritePort(num_to_bytes(io_ch - 1,
                                         1) + b'\x40\x00\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(1指的IO作为输出IO，0指的是IO作为输入IO)
            time.sleep(.01)
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            for i in range(4):
                if Attenuat['ch' + str(4 - i)] == False:
                    data = data * 4 + 2
                elif Attenuat['ch' + str(4 - i)] == True:
                    data = data * 4 + 1
                else:
                    print('Attenuat config error')
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x14' + num_to_bytes(data, 1))
            time.sleep(.01)
            data = 0
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            self.DWritePort(num_to_bytes(io_ch - 1,
                                         1) + b'\x40\x01\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(1指的IO作为输出IO，0指的是IO作为输入IO)
            time.sleep(.01)
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            for i in range(4):
                if AD_Gain['ch' + str(4 - i)] == True:
                    data = data * 4 + 2
                elif AD_Gain['ch' + str(4 - i)] == False:
                    data = data * 4 + 1
                else:
                    print('coup config error')
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x15' + num_to_bytes(data, 1))
            time.sleep(.01)
        elif io_ch == 3:
            data = 0
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            self.DWritePort(num_to_bytes(io_ch - 1,
                                         1) + b'\x40\x00\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(1指的IO作为输出IO，0指的是IO作为输入IO)
            time.sleep(.01)
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            for i in range(2):
                if DA_Gain['ch' + str(2 - i)] == True:
                    data = data * 4 + 2
                elif DA_Gain['ch' + str(2 - i)] == False:
                    data = data * 4 + 1
                else:
                    print('Attenuat config error')
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x14' + num_to_bytes(data, 1))
            time.sleep(.01)
            data = 0
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            self.DWritePort(num_to_bytes(io_ch - 1,
                                         1) + b'\x40\x01\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(1指的IO作为输出IO，0指的是IO作为输入IO)
            time.sleep(.01)
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            for i in range(4):
                if Attenuat['ch' + str(4 - i)] == False:
                    data = data * 4 + 2
                elif Attenuat['ch' + str(4 - i)] == True:
                    data = data * 4 + 1
                else:
                    print('coup config error')
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x15' + num_to_bytes(data, 1))
            time.sleep(.01)

    def AD_PD(self, ch_num, Value):
        pass

    def amp_set_gain(self, amp_no, amp_g):
        cmd_set_amp = b'\x00\x50'
        if amp_g < 7:
            g_data = int(np.round(amp_g / 0.055744))
        else:
            g_data = int(np.floor(amp_g / (0.055744 * 7.079458) + 128))
        g_code = num_to_bytes(g_data, bytenum=1)
        g_ch_code = num_to_bytes(amp_no - 1, bytenum=1)
        g_write_code = cmd_set_amp + g_ch_code + g_code
        # print(str_to_hexstr(g_write_code))
        self.DWritePort(g_write_code)
        time.sleep(0.2)

    def RL_set(self, RL1_word, RL2_word):
        cmd_rl1_wr = b'\x00\x51'
        cmd_rl2_wr = b'\x00\x52'
        RL1_write_code = cmd_rl1_wr + RL1_word
        RL2_write_code = cmd_rl2_wr + RL2_word
        # print(str_to_hexstr(RL1_write_code))
        self.DWritePort(RL1_write_code)
        time.sleep(0.2)
        # print(str_to_hexstr(RL2_write_code))
        self.DWritePort(RL2_write_code)
        time.sleep(0.2)

    def para_set(self, ADC_offset_ch1, ADC_offset_ch2, DDC_para_list, MODU_para_list):
        """
        DDC、DAC参数设定
        :param ADC_offset:
        :param DDC_para_list:   [digi_freq, digi_phase]
        :param DAC_para_list:   [freq_dac_1, phase_dac_1, self.DA_Amp['ch1'], self.DA_offset['ch1']
        :return:
        """
        print('\ninto ADC & DDC para setting')
        # （ADC_offset修正值，[下变频频率、相位]，[DAC输出相位、幅度、offset]）
        ADC_offset_byte_ch1 = num_to_bytes_signed(int(ADC_offset_ch1), 2)
        ADC_offset_byte_ch2 = num_to_bytes_signed(int(ADC_offset_ch2), 2)

        actral_fre_ch1 = self.Demodu_freq_gen(DDC_para_list[0])
        actral_fre_ch2 = self.Demodu_freq_gen(DDC_para_list[3])
        actral_fre_ch3 = self.Demodu_freq_gen(DDC_para_list[6])
        actral_fre_ch4 = self.Demodu_freq_gen(DDC_para_list[9])

        digi_freq_ch1 = int(actral_fre_ch1 * (2.0 ** 48) / self.ADC_sample_rate)
        # print 'digi_freq_ch1', DDC_para_list[0], digi_freq_ch1
        digi_phase_ch1 = int(DDC_para_list[1] * (2.0 ** 48) / 360.0)
        digi_phase_ch2 = int(DDC_para_list[2] * (2.0 ** 48) / 360.0)

        digi_freq_ch2 = int(actral_fre_ch2 * (2.0 ** 48) / self.ADC_sample_rate)
        digi_phase_ch3 = int(DDC_para_list[4] * (2.0 ** 48) / 360.0)
        digi_phase_ch4 = int(DDC_para_list[5] * (2.0 ** 48) / 360.0)

        digi_freq_ch3 = int(actral_fre_ch3 * (2.0 ** 48) / self.ADC_sample_rate)
        digi_phase_ch5 = int(DDC_para_list[7] * (2.0 ** 48) / 360.0)
        digi_phase_ch6 = int(DDC_para_list[8] * (2.0 ** 48) / 360.0)

        digi_freq_ch4 = int(actral_fre_ch4 * (2.0 ** 48) / self.ADC_sample_rate)
        digi_phase_ch7 = int(DDC_para_list[10] * (2.0 ** 48) / 360.0)
        digi_phase_ch8 = int(DDC_para_list[11] * (2.0 ** 48) / 360.0)

        freq_byte_ch1 = num_to_bytes(digi_freq_ch1, 6)
        phase_byte_ch1 = num_to_bytes(digi_phase_ch1, 6)
        phase_byte_ch2 = num_to_bytes(digi_phase_ch2, 6)

        freq_byte_ch2 = num_to_bytes(digi_freq_ch2, 6)
        phase_byte_ch3 = num_to_bytes(digi_phase_ch3, 6)
        phase_byte_ch4 = num_to_bytes(digi_phase_ch4, 6)

        freq_byte_ch3 = num_to_bytes(digi_freq_ch3, 6)
        phase_byte_ch5 = num_to_bytes(digi_phase_ch5, 6)
        phase_byte_ch6 = num_to_bytes(digi_phase_ch6, 6)

        freq_byte_ch4 = num_to_bytes(digi_freq_ch4, 6)
        phase_byte_ch7 = num_to_bytes(digi_phase_ch7, 6)
        phase_byte_ch8 = num_to_bytes(digi_phase_ch8, 6)

        modu_freq_ch1, modu_phase_ch1, modu_frange_ch1 = self.FM_freq_gen(MODU_para_list[0], MODU_para_list[1])
        modu_freq_ch2, modu_phase_ch2, modu_frange_ch2 = self.FM_freq_gen(MODU_para_list[2], MODU_para_list[3])
        modu_freq_ch3, modu_phase_ch3, modu_frange_ch3 = self.FM_freq_gen(MODU_para_list[4], MODU_para_list[5])
        modu_freq_ch4, modu_phase_ch4, modu_frange_ch4 = self.FM_freq_gen(MODU_para_list[6], MODU_para_list[7])

        modu_freq_byte_ch1 = num_to_bytes(modu_freq_ch1, 6)
        modu_phase_byte_ch1 = num_to_bytes(modu_phase_ch1, 6)
        modu_frange_byte_ch1 = num_to_bytes(modu_frange_ch1, 6)
        modu_freq_byte_ch2 = num_to_bytes(modu_freq_ch2, 6)
        modu_phase_byte_ch2 = num_to_bytes(modu_phase_ch2, 6)
        modu_frange_byte_ch2 = num_to_bytes(modu_frange_ch2, 6)
        modu_freq_byte_ch3 = num_to_bytes(modu_freq_ch3, 6)
        modu_phase_byte_ch3 = num_to_bytes(modu_phase_ch3, 6)
        modu_frange_byte_ch3 = num_to_bytes(modu_frange_ch3, 6)
        modu_freq_byte_ch4 = num_to_bytes(modu_freq_ch4, 6)
        modu_phase_byte_ch4 = num_to_bytes(modu_phase_ch4, 6)
        modu_frange_byte_ch4 = num_to_bytes(modu_frange_ch4, 6)

        DDC_word_ch1 = freq_byte_ch1 + phase_byte_ch1 + phase_byte_ch2
        DDC_word_ch2 = freq_byte_ch2 + phase_byte_ch3 + phase_byte_ch4
        DDC_word_ch3 = freq_byte_ch3 + phase_byte_ch5 + phase_byte_ch6
        DDC_word_ch4 = freq_byte_ch4 + phase_byte_ch7 + phase_byte_ch8

        modu_word_ch1 = modu_freq_byte_ch1 + modu_phase_byte_ch1 + modu_frange_byte_ch1
        modu_word_ch2 = modu_freq_byte_ch2 + modu_phase_byte_ch2 + modu_frange_byte_ch2
        modu_word_ch3 = modu_freq_byte_ch3 + modu_phase_byte_ch3 + modu_frange_byte_ch3
        modu_word_ch4 = modu_freq_byte_ch4 + modu_phase_byte_ch4 + modu_frange_byte_ch4

        self.DWritePort(b'\x00\x20' + ADC_offset_byte_ch1 + ADC_offset_byte_ch2 \
                        + DDC_word_ch1 + DDC_word_ch2 + DDC_word_ch3 + DDC_word_ch4 + modu_word_ch1 + modu_word_ch2 \
                        + modu_word_ch3 + modu_word_ch4)

    def FM_freq_gen(self, fre, phase):
        # fre 精度保留到1e-5
        a = int(25e6 / fre)
        # print('Fre = ', fre, a)
        frange_code = int(2 ** 48 / a) * a
        fre_step = int(2 ** 48 / a)
        if (frange_code / fre_step) % 4 == 0:
            buf = frange_code / fre_step - 1
            fre_step = frange_code / buf
        #     print('!!!234!!!')
        #     frange_code = int(2**47 / a) * a
        #     fre_step = int(2**47 / a)
        phase_code = phase * (frange_code) / 360.0
        print(fre_step, phase_code, frange_code)
        # print('FM_Fre: ideal Frequency = ', fre, 'actual Frequency = ', fre_step / frange_code * 25e6)
        return fre_step, phase_code, frange_code

    def Demodu_freq_gen(self, fre):
        # fre 精度保留到1e-5
        a = int(25e6 / fre)
        frange_code = int(2 ** 48 / a) * a
        fre_step = int(2 ** 48 / a)
        print("!@##$!@#$!@%!@$@#%@", frange_code / fre_step)
        if (frange_code / fre_step) % 4 == 0:
            buf = frange_code / fre_step - 1
            fre_step = frange_code / buf
        # if frange_code + fre_step >= 2**48:
        #     frange_code = int(2**47 / a) * a
        #     fre_step = int(2**47 / a)
        print('Demodu_Fre: ideal Frequency = ', fre, 'actual Frequency = ', fre_step / frange_code * 25e6)
        return fre_step / frange_code * 25e6

    def gcd(self, a, b):
        # a作为除数 必须大于b
        a, b = (a, b) if a >= b else (b, a)
        while b:
            a, b = b, a % b
        return a

    def _LP1_coe(self, f0, fs=25 * 10 ** 6, k=1):
        # expression: H(s)=K/(1+s/2pi f0)
        # return coe: a1/a0, b0/a0, b1/a0
        # f0为拐点频率=1/tc，fs为IIR滤波器输入数据采样率，k为比例系数（默认为1）
        f_conv = 1 * np.pi * f0 / fs
        # print('f_conv is ', f_conv)
        # print(1/(1+f_conv))
        a1_vs_a0 = (1 - f_conv) / (1 + f_conv)
        b0_vs_a0 = k * f_conv / (1 + f_conv)
        b1_vs_a0 = 1 * b0_vs_a0
        return [a1_vs_a0], [b0_vs_a0, b1_vs_a0]

        
    def IIR_configure(self, tc_ch1, tc_ch2):
        print('\ninto IIR configuration')
        fs = 25.0 * np.power(10, 6)
        # coe_width = 32
        coe_a_array_1, coe_b_array_1 = self._LP1_coe(1 / tc_ch1, fs=fs)
        coe_a_array_2, coe_b_array_2 = self._LP1_coe(1 / tc_ch2, fs=fs)
        print("iir coe = ", coe_a_array_1, coe_b_array_1)
        self.IIR_sub_config(a1_1=coe_a_array_1[0], b0_1=coe_b_array_1[0], a1_2=coe_a_array_2[0], b0_2=coe_b_array_2[0])

    def IIR_sub_config(self, a1_1, b0_1, a1_2, b0_2):
        coe_width = 48
        fill_bytes = num_to_bytes(0, 2)
        coe_a1_bytes_ch1 = num_to_bytes(int(a1_1 * 2 ** coe_width), 6) + fill_bytes
        coe_b0_bytes_ch1 = num_to_bytes(int(b0_1 * 2 ** coe_width), 6) + fill_bytes
        # # coe_b0_bytes_ch11 = fill_bytes + num_to_bytes(int(b0_1*2**coe_width), 4)
        # print "******************&*&*&&*&*&*&**&*&*&&*&****************************"
        # print a1_1
        # print a1_1*2**coe_width
        # print b0_1
        # print b0_1*2**(coe_width+8)
        # print str_to_hexstr(coe_a1_bytes_ch1)
        # print str_to_hexstr(coe_b0_bytes_ch1)
        # print "******************&*&*&&*&*&*&**&*&*&&*&****************************"
        coe_a1_bytes_ch2 = num_to_bytes(int(a1_2 * 2 ** coe_width), 6) + fill_bytes
        coe_b0_bytes_ch2 = num_to_bytes(int(b0_2 * 2 ** coe_width), 6) + fill_bytes

        cmd_iir_con = b'\x00\x21'
        wr_word = cmd_iir_con + coe_a1_bytes_ch1 + coe_b0_bytes_ch1 + coe_a1_bytes_ch2 + coe_b0_bytes_ch2
        # print(str_to_hexstr(wr_word))
        self.DWritePort(wr_word)

    def IIR_DAQ_configure(self, filter_order_ch1, filter_order_ch2, daq_sample_rate):
        filter_order_bytes_ch1 = num_to_bytes(filter_order_ch1 - 1, 1)
        filter_order_bytes_ch2 = num_to_bytes(filter_order_ch2 - 1, 1)
        if daq_sample_rate <= 10 ** 5:  # max output sampling rate is 100k(这个可以后面再测测）
            deci_ratio = int(round(self.IIR_o_sample_rate / daq_sample_rate))
        else:
            deci_ratio = int(round(self.IIR_o_sample_rate / 10 ** 5))
            # print('daq_sample_rate is set to 100k')
        self.daq_sample_rate = self.IIR_o_sample_rate / deci_ratio
        deci_ratio_bytes = num_to_bytes(deci_ratio - 1, 3) + b'\x00'
        print("daq_sample_rate=", daq_sample_rate)
        print("deci_ratio", deci_ratio)
        cmd_iir_con = b'\x00\x22'
        wr_word = cmd_iir_con + filter_order_bytes_ch1 + filter_order_bytes_ch2 + deci_ratio_bytes
        # print(str_to_hexstr(wr_word))
        self.DWritePort(wr_word)
        time.sleep(0.1)
        return self.daq_sample_rate

    def play_info(self, *args):
        for i in args:
            self.dic = i

        if 'type' in self.dic:
            if self.dic['type'] == 'AD_offset':
                ch_num = self.dic['ch']
                if ch_num == 1 or 2:
                    if 'Value' in self.dic:
                        self.AD_offset['ch' + str(ch_num)] = self.dic['Value']
            elif self.dic['type'] == 'De_fre':
                ch_num = self.dic['ch']
                if ch_num == 1 or 2 or 3 or 4:
                    if 'Value' in self.dic:
                        self.De_fre['ch' + str(ch_num)] = self.dic['Value']
                else:
                    print('cmd error')
            elif self.dic['type'] == 'De_phase':
                ch_num = self.dic['ch']
                if ch_num == 1 or 2 or 3 or 4 or 5 or 6 or 7 or 8:
                    if 'Value' in self.dic:
                        self.De_phase['ch' + str(ch_num)] = self.dic['Value']
                else:
                    print('cmd error')
            elif self.dic['type'] == 'Modu_fre':
                ch_num = self.dic['ch']
                if ch_num == 1 or 2 or 3 or 4:
                    if 'Value' in self.dic:
                        self.Modu_fre['ch' + str(ch_num)] = self.dic['Value']
                else:
                    print('cmd error')
            elif self.dic['type'] == 'Modu_phase':
                ch_num = self.dic['ch']
                if ch_num == 1 or 2 or 3 or 4:
                    if 'Value' in self.dic:
                        self.Modu_phase['ch' + str(ch_num)] = self.dic['Value']
                else:
                    print('cmd error')
            elif self.dic['type'] == 'sample_rate':
                if 'Value' in self.dic:
                    self.sample_rate = self.dic['Value']
                else:
                    print('cmd error')
            elif self.dic['type'] == 'tc':
                if 'Value' in self.dic:
                    self.tc = self.dic['Value'] / 16.0
                else:
                    print('cmd error')

    def LIA_Config(self):
        self.all_stop()
        self.play()
        self.all_start()

    def play(self):
        set_mVpp_str = ''  # 输入波源幅度值文件名
        freq_c_ddc = ''  # 频率文件名

        # IIR采集幅度换算系数，对应配置为（1/10衰减，AC耦合，可变放大器均为\x12的单位增益配置）
        # IIR配置为tc=0.01s，滤波器阶数为4，由于滤波器保持DC信号归一化，因此该系数对不同tc以及阶数均可使用。
        hex2v_ch1 = 8.78398552654686E-20
        hex2v_ch2 = 9.28217449741933E-20
        hex2v_ch3 = 9.21083311316624E-20
        hex2v_ch4 = 9.35505450096255E-20

        freq = 10.033 * 10 ** 6
        # freq = 1000*10**3
        f_demodulation_1 = self.De_fre['ch1']  # NCO解调频率以及DDS1调制频率设置
        f_demodulation_2 = self.De_fre['ch2']  # NCO解调频率设置
        f_demodulation_3 = self.De_fre['ch3']  # NCO解调频率以及DDS2调制频率设置
        f_demodulation_4 = self.De_fre['ch4']  # NCO解调频率设置
        # print 'frequency of demodulation_1 is ', f_demodulation_1
        # print 'frequency of demodulation_2 is ', f_demodulation_2
        # print 'frequency of demodulation_3 is ', f_demodulation_3
        # print 'frequency of demodulation_4 is ', f_demodulation_4

        phase_ddc_1 = self.De_phase['ch1']  # NCO解调相位设置
        phase_ddc_2 = self.De_phase['ch2']  # NCO解调相位设置
        phase_ddc_3 = self.De_phase['ch3']  # NCO解调相位设置
        phase_ddc_4 = self.De_phase['ch4']  # NCO解调相位设置
        phase_ddc_5 = self.De_phase['ch5']  # NCO解调相位设置
        phase_ddc_6 = self.De_phase['ch6']  # NCO解调相位设置
        phase_ddc_7 = self.De_phase['ch7']  # NCO解调相位设置
        phase_ddc_8 = self.De_phase['ch8']  # NCO解调相位设置
        ch1_modulation_fre = self.Modu_fre['ch1']
        ch2_modulation_fre = self.Modu_fre['ch2']
        ch3_modulation_fre = self.Modu_fre['ch3']
        ch4_modulation_fre = self.Modu_fre['ch4']

        ch1_modulation_phase = self.Modu_phase['ch1']
        ch2_modulation_phase = self.Modu_phase['ch2']
        ch3_modulation_phase = self.Modu_phase['ch3']
        ch4_modulation_phase = self.Modu_phase['ch4']

        # 解调频率相位设置，调制频率相位设置，调制波形幅度偏置设置
        self.para_set(ADC_offset_ch1=self.AD_offset['ch1'], ADC_offset_ch2=self.AD_offset['ch2'],
                      DDC_para_list=[f_demodulation_1, phase_ddc_1, phase_ddc_2,
                                     f_demodulation_2, phase_ddc_3, phase_ddc_4,
                                     f_demodulation_3, phase_ddc_5, phase_ddc_6,
                                     f_demodulation_4, phase_ddc_7, phase_ddc_8],
                      MODU_para_list=[ch1_modulation_fre, ch1_modulation_phase,
                                      ch2_modulation_fre, ch2_modulation_phase,
                                      ch3_modulation_fre, ch3_modulation_phase,
                                      ch4_modulation_fre, ch4_modulation_phase])
        self.daq_sample_rate = self.sample_rate  # 返回数据采样率 单位：sps
        tc_set = self.tc  # unit: s 注意一定要使用小数形式，否则可能计算出错
        set_mVpp_str = 'defaultAmp'  # 保存幅度文件名设置
        freq_c_ddc = 'defaultFreq'  # 保存频率文件名设置
        self.IIR_configure(tc_ch1=tc_set, tc_ch2=tc_set)  # IIR滤波器截止频率设置
        print("tc_set =", tc_set)
        self.IIR_DAQ_configure(filter_order_ch1=8, filter_order_ch2=8,
                               daq_sample_rate=self.daq_sample_rate)  # IIR滤波器阶数及降采样率设置

    def program_start(self):
        self.DWritePort(b'\x00\x06')
        self.DWritePort(b'\x00\x00\x00\x00')  # total num input

    def DAQ_play(self, data_num, extract_ratio):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        time.sleep(.1)
        self.DWritePort(b'\x00\x01')  # 进入到DAQ状态

        self.DWritePort(num_to_bytes(data_num, 4))
        self.DWritePort(num_to_bytes(extract_ratio, 2))  # 进入到DAQ状态
        DAQ_data = b''
        DAQ_data += self.DReadPort(data_num * 4)
        # print(len(DAQ_data))
        data = [[] for i in range(2)]

        for i in range(data_num):
            data_buf = 0
            for j in range(2):
                data_buf = bytes_to_num(DAQ_data[4 * i + (j % 2) * 2: 4 * i + (j % 2 + 1) * 2])
                # print(data_buf)
                if data_buf > 32767:
                    data_buf = (data_buf - 65536) / 65536.0
                else:
                    data_buf = data_buf / 65536.0
                data[j].append(data_buf * self.DAQ_gain)

        self.Daq_data = data

        return self.Daq_data

    def daq_FFT(self):
        x = np.array(range(len(self.Daq_data[0]))) * self.ADC_sample_rate / len(self.Daq_data[0])
        plt.plot(x, self.FFT(self.Daq_data[0]), label='Ch1')
        plt.plot(x, self.FFT(self.Daq_data[1]), label='Ch2')
        plt.legend()
        plt.show()

    def FFT(self, data):
        l = len(data)
        han = signal.hann(l)
        self.data = np.array(data)
        f_data = np.fft.fft(self.data * han)

        k = l
        F_data = np.abs(f_data)
        F_data_buf = np.around(F_data, decimals=10)
        return F_data_buf[0: k]

    def daq_plot(self):
        x = range(len(self.Daq_data[0]))
        # plt.scatter(x, self.Daq_data[0])
        # plt.scatter(x, self.Daq_data[1])
        plt.plot(x, self.Daq_data[0], label='Ch1')
        plt.plot(x, self.Daq_data[1], label='Ch2')
        # plt.show()
        # plt.plot(x, self.Daq_data[0], label='Ch1')
        # plt.plot(x, self.Daq_data[1], label='Ch2')
        plt.legend()
        plt.show()

    def auxDAQ_play(self, data_num):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        time.sleep(.1)
        self.DWritePort(b'\x00\x09')  # 进入到DAQ状态
        time.sleep(.1)
        self.DWritePort(num_to_bytes(data_num, 4))
        DAQ_data = b''
        DAQ_data += self.DReadPort(data_num * 8)
        data = [[] for i in range(2)]

        for i in range(data_num):
            for j in range(2):
                data_buf = bytes_to_num(DAQ_data[8 * i + (j % 4) * 4: 8 * i + (j % 4 + 1) * 4])
                # 以下两行为科大板卡AD由正突变负读数的临时解决措施
                if data_buf > 16550000: # 这里不是标准的2^15-1，是因为AD有内置的offset未校偏，锁相没有留这个硬件接口
                    data_buf = (data_buf - 2 ** 24) / 2 ** 24
                else:
                    data_buf = data_buf / 2 ** 24
                data[j].append(data_buf * self.auxdaq_gain)

        self.auxDaq_data = np.array(data)
        return self.auxDaq_data

    def auxdaq_plot(self, fs=250):
        x = np.array(range(len(self.auxDaq_data[0]))) / fs
        # plt.scatter(x, self.Daq_data[0])
        # plt.scatter(x, self.Daq_data[1])
        plt.plot(x, self.auxDaq_data[0], label='Ch1')
        plt.plot(x, self.auxDaq_data[1], label='Ch2')
        plt.xlabel('time/s')
        plt.ylabel('Amp/V')
        # plt.show()
        # plt.plot(x, self.Daq_data[0], label='Ch1')
        # plt.plot(x, self.Daq_data[1], label='Ch2')
        plt.legend()
        plt.show()

    def DDC_play(self, data_num):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        time.sleep(.1)
        self.DWritePort(b'\x00\x02')  # 进入到DDC状态
        self.DWritePort(num_to_bytes(data_num, 4))
        DDC_data = b''
        DDC_data += self.DReadPort(data_num * 16)
        # print len(DDC_data)
        data = [[] for i in range(4)]

        for i in range(data_num):
            data_buf = 0
            for j in range(4):
                data_buf = bytes_to_num(DDC_data[16 * i + (j % 4) * 4: 16 * i + (j % 4 + 1) * 4])
                # print data_buf
                if data_buf > 2 ** 31 - 1:
                    data_buf = (data_buf - 2 ** 32.0) / 2 ** 32.0
                else:
                    data_buf = data_buf / 2 ** 32.0
                # data_buf = data_buf / 2**64.0
                data[j].append(data_buf)

        self.DDC_data = data

        return self.DDC_data

    def DDC_plot(self):
        # plt.ion()
        x = np.array(range(len(self.DDC_data[0]))) * (1.0 / self.ADC_sample_rate * 10 ** 9)
        # print x
        plt.plot(x, self.DDC_data[0], label='Ch1_Fre1_x')
        plt.plot(x, self.DDC_data[1], label='Ch1_Fre1_y')
        plt.plot(x, self.DDC_data[2], label='Ch2_Fre2_x')
        plt.plot(x, self.DDC_data[3], label='Ch2_Fre2_y')
        # plt.plot(x, self.DDC_data[4], label='Ch2_Fre1_x')
        # plt.plot(x, self.DDC_data[5], label='Ch2_Fre1_y')
        # plt.plot(x, self.DDC_data[6], label='Ch2_Fre2_x')
        # plt.plot(x, self.DDC_data[7], label='Ch2_Fre2_y')
        # plt.plot(x, self.DDC_data[8], label='Ch1_Fre3_x')
        # plt.plot(x, self.DDC_data[9], label='Ch1_Fre3_y')
        # plt.plot(x, self.DDC_data[10], label='Ch1_Fre4_x')
        # plt.plot(x, self.DDC_data[11], label='Ch1_Fre4_y')
        # plt.plot(x, self.DDC_data[12], label='Ch2_Fre3_x')
        # plt.plot(x, self.DDC_data[13], label='Ch2_Fre3_y')
        # plt.plot(x, self.DDC_data[14], label='Ch2_Fre4_x')
        # plt.plot(x, self.DDC_data[15], label='Ch2_Fre4_y')

        plt.xlabel('Time/ns')
        plt.ylabel('Amplitude/1')
        plt.legend()
        # plt.pause(1)  #显示秒数
        # plt.close()
        plt.show()

    def start_infinite_iir_acq(self):
        '''启动无限IIR采集模式'''
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        time.sleep(0.01)
        self.DWritePort(b'\x00\x04')  # 进入到IIR状态
        time.sleep(6 * self.tc + 0.1) # 等待6个tc
        self.DWritePort(b'\x00\x00\x00\x00') # 采集点数为零代表启动无限采集
    
    def stop_infinite_iir_acq(self):
        '''停止无限IIR采集模式'''
        for _ in range(10):
            self.DWritePort(b'\x00\x00')
            time.sleep(0.05)
        self.flush_input_buffer()
    
    def get_infinite_iir_points(self, data_num):
        '''获取无限IIR采集模式下的数据，[r x y] * 4 + 2 = 14列'''
        IIR_data = self.DReadPort(data_num * (6 * 6 * 2 + 8))  # 80 bytes
        data = [[] for i in range(14)]
        # aux_ch1_data = []
        # aux_ch2_data = []
        for i in range(data_num):
            data_buf = 0
            for j in range(12):
                data_buf = bytes_to_num(IIR_data[80 * i + (j % 14) * 6:  80 * i + (j % 14 + 1) * 6])
                if data_buf > 2 ** 47 - 1:
                    data_buf = (data_buf - 2 ** 48.0) / 2 ** 48.0
                else:
                    data_buf = data_buf / 2 ** 48.0
                # data_buf = data_buf / 2**64.0
                data[j].append(data_buf * self.LIA_gain)

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

    def IIR_play(self, data_num, CW_mode=False):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')

        self.DWritePort(b'\x00\x04')  # 进入到IIR状态
        if not CW_mode:
            time.sleep(self.tc + 0.1)
        self.DWritePort(num_to_bytes(data_num, 4))
        IIR_data = b''
        IIR_data += self.DReadPort(data_num * (6 * 6 * 2 + 8))  # 80 bytes
        time.sleep(self.tc + 0.1)
        data = [[] for i in range(14)]
        aux_ch1_data = []
        aux_ch2_data = []
        for i in range(data_num):
            data_buf = 0
            for j in range(12):
                data_buf = bytes_to_num(IIR_data[80 * i + (j % 14) * 6:  80 * i + (j % 14 + 1) * 6])
                if data_buf > 2 ** 47 - 1:
                    data_buf = (data_buf - 2 ** 48.0) / 2 ** 48.0
                else:
                    data_buf = data_buf / 2 ** 48.0
                # data_buf = data_buf / 2**64.0
                data[j].append(data_buf * self.LIA_gain)

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
        # print(aux_ch1_data)
        # print(aux_ch2_data)
        self.IIR_data = data
        # print('data = ', data)
        # time.sleep(.01)
        return self.IIR_data

    def IIR_continuous_acq_start(self):
        # TODO:开始采集
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        time.sleep(self.tc + 0.1)
        self.DWritePort(b'\x00\x04')  # 进入到IIR状态
        time.sleep(self.tc + 0.1)
        self.DWritePort(b'\x00\x00\x00\x00')

    def IIR_continuous_acq_stop(self):
        """
        连续测磁模式--停止采集
        设备识别码：DNVCS-API-TotalField-0004
        API-TotalField
        """
        for _ in range(10):
            self.DWritePort(b'\x00\x00')
            time.sleep(0.05)
        # self.DReadPort(10000)

    def IIR_plot(self):
        x = np.array(range(len(self.IIR_data[0]))) / self.sample_rate
        plt.plot(x, self.IIR_data[0], label='Ch1_Fre1_r')
        plt.plot(x, self.IIR_data[1], label='Ch1_Fre1_y')
        plt.plot(x, self.IIR_data[2], label='Ch1_Fre1_x')
        plt.plot(x, self.IIR_data[3], label='Ch2_Fre1_r')
        plt.plot(x, self.IIR_data[4], label='Ch2_Fre1_y')
        plt.plot(x, self.IIR_data[5], label='Ch2_Fre1_x')
        # plt.plot(x, self.IIR_data[6], label='Ch1_Fre2_r')
        # plt.plot(x, self.IIR_data[7], label='Ch1_Fre2_y')
        # plt.plot(x, self.IIR_data[8], label='Ch1_Fre2_x')
        # plt.plot(x, self.IIR_data[9], label='Ch2_Fre2_r')
        # plt.plot(x, self.IIR_data[10], label='Ch2_Fre2_y')
        # plt.plot(x, self.IIR_data[11], label='Ch2_Fre2_x')
        # plt.plot(x, self.IIR_data[12], label='Ch1_Fre3_r')
        # plt.plot(x, self.IIR_data[13], label='Ch1_Fre3_y')
        # plt.plot(x, self.IIR_data[14], label='Ch1_Fre3_x')
        # plt.plot(x, self.IIR_data[15], label='Ch2_Fre3_r')
        # plt.plot(x, self.IIR_data[16], label='Ch2_Fre3_y')
        # plt.plot(x, self.IIR_data[17], label='Ch2_Fre3_x')
        # plt.plot(x, self.IIR_data[18], label='Ch1_Fre4_r')
        # plt.plot(x, self.IIR_data[19], label='Ch1_Fre4_y')
        # plt.plot(x, self.IIR_data[20], label='Ch1_Fre4_x')
        # plt.plot(x, self.IIR_data[21], label='Ch2_Fre4_r')
        # plt.plot(x, self.IIR_data[22], label='Ch2_Fre4_y')
        # plt.plot(x, self.IIR_data[23], label='Ch2_Fre4_x')
        print('iir_data_r: mean = ', np.mean(self.IIR_data[9]), 'STD = ', np.std(self.IIR_data[9]))
        # plt.xlabel('Time/ns')
        plt.ylabel('Amplitude/1')
        plt.legend()
        plt.show()

    def PID_play(self, data_num):
        """
        PID数据采集
        设备识别码：DNVCS-PID-TotalField-0004
        PID-TotalField
        :param data_num: 数据量 int between [1,1E6] 10
        """
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')

        self.DWritePort(b'\x00\x05')  # 进入到PID状态
        time.sleep(self.tc * 6)
        self.DWritePort(num_to_bytes(data_num, 4))
        PID_data = b''
        PID_data += self.DReadPort(data_num * 76)
        # print len(IIR_data)
        data = [[[] for i in range(5)] for j in range(2)]
        aux_ch1_data = []
        aux_ch2_data = []

        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(PID_data[76 * i: 76 * i + 2])
            # if frame_h == 21845:
            #     print("Frame header check succeeded")
            iir_data_r = bytes_to_num(PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2 ** 48.0
            if iir_data_y > 2 ** 47 - 1:
                ch1_iir_data_y = (iir_data_y - 2 ** 48.0) / 2 ** 48.0
            else:
                ch1_iir_data_y = iir_data_y / 2 ** 48.0
            if iir_data_x > 2 ** 47 - 1:
                ch1_iir_data_x = (iir_data_x - 2 ** 48.0) / 2 ** 48.0
            else:
                ch1_iir_data_x = iir_data_x / 2 ** 48.0
            if error_buf > 2 ** 63 - 1:
                ch1_error_buf = (error_buf - 2 ** 64.0) / 2 ** 64.0
            else:
                ch1_error_buf = error_buf / 2 ** 64.0
            ch1_feedback_buf = feedback_buf * 2 / 1048576 + 2.6 * 1e9
            data[0][0].append(ch1_iir_data_r)
            data[0][1].append(ch1_iir_data_x)
            data[0][2].append(ch1_iir_data_y)
            data[0][3].append(ch1_error_buf)
            data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2 ** 48.0
            if iir_data_y > 2 ** 47 - 1:
                ch1_iir_data_y = (iir_data_y - 2 ** 48.0) / 2 ** 48.0
            else:
                ch1_iir_data_y = iir_data_y / 2 ** 48.0
            if iir_data_x > 2 ** 47 - 1:
                ch1_iir_data_x = (iir_data_x - 2 ** 48.0) / 2 ** 48.0
            else:
                ch1_iir_data_x = iir_data_x / 2 ** 48.0
            if error_buf > 2 ** 63 - 1:
                ch1_error_buf = (error_buf - 2 ** 64.0) / 2 ** 64.0
            else:
                ch1_error_buf = error_buf / 2 ** 64.0
            ch1_feedback_buf = feedback_buf * 2 / 1048576 + 2.6 * 1e9
            data[1][0].append(ch1_iir_data_r)
            data[1][1].append(ch1_iir_data_x)
            data[1][2].append(ch1_iir_data_y)
            data[1][3].append(ch1_error_buf)
            data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(PID_data[76 * i + 66: 76 * i + 70]) % 2 ** 28
            ch2_data = bytes_to_num(PID_data[76 * i + 70: 76 * i + 74]) % 2 ** 28
            if ch1_data > 2 ** 27 - 1:
                ch1_data_buf = (ch1_data - 2 ** 28.0) / 2 ** 28.0
            else:
                ch1_data_buf = ch1_data / 2 ** 28.0

            if ch2_data > 2 ** 27 - 1:
                ch2_data_buf = (ch2_data - 2 ** 28.0) / 2 ** 28.0
            else:
                ch2_data_buf = ch2_data / 2 ** 28.0
            aux_ch1_data.append(ch1_data_buf)
            aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(PID_data[76 * i + 74: 76 * i + 75])
            # print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(PID_data[76 * i + 75: 76 * i + 76])
            # print('Time frame_l is ', frame_l)
            if frame_l == 170:
                pass
                # print("End of frame check succeeded")
        # print("PID_data:", data, len(data))
        self.PID_data = data
        self.aux_ch1_data = aux_ch1_data
        self.aux_ch2_data = aux_ch2_data
        return self.PID_data

    # def PID_AcquireStart(self):
    #     """
    #     PID数据连续采集
    #     设备识别码：DNVCS-PID-TotalField-0005
    #     PID-TotalField
    #     """
    #     self.PID_run_flag = True
    #     # self.flushInputBuffer()
    #     packs_byte = num_to_bytes(0, 4)
    #     self.DWritePort(b'\x00\x00')
    #     time.sleep(0.1)
    #     self.DWritePort(b'\x00\x05')  # 进入到PID状态
    #     self.DWritePort(packs_byte)
    #     # AINPUTN = 4
    #     self.AINPUTN = 2
    #     self.PID_data = [[] for _ in range(self.AINPUTN * 4)]
    #     self.aux_data = [[] for _ in range(2)]
    #
    # def PID_AcquireStop(self):
    #     """
    #     PID数据连续采集停止
    #     设备识别码：DNVCS-PID-TotalField-0011
    #     PID-TotalField
    #     """
    #     self.PID_run_flag = False
    #     self.DWritePort(b'\x00\x00')
    #     time.sleep(0.1)
    #     self.PID_data = [[] for _ in range(self.AINPUTN * 4)]
    #     self.aux_data = [[] for _ in range(2)]
    #     # self.DFlushInput()
    #     print('pid acq stop')
    #
    # def PID_Acquire_getpoints(self, data_num):
    #     """
    #     PID连续数据采集，不指定data_num时将以 五分之一 的采样率采样
    #     设备识别码：DNVCS-PID-TotalField-0009
    #     PID-TotalField
    #     :param data_num: 数据量 int between [1,1E6] 0
    #     """
    #     if(self.PID_run_flag):
    #         # 目前16列数据，0-3列为频率1结果，依次为x,y,误差项，反馈输出，频率2,3,4依次类推
    #         if(data_num):
    #             res, aux_ch1_data, aux_ch2_data = self.PID_sub_play(data_num=int(data_num))
    #         else:
    #             res, aux_ch1_data, aux_ch2_data = self.PID_sub_play(data_num=int(self.sample_rate * 0.2))
    #         for ii in range(2):
    #             self.PID_data[ii * 4] += list(np.array(res[ii][1]))
    #             self.PID_data[ii * 4 + 1] += list(np.array(res[ii][2]))
    #             self.PID_data[ii * 4 + 2] += list(np.array(res[ii][3]))
    #             self.PID_data[ii * 4 + 3] += list(np.array(res[ii][4]) * 4194304000.0)
    #         self.aux_data[0] += list(aux_ch1_data)
    #         self.aux_data[1] += list(aux_ch2_data)
    #         return [res, aux_ch1_data, aux_ch2_data]

    def PID_sub_play(self, data_num):
        """
        PID数据连续采集
        设备识别码：DNVCS-PID-TotalField-0007
        PID-TotalField
        :param data_num: 数据量 int between [1,1E6] 10
        """
        # 使用前需要确保系统处于IDLE状态
        PID_data = b''
        PID_data += self.DReadPort(data_num * 76)
        # print len(IIR_data)
        data = [[[] for i in range(5)] for j in range(2)]
        aux_ch1_data = []
        aux_ch2_data = []
        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(PID_data[76 * i: 76 * i + 2])
            if frame_h == 21845:
                print("Frame header check succeeded")
            iir_data_r = bytes_to_num(PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2 ** 48.0
            if iir_data_y > 2 ** 47 - 1:
                ch1_iir_data_y = (iir_data_y - 2 ** 48.0) / 2 ** 48.0
            else:
                ch1_iir_data_y = iir_data_y / 2 ** 48.0
            if iir_data_x > 2 ** 47 - 1:
                ch1_iir_data_x = (iir_data_x - 2 ** 48.0) / 2 ** 48.0
            else:
                ch1_iir_data_x = iir_data_x / 2 ** 48.0
            if error_buf > 2 ** 63 - 1:
                ch1_error_buf = (error_buf - 2 ** 64.0) / 2 ** 64.0
            else:
                ch1_error_buf = error_buf / 2 ** 64.0
            ch1_feedback_buf = feedback_buf * 2 / 1048576 + 2.6 * 1e9
            data[0][0].append(ch1_iir_data_r)
            data[0][1].append(ch1_iir_data_x)
            data[0][2].append(ch1_iir_data_y)
            data[0][3].append(ch1_error_buf)
            data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2 ** 48.0
            if iir_data_y > 2 ** 47 - 1:
                ch1_iir_data_y = (iir_data_y - 2 ** 48.0) / 2 ** 48.0
            else:
                ch1_iir_data_y = iir_data_y / 2 ** 48.0
            if iir_data_x > 2 ** 47 - 1:
                ch1_iir_data_x = (iir_data_x - 2 ** 48.0) / 2 ** 48.0
            else:
                ch1_iir_data_x = iir_data_x / 2 ** 48.0
            if error_buf > 2 ** 63 - 1:
                ch1_error_buf = (error_buf - 2 ** 64.0) / 2 ** 64.0
            else:
                ch1_error_buf = error_buf / 2 ** 64.0
            ch1_feedback_buf = feedback_buf * 2 / 1048576 + 2.6 * 1e9
            data[1][0].append(ch1_iir_data_r)
            data[1][1].append(ch1_iir_data_x)
            data[1][2].append(ch1_iir_data_y)
            data[1][3].append(ch1_error_buf)
            data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(PID_data[76 * i + 66: 76 * i + 70]) % 2 ** 28
            ch2_data = bytes_to_num(PID_data[76 * i + 70: 76 * i + 74]) % 2 ** 28
            if ch1_data > 2 ** 27 - 1:
                ch1_data_buf = (ch1_data - 2 ** 28.0) / 2 ** 28.0
            else:
                ch1_data_buf = ch1_data / 2 ** 28.0

            if ch2_data > 2 ** 27 - 1:
                ch2_data_buf = (ch2_data - 2 ** 28.0) / 2 ** 28.0
            else:
                ch2_data_buf = ch2_data / 2 ** 28.0
            aux_ch1_data.append(ch1_data_buf)
            aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(PID_data[76 * i + 74: 76 * i + 75])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(PID_data[76 * i + 75: 76 * i + 76])
            print('Time frame_l is ', frame_l)
            if frame_l == 170:
                print("End of frame check succeeded")

        return data, aux_ch1_data, aux_ch2_data

    def PID_plot(self):
        x = np.array(range(len(self.PID_data[0][0])))
        plt.plot(x, self.PID_data[0][1], label='Ch1_iir_x')
        plt.plot(x, self.PID_data[0][2], label='Ch1_iir_y')
        plt.plot(x, self.PID_data[0][3], label='Ch1_error')
        plt.plot(x, self.PID_data[0][4], label='Ch1_feedback')
        # # plt.plot(x, self.PID_data[1][1], label='Ch2_iir_x')
        # # plt.plot(x, self.PID_data[1][2], label='Ch2_iir_y')
        # plt.plot(x, self.PID_data[1][3], label='Ch2_error')
        # plt.plot(x, self.PID_data[1][4], label='Ch2_feedback')
        # # plt.plot(x, self.PID_data[2][1], label='Ch3_iir_x')
        # # plt.plot(x, self.PID_data[2][2], label='Ch3_iir_y')
        # plt.plot(x, self.PID_data[2][3], label='Ch3_error')
        # plt.plot(x, self.PID_data[2][4], label='Ch3_feedback')
        # # plt.plot(x, self.PID_data[3][0], label='Ch4_iir_r')
        # # plt.plot(x, self.PID_data[3][1], label='Ch4_iir_x')
        # # plt.plot(x, self.PID_data[3][2], label='Ch4_iir_y')
        # plt.plot(x, self.PID_data[3][3], label='Ch4_error')
        # plt.plot(x, self.PID_data[3][4], label='Ch4_feedback')
        plt.xlabel('Time/ns')
        plt.ylabel('error/1')
        plt.legend()
        plt.show()

    def Laser_PID_play(self, data_num):  # 目前没有加滤波，不知道是否会存在震荡，需后续实验测试。
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')

        self.DWritePort(b'\x00\x08')  # 进入到PID状态
        time.sleep(self.tc * 6)
        self.DWritePort(num_to_bytes(data_num, 4))
        PID_data = b''
        PID_data += self.DReadPort(data_num * 16)

        data = [[], [], []]
        ch1_data1 = 0
        for i in range(data_num):  # 数据共有96位
            frame_h = bytes_to_num(PID_data[16 * i: 16 * i + 2])  # 帧头
            # if frame_h == 21845:
            #     print("Frame header check succeeded")
            error_buf = bytes_to_num(PID_data[16 * i + 2: 16 * i + 6])  # error项
            feedback_buf = bytes_to_num(PID_data[16 * i + 6: 16 * i + 10])
            ch1_data = bytes_to_num(PID_data[16 * i + 10: 16 * i + 13])

            if error_buf > 2 ** 31 - 1:
                error_buf = error_buf - 2 ** 32
            data[0].append(error_buf / 2 ** 32)
            data[1].append(feedback_buf / 2 ** 32 * 2.5)
            if ch1_data > 2 ** 23 - 1:
                ch1_data = (ch1_data - 2 ** 24) / 2 ** 24
            else:
                ch1_data = ch1_data / 2 ** 24
            data[2].append(ch1_data)

            ch1_data1 = ch1_data
            time_stamp = bytes_to_num(PID_data[16 * i + 14: 16 * i + 15])
            # 当前的error信号应该等于上一次的datain与setpoint之差
            # print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(PID_data[16 * i + 15: 16 * i + 16])
            # if frame_l == 170:
            #     print("End of frame check succeeded")
        self.PID_data = data
        return self.PID_data

    def Laser_PID_plot(self):
        x = np.array(range(len(self.PID_data[0])))
        plt.plot(x, self.PID_data[0], label='Ch1_error')
        # plt.plot(x, self.PID_data[1], label='Ch1_feedback')
        # plt.plot(x, self.PID_data[2], label='Ch1_data')
        plt.xlabel('Time/ns')
        plt.ylabel('error/1')
        plt.legend()
        plt.show()

    def Laser1_SPI_Ctrl(self, Value):
        self.DWritePort(b'\x00\xb5')
        self.DWritePort(b'\x00\x00' + num_to_bytes(int(Value / 2.5 * 65536), 2))

    def CS_SPI_Ctrl(self, Value):
        self.DWritePort(b'\x00\xb3')
        time.sleep(0.05)
        self.DWritePort(b'\x00\x00' + num_to_bytes(int(Value / 2.5 * 65536), 2))
        time.sleep(0.05)

    def set_laser_power(self, Value):
        self.DWritePort(b'\x00\xb3')
        time.sleep(0.05)
        self.DWritePort(b'\x00\x00' + num_to_bytes(int(Value / 2.5 * 65536), 2))
        time.sleep(0.05)

    # 原有的coe占位太多，使用多个参数代替
    def PID_config(self, PID_ch_num, set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH):
        """
        设置PID参数
        设备识别码：DNVCS-PID-TotalField-0001
        PID-TotalField
        :param PID_ch_num: PID通道 int in [1,2,3,4] 1
        :param set_point: ??? int in [1,2,3,4] 0.0
        :param output_offset: ??? int in [1,2,3,4] int(2.7849*1e9-2.6*1e9)*0.5*1048576
        :param kp: ??? int in [1,2,3,4] 0.00008
        :param ki: ??? int in [1,2,3,4] 0.0002
        :param kd: ??? int in [1,2,3,4] -0.00001
        :param kt: ??? int in [1,2,3,4] 1.0000000
        :param Cal_ex: ??? int in [1,2,3,4] 2500000
        :param RD_ex: ??? int in [1,2,3,4] 0000
        :param PID_LIA_CH: ??? int in [1,2,3,4] 0
        """
        coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
        # ch_coe = [set_point, output_offset, kp, ki, kd, PID_LIA_CH]
        if PID_ch_num == 1:
            self.DWritePort(b'\x00\x24')
            self.DWritePort(num_to_bytes(int(coe[0] * 2 ** 64), 8))
            self.DWritePort(num_to_bytes(int(coe[1]), 6))
            self.DWritePort(num_to_bytes(int(coe[2] * 2 ** 32), 4))  # kp
            self.DWritePort(num_to_bytes(int(coe[3] * 2 ** 32), 4))  # ki
            self.DWritePort(num_to_bytes(int(coe[4] * 2 ** 32), 4))  # kd
            self.DWritePort(num_to_bytes(int(coe[5] * 2 ** 16), 4))  # kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(num_to_bytes(int(coe[6]), 1) + num_to_bytes(int(coe[7]), 3))
            self.DWritePort(num_to_bytes(int(coe[8]), 2))
        elif PID_ch_num == 2:
            self.DWritePort(b'\x00\x25')
            self.DWritePort(num_to_bytes(int(coe[0] * 2 ** 64), 8))
            self.DWritePort(num_to_bytes(int(coe[1]), 6))
            self.DWritePort(num_to_bytes(int(coe[2] * 2 ** 32), 4))  # kp
            self.DWritePort(num_to_bytes(int(coe[3] * 2 ** 32), 4))  # ki
            self.DWritePort(num_to_bytes(int(coe[4] * 2 ** 32), 4))  # kd
            self.DWritePort(num_to_bytes(int(coe[5] * 2 ** 16), 4))  # kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(num_to_bytes(int(coe[6]), 1) + num_to_bytes(int(coe[7]), 3))
            self.DWritePort(num_to_bytes(int(coe[8]), 2))
        elif PID_ch_num == 3:
            self.DWritePort(b'\x00\x26')
            self.DWritePort(num_to_bytes(int(coe[0] * 2 ** 64), 8))
            self.DWritePort(num_to_bytes(int(coe[1]), 6))
            self.DWritePort(num_to_bytes(int(coe[2] * 2 ** 32), 4))  # kp
            self.DWritePort(num_to_bytes(int(coe[3] * 2 ** 32), 4))  # ki
            self.DWritePort(num_to_bytes(int(coe[4] * 2 ** 32), 4))  # kd
            self.DWritePort(num_to_bytes(int(coe[5] * 2 ** 16), 4))  # kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(num_to_bytes(int(coe[6]), 1) + num_to_bytes(int(coe[7]), 3))
            self.DWritePort(num_to_bytes(int(coe[8]), 2))
        elif PID_ch_num == 4:
            self.DWritePort(b'\x00\x27')
            self.DWritePort(num_to_bytes(int(coe[0] * 2 ** 64), 8))
            self.DWritePort(num_to_bytes(int(coe[1]), 6))
            self.DWritePort(num_to_bytes(int(coe[2] * 2 ** 32), 4))  # kp
            self.DWritePort(num_to_bytes(int(coe[3] * 2 ** 32), 4))  # ki
            self.DWritePort(num_to_bytes(int(coe[4] * 2 ** 32), 4))  # kd
            self.DWritePort(num_to_bytes(int(coe[5] * 2 ** 16), 4))  # kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(num_to_bytes(int(coe[6]), 1) + num_to_bytes(int(coe[7]), 3))
            self.DWritePort(num_to_bytes(int(coe[8]), 2))

        elif PID_ch_num == 5:  # 激光稳定PID
            self.DWritePort(b'\x00\x23')
            self.DWritePort(
                num_to_bytes(int(coe[0] * 2 ** 32), 4))  # set_point：预设点为期望慢速ADC采集到的荧光直流信号的大小，需要预先读取一次慢速ADC的数据，然后将数据写入。
            self.DWritePort(b'\x00' * 4)
            self.DWritePort(
                num_to_bytes(int(coe[1] / 2.5 * 65536), 2) + b'\x00' * 4)  # output_offset：输出偏置，不太清楚怎么设置，比预想激光功率略小？

            self.DWritePort(num_to_bytes(int(coe[2] * 2 ** 32), 4))
            self.DWritePort(num_to_bytes(int(coe[3] * 2 ** 32), 4))
            self.DWritePort(num_to_bytes(int(coe[4] * 2 ** 32), 4))
            self.DWritePort(num_to_bytes(int(coe[5] * 2 ** 16), 4))  # kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(b'\x00\x00' + num_to_bytes(int(coe[7]), 1) + num_to_bytes(int(coe[6]), 1))
            self.DWritePort(num_to_bytes(int(coe[8]), 1))
            print('COE 8', coe[8])

    def PID_enable(self, ch_num):
        """
        PID模式启动
        设备识别码：DNVCS-PID-TotalField-0002
        PID-TotalField
        :param ch_num: PID通道 int in [1,2,3,4] 1
        """
        if ch_num == 1:
            self.DWritePort(b'\x00\x28')
        elif ch_num == 2:
            self.DWritePort(b'\x00\x2A')
        elif ch_num == 3:
            self.DWritePort(b'\x00\x2C')
        elif ch_num == 4:
            self.DWritePort(b'\x00\x2E')
        elif ch_num == 5:  # 激光稳定PID
            self.DWritePort(b'\x00\x30')

    def PID_disable(self, ch_num):
        """
        PID模式关闭
        设备识别码：DNVCS-PID-TotalField-0003
        PID-TotalField
        :param ch_num: PID通道 int in [1,2,3,4] 1
        """
        if ch_num == 1:
            self.DWritePort(b'\x00\x29')
        elif ch_num == 2:
            self.DWritePort(b'\x00\x2B')
        elif ch_num == 3:
            self.DWritePort(b'\x00\x2D')
        elif ch_num == 4:
            self.DWritePort(b'\x00\x2F')
        elif ch_num == 5:  # 激光稳定PID
            self.DWritePort(b'\x00\x31')

    def all_start(self):
        """
        FPGA开启
        设备识别码：DNVCS-API-TotalField-0025
        API-TotalField
        """
        self.DWritePort(b'\x00\x3C')

    def all_stop(self):
        """
        FPGA关闭
        设备识别码：DNVCS-API-TotalField-0026
        API-TotalField
        """
        self.DWritePort(b'\x00\x3D')

    def MW_SPI_Ctrl(self, ch1_Fre_buf, ch1_modu, ch1_atte, ch2_Fre_buf, ch2_modu, ch2_atte):
        # 0, 268435455
        # print('MW SPI Ctrl:', ch1_Fre_buf, ch1_modu, ch1_atte, ch2_Fre_buf, ch2_modu, ch2_atte)
        ch1_Fre = int((ch1_Fre_buf - 2600000000) * 0.5)
        ch2_Fre = int((ch2_Fre_buf - 2600000000) * 0.5)
        if ch1_Fre > 268535455 or ch1_Fre < 0:
            ch1_Fre = 0
            print('ch1_Fre input Out of range', ch1_Fre)
            print('ch_Fre = ', )
        if ch2_Fre > 268535455 or ch2_Fre < 0:
            print('ch2_Fre input Out of range')
            ch2_Fre = 0
        if ch1_modu > 30 or ch1_modu < 0 or ch2_modu > 30 or ch2_modu < 0:
            print('ch3_Fre input Out of range')

        if ch1_atte > 30 or ch1_atte < 0 or ch2_atte > 30 or ch2_atte < 0:
            print('ch4_Fre input Out of range')

        self.DWritePort(b'\x00' + b'\xb1')
        data_buf1 = 3 + ch2_atte * 2 ** 2 + ch2_modu * 2 ** 7 + ch2_Fre * 2 ** 12 + ch1_atte * 2 ** 40 + ch1_modu * 2 ** 45 + ch1_Fre * 2 ** 50 + 1 * 2 ** 78
        self.DWritePort(num_to_bytes_old0(data_buf1, 10))
        time.sleep(.1)

    def AUX_AD_REG_WR(self, reg_addr, data):
        wr_cmd = b'\x00\xc0'
        reg_addr_word = num_to_bytes(64 + reg_addr, 1) + b'\x00'
        # print(str_to_hexstr(wr_cmd+dev_addr_word+reg_addr_word+data))
        self.DWritePort(wr_cmd + reg_addr_word + data)

    def AUX_AD_REG_RD(self, reg_addr):
        rd_cmd = b'\x00\xc1'
        reg_addr_word = num_to_bytes(32 + reg_addr, 1) + b'\x00'
        # print(str_to_hexstr(rd_cmd + dev_addr_word + reg_addr_word))
        self.DWritePort(rd_cmd + reg_addr_word)
        time.sleep(0.1)
        print(str_to_hexstr(self.DReadPort(4)))

    def STCN75_REG_WR(self, reg_addr, data):
        wr_cmd = b'\x00\xc2'
        dev_addr_word = num_to_bytes(0, 1)
        reg_addr_word = num_to_bytes(reg_addr, 1)
        print(str_to_hexstr(wr_cmd + dev_addr_word + reg_addr_word + data))
        self.DWritePort(wr_cmd + dev_addr_word + reg_addr_word + data)

    def STCN75_REG_RD(self, reg_addr):
        rd_cmd = b'\x00\xc3'
        dev_addr_word = num_to_bytes(0, 1)
        reg_addr_word = num_to_bytes(reg_addr, 1)
        self.DWritePort(rd_cmd + dev_addr_word + reg_addr_word)
        time.sleep(0.1)
        data = bytes_to_num(self.DReadPort(4)) / 2 ** 7
        tmp = data * 0.5
        print('板卡温度为', tmp, '℃')
        return tmp

    def XADC_TEMP_RD(self):
        rd_cmd = b'\x00\xc4'
        self.DWritePort(rd_cmd)
        time.sleep(0.1)
        # data = self.DReadPort(2)
        tmp = bytes_to_num(self.DReadPort(2)) * 503.975 / 4096 - 273.15
        # tmp = data * 0.5
        print('板卡温度为', tmp, '℃')
        return tmp

    def DEVICE_varify(self):
        self.DWritePort(b'\x00\xee')
        print('板卡编号为', str_to_hexstr(self.DReadPort(2)))

    def mag_rd(self):
        self.DWritePort(b'\x00\xc5')
        data = self.DReadPort(6)
        mag_x = bytes_to_num(data[0:2])
        mag_y = bytes_to_num(data[2:4])
        mag_z = bytes_to_num(data[4:6])
        if (mag_x > 32768):
            mag_x = -(2 ** 16 - mag_x)
        if (mag_y > 32768):
            mag_y = -(2 ** 16 - mag_y)
        if (mag_z > 32768):
            mag_z = -(2 ** 16 - mag_z)
        print("x:", mag_x / 10, "uT", "y:", mag_y / 10, "uT", "z", mag_z / 10, "uT")
        return mag_x, mag_y, mag_z

    def DS18B20_TEMP_RD(self):
        rd_cmd = b'\x00\xc6'
        self.DWritePort(rd_cmd)
        tempdata = self.DReadPort(4)
        tmp = bytes_to_num(tempdata) / 100
        if (tmp < 1048575 / 100):
            print("Temperature is:", tmp)
        else:
            print("Temperature is:-", (bytes_to_num(tempdata[2:4]) - 8192) / 100)
        return tmp

    def error_check(self, data_num):

        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        time.sleep(.1)
        self.DWritePort(b'\x00\x06')

        self.DWritePort(num_to_bytes(data_num, 4))
        DAQ_data = b''
        DAQ_data += self.DReadPort(int((data_num) * 2))
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
        return checked_flag, data_num, checked_num

    def PLL_RD(self, addr):
        self.DWritePort(b'\x00\x42')  # 进入到IIR状态
        self.DWritePort(num_to_bytes(addr + 32768, 2))
        data = self.DReadPort(4)
        if data == b'\x80\x15\x00\x00':
            status = 1
        else:
            status = 0
        print(str_to_hexstr(data))
        time.sleep(.01)
        return status

    ### XYJ 20230901重写的LIA函数代码 ###
    def AD_offset_config(self, ch_num, Value):
        # LIA_config = {'type': 'De_fre', 'ch': 1, 'Value': 10.033*10**6}
        LIA_config = {'type': 'AD_offset', 'ch': ch_num, 'Value': Value}
        self.play_info(LIA_config)

    def De_fre_config(self, ch_num, Value):
        # LIA_config = {'type': 'De_fre', 'ch': 1, 'Value': 10.033*10**6}
        LIA_config = {'type': 'De_fre', 'ch': ch_num, 'Value': Value}
        self.play_info(LIA_config)

    def De_phase_config(self, ch_num, Value):
        # LIA_config = {'type': 'De_fre', 'ch': 1, 'Value': 0.0}
        LIA_config = {'type': 'De_phase', 'ch': ch_num, 'Value': Value}
        self.play_info(LIA_config)

    def Modu_fre_config(self, ch_num, Value):
        # LIA_config = {'type': 'De_fre', 'ch': 1, 'Value': 10.033*10**6}
        LIA_config = {'type': 'Modu_fre', 'ch': ch_num, 'Value': Value}
        self.play_info(LIA_config)
        return self.Demodu_freq_gen(Value)

    def sample_rate_config(self, Value):
        # LIA_config = {'type': 'sample_rate', 'Value': 10**3}
        LIA_config = {'type': 'sample_rate', 'Value': Value}
        self.play_info(LIA_config)
        actual_sample_rate, deci_ratio = self.get_actual_sample_rate(Value)
        return actual_sample_rate, deci_ratio

    def set_tc(self, Value):
        # LIA_config = {'type': 'tc', 'Value': 1.0}
        LIA_config = {'type': 'tc', 'Value': Value}
        self.play_info(LIA_config)
        return Value

    def get_actual_mw_freq(self, mw_freq):
        mw_freq_bias = 2600000000 + int((mw_freq - 2600000000) * 0.5) * 2
        return mw_freq_bias

    def get_actual_sample_rate(self, daq_sample_rate):
        '''根据设置的采样率计算真实采样率和运算抽取率'''
        if daq_sample_rate <= 10 ** 5:  # max output sampling rate is 100k(这个可以后面再测测）
            deci_ratio = int(round(self.IIR_o_sample_rate / daq_sample_rate))
        else:
            deci_ratio = int(round(self.IIR_o_sample_rate / 10 ** 5))
        actual_daq_sample_rate = self.IIR_o_sample_rate / deci_ratio
        return actual_daq_sample_rate, deci_ratio

    def IIR_play_Num(self, data_num=100):
        """
        连续测磁模式--单个数据点返回
        设备识别码：DNVCS-API-TotalField-0003
        API-TotalField
        :param data_num: 数据点 int between [1,1E6] 100
        """
        start_time = time.time()
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        self.DWritePort(b'\x00\x04')  # 进入到IIR状态

        time.sleep(self.tc + 0.1)
        self.DWritePort(num_to_bytes(data_num, 4))
        IIR_data = b''
        IIR_data += self.DReadPort(data_num * (6 * 6 * 2 + 8))  # 80 bytes
        # time.sleep(self.tc + 0.1)
        time.sleep(self.tc)
        # print(len(IIR_data))
        data = [[] for _ in range(14)]
        aux_ch1_data = []
        aux_ch2_data = []
        for i in range(data_num):
            data_buf = 0
            for j in range(12):
                data_buf = bytes_to_num(IIR_data[80 * i + (j % 14) * 6:  80 * i + (j % 14 + 1) * 6])
                if data_buf > 2 ** 47 - 1:
                    data_buf = (data_buf - 2 ** 48.0) / 2 ** 48.0
                else:
                    data_buf = data_buf / 2 ** 48.0
                # data_buf = data_buf / 2**64.0
                data[j].append(data_buf * LIA_gain)

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
        # print(aux_ch1_data)
        # print(aux_ch2_data)
        if (hasattr(self, 'last_time')):  # 5.16 以sep时间间隔的方式修改时间戳
            if (time.time() - self.last_time < 4):
                tslist = np.linspace(self.last_time, time.time(), data_num)
            else:
                tslist = np.linspace(time.time() - self.tc - 0.1, time.time(), data_num)
        else:
            tslist = np.linspace(time.time() - self.tc - 0.1, time.time(), data_num)
            print("Start_Time:", time.time() - self.tc - 0.1, time.time())
        self.last_time = time.time()
        # data = [list(tslist)]+data
        data = [list(tslist)] + data
        self.IIR_data = data
        # print('data = ', data)
        # time.sleep(.01)
        # return self.IIR_data[0]
        ts = np.linspace(start_time, time.time(), len(self.IIR_data[0]))
        fn = DATAPATH + '/ExpRealtimeDisplay/' + gettimestr() + '_realtime.csv'
        write_to_csv(fn, [ts] + list(self.IIR_data))
        return self.IIR_data
        # pass

    def doubleCH_getcoe(self, data1,data2,x):
        """
        连续测磁模式--多个数据点返回
        设备识别码：DNVCS-API-TotalField-0005
        API-TotalField
        :param data1: 锁相返回通道 int between [0,14] 0
        :param data2: 锁相返回通道 int between [0,14] 0
        :param x: 锁相返回通道 int between [0,14] 1.134
        """
        data = []
        for i in range(len(data1)):
            data.append(data1[i]-x*data2[i])
        
        return data

    def IIR_play_getpoints(self, ch_id=0, points=10):
        """
        连续测磁模式--多个数据点返回
        设备识别码：DNVCS-API-TotalField-0005
        API-TotalField
        :param ch_id: 锁相返回通道 int between [0,14] 0
        :param points: 数据上传标识 int between [1,1E2] 10
        """
        if (isinstance(ch_id, list)):
            data = [[]]
            for _ in ch_id: data.append([])
        else:
            data = [[],[]]
        if(not self.IIR_run_flag):
            return [[],[]]
        if(self.show_data_queue.qsize() >= points):
            for _ in range(points):
                tmpdata = self.show_data_queue.get()
                data[0].append(tmpdata[0])
                if(isinstance(ch_id, list)):
                    for ch in range(len(ch_id)):
                        data[ch+1].append(tmpdata[1][ch])
                else:
                    data[1].append(tmpdata[1][ch_id])
            return data
        else:
            time.sleep(points/(2*self.sample_rate))
            return self.IIR_play_getpoints(ch_id,points)
        

    def IIR_play_doubleCH_getpoints(self, ch_id1, ch_id2, points=10):
        """
        连续测磁模式--多个数据点返回
        设备识别码：DNVCS-API-TotalField-0005
        API-TotalField
        :param ch_id1: 锁相返回通道1 int between [0,14] 0
        :param ch_id2: 锁相返回通道2 int between [0,14] 1
        :param points: 数据上传标识 int between [1,1E2] 10
        """
        data = [[],[],[]]
        if(not self.IIR_run_flag):
            return [[],[],[]]
        if(self.show_data_queue.qsize() >= points):
            for _ in range(points):
                tmpdata = self.show_data_queue.get()
                data[0].append(tmpdata[0])
                data[1].append(tmpdata[1][ch_id1])
                data[2].append(tmpdata[1][ch_id2])
            return data
        else:
            time.sleep(points/(2*self.sample_rate))
            return self.IIR_play_doubleCH_getpoints(ch_id1,ch_id2,points)

    def thread_IIR_play(self, background_flag=False, socket_upload_flag=False, address=None, port=None, show_flag=True):
        """
        连续测磁模式--单个数据点返回
        设备识别码：DNVCS-API-TotalField-0004
        API-TotalField
        :param background_flag: 是否挂在后台 bool in [Ture,False] False
        :param socket_upload_flag: 数据上传（网口通讯）标识 bool in [Ture,False] False
        :param address: IP地址 str unknown unknown 192.168.1.2
        :param port: 端口 int between [1,1E6] 1111
        :param show_flag: 数据展示标识 bool in [Ture,False] True
        """
        self.IIR_run_flag = True
        self.cursor = 0
        self.raw_data_byte = b''
        self.IIR_str = b''
        self.socket_upload_flag = socket_upload_flag
        self.canvas_show_flag = show_flag
        self.show_data_queue = queue.Queue(maxsize=10000)  # 队列的大小

        ExpDataPath = '/ExpRealtimeDisplay/'
        dirs = [ExpDataPath]
        for di in dirs:
            if not os.path.exists(DATAPATH + di):
                os.mkdir(DATAPATH + di)

        if(socket_upload_flag):
            thd_send = threading.Thread(target=self.thread_IIR_send, args=(address, port,), daemon=True)
            thd_send.start()
        thd_read = threading.Thread(target=self.thread_IIR_read, daemon=True)
        thd_decode = threading.Thread(target=self.thread_IIR_decode, daemon=True)

        thd_read.start()
        time.sleep(1)
        thd_decode.start()
        time.sleep(1)

        if(not background_flag):
            while self.IIR_run_flag:
                print("Qsize & Count", self.show_data_queue.qsize(), self.raw_data_queue.qsize(), self.count, time.time())
                time.sleep(1)
        # self.show_data_queue.queue.clear()  # 在每次运行结束后清空队列
        # self.raw_data_queue.queue.clear()
        # self.DWritePort(b'\x00\x00')
        # self.IIR_continuous_acq_stop()  # 程序正常结束后发送“\x00\x00”停止采集

    def thread_IIR_read(self):
        print('thread_read_pid start')
        # self.thread_record_run_flag = True
        # time.sleep(0.1)
        # self.DWritePort(num_to_bytes(self.board_num, 1) + b'\x08')  # 进入到PID状态
        # self.DWritePort(packs_byte)
        self.DWritePort(b'\x00\x00')
        self.DWritePort(b'\x00\x04')  # 进入到IIR状态
        time.sleep(self.tc + 0.1)
        self.DWritePort(b'\x00\x00\x00\x00')  # 开启IIR连续采集
        while self.IIR_run_flag:
            # while self.run_flag:
            # self.DWritePort(b'\x00\x00')
            # self.DWritePort(b'\x00\x04')  # 进入到IIR状态
            # time.sleep(self.tc + 0.1)
            # self.DWritePort(num_to_bytes(self.IIR_data_num, 4))
            time.sleep(0.08)  # 间隔0.08s采集一次
            # data_str_tmp = self.DReadPort(1600000)
            data_str_tmp = self.DReadPort(self.sample_rate/10 * 80)  # 设置每次获取的点数为采样率/10个点
            self.raw_data_queue.put(data_str_tmp)
            # self.raw_data_byte = self.raw_data_queue.get()
            # print("input")
            # qsize = self.raw_data_queue.qsize()
            # for i in range(qsize):
            # self.raw_data_queue
        # self.thread_record_run_flag = False
        self.raw_data_queue.queue.clear()

    def thread_IIR_send(self, host, port):
        import socket
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # host = '169.254.102.55'
        # host = '169.254.51.191'
        # port = 8001  # 使用与中转模块相同的端口号
        # client_socket.bind((host,port))
        # client_socket.listen(5)
        client_socket.connect((host, port))

        time.sleep(1)
        # client_socket.send(b'1')
        # print(client_socket.recv(1024).decode())
        # client_socket.close()

        while self.IIR_run_flag:
            while not self.show_data_queue.empty():
                # 向上位机发送数据（时间戳+电压）
                s = self.show_data_queue.get()
                # print("Send:",s)
                client_socket.sendall(("SS" + str(s) + "EE").encode())
            time.sleep(0.08)
        client_socket.close()

    def thread_IIR_decode(self):
        self.iir_start_time = time.time()
        IIR_data = [[] for _ in range(14)]
        self.count = 0
        while self.IIR_run_flag:
            # self.IIR_str += self.raw_data_byte
            if (self.raw_data_queue.empty()):
                time.sleep(0.01)
            else:
                self.IIR_str += self.raw_data_queue.get()
                # print(self.IIR_str)
                while len(self.IIR_str) - self.cursor >= 160:
                    for j in range(12):
                        data_buf = bytes_to_num(self.IIR_str[80 + (j % 14) * 6:  80 + (j % 14 + 1) * 6])
                        if data_buf > 2 ** 47 - 1:
                            data_buf = (data_buf - 2 ** 48.0) / 2 ** 48.0
                        else:
                            data_buf = data_buf / 2 ** 48.0
                        # data_buf = data_buf / 2**64.0
                        # print(r"&&--  LIA_gain=", LIA_gain)
                        IIR_data[j].append(data_buf * LIA_gain)

                    ch1_data = bytes_to_num(self.IIR_str[80 + 72: 80 + 76])
                    ch2_data = bytes_to_num(self.IIR_str[80 + 76: 80 + 80])
                    if(not (ch1_data==0 and ch2_data==0)):
                        print("In error ch12")
                        self.cursor += 1
                        continue
                    if ch1_data > 2 ** 15 - 1:
                        ch1_data_buf = (ch1_data - 2 ** 16.0) / 2 ** 16.0
                    else:
                        ch1_data_buf = ch1_data / 2 ** 16.0

                    if ch2_data > 2 ** 15 - 1:
                        ch2_data_buf = (ch2_data - 2 ** 16.0) / 2 ** 16.0
                    else:
                        ch2_data_buf = ch2_data / 2 ** 16.0
                    IIR_data[12].append(ch1_data_buf)
                    IIR_data[13].append(ch2_data_buf)

                    self.cursor += 80
                    # if(ch1_data_buf == 0):
                    # print("IIR_data:",ch1_data_buf,ch2_data_buf)
                    # print("Byte_Data:",self.IIR_str[80: 80 + 72],self.IIR_str[80  + 72: 80  + 76],self.IIR_str[80  + 76: 80  + 80])
                    self.IIR_str = self.IIR_str[self.cursor:]
                    self.cursor = 0

                    self.count += 1
                    if(self.socket_upload_flag or self.canvas_show_flag):
                        self.show_data_queue.put([self.count, [IIR_data[i][-1] for i in range(len(IIR_data))]])

                    if (len(IIR_data[0]) >= self.sample_rate*600): # 每十分钟存储一次数据
                        ts = np.linspace(self.iir_start_time, time.time(), len(IIR_data[0]))
                        fn = DATAPATH + '/ExpRealtimeDisplay/' + gettimestr() + '_realtime.csv' # 连续测磁数据保存
                        write_to_csv(fn,[ts]+list(IIR_data))
                        self.iir_start_time = time.time()
                        # del IIR_data[-1]
                        # ~ write_to_csv(fn,[ts]+list(IIR_data))
                        # # print(len(IIR_data[0]))
                        IIR_data = [[] for _ in range(14)]
        self.run_flag = False
        # 将未满600s的数据保存到文件中，避免数据丢失
        ts = np.linspace(self.iir_start_time, time.time(), len(IIR_data[0]))
        fn = DATAPATH + '/ExpRealtimeDisplay/' + gettimestr() + '_realtime.csv'
        write_to_csv(fn, [ts] + list(IIR_data))

if __name__ == '__main__':
    # LIA_mini_API = LIA_API(libusb_path="/home/pi/Program/NVMagUI/interface/Lockin/usblib/module_64/libusb-1.0.so")
    LIA_mini_API = LIA_API(libusb_path=r"D:\Software Learning\NVMagUI_v202507171703\interface\Lockin\usblib\module_64\libusb-1.0.dll")
    LIA_mini_API.USB_START()

    LIA_mini_API.all_start()

    LIA_mini_API.set_param('lockin_sample_rate', 50)
    LIA_mini_API.play()


    output_offset = 2.7e9 + 50

    ex_ratio = 499999
    rd_ratio = 0
    acq_pts = 1000000

    print(f'EX_RATIO={ex_ratio}, RD_RATIO={rd_ratio}, PID Sample Rate={int(25e6/(rd_ratio + 1) / (ex_ratio + 1))}, Points={acq_pts}')

    LIA_mini_API.PID_config(PID_ch_num=1,
                            set_point=0,
                            output_offset=int((output_offset - 2.6e9) * 0.5 * 1048576),
                            kp=0,
                            ki=0,
                            kd=0,
                            kt=1,
                            Cal_ex=ex_ratio,
                            RD_ex=rd_ratio,
                            PID_LIA_CH=0,
                            )

    LIA_mini_API.PID_config(PID_ch_num=2,
                            set_point=0,
                            output_offset=int((output_offset - 2.6e9) * 0.5 * 1048576),
                            kp=0,
                            ki=0,
                            kd=0,
                            kt=1,
                            Cal_ex=ex_ratio,
                            RD_ex=rd_ratio,
                            PID_LIA_CH=0,
                            )
    LIA_mini_API.PID_enable(1)
    LIA_mini_API.PID_enable(2)


    start_time = time.time()
    data = LIA_mini_API.PID_play(data_num=acq_pts)
    stop_time=time.time()
    print(f'Real Sample Rate={len(data[0][0]) / (stop_time - start_time):.3f} Hz, Real Acquired Points={len(data[0][0])}')
    #
    for i in range(len(data)):
        fig, axes = plt.subplots(nrows=5, ncols=1)
        for j in range(5):
            axes[j].plot(data[i][j])
            axes[j].set_title(f'Data Col[{i},{j}]')
        plt.show()





    # print(LIA_mini_API.error_check(100))


    LIA_mini_API.USB_END()
