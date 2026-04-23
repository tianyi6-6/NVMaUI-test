# coding=UTF-8
# /*************************************************
# Copyright:
# Author:TY
# Date:
# Description:
# **************************************************/

import os
import scipy
import matplotlib.pyplot as plt
import scipy.signal as signal
import configparser
import time
import numpy as np
import serial
import queue
import threading
import queue
import ctypes
from ctypes import (
    c_int, c_void_p, c_ubyte, c_ushort, c_uint,c_uint8,c_uint16, c_char_p, POINTER,
    Structure, byref, create_string_buffer, cast
)
import platform
import re
import logging

DAQ_gain = 1.0
LIA_gain = 1.0

CHUNIT = 4


# 定义常量
LIBUSB_SUCCESS = 0
LIBUSB_ERROR_TIMEOUT = -7
LIBUSB_REQUEST_TYPE_STANDARD = (0x00 << 5)
LIBUSB_RECIPIENT_DEVICE = 0x00

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
    def __init__(self, libusb_path : str):
        # 加载 libusb-1.0 动态库（Linux 路径，Windows 需调整为 libusb-1.0.dll）
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

def str_to_decimals(s):
    # for debug use
    return map(ord, s)


def interger2bin(x, n):
    format(x, 'b').zfill(n)


def cal_real_lcength(send_int_ch, send_int_small_ch):
    """
    For debug use.
    :param send_int_ch: the big unit->0.625, a list
    :param send_int_small_ch:the small unit->0.05, a list
    :return:
    """
    big_unit = 0.625
    small_unit = 0.05
    cals = []
    cals.append(send_int_ch[0] * big_unit + send_int_small_ch[0] * small_unit)
    for i in range(1, len(send_int_ch)):
        if i % 2 == 0:
            # high level
            cals.append(
                send_int_ch[i] * big_unit - send_int_small_ch[i - 1] * small_unit + send_int_small_ch[i] * small_unit)
        else:
            # low level
            cals.append(
                send_int_ch[i] * big_unit - send_int_small_ch[i - 1] * small_unit + send_int_small_ch[i] * small_unit)
    return cals



def str_to_hexstr1(s, space=True):
    ss = s.encode('hex')
    if space:
        sl = [ss[i:i + 2] for i in range(0, len(ss), 2)]
        return ''.join(sl)
    else:
        return ss


def bytes_to_numV1(bytes_):
    return np.frombuffer((8 - len(bytes_)) * '\x00' + bytes_, dtype='>u8')[0]


def bytes_to_numV2(bytes_, high_head=True):
    pass


def bytes_to_numT1(bytes_):
    num = bytes_to_num(bytes_)
    if num > 32768:
        Num = num - 65536
    else:
        Num = num
    return Num




class config_mini(USBController):
    def __init__(self, libusb_path:str, *args, **kwargs):
        # CP2013GM.__init__(self, portx=portx, bps=bps)
        self.read_endpoint = 0x86  # 上位机←设备
        self.write_endpoint = 0x02  # 上位机→设备

        self.bulk_buffer_packet_size = 512

        self.vendor_id = 0x04b4
        self.product_id = 0x00f1

        USBController.__init__(self, libusb_path=libusb_path)

        self.ADC_sample_rate = 25.0 * np.power(10, 6)
        self.IIR_o_sample_rate = 25.0 * np.power(10, 6)# orig IIR sample rate unit:Sps
        self.daq_sample_rate = 1.0*10**3           # output sample rate unit:Sps
        self.De_fre = {'ch1': 1000, 'ch2': 2200, 'ch3': 3500, 'ch4': 4800}
        self.De_phase = {'ch1': 0.0, 'ch2': 0.0, 'ch3': 0.0, 'ch4': 0.0, 'ch5': 0.0, 'ch6': 0.0, 'ch7': 0.0, 'ch8': 0.0}
        self.Modu_fre = {'ch1': 100000, 'ch2': 100000, 'ch3': 100000, 'ch4': 100000}
        self.Modu_phase = {'ch1': 0.0, 'ch2': 0.0, 'ch3': 0.0, 'ch4': 0.0}
        self.AD_offset = {'ch1': -0, 'ch2': -0, 'ch3': -0, 'ch4': -0}
        self.DA_offset = {'ch1': 0.0, 'ch2': 0.0}
        self.sample_rate = 10.0
        self.tc = 0.002
        self.raw_data_queue = queue.Queue(maxsize=5000)
        self.data_queue = queue.Queue(maxsize=5000)
        self.exp_UI = None # 通过UI启动，可以反向控制UI的界面配置

    def SBZZ(self):
        path_ = 'PLL_WR_REG.txt'
        f = open(path_, 'r+')
        data = f.read()
        data_buf = data.split(',\n')
        for i in range(len(data_buf)):
            temp = int(data_buf[i], 16)
            buf = num_to_bytes(temp, 4)
            self.DWritePort(b'\x00\x41')
            self.DWritePort(buf)
            time.sleep(.1)

    def ioconfig(self, io_ch, coup, match, Attenuat, DA_Gain, AD_Gain):
        if io_ch == 1:
            self.DWritePort(b'\x00\xB8')
            time.sleep(.01)
            data = 0
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x00\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(0指的IO作为输出IO，1指的是IO作为输入IO)
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
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x01\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(0指的IO作为输出IO，1指的是IO作为输入IO)
            time.sleep(.01)
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            for i in range(4):
                if match['ch' + str(4 - i)] == '50':
                    data = data * 4 + 2
                elif match['ch' + str(4 - i)] == '1M':
                    data = data * 4 + 1
                else:
                    print('match config error')
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x15' + num_to_bytes(data, 1))
            time.sleep(.01)
        elif io_ch == 2:
            data = 0
            self.DWritePort(b'\x00\x43')  # IO扩展器写入指令
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x00\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(1指的IO作为输出IO，0指的是IO作为输入IO)
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
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x01\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(1指的IO作为输出IO，0指的是IO作为输入IO)
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
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x00\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(1指的IO作为输出IO，0指的是IO作为输入IO)
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
            self.DWritePort(num_to_bytes(io_ch - 1, 1) + b'\x40\x01\x00')  # 第一个byte指定IO扩展器，第二个bytes指定读还是写,40是写入,41是读出,第三个byte指的是地址(00是IO口方向),第四个byte指的是写入的数据(1指的IO作为输出IO，0指的是IO作为输入IO)
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
            g_data = int(np.round(amp_g/0.055744))
        else:
            g_data = int(np.floor(amp_g/(0.055744*7.079458)+128))
        g_code = num_to_bytes(g_data, bytenum=1)
        g_ch_code = num_to_bytes(amp_no-1, bytenum=1)
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

    def SWITCH_SET(self,switch_num):
        self.DWritePort(b"\x00\xc7")
        if(switch_num==0):
            self.DWritePort(b"\xff\x00")
        else:
            self.DWritePort(b"\x00\xff")
        return 0

    def speed_set(self,speed):
        self.DWritePort(b"\x00\xc5")
        speed_data=int(25000000/speed)
        self.DWritePort(num_to_bytes(speed_data,1))
        return 0

    def UACM_config(self,config_data,receive_num):
        # self.DWritePort(b"\x00\x99")
        num=len(config_data)
        print(num_to_bytes((144+num), 1)+num_to_bytes((receive_num),1))
        self.DWritePort(num_to_bytes((144+num), 1)+num_to_bytes((receive_num), 1))
        self.DWritePort(config_data)
        self.DReadPort(receive_num)
        return 0

    def UACM_send(self,send_data):
        self.DWritePort(b"\x00\x99")
        num=len(send_data)
        self.DWritePort(num_to_bytes(num, 2))
        self.DWritePort(send_data)
        return 0

    def para_set(self, ADC_offset_ch1, ADC_offset_ch2, DDC_para_list, MODU_para_list, ch_num):
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

        # DDC_para set
        # ([0])freq unit: Hz
        # ([1])phase unit: degree (from pi-->degree)
        actral_fre_ch1 = self.Demodu_freq_gen(DDC_para_list[0])
        actral_fre_ch2 = self.Demodu_freq_gen(DDC_para_list[3])
        actral_fre_ch3 = self.Demodu_freq_gen(DDC_para_list[6])
        actral_fre_ch4 = self.Demodu_freq_gen(DDC_para_list[9])
        digi_freq_ch1 = int(actral_fre_ch1 * (2.0**48)/self.ADC_sample_rate)
        # print 'digi_freq_ch1', DDC_para_list[0], digi_freq_ch1
        digi_phase_ch1 = int(DDC_para_list[1]*(2.0**48)/360.0)
        digi_phase_ch2 = int(DDC_para_list[2]*(2.0**48)/360.0)

        digi_freq_ch2 = int(actral_fre_ch2 * (2.0**48)/self.ADC_sample_rate)
        digi_phase_ch3 = int(DDC_para_list[4]*(2.0**48)/360.0)
        digi_phase_ch4 = int(DDC_para_list[5]*(2.0**48)/360.0)

        digi_freq_ch3 = int(actral_fre_ch3 * (2.0**48)/self.ADC_sample_rate)
        digi_phase_ch5 = int(DDC_para_list[7]*(2.0**48)/360.0)
        digi_phase_ch6 = int(DDC_para_list[8]*(2.0**48)/360.0)

        digi_freq_ch4 = int(actral_fre_ch4 * (2.0**48)/self.ADC_sample_rate)
        digi_phase_ch7 = int(DDC_para_list[10]*(2.0**48)/360.0)
        digi_phase_ch8 = int(DDC_para_list[11]*(2.0**48)/360.0)

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

        self.DWritePort(num_to_bytes(ch_num, 1) + b'\x20')
        # input()
        time.sleep(.01)
        self.DWritePort(ADC_offset_byte_ch1 + ADC_offset_byte_ch2\
                            + DDC_word_ch1 + DDC_word_ch2 + DDC_word_ch3 + DDC_word_ch4 + modu_word_ch1 + modu_word_ch2\
                            + modu_word_ch3 + modu_word_ch4)
        # input()
        time.sleep(0.01)

    def FM_freq_gen(self, fre, phase):
        # fre 精度保留到1e-5
        a = int(25e6 / fre)
        # print('Fre = ', fre, a)
        frange_code = int(2**48 / a) * a
        fre_step = int(2**48 / a)
        phase_code = phase * (frange_code)/360.0
        # print(fre_step, phase_code, frange_code)
        # print('FM_Fre: ideal Frequency = ', fre, 'actual Frequency = ', fre_step / frange_code * 25e6)
        return fre_step, phase_code, frange_code

    def Demodu_freq_gen(self, fre):
        # fre 精度保留到1e-5
        a = int(25e6 / fre)
        frange_code = int(2**48 / a) * a
        fre_step = int(2**48 / a)
        print('Demodu_Fre: ideal Frequency = ', fre, 'actual Frequency = ', fre_step / frange_code * 25e6)
        return fre_step / frange_code * 25e6

    def _LP1_coe(self, f0, fs=25*10**6, k=1):
        # expression: H(s)=K/(1+s/2pi f0)
        # return coe: a1/a0, b0/a0, b1/a0
        # f0为拐点频率=1/tc，fs为IIR滤波器输入数据采样率，k为比例系数（默认为1）
        f_conv = 1*np.pi*f0/fs
        # print('f_conv is ', f_conv)
        # print(1/(1+f_conv))
        a1_vs_a0 = (1-f_conv)/(1+f_conv)
        b0_vs_a0 = k*f_conv/(1+f_conv)
        b1_vs_a0 = 1*b0_vs_a0
        return [a1_vs_a0], [b0_vs_a0, b1_vs_a0]

    def IIR_configure(self, tc_ch1, tc_ch2, ch_num):
        # print('\ninto IIR configuration')
        fs = 25.0 * np.power(10, 6)
        # coe_width = 32
        coe_a_array_1, coe_b_array_1 = self._LP1_coe(1/tc_ch1, fs=fs)
        coe_a_array_2, coe_b_array_2 = self._LP1_coe(1/tc_ch2, fs=fs)
        # print("iir coe = ", coe_a_array_1, coe_b_array_1)
        self.IIR_sub_config(a1_1=coe_a_array_1[0], b0_1=coe_b_array_1[0], a1_2=coe_a_array_2[0], b0_2=coe_b_array_2[0], ch_num=ch_num)

    def IIR_sub_config(self, a1_1, b0_1, a1_2, b0_2, ch_num):
        coe_width = 48
        fill_bytes = num_to_bytes(0, 2)
        coe_a1_bytes_ch1 = num_to_bytes(int(a1_1*2**coe_width), 6) + fill_bytes
        coe_b0_bytes_ch1 = num_to_bytes(int(b0_1*2**coe_width), 6) + fill_bytes
        # # coe_b0_bytes_ch11 = fill_bytes + num_to_bytes(int(b0_1*2**coe_width), 4)
        # print "******************&*&*&&*&*&*&**&*&*&&*&****************************"
        # print a1_1
        # print a1_1*2**coe_width
        # print b0_1
        # print b0_1*2**(coe_width+8)
        # print str_to_hexstr(coe_a1_bytes_ch1)
        # print str_to_hexstr(coe_b0_bytes_ch1)
        # print "******************&*&*&&*&*&*&**&*&*&&*&****************************"
        coe_a1_bytes_ch2 = num_to_bytes(int(a1_2*2**coe_width), 6) + fill_bytes
        coe_b0_bytes_ch2 = num_to_bytes(int(b0_2*2**coe_width), 6) + fill_bytes

        cmd_iir_con = num_to_bytes(ch_num, 1) + b'\x21'
        wr_word = cmd_iir_con + coe_a1_bytes_ch1 + coe_b0_bytes_ch1 + coe_a1_bytes_ch2 + coe_b0_bytes_ch2
        # print(str_to_hexstr(wr_word))
        self.DWritePort(wr_word)
        time.sleep(0.1)

    def IIR_DAQ_configure(self, filter_order_ch1, filter_order_ch2, daq_sample_rate, ch_num):
        filter_order_bytes_ch1 = num_to_bytes(filter_order_ch1-1, 1)
        filter_order_bytes_ch2 = num_to_bytes(filter_order_ch2-1, 1)
        if daq_sample_rate <= 10**5:    # max output sampling rate is 100k(这个可以后面再测测）
            deci_ratio = int(round(self.IIR_o_sample_rate/daq_sample_rate))
        else:
            deci_ratio = int(round(self.IIR_o_sample_rate/10**5))
            # print('daq_sample_rate is set to 100k')
        self.daq_sample_rate = self.IIR_o_sample_rate/deci_ratio
        deci_ratio_bytes = num_to_bytes(deci_ratio-1, 3)
        cmd_iir_con = num_to_bytes(ch_num, 1) + b'\x22'
        wr_word = cmd_iir_con + filter_order_bytes_ch1 + filter_order_bytes_ch2 + deci_ratio_bytes
        # print(str_to_hexstr(wr_word))
        self.DWritePort(wr_word)
        time.sleep(0.05)
        return self.daq_sample_rate

    def play_info(self, *args):
        for i in args:
            self.dic = i

        if 'type' in self.dic:
            if self.dic['type'] == 'De_fre':
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


    def play(self, ch_num):
        set_mVpp_str = ''       # 输入波源幅度值文件名
        freq_c_ddc = ''         # 频率文件名

        # IIR采集幅度换算系数，对应配置为（1/10衰减，AC耦合，可变放大器均为\x12的单位增益配置）
        # IIR配置为tc=0.01s，滤波器阶数为4，由于滤波器保持DC信号归一化，因此该系数对不同tc以及阶数均可使用。
        hex2v_ch1 = 8.78398552654686E-20
        hex2v_ch2 = 9.28217449741933E-20
        hex2v_ch3 = 9.21083311316624E-20
        hex2v_ch4 = 9.35505450096255E-20

        freq = 10.033*10**6
        # freq = 1000*10**3
        f_demodulation_1 = self.De_fre['ch1']  # NCO解调频率以及DDS1调制频率设置
        f_demodulation_2 = self.De_fre['ch2']  # NCO解调频率设置
        f_demodulation_3 = self.De_fre['ch3']  # NCO解调频率以及DDS2调制频率设置
        f_demodulation_4 = self.De_fre['ch4']  # NCO解调频率设置
        # print 'frequency of demodulation_1 is ', f_demodulation_1
        # print 'frequency of demodulation_2 is ', f_demodulation_2
        # print 'frequency of demodulation_3 is ', f_demodulation_3
        # print 'frequency of demodulation_4 is ', f_demodulation_4

        phase_ddc_1 = self.De_phase['ch1']    # NCO解调相位设置
        phase_ddc_2 = self.De_phase['ch2']    # NCO解调相位设置
        phase_ddc_3 = self.De_phase['ch3']    # NCO解调相位设置
        phase_ddc_4 = self.De_phase['ch4']    # NCO解调相位设置
        phase_ddc_5 = self.De_phase['ch5']    # NCO解调相位设置
        phase_ddc_6 = self.De_phase['ch6']    # NCO解调相位设置
        phase_ddc_7 = self.De_phase['ch7']    # NCO解调相位设置
        phase_ddc_8 = self.De_phase['ch8']    # NCO解调相位设置
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
                                      ch4_modulation_fre, ch4_modulation_phase], ch_num=ch_num)

        print("DAC_Param:", self.AD_offset['ch1'], self.AD_offset['ch2'],
                       "DDC_para_list",[f_demodulation_1, phase_ddc_1, phase_ddc_2,
                                      f_demodulation_2, phase_ddc_3, phase_ddc_4,
                                      f_demodulation_3, phase_ddc_5, phase_ddc_6,
                                      f_demodulation_4, phase_ddc_7, phase_ddc_8],
                       "MODU_para_list",[ch1_modulation_fre, ch1_modulation_phase,
                                      ch2_modulation_fre, ch2_modulation_phase,
                                      ch3_modulation_fre, ch3_modulation_phase,
                                      ch4_modulation_fre, ch4_modulation_phase], ch_num)

        self.daq_sample_rate = self.sample_rate   #返回数据采样率 单位：sps
        tc_set = self.tc   # unit: s 注意一定要使用小数形式，否则可能计算出错
        set_mVpp_str = 'defaultAmp'  # 保存幅度文件名设置
        freq_c_ddc = 'defaultFreq'  # 保存频率文件名设置
        self.IIR_configure(tc_ch1=tc_set, tc_ch2=tc_set, ch_num=ch_num)  # IIR滤波器截止频率设置
        print("tc_set =", tc_set)
        self.IIR_DAQ_configure(filter_order_ch1=4, filter_order_ch2=4, daq_sample_rate=self.daq_sample_rate, ch_num=ch_num)    # IIR滤波器阶数及降采样率设置

    def program_start(self):
        self.DWritePort(b'\x00\x06')
        self.DWritePort(b'\x00\x00\x00\x00')  # total num input

    def DAQ_play(self, ch_num, data_num, extract_ratio):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        # input()
        time.sleep(.001)
        self.DWritePort(num_to_bytes(ch_num, 1) + b'\x01')  # 进入到DAQ状态
        self.DWritePort(num_to_bytes(data_num, 4))
        time.sleep(.001)
        self.DWritePort(num_to_bytes(extract_ratio, 2))  # 进入到DAQ状态

        DAQ_data = b''
        DAQ_data += self.DReadPort(data_num * 4 * 8)
        # DAQ_data += self.DReadPort(16)
        print(DAQ_data)
        data = [[] for i in range(16)]

        for i in range(data_num):
            data_buf = 0
            for j in range(16):
                data_buf = bytes_to_num(DAQ_data[32 * i + (j % 16) * 2: 32 * i + (j % 16 + 1) * 2])
                print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                if data_buf > 32767:
                    data_buf = (data_buf - 65536) / 65536.0
                else:
                    data_buf = data_buf / 65536.0
                data[j].append(data_buf * DAQ_gain)

        self.Daq_data = data

        return self.Daq_data

    def daq_plot(self):
        x = np.array(range(len(self.Daq_data[0]))) * len(self.Daq_data[0]) / self.ADC_sample_rate
        # plt.plot(x, self.Daq_data[0], label='Board8_Ch1')
        # plt.plot(x, self.Daq_data[1], label='Board8_Ch2')
        # plt.plot(x, self.Daq_data[2], label='Board7_Ch1')
        # plt.plot(x, self.Daq_data[3], label='Board7_Ch2')
        # plt.plot(x, self.Daq_data[4], label='Board6_Ch1')
        # plt.plot(x, self.Daq_data[5], label='Board6_Ch2')
        # plt.plot(x, self.Daq_data[6], label='Board5_Ch1')
        # plt.plot(x, self.Daq_data[7], label='Board5_Ch2')
        # plt.plot(x, self.Daq_data[8], label='Board4_Ch1')
        # plt.plot(x, self.Daq_data[9], label='Board4_Ch2')
        # plt.plot(x, self.Daq_data[10], label='Board3_Ch1')
        # plt.plot(x, self.Daq_data[11], label='Board3_Ch2')
        plt.plot(x, self.Daq_data[12], label='Board2_Ch1')
        # plt.plot(x, self.Daq_data[13], label='Board2_Ch2')
        plt.plot(x, self.Daq_data[14], label='Board1_Ch1')
        # plt.plot(x, self.Daq_data[15], label='Board1_Ch2')
        plt.legend()
        plt.show()

    def AUXDAQ_play(self, ch_num, data_num):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        # input()
        time.sleep(.001)
        self.DWritePort(num_to_bytes(ch_num, 1) + b'\x09')  # 进入到DAQ状态
        self.DWritePort(num_to_bytes(data_num, 4))
        time.sleep(.001)
        # self.DWritePort(num_to_bytes(extract_ratio, 2))  # 进入到DAQ状态

        AUXDAQ_data = b''
        AUXDAQ_data += self.DReadPort(data_num * 8 * 8)
        # DAQ_data += self.DReadPort(16)
        print(AUXDAQ_data)
        data = [[] for i in range(16)]

        for i in range(data_num):
            data_buf = 0
            for j in range(16):
                data_buf = bytes_to_num(AUXDAQ_data[64 * i + (j % 16) * 4: 64 * i + (j % 16 + 1) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                if data_buf > 2 ** 23 - 1:
                    data_buf = (data_buf - 2 ** 24) / 2 ** 24
                else:
                    data_buf = data_buf / 2 ** 24
                data[j].append(data_buf)

        self.AUXDaq_data = data

        return self.AUXDaq_data

    def auxdaq_plot(self):
        x = np.array(range(len(self.AUXDaq_data[0]))) * len(self.AUXDaq_data[0]) / 100
        # plt.plot(x, self.AUXDaq_data[0], label='Board8_Ch1')
        # plt.plot(x, self.AUXDaq_data[1], label='Board8_Ch2')
        # plt.plot(x, self.AUXDaq_data[2], label='Board7_Ch1')
        # plt.plot(x, self.AUXDaq_data[3], label='Board7_Ch2')
        # plt.plot(x, self.AUXDaq_data[4], label='Board6_Ch1')
        # plt.plot(x, self.AUXDaq_data[5], label='Board6_Ch2')
        plt.plot(x, self.AUXDaq_data[6], label='Board5_Ch1')
        plt.plot(x, self.AUXDaq_data[7], label='Board5_Ch2')
        plt.plot(x, self.AUXDaq_data[8], label='Board4_Ch1')
        plt.plot(x, self.AUXDaq_data[9], label='Board4_Ch2')
        plt.plot(x, self.AUXDaq_data[10], label='Board3_Ch1')
        plt.plot(x, self.AUXDaq_data[11], label='Board3_Ch2')
        plt.plot(x, self.AUXDaq_data[12], label='Board2_Ch1')
        plt.plot(x, self.AUXDaq_data[13], label='Board2_Ch2')
        plt.plot(x, self.AUXDaq_data[14], label='Board1_Ch1')
        plt.plot(x, self.AUXDaq_data[15], label='Board1_Ch2')
        plt.legend()
        plt.show()

    def flux_play_UI(self, board_num, data_num):
        """
        单通道磁通门读回
        设备识别码：DNVCS-API-Multichannel-0001
        API-Multichannel
        :param board_num: 板卡序号 int between [1，8] 1
        :param data_num: 磁通门数据采集点数 int between [0,10000] 10
        """
        self.DWritePort(b'\x00\x00')
        time.sleep(.001)
        self.DWritePort(num_to_bytes(board_num, 1) + b'\xAB')  # 进入到FLUX状态
        # self.DWritePort(num_to_bytes((data_num + 1), 4))  # 进入到FLUX状态
        self.DWritePort(num_to_bytes(data_num + 1, 4))  # 进入到FLUX状态
        FLUX_buf = b''
        flux_counter = 0
        buf_list = [[]] * 8
        flux_data = [[]] * 8
        self.flux_play_flag = True
        vref = 12.5
        gain = 1
        while self.flux_play_flag:
            FLUX_buf += self.DReadPort(16 * 8 * 2)
            flux_counter += 2
            for flux_ch in range(len(flux_data)):
                buf_list[flux_ch].append(FLUX_buf[(flux_ch - 1) * 16 : flux_ch * 16 - 1])
                for flux_data_num in range(len(flux_data[flux_ch])):
                    flux_data[flux_ch].append(buf_list[flux_ch][flux_data_num])

            f_data1 = flux_data[board_num]
            self.exp_UI.canvas_setplot(0, range(len(f_data1)), f_data1)
            self.exp_UI.log_exp.log_insert_new("Flux_data", f_data1)

    def FLUX_play(self, ch_num, data_num):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        time.sleep(.001)
        self.DWritePort(num_to_bytes(ch_num, 1) + b'\xAB')  # 进入到FLUX状态
        # self.DWritePort(num_to_bytes((data_num + 1), 4))  # 进入到FLUX状态
        self.DWritePort(num_to_bytes(data_num+1 , 4))  # 进入到FLUX状态
        FLUX_data = b''
        FLUX_data += self.DReadPort((data_num) * 16 * 8)
        # print(FLUX_data)
        FLUX_data1 = []
        FLUX_data2 = []
        FLUX_data3 = []
        FLUX_data4 = []
        FLUX_data5 = []
        FLUX_data6 = []
        FLUX_data7 = []
        FLUX_data8 = []
        for i in range(data_num):
            FLUX_data1.append(FLUX_data[i * 128:15 + i * 128])
            FLUX_data2.append(FLUX_data[16 + i * 128:31 + i * 128])
            FLUX_data3.append(FLUX_data[32 + i * 128:47 + i * 128])
            FLUX_data4.append(FLUX_data[48 + i * 128:63 + i * 128])
            FLUX_data5.append(FLUX_data[64 + i * 128:79 + i * 128])
            FLUX_data6.append(FLUX_data[80 + i * 128:95 + i * 128])
            FLUX_data7.append(FLUX_data[96 + i * 128:111 + i * 128])
            FLUX_data8.append(FLUX_data[112 + i * 128:127 + i * 128])
        FLUX1_data = b''.join(FLUX_data1)
        start_num = 0
        # input()
        while 1:
            if FLUX1_data[start_num:start_num + 1] != b'\xcc':
                # print(start_num, FLUX1_data[start_num:start_num + 1])
                if (start_num < 15):
                    start_num = start_num + 1
                else:
                    break
                # input()
            else:
                # print("break1", start_num)
                break
        FLUX1_data = FLUX1_data[start_num:start_num + 15 * data_num]

        FLUX2_data = b''.join(FLUX_data2)
        start_num = 0
        while 1:
            if FLUX2_data[start_num:start_num + 1] != b'\xcc':
                if (start_num < 15):
                    start_num = start_num + 1
                else:
                    break
                # print(start_num,FLUX2_data[start_num:start_num+1])
            else:
                # print("break2",start_num)
                break
        FLUX2_data = FLUX2_data[start_num:start_num + 15 * data_num]

        FLUX3_data = b''.join(FLUX_data3)
        print("FLUX3_data",FLUX3_data)
        start_num = 0
        while 1:
            if FLUX3_data[start_num:start_num + 1] != b'\xcc':
                if (start_num < 15):
                    start_num = start_num + 1
                else:
                    break
                # print(start_num,FLUX3_data[start_num:start_num+1])
            else:
                # print("break3",start_num)
                break
        FLUX3_data = FLUX3_data[start_num:start_num + 15 * data_num]

        FLUX4_data = b''.join(FLUX_data4)
        start_num = 0
        while 1:
            if FLUX4_data[start_num:start_num + 1] != b'\xcc':
                if (start_num < 15):
                    start_num = start_num + 1
                else:
                    break
                # print(start_num,FLUX4_data[start_num:start_num+1])
            else:
                # print("break4",start_num)
                break
        FLUX4_data = FLUX4_data[start_num:start_num + 15 * data_num]

        FLUX5_data = b''.join(FLUX_data5)
        start_num = 0
        while 1:
            if FLUX5_data[start_num:start_num + 1] != b'\xcc':
                if (start_num < 15):
                    start_num = start_num + 1
                else:
                    break
                # print(start_num,FLUX5_data[start_num:start_num+1])
            else:
                # print("break5",start_num)
                break
        FLUX5_data = FLUX5_data[start_num:start_num + 15 * data_num]

        FLUX6_data = b''.join(FLUX_data6)
        start_num = 0
        while 1:
            if FLUX6_data[start_num:start_num + 1] != b'\xcc':
                if (start_num < 15):
                    start_num = start_num + 1
                else:
                    break
                # print(start_num,FLUX6_data[start_num:start_num+1])
            else:
                # print("break6",start_num)
                break
        FLUX6_data = FLUX6_data[start_num:start_num + 15 * data_num]

        FLUX7_data = b''.join(FLUX_data7)
        start_num = 0
        while 1:
            if FLUX7_data[start_num:start_num + 1] != b'\xcc':
                if (start_num < 15):
                    start_num = start_num + 1
                else:
                    break
                # print(start_num,FLUX7_data[start_num:start_num+1])
            else:
                # print("break7",start_num)
                break
        FLUX7_data = FLUX7_data[start_num:start_num + 15 * data_num]

        FLUX8_data = b''.join(FLUX_data8)
        start_num = 0
        while 1:
            if FLUX8_data[start_num:start_num + 1] != b'\xcc':
                if (start_num < 15):
                    start_num = start_num + 1
                else:
                    break
                # print(start_num,FLUX8_data[start_num:start_num+1])
            else:
                # print("break8",start_num)
                break
        FLUX8_data = FLUX8_data[start_num:start_num + 15 * data_num]
        # print("FLUX1_data", FLUX1_data)
        # print(FLUX2_data)
        # print(FLUX3_data)s
        # print(FLUX4_data)
        # print(FLUX5_data)
        data1 = [[] for i in range(3)]
        data2 = [[] for i in range(3)]
        data3 = [[] for i in range(3)]
        data4 = [[] for i in range(3)]
        data5 = [[] for i in range(3)]
        data6 = [[] for i in range(3)]
        data7 = [[] for i in range(3)]
        data8 = [[] for i in range(3)]
        vref = 12.5
        gain = 1
        for i in range(data_num-1):
            data_buf = 0
            for j in range(3):
                data_buf = bytes_to_num(FLUX1_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                data1[j].append(data_buf)
        for i in range(data_num-1):
            data_buf = 0
            for j in range(3):
                data_buf = bytes_to_num(FLUX2_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                data2[j].append(data_buf)
        for i in range(data_num-1):
            data_buf = 0
            for j in range(3):
                data_buf = bytes_to_num(FLUX3_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                data3[j].append(data_buf)
        for i in range(data_num-1):
            data_buf = 0
            for j in range(3):
                data_buf = bytes_to_num(FLUX4_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                data4[j].append(data_buf)
        for i in range(data_num-1):
            data_buf = 0
            for j in range(3):
                data_buf = bytes_to_num(FLUX5_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                data5[j].append(data_buf)
        for i in range(data_num-1):
            data_buf = 0
            for j in range(3):
                data_buf = bytes_to_num(FLUX6_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                data6[j].append(data_buf)
        for i in range(data_num-1):
            data_buf = 0
            for j in range(3):
                data_buf = bytes_to_num(FLUX7_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                data7[j].append(data_buf)
        for i in range(data_num-1):
            data_buf = 0
            for j in range(3):
                data_buf = bytes_to_num(FLUX8_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                data8[j].append(data_buf)
        # path_ = 'data/' + str(time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())) + 'FLUX1data.csv'
        # print(data1[1],data1[2])
        # csv_save(path_, data1[1],data1[2])
        # print(FLUX1_data)
        # print(FLUX2_data)
        # print(FLUX3_data)
        # print(FLUX4_data)
        # print(FLUX5_data)
        self.FLUX_data1 = data1
        self.FLUX_data2 = data2
        self.FLUX_data3 = data3
        self.FLUX_data4 = data4
        self.FLUX_data5 = data5
        self.FLUX_data6 = data6
        self.FLUX_data7 = data7
        self.FLUX_data8 = data8

        # return self.FLUX_data

    def FLUX_plot(self):
        # exit()
        x = np.array(range(len(self.FLUX_data1[0]))) * len(self.FLUX_data1[0]) / 1000
        # plt.plot(x, self.FLUX_data1[0], label='Board1_x')
        # plt.plot(x, self.FLUX_data1[1], label='Board1_y')
        # plt.plot(x, self.FLUX_data1[2], label='Board1_z')
        # plt.plot(x, self.FLUX_data2[0], label='Board2_x')
        # plt.plot(x, self.FLUX_data2[1], label='Board2_y')
        # plt.plot(x, self.FLUX_data2[2], label='Board2_z')
        plt.plot(x, self.FLUX_data3[0], label='Board3_x')
        plt.plot(x, self.FLUX_data3[1], label='Board3_y')
        plt.plot(x, self.FLUX_data3[2], label='Board3_z')
        plt.plot(x, self.FLUX_data4[0], label='Board4_x')
        plt.plot(x, self.FLUX_data4[1], label='Board4_y')
        plt.plot(x, self.FLUX_data4[2], label='Board4_z')
        plt.ylabel('uT')
        plt.plot(x, self.FLUX_data5[0], label='Board5_x')
        plt.plot(x, self.FLUX_data5[1], label='Board5_y')
        plt.plot(x, self.FLUX_data5[2], label='Board5_z')
        # plt.plot(x, self.FLUX_data6[0], label='Board6_x')
        # plt.plot(x, self.FLUX_data6[1], label='Board6_y')
        # plt.plot(x, self.FLUX_data6[2], label='Board6_z')
        # plt.plot(x, self.FLUX_data7[0], label='Board7_x')
        # plt.plot(x, self.FLUX_data7[1], label='Board7_y')
        # plt.plot(x, self.FLUX_data7[2], label='Board7_z')
        # plt.plot(x, self.FLUX_data8[0], label='Board8_x')
        # plt.plot(x, self.FLUX_data8[1], label='Board8_y')
        # plt.plot(x, self.FLUX_data8[2], label='Board8_z')
        plt.legend()
        plt.show()

    def IIR_play(self, ch_num, data_num, CW_mode=False):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')
        self.DWritePort(num_to_bytes(ch_num, 1) + b'\x04')  # 进入到IIR状态
        if CW_mode == False:
            time.sleep(self.tc*6)
        else:
            # time.sleep(self.tc)
            pass
        self.DWritePort(num_to_bytes(data_num, 4))

        board1_IIR_data = b''
        board2_IIR_data = b''
        board3_IIR_data = b''
        board4_IIR_data = b''
        board5_IIR_data = b''
        board6_IIR_data = b''
        board7_IIR_data = b''
        board8_IIR_data = b''
        IIR_DATA = b''
        IIR_DATA += self.DReadPort(data_num*640)
        # print(IIR_DATA)
        for i in range(data_num):
            # board1_IIR_data += self.DReadPort((6 * 6 * 4 + 8))
            board1_IIR_data += IIR_DATA[i*640:80+i*640]
            # print("BOARD1_DATA = ",board1_IIR_data,len(board1_IIR_data))
            board2_IIR_data += IIR_DATA[80+i*640:80*2+i*640]
            # print("BOARD2_DATA = ",board2_IIR_data)
            board3_IIR_data += IIR_DATA[80*2+i*640:80*3+i*640]
            # print("BOARD3_DATA = ",board3_IIR_data)
            board4_IIR_data += IIR_DATA[80*3+i*640:80*4+i*640]
            # print("BOARD4_DATA = ",board4_IIR_data)
            board5_IIR_data += IIR_DATA[80*4+i*640:80*5+i*640]
            # print("BOARD5_DATA = ",board5_IIR_data)
            board6_IIR_data += IIR_DATA[80*5+i*640:80*6+i*640]
            # print("BOARD6_DATA = ",board6_IIR_data)
            board7_IIR_data += IIR_DATA[80*6+i*640:80*7+i*640]
            # print("BOARD7_DATA = ",board7_IIR_data)
            board8_IIR_data += IIR_DATA[80*7+i*640:80*8+i*640]
            # print("BOARD8_DATA = ",board8_IIR_data)
            # print len(IIR_data)
        # print('data receive down.')
        # time.sleep(1.0/self.sample_rate + 0.001)
        board1_data = [[] for i in range(26)]
        board2_data = [[] for i in range(26)]
        board3_data = [[] for i in range(26)]
        board4_data = [[] for i in range(26)]
        board5_data = [[] for i in range(26)]
        board6_data = [[] for i in range(26)]
        board7_data = [[] for i in range(26)]
        board8_data = [[] for i in range(26)]
        board1_aux_ch1_data = []
        board1_aux_ch2_data = []
        board2_aux_ch1_data = []
        board2_aux_ch2_data = []
        board3_aux_ch1_data = []
        board3_aux_ch2_data = []
        board4_aux_ch1_data = []
        board4_aux_ch2_data = []
        board5_aux_ch1_data = []
        board5_aux_ch2_data = []
        board6_aux_ch1_data = []
        board6_aux_ch2_data = []
        board7_aux_ch1_data = []
        board7_aux_ch2_data = []
        board8_aux_ch1_data = []
        board8_aux_ch2_data = []
        for i in range(data_num):
            data_buf = 0
            for j in range(12):
                data_buf = bytes_to_num(board1_IIR_data[80 * i + (j % 12) * 6:  80* i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board1_data[j].append(data_buf * LIA_gain)

            ch1_data = bytes_to_num(board1_IIR_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board1_IIR_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board1_data[12].append(ch1_data_buf)
            board1_data[13].append(ch2_data_buf)
            board1_aux_ch1_data.append(ch1_data_buf)
            board1_aux_ch2_data.append(ch2_data_buf)
            # print('board1 data transform complete!!!!')
        for i in range(data_num):
            data_buf = 0
            for j in range(12):
                data_buf = bytes_to_num(board2_IIR_data[80 * i + (j % 12) * 6:  80* i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board2_data[j].append(data_buf * LIA_gain)

            ch1_data = bytes_to_num(board2_IIR_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board2_IIR_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board2_data[12].append(ch1_data_buf)
            board2_data[13].append(ch2_data_buf)
            board2_aux_ch1_data.append(ch1_data_buf)
            board2_aux_ch2_data.append(ch2_data_buf)

        for i in range(data_num):
            data_buf = 0
            for j in range(24):
                data_buf = bytes_to_num(board3_IIR_data[80 * i + (j % 12) * 6:  80 * i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board3_data[j].append(data_buf * LIA_gain)

            ch1_data = bytes_to_num(board3_IIR_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board3_IIR_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board3_aux_ch1_data.append(ch1_data_buf)
            board3_aux_ch2_data.append(ch2_data_buf)
            board3_data[12].append(ch1_data_buf)
            board3_data[13].append(ch2_data_buf)

        for i in range(data_num):
            data_buf = 0
            for j in range(24):
                data_buf = bytes_to_num(board4_IIR_data[80 * i + (j % 12) * 6:  80 * i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board4_data[j].append(data_buf * LIA_gain)

            ch1_data = bytes_to_num(board4_IIR_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board4_IIR_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board4_aux_ch1_data.append(ch1_data_buf)
            board4_aux_ch2_data.append(ch2_data_buf)
            board4_data[12].append(ch1_data_buf)
            board4_data[13].append(ch2_data_buf)

        for i in range(data_num):
            data_buf = 0
            for j in range(24):
                data_buf = bytes_to_num(board5_IIR_data[80 * i + (j % 12) * 6:  80 * i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board5_data[j].append(data_buf * LIA_gain)

            ch1_data = bytes_to_num(board5_IIR_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board5_IIR_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board5_aux_ch1_data.append(ch1_data_buf)
            board5_aux_ch2_data.append(ch2_data_buf)
            board5_data[12].append(ch1_data_buf)
            board5_data[13].append(ch2_data_buf)

        for i in range(data_num):
            data_buf = 0
            for j in range(24):
                data_buf = bytes_to_num(board6_IIR_data[80 * i + (j % 12) * 6:  80 * i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board6_data[j].append(data_buf * LIA_gain)

            ch1_data = bytes_to_num(board6_IIR_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board6_IIR_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board6_aux_ch1_data.append(ch1_data_buf)
            board6_aux_ch2_data.append(ch2_data_buf)
            board6_data[12].append(ch1_data_buf)
            board6_data[13].append(ch2_data_buf)

        for i in range(data_num):
            data_buf = 0
            for j in range(24):
                data_buf = bytes_to_num(board7_IIR_data[80 * i + (j % 12) * 6:  80 * i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board7_data[j].append(data_buf * LIA_gain)

            ch1_data = bytes_to_num(board7_IIR_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board7_IIR_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board7_aux_ch1_data.append(ch1_data_buf)
            board7_aux_ch2_data.append(ch2_data_buf)
            board7_data[12].append(ch1_data_buf)
            board7_data[13].append(ch2_data_buf)

        for i in range(data_num):
            data_buf = 0
            for j in range(24):
                data_buf = bytes_to_num(board8_IIR_data[80 * i + (j % 12) * 6:  80 * i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board8_data[j].append(data_buf * LIA_gain)

            ch1_data = bytes_to_num(board8_IIR_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board8_IIR_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board8_aux_ch1_data.append(ch1_data_buf)
            board8_aux_ch2_data.append(ch2_data_buf)
            board8_data[12].append(ch1_data_buf)
            board8_data[13].append(ch2_data_buf)

        self.Board1_IIR_data = board1_data
        self.Board2_IIR_data = board2_data
        self.Board3_IIR_data = board3_data
        self.Board4_IIR_data = board4_data
        self.Board5_IIR_data = board5_data
        # print(self.Board5_IIR_data)
        self.Board6_IIR_data = board6_data
        self.Board7_IIR_data = board7_data
        self.Board8_IIR_data = board8_data
        # print(np.std(self.Board1_IIR_data[1]))
        return self.Board1_IIR_data, self.Board2_IIR_data, self.Board3_IIR_data, self.Board4_IIR_data, self.Board5_IIR_data, self.Board6_IIR_data, self.Board7_IIR_data, self.Board8_IIR_data

    def IIR_plot(self):
        x = np.array(range(len(self.Board1_IIR_data[0])))
        # plt.plot(x, self.Board1_IIR_data[0], label='Board1_Ch1_Fre1_r')
        plt.plot(x, self.Board1_IIR_data[1], label='Board1_Ch1_Fre1_y')
        plt.plot(x, self.Board1_IIR_data[2], label='Board1_Ch1_Fre1_x')
        # plt.plot(x, self.Board1_IIR_data[3], label='Board1_Ch2_Fre1_r')
        # plt.plot(x, self.Board1_IIR_data[4], label='Board1_Ch2_Fre1_y')
        # plt.plot(x, self.Board1_IIR_data[5], label='Board1_Ch2_Fre1_x')
        # plt.plot(x, self.Board2_IIR_data[0], label='Board2_Ch1_Fre1_r')
        plt.plot(x, self.Board2_IIR_data[1], label='Board2_Ch1_Fre1_y')
        plt.plot(x, self.Board2_IIR_data[2], label='Board2_Ch1_Fre1_x')
        # plt.plot(x, self.Board2_IIR_data[3], label='Board2_Ch2_Fre1_r')
        # plt.plot(x, self.Board2_IIR_data[4], label='Board2_Ch2_Fre1_y')
        # plt.plot(x, self.Board2_IIR_data[5], label='Board2_Ch2_Fre1_x')
        # plt.plot(x, self.Board3_IIR_data[0], label='Board3_Ch1_Fre1_r')
        # plt.plot(x, self.Board3_IIR_data[1], label='Board3_Ch1_Fre1_y')
        # plt.plot(x, self.Board3_IIR_data[2], label='Board3_Ch1_Fre1_x')
        # plt.plot(x, self.Board3_IIR_data[3], label='Board3_Ch2_Fre1_r')
        # plt.plot(x, self.Board3_IIR_data[4], label='Board3_Ch2_Fre1_y')
        # plt.plot(x, self.Board3_IIR_data[5], label='Board3_Ch2_Fre1_x')
        # plt.plot(x, self.Board4_IIR_data[0], label='Board4_Ch1_Fre1_r')
        # plt.plot(x, self.Board4_IIR_data[1], label='Board4_Ch1_Fre1_y')
        # plt.plot(x, self.Board4_IIR_data[2], label='Board4_Ch1_Fre1_x')
        # plt.plot(x, self.Board4_IIR_data[3], label='Board4_Ch2_Fre1_r')
        # plt.plot(x, self.Board4_IIR_data[4], label='Board4_Ch2_Fre1_y')
        # plt.plot(x, self.Board4_IIR_data[5], label='Board4_Ch2_Fre1_x')
        # plt.plot(x, self.Board5_IIR_data[0], label='Board5_Ch1_Fre1_r')
        # plt.plot(x, self.Board5_IIR_data[1], label='Board5_Ch1_Fre1_y')
        # plt.plot(x, self.Board5_IIR_data[2], label='Board5_Ch1_Fre1_x')
        # plt.plot(x, self.Board5_IIR_data[3], label='Board5_Ch2_Fre1_r')
        # plt.plot(x, self.Board5_IIR_data[4], label='Board5_Ch2_Fre1_y')
        # plt.plot(x, self.Board5_IIR_data[5], label='Board5_Ch2_Fre1_x')
        # plt.plot(x, self.Board6_IIR_data[0], label='Board6_Ch1_Fre1_r')
        # plt.plot(x, self.Board6_IIR_data[1], label='Board6_Ch1_Fre1_y')
        # plt.plot(x, self.Board6_IIR_data[2], label='Board6_Ch1_Fre1_x')
        # plt.plot(x, self.Board6_IIR_data[3], label='Board6_Ch2_Fre1_r')
        # plt.plot(x, self.Board6_IIR_data[4], label='Board6_Ch2_Fre1_y')
        # plt.plot(x, self.Board6_IIR_data[5], label='Board6_Ch2_Fre1_x')
        # plt.plot(x, self.Board7_IIR_data[0], label='Board7_Ch1_Fre1_r')
        # plt.plot(x, self.Board7_IIR_data[1], label='Board7_Ch1_Fre1_y')
        # plt.plot(x, self.Board7_IIR_data[2], label='Board7_Ch1_Fre1_x')
        # plt.plot(x, self.Board7_IIR_data[3], label='Board7_Ch2_Fre1_r')
        # plt.plot(x, self.Board7_IIR_data[4], label='Board7_Ch2_Fre1_y')
        # plt.plot(x, self.Board7_IIR_data[5], label='Board7_Ch2_Fre1_x')
        # plt.plot(x, self.Board8_IIR_data[0], label='Board8_Ch1_Fre1_r')
        # plt.plot(x, self.Board8_IIR_data[1], label='Board8_Ch1_Fre1_y')
        # plt.plot(x, self.Board8_IIR_data[2], label='Board8_Ch1_Fre1_x')
        # plt.plot(x, self.Board8_IIR_data[3], label='Board8_Ch2_Fre1_r')
        # plt.plot(x, self.Board8_IIR_data[4], label='Board8_Ch2_Fre1_y')
        # plt.plot(x, self.Board8_IIR_data[5], label='Board8_Ch2_Fre1_x')
        # plt.plot(x, self.Board1_IIR_data[6], label='Board1_Ch1_Fre2_r')
        # plt.plot(x, self.Board1_IIR_data[7], label='Board1_Ch1_Fre2_y')
        # plt.plot(x, self.Board1_IIR_data[8], label='Board1_Ch1_Fre2_x')
        # plt.plot(x, self.Board1_IIR_data[9], label='Board1_Ch2_Fre2_r')
        # plt.plot(x, self.Board1_IIR_data[10], label='Board1_Ch2_Fre2_y')
        # plt.plot(x, self.Board1_IIR_data[11], label='Board1_Ch2_Fre2_x')
        # plt.plot(x, self.Board1_IIR_data[12], label='Board1_Ch1_Fre3_r')
        # plt.plot(x, self.Board1_IIR_data[13], label='Board1_Ch1_Fre3_y')
        # plt.plot(x, self.Board1_IIR_data[14], label='Board1_Ch1_Fre3_x')
        # plt.plot(x, self.Board1_IIR_data[15], label='Board1_Ch2_Fre3_r')
        # plt.plot(x, self.Board1_IIR_data[16], label='Board1_Ch2_Fre3_y')
        # plt.plot(x, self.Board1_IIR_data[17], label='Board1_Ch2_Fre3_x')
        # plt.plot(x, self.IIR_data[18], label='Board_Ch1_Fre4_r')
        # plt.plot(x, self.IIR_data[19], label='Board_Ch1_Fre4_y')
        # plt.plot(x, self.IIR_data[20], label='Board_Ch1_Fre4_x')
        # plt.plot(x, self.Board1_IIR_data[21], label='Board1_Ch2_Fre4_r')
        # plt.plot(x, self.Board1_IIR_data[22], label='Board1_Ch2_Fre4_y')
        # plt.plot(x, self.Board1_IIR_data[23], label='Board1_Ch2_Fre4_x')
        # plt.xlabel('Time/ns')
        plt.ylabel('Amplitude/1')
        plt.legend()
        plt.show()

    def five_ch_read_UI(self, datanum_nv, datanum_flux):
        """
        2通道锁相+3通道磁通门读回
        设备识别码：DNVCS-API-Multichannel-0001
        API-Multichannel
        :param datanum_nv: 锁相板卡数据采集点数 int between [0,10000] 10
        :param datanum_flux: 磁通门数据采集点数 int between [0,10000] 10
        """
        self.DWritePort(b"\x38\x00")
        self.DWritePort(num_to_bytes(datanum_nv, 4))
        self.DWritePort(num_to_bytes(datanum_flux+2, 4))
        self.five_ch_flag = True
        board_NV_data = [b'', b'']
        board_FLUX_data = [b'', b'', b'']
        board_data = [[[] for _ in range(26)], [[] for _ in range(26)],
                      [[] for _ in range(3)], [[] for _ in range(3)], [[] for _ in range(3)]]
        byte_num = 0
        nv_counter = 0
        flux_counter = 0
        while self.five_ch_flag:
            data = self.DReadPort(datanum_nv*164+datanum_flux*52)
            while (byte_num < (datanum_nv * 164 + datanum_flux * 52)):
                if (data[byte_num:byte_num + 4] == b'\x12\x34\x12\x34'):
                    board_NV_data[0] += data[byte_num + 4: byte_num + 84]
                    board_NV_data[1] += data[byte_num + 84: byte_num + 164]
                    nv_counter += 1
                    byte_num += 164
                else:
                    if (data[byte_num:byte_num + 4] == b'\xab\xcd\xab\xcd'):
                        board_FLUX_data[0] += data[byte_num + 4: byte_num + 19]
                        board_FLUX_data[1] += data[byte_num + 20: byte_num + 35]
                        board_FLUX_data[2] += data[byte_num + 36: byte_num + 51]
                        flux_counter += 1
                        byte_num += 52

            for board_nv in range(len(board_NV_data)):
                for i in range(nv_counter):
                    data_buf = 0
                    for j in range(12):
                        data_buf = bytes_to_num(board_NV_data[board_nv][80 * i + (j % 12) * 6:  80 * i + (j % 12 + 1) * 6])
                        if data_buf > 2 ** 47 - 1:
                            data_buf = (data_buf - 2 ** 48.0) / 2 ** 48.0
                        else:
                            data_buf = data_buf / 2 ** 48.0
                        board_data[board_nv][j].append(data_buf * LIA_gain)
                    ch1_data = bytes_to_num(board_NV_data[board_nv][80 * i + 72: 80 * i + 76]) % 2 ** 28
                    ch2_data = bytes_to_num(board_NV_data[board_nv][80 * i + 76: 80 * i + 80]) % 2 ** 28
                    if ch1_data > 2 ** 27 - 1:
                        ch1_data_buf = (ch1_data - 2 ** 28.0) / 2 ** 28.0
                    else:
                        ch1_data_buf = ch1_data / 2 ** 28.0

                    if ch2_data > 2 ** 27 - 1:
                        ch2_data_buf = (ch2_data - 2 ** 28.0) / 2 ** 28.0
                    else:
                        ch2_data_buf = ch2_data / 2 ** 28.0
                    board_data[board_nv][12].append(ch1_data_buf)
                    board_data[board_nv][13].append(ch2_data_buf)
            vref = 12.5
            gain = 1
            for board_flux in range(len(board_FLUX_data)):
                for i in range(flux_counter):
                    for j in range(3):
                        data_buf = bytes_to_num(board_FLUX_data[i+2][1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                        # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                        data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                        board_data[i+2][j].append(data_buf)
            for canvas_id in range(5):
                b_data1 = board_data[canvas_id]
                self.exp_UI.canvas_setplot(canvas_id, len(b_data1), b_data1)
                self.exp_UI.log_exp.log_insert_new(canvas_id+1, b_data1)
            # return board_data

    def five_ch_read(self,datanum_nv,datanum_flux):
        self.DWritePort(b"\x38\x00")
        self.DWritePort(num_to_bytes(datanum_nv, 4))
        self.DWritePort(num_to_bytes(datanum_flux+2, 4))
        data=self.DReadPort(datanum_nv*164+datanum_flux*52)
        print("read complete")
        board1_NV_data = b''
        board2_NV_data = b''
        board3_FLUX_data = b''
        board4_FLUX_data = b''
        board5_FLUX_data = b''
        start_num=0
        byte_num=0
        while(byte_num<(datanum_nv*164+datanum_flux*52)):
            # print(byte_num,data[byte_num:byte_num + 4])
            if(data[byte_num:byte_num+4] == b'\x12\x34\x12\x34'):
                board1_NV_data += data[byte_num + 4: byte_num + 84]
                board2_NV_data += data[byte_num + 84: byte_num + 164]
                byte_num+=164
                # print(byte_num)
            else:
                if(data[byte_num:byte_num+4] == b'\xab\xcd\xab\xcd'):
                    board3_FLUX_data += data[byte_num + 4: byte_num + 19]
                    board4_FLUX_data += data[byte_num + 20: byte_num + 35]
                    board5_FLUX_data += data[byte_num + 36: byte_num + 51]
                    byte_num += 52
                    # print(byte_num)
        # print(board1_NV_data)
        # print(board2_NV_data)
        # print(len(board3_FLUX_data))
        # print(len(board4_FLUX_data))
        # print(len(board5_FLUX_data))
        board1_data = [[] for i in range(26)]
        board2_data = [[] for i in range(26)]
        for i in range(datanum_nv):
            data_buf = 0
            for j in range(12):
                data_buf = bytes_to_num(board1_NV_data[80 * i + (j % 12) * 6:  80* i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board1_data[j].append(data_buf * LIA_gain)
            ch1_data = bytes_to_num(board1_NV_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board1_NV_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board1_data[12].append(ch1_data_buf)
            board1_data[13].append(ch2_data_buf)
        for i in range(datanum_nv):
            data_buf = 0
            for j in range(12):
                data_buf = bytes_to_num(board2_NV_data[80 * i + (j % 12) * 6:  80* i + (j % 12 + 1) * 6])
                if data_buf > 2**47-1:
                    data_buf = (data_buf - 2**48.0) / 2**48.0
                else:
                    data_buf = data_buf / 2**48.0
                # data_buf = data_buf / 2**64.0
                board2_data[j].append(data_buf * LIA_gain)
            ch1_data = bytes_to_num(board2_NV_data[80 * i + 72: 80 * i + 76]) % 2**28
            ch2_data = bytes_to_num(board2_NV_data[80 * i + 76: 80 * i + 80]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board2_data[12].append(ch1_data_buf)
            board2_data[13].append(ch2_data_buf)

            while 1:
                if board3_FLUX_data[start_num:start_num + 1] != b'\xcc':
                    # print(start_num, FLUX1_data[start_num:start_num + 1])
                    if (start_num < 15):
                        start_num = start_num + 1
                    else:
                        break
                    # input()
                else:
                    # print("break1", start_num)
                    break
            board3_FLUX_data = board3_FLUX_data[start_num:start_num + 15 * datanum_flux]

            start_num=0
            while 1:
                if board4_FLUX_data[start_num:start_num + 1] != b'\xcc':
                    # print(start_num, FLUX1_data[start_num:start_num + 1])
                    if (start_num < 15):
                        start_num = start_num + 1
                    else:
                        break
                    # input()
                else:
                    # print("break1", start_num)
                    break
            board4_FLUX_data = board4_FLUX_data[start_num:start_num + 15 * datanum_flux]
            start_num = 0
            while 1:
                if board5_FLUX_data[start_num:start_num + 1] != b'\xcc':
                    # print(start_num, FLUX1_data[start_num:start_num + 1])
                    if (start_num < 15):
                        start_num = start_num + 1
                    else:
                        break
                    # input()
                else:
                    # print("break1", start_num)
                    break
            board5_FLUX_data = board5_FLUX_data[start_num:start_num + 15 * datanum_flux]

            fluxdata1 = [[] for i in range(3)]
            fluxdata2 = [[] for i in range(3)]
            fluxdata3 = [[] for i in range(3)]
            vref = 12.5
            gain = 1
            for i in range(datanum_flux-2):
                data_buf = 0
                for j in range(3):
                    data_buf = bytes_to_num(board3_FLUX_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                    # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                    data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                    fluxdata1[j].append(data_buf)
            for i in range(datanum_flux-2):
                data_buf = 0
                for j in range(3):
                    data_buf = bytes_to_num(board4_FLUX_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                    # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                    data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                    fluxdata2[j].append(data_buf)
            for i in range(datanum_flux-2):
                data_buf = 0
                for j in range(3):
                    data_buf = bytes_to_num(board5_FLUX_data[1 + 15 * i + (j % 3) * 4: 5 + 15 * i + (j % 3) * 4])
                    # print(i,j,16 * i + (j % 16) * 2, 16 * i + (j % 16 + 1) * 2,data_buf)
                    data_buf = data_buf * vref / (2 ** 31 - 1) / gain
                    fluxdata3[j].append(data_buf)
        # print(board1_data)
        # print(board2_data)
        # print(fluxdata1)
        # print(fluxdata2)
        # print(fluxdata3)

        self.IIR_data1  = board1_data
        self.IIR_data2  = board2_data
        self.FLUX_data1 = fluxdata1
        self.FLUX_data2 = fluxdata2
        self.FLUX_data3 = fluxdata3

    def five_ch_plot(self):
        x = np.array(range(len(self.IIR_data1[0])))
        plt.plot(x, self.IIR_data1[0], label='Board1_Ch1_Fre1_r')
        plt.plot(x, self.IIR_data1[1], label='Board1_Ch1_Fre1_y')
        plt.plot(x, self.IIR_data1[2], label='Board1_Ch1_Fre1_x')
        plt.plot(x, self.IIR_data2[0], label='Board2_Ch1_Fre1_r')
        plt.plot(x, self.IIR_data2[1], label='Board2_Ch1_Fre1_y')
        plt.plot(x, self.IIR_data2[2], label='Board2_Ch1_Fre1_x')
        plt.ylabel('V/1')
        plt.ylabel('Amplitude/1')
        plt.legend()
        plt.show()
        x = np.array(range(len(self.FLUX_data1[0])))
        plt.plot(x, self.FLUX_data1[0], label='Board1_x')
        plt.plot(x, self.FLUX_data1[1], label='Board1_y')
        plt.plot(x, self.FLUX_data1[2], label='Board1_z')
        plt.plot(x, self.FLUX_data2[0], label='Board2_x')
        plt.plot(x, self.FLUX_data2[1], label='Board2_y')
        plt.plot(x, self.FLUX_data2[2], label='Board2_z')
        plt.plot(x, self.FLUX_data3[0], label='Board3_x')
        plt.plot(x, self.FLUX_data3[1], label='Board3_y')
        plt.plot(x, self.FLUX_data3[2], label='Board3_z')
        # plt.xlabel('Time/ns')
        plt.ylabel('uT/1')
        plt.ylabel('Amplitude/1')
        plt.legend()
        plt.show()

    def PID_play(self, ch_num, data_num):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')

        self.DWritePort(num_to_bytes(ch_num, 1) + b'\x05')  # 进入到PID状态
        time.sleep(self.tc * 1)
        self.DWritePort(num_to_bytes(data_num, 4))
        board1_PID_data = b''
        board2_PID_data = b''
        board3_PID_data = b''
        board4_PID_data = b''
        board5_PID_data = b''
        board6_PID_data = b''
        board7_PID_data = b''
        board8_PID_data = b''
        PID_data=self.DReadPort(76*8*data_num)
        # print("solved")
        # input()
        for i in range(data_num):
            board1_PID_data += PID_data[i*608:i*608+76]
            board2_PID_data += PID_data[i*608+76:i*608+76*2]
            board3_PID_data += PID_data[i*608+76*2:i*608+76*3]
            board4_PID_data += PID_data[i*608+76*3:i*608+76*4]
            board5_PID_data += PID_data[i*608+76*4:i*608+76*5]
            board6_PID_data += PID_data[i*608+76*5:i*608+76*6]
            board7_PID_data += PID_data[i*608+76*6:i*608+76*7]
            board8_PID_data += PID_data[i*608+76*7:i*608+76*8]
            # print(i)
        print('data transform down')
        board1_data = [[[] for i in range(5)] for j in range(4)]
        board2_data = [[[] for i in range(5)] for j in range(4)]
        board3_data = [[[] for i in range(5)] for j in range(4)]
        board4_data = [[[] for i in range(5)] for j in range(4)]
        board5_data = [[[] for i in range(5)] for j in range(4)]
        board6_data = [[[] for i in range(5)] for j in range(4)]
        board7_data = [[[] for i in range(5)] for j in range(4)]
        board8_data = [[[] for i in range(5)] for j in range(4)]

        board1_aux_ch1_data = []
        board1_aux_ch2_data = []
        board2_aux_ch1_data = []
        board2_aux_ch2_data = []
        board3_aux_ch1_data = []
        board3_aux_ch2_data = []
        board4_aux_ch1_data = []
        board4_aux_ch2_data = []
        board5_aux_ch1_data = []
        board5_aux_ch2_data = []
        board6_aux_ch1_data = []
        board6_aux_ch2_data = []
        board7_aux_ch1_data = []
        board7_aux_ch2_data = []
        board8_aux_ch1_data = []
        board8_aux_ch2_data = []

        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board1_PID_data[76 * i: 76 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board1_PID_data[76 * i + 1: 76 * i + 2])
            print(Board_num)
            iir_data_r = bytes_to_num(board1_PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(board1_PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(board1_PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(board1_PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(board1_PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board1_data[0][0].append(ch1_iir_data_r)
            board1_data[0][1].append(ch1_iir_data_x)
            board1_data[0][2].append(ch1_iir_data_y)
            board1_data[0][3].append(ch1_error_buf)
            board1_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board1_PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(board1_PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(board1_PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(board1_PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(board1_PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board1_data[1][0].append(ch1_iir_data_r)
            board1_data[1][1].append(ch1_iir_data_x)
            board1_data[1][2].append(ch1_iir_data_y)
            board1_data[1][3].append(ch1_error_buf)
            board1_data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board1_PID_data[76 * i + 66: 140 * i + 70]) % 2**28
            ch2_data = bytes_to_num(board1_PID_data[76 * i + 70: 140 * i + 74]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board1_aux_ch1_data.append(ch1_data_buf)
            board1_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board1_PID_data[76 * i + 75: 76 * i + 75])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board1_PID_data[76 * i + 76: 76 * i + 76])
            if frame_l == 170:
                print("End of frame check succeeded")


        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board2_PID_data[76 * i: 76 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board2_PID_data[76 * i + 1: 76 * i + 2])
            print(Board_num)
            iir_data_r = bytes_to_num(board2_PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(board2_PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(board2_PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(board2_PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(board2_PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board2_data[0][0].append(ch1_iir_data_r)
            board2_data[0][1].append(ch1_iir_data_x)
            board2_data[0][2].append(ch1_iir_data_y)
            board2_data[0][3].append(ch1_error_buf)
            board2_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board2_PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(board2_PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(board2_PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(board2_PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(board2_PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board2_data[1][0].append(ch1_iir_data_r)
            board2_data[1][1].append(ch1_iir_data_x)
            board2_data[1][2].append(ch1_iir_data_y)
            board2_data[1][3].append(ch1_error_buf)
            board2_data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board2_PID_data[76 * i + 66: 140 * i + 70]) % 2**28
            ch2_data = bytes_to_num(board2_PID_data[76 * i + 70: 140 * i + 74]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board2_aux_ch1_data.append(ch1_data_buf)
            board2_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board2_PID_data[76 * i + 75: 76 * i + 75])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board2_PID_data[76 * i + 76: 76 * i + 76])
            if frame_l == 170:
                print("End of frame check succeeded")


        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board3_PID_data[76 * i: 76 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board3_PID_data[76 * i + 1: 76 * i + 2])
            print(Board_num)
            iir_data_r = bytes_to_num(board3_PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(board3_PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(board3_PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(board3_PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(board3_PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board3_data[0][0].append(ch1_iir_data_r)
            board3_data[0][1].append(ch1_iir_data_x)
            board3_data[0][2].append(ch1_iir_data_y)
            board3_data[0][3].append(ch1_error_buf)
            board3_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board3_PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(board3_PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(board3_PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(board3_PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(board3_PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board3_data[1][0].append(ch1_iir_data_r)
            board3_data[1][1].append(ch1_iir_data_x)
            board3_data[1][2].append(ch1_iir_data_y)
            board3_data[1][3].append(ch1_error_buf)
            board3_data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board3_PID_data[76 * i + 66: 140 * i + 70]) % 2**28
            ch2_data = bytes_to_num(board3_PID_data[76 * i + 70: 140 * i + 74]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board3_aux_ch1_data.append(ch1_data_buf)
            board3_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board3_PID_data[76 * i + 75: 76 * i + 75])
            print('Time stamp is ', time_stamp)
            frame_l = bytes_to_num(board3_PID_data[76 * i + 76: 76 * i + 76])
            if frame_l == 170:
                print("End of frame check succeeded")


        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board4_PID_data[76 * i: 76 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board4_PID_data[76 * i + 1: 76 * i + 2])
            print(Board_num)
            iir_data_r = bytes_to_num(board4_PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(board4_PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(board4_PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(board4_PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(board4_PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board4_data[0][0].append(ch1_iir_data_r)
            board4_data[0][1].append(ch1_iir_data_x)
            board4_data[0][2].append(ch1_iir_data_y)
            board4_data[0][3].append(ch1_error_buf)
            board4_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board4_PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(board4_PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(board4_PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(board4_PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(board4_PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board4_data[1][0].append(ch1_iir_data_r)
            board4_data[1][1].append(ch1_iir_data_x)
            board4_data[1][2].append(ch1_iir_data_y)
            board4_data[1][3].append(ch1_error_buf)
            board4_data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board4_PID_data[76 * i + 66: 140 * i + 70]) % 2**28
            ch2_data = bytes_to_num(board4_PID_data[76 * i + 70: 140 * i + 74]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board4_aux_ch1_data.append(ch1_data_buf)
            board4_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board4_PID_data[76 * i + 75: 76 * i + 75])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board4_PID_data[76 * i + 76: 76 * i + 76])
            if frame_l == 170:
                print("End of frame check succeeded")


        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board5_PID_data[76 * i: 76 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board5_PID_data[76 * i + 1: 76 * i + 2])
            print(Board_num)
            iir_data_r = bytes_to_num(board5_PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(board5_PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(board5_PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(board5_PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(board5_PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board5_data[0][0].append(ch1_iir_data_r)
            board5_data[0][1].append(ch1_iir_data_x)
            board5_data[0][2].append(ch1_iir_data_y)
            board5_data[0][3].append(ch1_error_buf)
            board5_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board5_PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(board5_PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(board5_PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(board5_PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(board5_PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board5_data[1][0].append(ch1_iir_data_r)
            board5_data[1][1].append(ch1_iir_data_x)
            board5_data[1][2].append(ch1_iir_data_y)
            board5_data[1][3].append(ch1_error_buf)
            board5_data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board5_PID_data[76 * i + 66: 140 * i + 70]) % 2**28
            ch2_data = bytes_to_num(board5_PID_data[76 * i + 70: 140 * i + 74]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board5_aux_ch1_data.append(ch1_data_buf)
            board5_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board5_PID_data[76 * i + 75: 76 * i + 75])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board5_PID_data[76 * i + 76: 76 * i + 76])
            if frame_l == 170:
                print("End of frame check succeeded")


        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board6_PID_data[76 * i: 76 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board6_PID_data[76 * i + 1: 76 * i + 2])
            print(Board_num)
            iir_data_r = bytes_to_num(board6_PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(board6_PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(board6_PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(board6_PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(board6_PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board6_data[0][0].append(ch1_iir_data_r)
            board6_data[0][1].append(ch1_iir_data_x)
            board6_data[0][2].append(ch1_iir_data_y)
            board6_data[0][3].append(ch1_error_buf)
            board6_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board6_PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(board6_PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(board6_PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(board6_PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(board6_PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board6_data[1][0].append(ch1_iir_data_r)
            board6_data[1][1].append(ch1_iir_data_x)
            board6_data[1][2].append(ch1_iir_data_y)
            board6_data[1][3].append(ch1_error_buf)
            board6_data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board6_PID_data[76 * i + 66: 140 * i + 70]) % 2**28
            ch2_data = bytes_to_num(board6_PID_data[76 * i + 70: 140 * i + 74]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board6_aux_ch1_data.append(ch1_data_buf)
            board6_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board6_PID_data[76 * i + 75: 76 * i + 75])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board6_PID_data[76 * i + 76: 76 * i + 76])
            if frame_l == 170:
                print("End of frame check succeeded")


        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board7_PID_data[76 * i: 76 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board7_PID_data[76 * i + 1: 76 * i + 2])
            print(Board_num)
            iir_data_r = bytes_to_num(board7_PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(board7_PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(board7_PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(board7_PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(board7_PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board7_data[0][0].append(ch1_iir_data_r)
            board7_data[0][1].append(ch1_iir_data_x)
            board7_data[0][2].append(ch1_iir_data_y)
            board7_data[0][3].append(ch1_error_buf)
            board7_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board7_PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(board7_PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(board7_PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(board7_PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(board7_PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board7_data[1][0].append(ch1_iir_data_r)
            board7_data[1][1].append(ch1_iir_data_x)
            board7_data[1][2].append(ch1_iir_data_y)
            board7_data[1][3].append(ch1_error_buf)
            board7_data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board7_PID_data[76 * i + 66: 140 * i + 70]) % 2**28
            ch2_data = bytes_to_num(board7_PID_data[76 * i + 70: 140 * i + 74]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board7_aux_ch1_data.append(ch1_data_buf)
            board7_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board7_PID_data[76 * i + 75: 76 * i + 75])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board7_PID_data[76 * i + 76: 76 * i + 76])
            if frame_l == 170:
                print("End of frame check succeeded")


        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board8_PID_data[76 * i: 76 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board8_PID_data[76 * i + 1: 76 * i + 2])
            print(Board_num)
            iir_data_r = bytes_to_num(board8_PID_data[76 * i + 2: 76 * i + 8])
            iir_data_x = bytes_to_num(board8_PID_data[76 * i + 8: 76 * i + 14])
            iir_data_y = bytes_to_num(board8_PID_data[76 * i + 14: 76 * i + 20])
            error_buf = bytes_to_num(board8_PID_data[76 * i + 20: 76 * i + 28])
            feedback_buf = bytes_to_num(board8_PID_data[76 * i + 28: 76 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board8_data[0][0].append(ch1_iir_data_r)
            board8_data[0][1].append(ch1_iir_data_x)
            board8_data[0][2].append(ch1_iir_data_y)
            board8_data[0][3].append(ch1_error_buf)
            board8_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board8_PID_data[76 * i + 34: 76 * i + 40])
            iir_data_x = bytes_to_num(board8_PID_data[76 * i + 40: 76 * i + 46])
            iir_data_y = bytes_to_num(board8_PID_data[76 * i + 46: 76 * i + 52])
            error_buf = bytes_to_num(board8_PID_data[76 * i + 52: 76 * i + 60])
            feedback_buf = bytes_to_num(board8_PID_data[76 * i + 60: 76 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**20.0 * 2+2.6*1e9
            board8_data[1][0].append(ch1_iir_data_r)
            board8_data[1][1].append(ch1_iir_data_x)
            board8_data[1][2].append(ch1_iir_data_y)
            board8_data[1][3].append(ch1_error_buf)
            board8_data[1][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board8_PID_data[76 * i + 66: 140 * i + 70]) % 2**28
            ch2_data = bytes_to_num(board8_PID_data[76 * i + 70: 140 * i + 74]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board8_aux_ch1_data.append(ch1_data_buf)
            board8_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board8_PID_data[76 * i + 75: 76 * i + 75])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board8_PID_data[76 * i + 76: 76 * i + 76])
            if frame_l == 170:
                print("End of frame check succeeded")

        self.board1_data=board1_data
        self.board2_data=board2_data
        self.board3_data=board3_data
        self.board4_data=board4_data
        self.board5_data=board5_data
        self.board6_data=board6_data
        self.board7_data=board7_data
        self.board8_data=board8_data
        return self.board1_data, self.board2_data, self.board3_data, self.board4_data,self.board5_data, self.board6_data, self.board7_data, self.board8_data

    def PID_play_unlimited(self, ch_num, data_num):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')

        self.DWritePort(num_to_bytes(ch_num, 1) + b'\x05')  # 进入到PID状态
        time.sleep(self.tc * 6)
        self.DWritePort(num_to_bytes(0, 4))
        board1_PID_data = b''
        board2_PID_data = b''
        board3_PID_data = b''
        board4_PID_data = b''
        for i in range(data_num):
            board1_PID_data += self.DReadPort(140)
            board2_PID_data += self.DReadPort(140)
            board3_PID_data += self.DReadPort(140)
            board4_PID_data += self.DReadPort(140)
        LIA_mini.DWritePort(b'\x00' * 16)
        time.sleep(0.01)
        board1_data = [[[] for i in range(5)] for j in range(4)]
        board2_data = [[[] for i in range(5)] for j in range(4)]
        board3_data = [[[] for i in range(5)] for j in range(4)]
        board4_data = [[[] for i in range(5)] for j in range(4)]

        board1_aux_ch1_data = []
        board1_aux_ch2_data = []
        board2_aux_ch1_data = []
        board2_aux_ch2_data = []
        board3_aux_ch1_data = []
        board3_aux_ch2_data = []
        board4_aux_ch1_data = []
        board4_aux_ch2_data = []

        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board1_PID_data[140 * i: 140 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board1_PID_data[140 * i + 1: 140 * i + 2])
            # print(Board_num)
            iir_data_r = bytes_to_num(board1_PID_data[140 * i + 2: 140 * i + 8])
            iir_data_x = bytes_to_num(board1_PID_data[140 * i + 8: 140 * i + 14])
            iir_data_y = bytes_to_num(board1_PID_data[140 * i + 14: 140 * i + 20])
            error_buf = bytes_to_num(board1_PID_data[140 * i + 20: 140 * i + 28])
            feedback_buf = bytes_to_num(board1_PID_data[140 * i + 28: 140 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board1_data[0][0].append(ch1_iir_data_r)
            board1_data[0][1].append(ch1_iir_data_x)
            board1_data[0][2].append(ch1_iir_data_y)
            board1_data[0][3].append(ch1_error_buf)
            board1_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board1_PID_data[140 * i + 34: 140 * i + 40])
            iir_data_x = bytes_to_num(board1_PID_data[140 * i + 40: 140 * i + 46])
            iir_data_y = bytes_to_num(board1_PID_data[140 * i + 46: 140 * i + 52])
            error_buf = bytes_to_num(board1_PID_data[140 * i + 52: 140 * i + 60])
            feedback_buf = bytes_to_num(board1_PID_data[140 * i + 60: 140 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board1_data[1][0].append(ch1_iir_data_r)
            board1_data[1][1].append(ch1_iir_data_x)
            board1_data[1][2].append(ch1_iir_data_y)
            board1_data[1][3].append(ch1_error_buf)
            board1_data[1][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board1_PID_data[140 * i + 66: 140 * i + 72])
            iir_data_x = bytes_to_num(board1_PID_data[140 * i + 72: 140 * i + 78])
            iir_data_y = bytes_to_num(board1_PID_data[140 * i + 78: 140 * i + 84])
            error_buf = bytes_to_num(board1_PID_data[140 * i + 84: 140 * i + 92])
            feedback_buf = bytes_to_num(board1_PID_data[140 * i + 92: 140 * i + 98])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board1_data[2][0].append(ch1_iir_data_r)
            board1_data[2][1].append(ch1_iir_data_x)
            board1_data[2][2].append(ch1_iir_data_y)
            board1_data[2][3].append(ch1_error_buf)
            board1_data[2][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board1_PID_data[140 * i + 98: 140 * i + 104])
            iir_data_x = bytes_to_num(board1_PID_data[140 * i + 104: 140 * i + 110])
            iir_data_y = bytes_to_num(board1_PID_data[140 * i + 110: 140 * i + 116])
            error_buf = bytes_to_num(board1_PID_data[140 * i + 116: 140 * i + 124])
            feedback_buf = bytes_to_num(board1_PID_data[140 * i + 124: 140 * i + 130])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board1_data[3][0].append(ch1_iir_data_r)
            board1_data[3][1].append(ch1_iir_data_x)
            board1_data[3][2].append(ch1_iir_data_y)
            board1_data[3][3].append(ch1_error_buf)
            board1_data[3][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board1_PID_data[140 * i + 130: 140 * i + 134]) % 2**28
            ch2_data = bytes_to_num(board1_PID_data[140 * i + 134: 140 * i + 138]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board1_aux_ch1_data.append(ch1_data_buf)
            board1_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board1_PID_data[140 * i + 139: 140 * i + 139])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board1_PID_data[140 * i + 140: 140 * i + 140])
            if frame_l == 170:
                print("End of frame check succeeded")

        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board2_PID_data[140 * i: 140 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board2_PID_data[140 * i + 1: 140 * i + 2])
            # print(Board_num)
            iir_data_r = bytes_to_num(board2_PID_data[140 * i + 2: 140 * i + 8])
            iir_data_x = bytes_to_num(board2_PID_data[140 * i + 8: 140 * i + 14])
            iir_data_y = bytes_to_num(board2_PID_data[140 * i + 14: 140 * i + 20])
            error_buf = bytes_to_num(board2_PID_data[140 * i + 20: 140 * i + 28])
            feedback_buf = bytes_to_num(board2_PID_data[140 * i + 28: 140 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board2_data[0][0].append(ch1_iir_data_r)
            board2_data[0][1].append(ch1_iir_data_x)
            board2_data[0][2].append(ch1_iir_data_y)
            board2_data[0][3].append(ch1_error_buf)
            board2_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board2_PID_data[140 * i + 34: 140 * i + 40])
            iir_data_x = bytes_to_num(board2_PID_data[140 * i + 40: 140 * i + 46])
            iir_data_y = bytes_to_num(board2_PID_data[140 * i + 46: 140 * i + 52])
            error_buf = bytes_to_num(board2_PID_data[140 * i + 52: 140 * i + 60])
            feedback_buf = bytes_to_num(board2_PID_data[140 * i + 60: 140 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board2_data[1][0].append(ch1_iir_data_r)
            board2_data[1][1].append(ch1_iir_data_x)
            board2_data[1][2].append(ch1_iir_data_y)
            board2_data[1][3].append(ch1_error_buf)
            board2_data[1][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board2_PID_data[140 * i + 66: 140 * i + 72])
            iir_data_x = bytes_to_num(board2_PID_data[140 * i + 72: 140 * i + 78])
            iir_data_y = bytes_to_num(board2_PID_data[140 * i + 78: 140 * i + 84])
            error_buf = bytes_to_num(board2_PID_data[140 * i + 84: 140 * i + 92])
            feedback_buf = bytes_to_num(board2_PID_data[140 * i + 92: 140 * i + 98])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board2_data[2][0].append(ch1_iir_data_r)
            board2_data[2][1].append(ch1_iir_data_x)
            board2_data[2][2].append(ch1_iir_data_y)
            board2_data[2][3].append(ch1_error_buf)
            board2_data[2][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board2_PID_data[140 * i + 98: 140 * i + 104])
            iir_data_x = bytes_to_num(board2_PID_data[140 * i + 104: 140 * i + 110])
            iir_data_y = bytes_to_num(board2_PID_data[140 * i + 110: 140 * i + 116])
            error_buf = bytes_to_num(board2_PID_data[140 * i + 116: 140 * i + 124])
            feedback_buf = bytes_to_num(board2_PID_data[140 * i + 124: 140 * i + 130])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board2_data[3][0].append(ch1_iir_data_r)
            board2_data[3][1].append(ch1_iir_data_x)
            board2_data[3][2].append(ch1_iir_data_y)
            board2_data[3][3].append(ch1_error_buf)
            board2_data[3][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board2_PID_data[140 * i + 130: 140 * i + 134]) % 2**28
            ch2_data = bytes_to_num(board2_PID_data[140 * i + 134: 140 * i + 138]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board2_aux_ch1_data.append(ch1_data_buf)
            board2_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board2_PID_data[140 * i + 139: 140 * i + 139])
            # print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board2_PID_data[140 * i + 140: 140 * i + 140])
            if frame_l == 170:
                print("End of frame check succeeded")

        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board3_PID_data[140 * i: 140 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board3_PID_data[140 * i + 1: 140 * i + 2])
            # print(Board_num)
            iir_data_r = bytes_to_num(board3_PID_data[140 * i + 2: 140 * i + 8])
            iir_data_x = bytes_to_num(board3_PID_data[140 * i + 8: 140 * i + 14])
            iir_data_y = bytes_to_num(board3_PID_data[140 * i + 14: 140 * i + 20])
            error_buf = bytes_to_num(board3_PID_data[140 * i + 20: 140 * i + 28])
            feedback_buf = bytes_to_num(board3_PID_data[140 * i + 28: 140 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board3_data[0][0].append(ch1_iir_data_r)
            board3_data[0][1].append(ch1_iir_data_x)
            board3_data[0][2].append(ch1_iir_data_y)
            board3_data[0][3].append(ch1_error_buf)
            board3_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board3_PID_data[140 * i + 34: 140 * i + 40])
            iir_data_x = bytes_to_num(board3_PID_data[140 * i + 40: 140 * i + 46])
            iir_data_y = bytes_to_num(board3_PID_data[140 * i + 46: 140 * i + 52])
            error_buf = bytes_to_num(board3_PID_data[140 * i + 52: 140 * i + 60])
            feedback_buf = bytes_to_num(board3_PID_data[140 * i + 60: 140 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board3_data[1][0].append(ch1_iir_data_r)
            board3_data[1][1].append(ch1_iir_data_x)
            board3_data[1][2].append(ch1_iir_data_y)
            board3_data[1][3].append(ch1_error_buf)
            board3_data[1][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board3_PID_data[140 * i + 66: 140 * i + 72])
            iir_data_x = bytes_to_num(board3_PID_data[140 * i + 72: 140 * i + 78])
            iir_data_y = bytes_to_num(board3_PID_data[140 * i + 78: 140 * i + 84])
            error_buf = bytes_to_num(board3_PID_data[140 * i + 84: 140 * i + 92])
            feedback_buf = bytes_to_num(board3_PID_data[140 * i + 92: 140 * i + 98])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board3_data[2][0].append(ch1_iir_data_r)
            board3_data[2][1].append(ch1_iir_data_x)
            board3_data[2][2].append(ch1_iir_data_y)
            board3_data[2][3].append(ch1_error_buf)
            board3_data[2][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board3_PID_data[140 * i + 98: 140 * i + 104])
            iir_data_x = bytes_to_num(board3_PID_data[140 * i + 104: 140 * i + 110])
            iir_data_y = bytes_to_num(board3_PID_data[140 * i + 110: 140 * i + 116])
            error_buf = bytes_to_num(board3_PID_data[140 * i + 116: 140 * i + 124])
            feedback_buf = bytes_to_num(board3_PID_data[140 * i + 124: 140 * i + 130])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board3_data[3][0].append(ch1_iir_data_r)
            board3_data[3][1].append(ch1_iir_data_x)
            board3_data[3][2].append(ch1_iir_data_y)
            board3_data[3][3].append(ch1_error_buf)
            board3_data[3][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board3_PID_data[140 * i + 130: 140 * i + 134]) % 2**28
            ch2_data = bytes_to_num(board3_PID_data[140 * i + 134: 140 * i + 138]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board3_aux_ch1_data.append(ch1_data_buf)
            board3_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board3_PID_data[140 * i + 139: 140 * i + 139])
            print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board3_PID_data[140 * i + 140: 140 * i + 140])
            if frame_l == 170:
                print("End of frame check succeeded")

        for i in range(data_num):
            data_buf = 0
            frame_h = bytes_to_num(board4_PID_data[140 * i: 140 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board4_PID_data[140 * i + 1: 140 * i + 2])
            # print(Board_num)
            iir_data_r = bytes_to_num(board4_PID_data[140 * i + 2: 140 * i + 8])
            iir_data_x = bytes_to_num(board4_PID_data[140 * i + 8: 140 * i + 14])
            iir_data_y = bytes_to_num(board4_PID_data[140 * i + 14: 140 * i + 20])
            error_buf = bytes_to_num(board4_PID_data[140 * i + 20: 140 * i + 28])
            feedback_buf = bytes_to_num(board4_PID_data[140 * i + 28: 140 * i + 34])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board4_data[0][0].append(ch1_iir_data_r)
            board4_data[0][1].append(ch1_iir_data_x)
            board4_data[0][2].append(ch1_iir_data_y)
            board4_data[0][3].append(ch1_error_buf)
            board4_data[0][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board4_PID_data[140 * i + 34: 140 * i + 40])
            iir_data_x = bytes_to_num(board4_PID_data[140 * i + 40: 140 * i + 46])
            iir_data_y = bytes_to_num(board4_PID_data[140 * i + 46: 140 * i + 52])
            error_buf = bytes_to_num(board4_PID_data[140 * i + 52: 140 * i + 60])
            feedback_buf = bytes_to_num(board4_PID_data[140 * i + 60: 140 * i + 66])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board4_data[1][0].append(ch1_iir_data_r)
            board4_data[1][1].append(ch1_iir_data_x)
            board4_data[1][2].append(ch1_iir_data_y)
            board4_data[1][3].append(ch1_error_buf)
            board4_data[1][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board4_PID_data[140 * i + 66: 140 * i + 72])
            iir_data_x = bytes_to_num(board4_PID_data[140 * i + 72: 140 * i + 78])
            iir_data_y = bytes_to_num(board4_PID_data[140 * i + 78: 140 * i + 84])
            error_buf = bytes_to_num(board4_PID_data[140 * i + 84: 140 * i + 92])
            feedback_buf = bytes_to_num(board4_PID_data[140 * i + 92: 140 * i + 98])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board4_data[2][0].append(ch1_iir_data_r)
            board4_data[2][1].append(ch1_iir_data_x)
            board4_data[2][2].append(ch1_iir_data_y)
            board4_data[2][3].append(ch1_error_buf)
            board4_data[2][4].append(ch1_feedback_buf)

            iir_data_r = bytes_to_num(board4_PID_data[140 * i + 98: 140 * i + 104])
            iir_data_x = bytes_to_num(board4_PID_data[140 * i + 104: 140 * i + 110])
            iir_data_y = bytes_to_num(board4_PID_data[140 * i + 110: 140 * i + 116])
            error_buf = bytes_to_num(board4_PID_data[140 * i + 116: 140 * i + 124])
            feedback_buf = bytes_to_num(board4_PID_data[140 * i + 124: 140 * i + 130])
            ch1_iir_data_r = iir_data_r / 2**48.0
            if iir_data_y > 2**47-1:
                ch1_iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_y = iir_data_y / 2**48.0
            if iir_data_x > 2**47-1:
                ch1_iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
            else:
                ch1_iir_data_x = iir_data_x / 2**48.0
            if error_buf > 2**63-1:
                ch1_error_buf = (error_buf - 2**64.0) / 2**64.0
            else:
                ch1_error_buf = error_buf / 2**64.0
            ch1_feedback_buf = feedback_buf / 2**48.0
            board4_data[3][0].append(ch1_iir_data_r)
            board4_data[3][1].append(ch1_iir_data_x)
            board4_data[3][2].append(ch1_iir_data_y)
            board4_data[3][3].append(ch1_error_buf)
            board4_data[3][4].append(ch1_feedback_buf)

            ch1_data = bytes_to_num(board4_PID_data[140 * i + 130: 140 * i + 134]) % 2**28
            ch2_data = bytes_to_num(board4_PID_data[140 * i + 134: 140 * i + 138]) % 2**28
            if ch1_data > 2**27-1:
                ch1_data_buf = (ch1_data - 2**28.0) / 2**28.0
            else:
                ch1_data_buf = ch1_data / 2**28.0

            if ch2_data > 2**27-1:
                ch2_data_buf = (ch2_data - 2**28.0) / 2**28.0
            else:
                ch2_data_buf = ch2_data / 2**28.0
            board4_aux_ch1_data.append(ch1_data_buf)
            board4_aux_ch2_data.append(ch2_data_buf)
            time_stamp = bytes_to_num(board4_PID_data[140 * i + 139: 140 * i + 139])
            # print('Time stamp is ', time_stamp)

            frame_l = bytes_to_num(board4_PID_data[140 * i + 140: 140 * i + 140])
            if frame_l == 170:
                print("End of frame check succeeded")
        self.board1_data = board1_data
        self.board2_data = board2_data
        self.board3_data = board3_data
        self.board4_data = board4_data

        return self.board1_data, self.board2_data, self.board3_data, self.board4_data

    def PID_plot(self):
        x = np.array(range(len(self.board1_data[0][0])))
        # plt.plot(x, self.board1_data[0][0], label='Board1_Ch1_iir_r')
        # plt.plot(x, self.board1_data[0][1], label='Board1_Ch1_iir_x')
        # plt.plot(x, self.board1_data[0][2], label='Board1_Ch1_iir_y')
        # plt.plot(x, self.board1_data[0][3], label='Board1_Ch1_error')
        plt.plot(x, self.board1_data[0][4], label='Board1_Ch1_feedback')
        # plt.plot(x, self.board2_data[0][0], label='Board2_Ch1_iir_r')
        # plt.plot(x, self.board2_data[0][1], label='Board2_Ch1_iir_x')
        # plt.plot(x, self.board2_data[0][2], label='Board2_Ch1_iir_y')
        # plt.plot(x, self.board2_data[0][3], label='Board2_Ch1_error')
        plt.plot(x, self.board2_data[0][4], label='Board2_Ch1_feedback')
        # plt.plot(x, self.board3_data[0][0], label='Board3_Ch1_iir_r')
        # plt.plot(x, self.board3_data[0][1], label='Board3_Ch1_iir_x')
        # plt.plot(x, self.board3_data[0][2], label='Board3_Ch1_iir_y')
        # plt.plot(x, self.board3_data[0][3], label='Board3_Ch1_error')
        plt.plot(x, self.board3_data[0][4], label='Board3_Ch1_feedback')
        # plt.plot(x, self.board4_data[0][0], label='Board4_Ch1_iir_r')
        # plt.plot(x, self.board4_data[0][1], label='Board4_Ch1_iir_x')
        # plt.plot(x, self.board4_data[0][2], label='Board4_Ch1_iir_y')
        # plt.plot(x, self.board4_data[0][3], label='Board4_Ch1_error')
        plt.plot(x, self.board4_data[0][4], label='Board4_Ch1_feedback')
        # plt.plot(x, self.board5_data[0][0], label='Board5_Ch1_iir_r')
        # plt.plot(x, self.board5_data[0][1], label='Board5_Ch1_iir_x')
        # plt.plot(x, self.board5_data[0][2], label='Board5_Ch1_iir_y')
        # plt.plot(x, self.board5_data[0][3], label='Board5_Ch1_error')
        plt.plot(x, self.board5_data[0][4], label='Board5_Ch1_feedback')
        # # plt.plot(x, self.PID_data[1][3], label='Ch2_error')
        # # plt.plot(x, self.PID_data[1][4], label='Ch2_feedback')
        # plt.plot(x, self.board1_data[2][1], label='Ch3_iir_x')
        # plt.plot(x, self.board1_data[2][2], label='Ch3_iir_y')
        # # plt.plot(x, self.PID_data[2][3], label='Ch3_error')
        # # plt.plot(x, self.PID_data[2][4], label='Ch3_feedback')
        # plt.plot(x, self.board1_data[3][0], label='Ch4_iir_r')
        # plt.plot(x, self.board1_data[3][1], label='Ch4_iir_x')
        # plt.plot(x, self.board1_data[3][2], label='Ch4_iir_y')
        # plt.plot(x, self.board1_data[3][3], label='Ch4_error')
        # plt.plot(x, self.board1_data[3][4], label='Ch4_feedback')
        plt.xlabel('Time/ns')
        plt.ylabel('error/1')
        plt.legend()
        plt.show()
        # input()
        # plt.pause(6)# 间隔的秒数：6s
        plt.close()

    def Laser1_SPI_Ctrl(self, Value):
        self.DWritePort(b'\x00\xb5')
        self.DWritePort(b'\x00\x00' + num_to_bytes(int(Value/2.5 * 65536), 2))

    def CS_SPI_Ctrl(self, board_num, Value):
        def num_to_bytes_laser(num, bytenum, high_head=True):
            if high_head:
                return np.array([num], dtype='>u8').tobytes()[-bytenum:]
            else:
                return np.array([num], dtype='<u8').tobytes()[:bytenum]
        print("BYtes:",b'\x00\x00' + num_to_bytes_laser(int(Value/2.5 * 65536), 2),(num_to_bytes_laser(board_num, 1) + b'\xb3'))
        self.DWritePort(num_to_bytes_laser(board_num, 1) + b'\xb3')
        self.DWritePort(b'\x00\x00' + num_to_bytes_laser(int(Value/2.5 * 65536), 2))

    def PID_config(self, board_num, PID_ch_num, coe):
        # ch_coe = [set_point, output_offset, kp, ki, kd, PID_LIA_CH]
        if PID_ch_num == 1:
            self.DWritePort(num_to_bytes(board_num, 1) + b'\x24')
            self.DWritePort(num_to_bytes(int(coe[0] * 2**64), 8))
            self.DWritePort(num_to_bytes(int(coe[1]), 6))
            self.DWritePort(num_to_bytes(int(coe[2] * 2**32), 4))# kp
            self.DWritePort(num_to_bytes(int(coe[3] * 2**32), 4))# ki
            self.DWritePort(num_to_bytes(int(coe[4] * 2**32), 4))# kd
            self.DWritePort(num_to_bytes(int(coe[5] * 2**16), 4))# kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(num_to_bytes(int(coe[6]), 1) + num_to_bytes(int(coe[7]), 3))
            self.DWritePort(num_to_bytes(int(coe[8]), 1) + b'\x00')
        elif PID_ch_num == 2:
            self.DWritePort(num_to_bytes(board_num, 1) + b'\x25')
            self.DWritePort(num_to_bytes(int(coe[0] * 2**64), 8))
            self.DWritePort(num_to_bytes(int(coe[1]), 6))
            self.DWritePort(num_to_bytes(int(coe[2] * 2**32), 4))# kp
            self.DWritePort(num_to_bytes(int(coe[3] * 2**32), 4))# ki
            self.DWritePort(num_to_bytes(int(coe[4] * 2**32), 4))# kd
            self.DWritePort(num_to_bytes(int(coe[5] * 2**16), 4))# kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(num_to_bytes(int(coe[6]), 1) + num_to_bytes(int(coe[7]), 3))
            self.DWritePort(num_to_bytes(int(coe[8]), 1) + b'\x00')
        elif PID_ch_num == 3:
            self.DWritePort(num_to_bytes(board_num, 1) + b'\x26')
            self.DWritePort(num_to_bytes(int(coe[0] * 2**64), 8))
            self.DWritePort(num_to_bytes(int(coe[1]), 6))
            self.DWritePort(num_to_bytes(int(coe[2] * 2**32), 4))# kp
            self.DWritePort(num_to_bytes(int(coe[3] * 2**32), 4))# ki
            self.DWritePort(num_to_bytes(int(coe[4] * 2**32), 4))# kd
            self.DWritePort(num_to_bytes(int(coe[5] * 2**16), 4))# kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(num_to_bytes(int(coe[6]), 1) + num_to_bytes(int(coe[7]), 3))
            self.DWritePort(num_to_bytes(int(coe[8]), 1) + b'\x00')
        elif PID_ch_num == 4:
            self.DWritePort(num_to_bytes(board_num, 1) + b'\x27')
            self.DWritePort(num_to_bytes(int(coe[0] * 2**64), 8))
            self.DWritePort(num_to_bytes(int(coe[1]), 6))
            self.DWritePort(num_to_bytes(int(coe[2] * 2**32), 4))# kp
            self.DWritePort(num_to_bytes(int(coe[3] * 2**32), 4))# ki
            self.DWritePort(num_to_bytes(int(coe[4] * 2**32), 4))# kd
            self.DWritePort(num_to_bytes(int(coe[5] * 2**16), 4))# kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(num_to_bytes(int(coe[6]), 1) + num_to_bytes(int(coe[7]), 3))
            self.DWritePort(num_to_bytes(int(coe[8]), 1) + b'\x00')

        elif PID_ch_num == 5:# 激光稳定PID
            print('Laser_pid')
            self.DWritePort(num_to_bytes(board_num, 1) + b'\x23')
            self.DWritePort(num_to_bytes(int(coe[0] * 2**32 * 2**28), 8)) # set_point：预设点为期望慢速ADC采集到的荧光直流信号的大小，需要预先读取一次慢速ADC的数据，然后将数据写入。
            self.DWritePort(num_to_bytes(int(coe[1]/2.5 * 65536), 2) + b'\x00\x00\x00\x00') # output_offset：输出偏置，不太清楚怎么设置，比预想激光功率略小？

            self.DWritePort(num_to_bytes(int(coe[2] * 2**32), 4))
            self.DWritePort(num_to_bytes(int(coe[3] * 2**32), 4))
            self.DWritePort(num_to_bytes(int(coe[4] * 2**32), 4))
            self.DWritePort(num_to_bytes(int(coe[5] * 2**16), 4))# kt：校正系数，调整校正系数以保证前面KP\KI\KD各项系数不出现过大或过小的情况，默认值1。
            self.DWritePort(b'\x00\x00' + num_to_bytes(int(coe[7]), 1) + num_to_bytes(int(coe[6]), 1))
            self.DWritePort(num_to_bytes(int(coe[8]), 2))

        time.sleep(0.001)

    def PID_enable(self, board_ch, ch_num):
        if ch_num == 1:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x28')
        elif ch_num == 2:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x2A')
        elif ch_num == 3:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x2C')
        elif ch_num == 4:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x2E')
        elif ch_num == 5:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x30')
        time.sleep(.001)  #  must be preserved

    def PID_disable(self, board_ch, ch_num):
        if ch_num == 1:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x29')
        elif ch_num == 2:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x2B')
        elif ch_num == 3:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x2D')
        elif ch_num == 4:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x2F')
        elif ch_num == 5:
            self.DWritePort(num_to_bytes(board_ch, 1) + b'\x31')
        time.sleep(.001) #  must be preserved

    def thread_read_pid(self):
        print('thread_read_pid start')
        self.thread_record_run_flag = True
        packs_byte = num_to_bytes(int(self.Laser_pid_data_num + self.Laser_pid_data_num / 50 + 1), 4)
        time.sleep(0.1)
        self.DWritePort(num_to_bytes(self.board_num, 1) + b'\x08')  # 进入到PID状态
        self.DWritePort(packs_byte)
        while self.run_flag:
            pnum = self.ser.in_waiting
            # print(pnum)
            if pnum > 0:
                data_str_tmp = self.DReadPort(pnum)
                self.raw_data_queue.put(data_str_tmp)
        self.thread_record_run_flag = False

    def thread_read_magpid(self):
        print('thread_read_pid start')
        self.thread_record_run_flag = True
        packs_byte = num_to_bytes(int(self.Laser_pid_data_num + self.Laser_pid_data_num / 100 + 1), 4)
        self.DWritePort(num_to_bytes(self.board_num, 1) + b'\x05')  # 进入到PID状态
        self.DWritePort(packs_byte)
        while self.run_flag:
            pnum = self.ser.in_waiting
            # print(pnum)
            if pnum > 0:
                data_str_tmp = self.DReadPort(pnum)
                self.raw_data_queue.put(data_str_tmp)
        self.thread_record_run_flag = False

    def AcquireStartV3_PID(self, board_num, board_ch, data_num):  # board_num 3 5 6 7, board_ch:1 2 3 4
        # 双线程实现PID, 2022-07-19
        self.run_flag = True
        self.cursor = 0
        self.data_str = b''
        self.Laser_pid_data_num = data_num
        self.board_ch = board_ch
        self.board_num = board_num
        while not self.raw_data_queue.empty():
            self.raw_data_queue.get()
        thd_read = threading.Thread(target=self.thread_read_pid, daemon=True)

        thd_decode = threading.Thread(target=self.thread_decode_pid, daemon=True)

        thd_read.start()
        time.sleep(1)
        thd_decode.start()
        while self.run_flag:
            time.sleep(1)
        return self.board_data

    def AcquireStartV3_MagPID(self, board_num, board_ch, data_num):  # board_num 3 5 6 7, board_ch:1 2 3 4

        # 双线程实现PID, 2022-07-19
        self.run_flag = True
        self.cursor = 0
        self.data_str = b''
        self.Laser_pid_data_num = data_num
        self.board_ch = board_ch
        self.board_num = board_num
        while not self.raw_data_queue.empty():
            self.raw_data_queue.get()
        thd_read = threading.Thread(target=self.thread_read_magpid, daemon=True)

        thd_decode = threading.Thread(target=self.thread_decode_magpid, daemon=True)

        thd_read.start()
        time.sleep(0.01)
        thd_decode.start()
        while self.run_flag:
            time.sleep(.01)
        time.sleep(data_num / 400.0)
        return self.board_data

    def thread_decode_magpid(self):
        print('thread_decode_pid self.run_flag ', self.run_flag)
        self.board_data = [[[] for i in range(20)] for i in range(4)]
        time_count = 0
        while self.run_flag:
            # 当前有效数据总长度 >= 140时，开始解析实际数据格式
            # print('thread_decode_pid', len(self.data_str))
            while len(self.data_str) - self.cursor >= 560:
                print(self.data_str[(self.board_ch - 1) * 35 + self.cursor], self.data_str[(self.board_ch - 1) * 35 + self.cursor + 1], self.data_str[(self.board_ch - 1) * 35 + self.cursor + 34])
                if self.data_str[(self.board_ch - 1) * 140 + self.cursor] == 85 and \
                   self.data_str[(self.board_ch - 1) * 140 + self.cursor + 1] == self.board_num and \
                   self.data_str[(self.board_ch - 1) * 140 + self.cursor + 139] == 170:
                    time_count += 1
                    print('data successful! ', str(time_count))
                    # 判断数据格式正确，开始读取

                    # tmp_data = np.zeros(80)
                    for i in range(4):  # board
                        for j in range(4):
                            # error_buf, feedback_buf, DC_data
                            iir_data_r = bytes_to_num(self.data_str[self.cursor + 2 + 140 * i + 32 * j: self.cursor + 8 + 140 * i + 32 * j])
                            iir_data_y = bytes_to_num(self.data_str[self.cursor + 8 + 140 * i + 32 * j: self.cursor + 14 + 140 * i + 32 * j])
                            iir_data_x = bytes_to_num(self.data_str[self.cursor + 14 + 140 * i + 32 * j: self.cursor + 20 + 140 * i + 32 * j])
                            error_buf = bytes_to_num(self.data_str[self.cursor + 20 + 140 * i + 32 * j: self.cursor + 28 + 140 * i + 32 * j])
                            feedback_buf = bytes_to_num(self.data_str[self.cursor + 28 + 140 * i + 32 * j: self.cursor + 34 + 140 * i + 32 * j])
                            # 数据符号化
                            if iir_data_r > 2**47-1:
                                iir_data_r = (iir_data_r - 2**48.0) / 2**48.0
                            else:
                                iir_data_r = iir_data_r / 2**48.0

                            if iir_data_x > 2**47-1:
                                iir_data_x = (iir_data_x - 2**48.0) / 2**48.0
                            else:
                                iir_data_x = iir_data_x / 2**48.0

                            if iir_data_y > 2**47-1:
                                iir_data_y = (iir_data_y - 2**48.0) / 2**48.0
                            else:
                                iir_data_y = iir_data_y / 2**48.0

                            if error_buf > 2**63-1:
                                error_buf = (error_buf - 2**64.0) / 2**64.0
                            else:
                                error_buf = error_buf / 2**64.0

                            feedback_buf = feedback_buf / 524288 + 2600000000
                            #
                            # tmp_data[20 * i + 0 + 5 * j] = iir_data_r
                            # tmp_data[20 * i + 5 * j + 1] = iir_data_x
                            # tmp_data[20 * i + 5 * j + 2] = iir_data_y
                            # tmp_data[20 * i + 5 * j + 3] = error_buf
                            # tmp_data[20 * i + 5 * j + 4] = feedback_buf

                            self.board_data[i][0 + 5 * j].append(iir_data_r)
                            self.board_data[i][1 + 5 * j].append(iir_data_y)
                            self.board_data[i][2 + 5 * j].append(iir_data_x)
                            self.board_data[i][3 + 5 * j].append(error_buf)
                            self.board_data[i][4 + 5 * j].append(feedback_buf)
                    # print('time stamp(received):', int(tmp_data[18]))
                    # self.data_queue.put(tmp_data)
                    # 完成提取，截取数据
                    self.cursor = self.cursor + 140
                else:
                    self.cursor += 1
            # 更新当前坐标
            self.data_str = self.data_str[self.cursor:]
            # print('len=', len(self.data_str))
            self.cursor = 0
            # 获取数据
            qsize = self.raw_data_queue.qsize()
            for i in range(qsize):
                self.data_str = self.data_str + self.raw_data_queue.get()
            # print('data_queue', self.data_queue)
            if len(self.board_data[0][0]) >= self.Laser_pid_data_num:
                print('self.Laser_pid_data_num', self.Laser_pid_data_num, 'self.board_data[3]', self.board_data[3])
                self.run_flag = False

    def thread_decode_pid(self):
        print('thread_decode_pid self.run_flag ', self.run_flag)
        self.board_data = [[[] for i in range(3)] for i in range(4)]
        time_count = 0
        while self.run_flag:
            # 当前有效数据总长度 >= 140时，开始解析实际数据格式
            # print('thread_decode_pid', len(self.data_str))
            while len(self.data_str) - self.cursor >= 64:
                # print(self.board_ch)
                # print(self.data_str[(self.board_ch - 1) * 16 + self.cursor])
                # print(self.data_str[(self.board_ch - 1) * 16 + self.cursor + 1])
                # print(self.data_str[(self.board_ch - 1) * 16 + self.cursor + 15])
                # print(self.cursor)
                # print(self.data_str[self.cursor], self.data_str[self.cursor + 1], self.data_str[self.cursor +139])
                # print_bytes(self.data_str[self.cursor:self.cursor + 140])
                if self.data_str[(self.board_ch - 1) * 16 + self.cursor] == 85 and \
                   self.data_str[(self.board_ch - 1) * 16 + self.cursor + 1] == self.board_num and \
                   self.data_str[(self.board_ch - 1) * 16 + self.cursor + 15] == 170:
                    time_count += 1
                    # print('data successful! ', str(time_count))
                    # 判断数据格式正确，开始读取

                    # tmp_data = np.zeros(12)
                    for i in range(4):
                        # error_buf, feedback_buf, DC_data
                        error_buf = bytes_to_num(self.data_str[self.cursor + 2 + 16 * i: self.cursor + 6 + 16 * i])
                        feedback_buf = bytes_to_num(self.data_str[self.cursor + 6 + 16 * i: self.cursor + 10 + 16 * i])
                        DC_data = bytes_to_num(self.data_str[self.cursor + 20 + 10 * i: self.cursor + 14 + 16 * i]) % 2**28
                        # 数据符号化
                        if error_buf > 2 ** 31 - 1:
                            error_buf = float(error_buf - 2 ** 32) / 2 ** 28
                        else:
                            error_buf = float(error_buf) / 2 ** 28
                        feedback_buf = feedback_buf / 2 ** 32 * 2.5
                        # tmp_data[3 * i + 0] = error_buf
                        # tmp_data[3 * i + 1] = feedback_buf
                        # tmp_data[3 * i + 2] = DC_data
                        self.board_data[i][0].append(error_buf)
                        self.board_data[i][1].append(feedback_buf)
                        self.board_data[i][2].append(DC_data)
                    # print('time stamp(received):', int(tmp_data[18]))
                    # self.data_queue.put(tmp_data)
                    # 完成提取，截取数据
                    self.cursor = self.cursor + 64
                else:
                    self.cursor += 1
            # 更新当前坐标
            self.data_str = self.data_str[self.cursor:]
            # print('len=', len(self.data_str))
            self.cursor = 0
            # 获取数据
            qsize = self.raw_data_queue.qsize()
            for i in range(qsize):
                self.data_str = self.data_str + self.raw_data_queue.get()
            # print('data_queue', self.data_queue)
            if len(self.board_data[0][0]) >= self.Laser_pid_data_num:
                print('self.Laser_pid_data_num', self.Laser_pid_data_num, 'self.board_data[3]', self.board_data[3])
                self.run_flag = False

    def Laser_PID_play(self, ch_num, data_num):
        # 使用前需要确保系统处于IDLE状态
        self.DWritePort(b'\x00\x00')

        self.DWritePort(num_to_bytes(ch_num, 1) + b'\x08')  # 进入到PID状态
        time.sleep(self.tc * 6)
        self.DWritePort(num_to_bytes(data_num, 4))
        board1_PID_data = b''
        board2_PID_data = b''
        board3_PID_data = b''
        board4_PID_data = b''
        board5_PID_data = b''
        board6_PID_data = b''
        board7_PID_data = b''
        board8_PID_data = b''

        PID_data=self.DReadPort(16*8*data_num)
        # print("solved")
        # input()
        for i in range(data_num):
            board1_PID_data += PID_data[i*16*8:i*16*8+16]
            board2_PID_data += PID_data[i*16*8+16:i*16*8+16*2]
            board3_PID_data += PID_data[i*16*8+16*2:i*16*8+16*3]
            board4_PID_data += PID_data[i*16*8+16*3:i*16*8+16*4]
            board5_PID_data += PID_data[i*16*8+16*4:i*16*8+16*5]
            board6_PID_data += PID_data[i*16*8+16*5:i*16*8+16*6]
            board7_PID_data += PID_data[i*16*8+16*6:i*16*8+16*7]
            board8_PID_data += PID_data[i*16*8+16*7:i*16*8+16*8]

        board1_data = [[] for i in range(3)]
        board2_data = [[] for i in range(3)]
        board3_data = [[] for i in range(3)]
        board4_data = [[] for i in range(3)]
        board5_data = [[] for i in range(3)]
        board6_data = [[] for i in range(3)]
        board7_data = [[] for i in range(3)]
        board8_data = [[] for i in range(3)]

        for i in range(data_num):

            frame_h = bytes_to_num(board1_PID_data[16 * i: 16 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board1_PID_data[16 * i + 1: 16 * i + 2])
            # print(Board_num)
            error_buf = bytes_to_num(board1_PID_data[16 * i + 2: 16 * i + 6])
            feedback_buf = bytes_to_num(board1_PID_data[16 * i + 6: 16 * i + 10])
            ch1_data = bytes_to_num(board1_PID_data[16 * i + 10: 16 * i + 14]) % 2**28

            if error_buf > 2 **31  - 1:
                error_buf = error_buf - 2**32
            board1_data[0].append(error_buf/2**28)
            board1_data[1].append(feedback_buf / 2**32 * 2.5)
            board1_data[2].append(ch1_data/2**28)

            frame_h = bytes_to_num(board2_PID_data[16 * i: 16 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board2_PID_data[16 * i + 1: 16 * i + 2])
            # print(Board_num)
            error_buf = bytes_to_num(board2_PID_data[16 * i + 2: 16 * i + 6])
            feedback_buf = bytes_to_num(board2_PID_data[16 * i + 6: 16 * i + 10])
            ch1_data = bytes_to_num(board2_PID_data[16 * i + 10: 16 * i + 14]) % 2**28

            if error_buf > 2 **31  - 1:
                error_buf = error_buf - 2**32
            board2_data[0].append(error_buf/2**28)
            board2_data[1].append(feedback_buf / 2**32 * 2.5)
            board2_data[2].append(ch1_data/2**28)

            frame_h = bytes_to_num(board3_PID_data[16 * i: 16 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board3_PID_data[16 * i + 1: 16 * i + 2])
            # print(Board_num)
            error_buf = bytes_to_num(board3_PID_data[16 * i + 2: 16 * i + 6])
            feedback_buf = bytes_to_num(board3_PID_data[16 * i + 6: 16 * i + 10])
            ch1_data = bytes_to_num(board3_PID_data[16 * i + 10: 16 * i + 14]) % 2**28

            if error_buf > 2 **31 - 1:
                error_buf = error_buf - 2**32
            board3_data[0].append(error_buf/2**28)
            board3_data[1].append(feedback_buf / 2**32 * 2.5)
            board3_data[2].append(ch1_data/2**28)

            frame_h = bytes_to_num(board4_PID_data[16 * i: 16 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board4_PID_data[16 * i + 1: 16 * i + 2])
            # print(Board_num)
            error_buf = bytes_to_num(board4_PID_data[16 * i + 2: 16 * i + 6])
            feedback_buf = bytes_to_num(board4_PID_data[16 * i + 6: 16 * i + 10])
            ch1_data = bytes_to_num(board4_PID_data[16 * i + 10: 16 * i + 14]) % 2**28

            if error_buf > 2 **31  - 1:
                error_buf = error_buf - 2**32
            board4_data[0].append(error_buf/2**28)
            board4_data[1].append(feedback_buf / 2**32 * 2.5)
            board4_data[2].append(ch1_data/2**28)

            frame_h = bytes_to_num(board5_PID_data[16 * i: 16 * i + 1])
            if frame_h == 85:
                print("Frame header check succeeded")
            Board_num = bytes_to_num(board5_PID_data[16 * i + 1: 16 * i + 2])
            # print(Board_num)
            error_buf = bytes_to_num(board5_PID_data[16 * i + 2: 16 * i + 6])
            feedback_buf = bytes_to_num(board5_PID_data[16 * i + 6: 16 * i + 10])
            ch1_data = bytes_to_num(board5_PID_data[16 * i + 10: 16 * i + 14]) % 2**28

            if error_buf > 2 **31  - 1:
                error_buf = error_buf - 2**32
            board5_data[0].append(error_buf/2**28)
            board5_data[1].append(feedback_buf / 2**32 * 2.5)
            board5_data[2].append(ch1_data/2**28)

        self.board1_data = board1_data
        self.board2_data = board2_data
        self.board3_data = board3_data
        self.board4_data = board4_data
        self.board5_data = board5_data
        return self.board1_data, self.board2_data, self.board3_data, self.board4_data,self.board5_data

    def Laser_PID_plot(self):
        x = np.array(range(len(self.board1_data[0]))) / 7.0
        # plt.plot(x, self.board1_data[0], label='Board1_Ch1_error')
        plt.plot(x, self.board1_data[1], label='Board1_Ch1_feedback')
        # plt.plot(x, self.board2_data[0], label='Board2_Ch1_error')
        plt.plot(x, self.board2_data[1], label='Board2_Ch1_feedback')
        # plt.plot(x, self.board3_data[0], label='Board3_Ch1_error')
        # plt.plot(x, self.board4_data[0], label='Board4_Ch1_error')
        # plt.plot(x, self.board5_data[0], label='Board5_Ch1_error')
        plt.plot(x, self.board3_data[1], label='Board3_Ch1_feedback')
        # plt.plot(x, self.board_data[3][0], label='Ch1_error/1')
        plt.plot(x, self.board4_data[1], label='Board4_Ch1_feedback')
        plt.plot(x, self.board5_data[1], label='Board5_Ch1_feedback')
        plt.xlabel('Time/s')
        plt.ylabel('1')
        plt.legend()
        plt.show()

    def all_start(self, board_ch):
        self.DWritePort(num_to_bytes(board_ch, 1) + b'\x3C')
        time.sleep(0.001)

    def all_stop(self, board_ch):
        self.DWritePort(num_to_bytes(board_ch, 1) + b'\x3D')
        time.sleep(0.001)

    def MW_SPI_Ctrl(self, board_ch, ch1_Fre, ch1_modu, ch1_atte, ch2_Fre, ch2_modu, ch2_atte):
        # 0, 268435455
        if ch1_Fre > 268535455 or ch1_Fre < 0:
            ch1_Fre = 0
            print('ch1_Fre input Out of range', ch1_Fre)
            print('ch_Fre = ', )
        if ch2_Fre > 268535455 or ch2_Fre < 0:
            print('ch2_Fre input Out of range')
            ch2_Fre = 0
        if ch1_modu > 100 or ch1_modu < 0 or ch2_modu > 100 or ch2_modu < 0:
            print('ch3_Fre input Out of range')

        if ch1_atte > 30 or ch1_atte < 0 or ch2_atte > 30 or ch2_atte < 0:
            print('ch4_Fre input Out of range')

        self.DWritePort(num_to_bytes(board_ch, 1) + b'\xb1')
        data_buf1 = 3 + ch2_atte * 2**2 + ch2_modu * 2**7 + ch2_Fre * 2 ** 12 + ch1_atte * 2 **40 + ch1_modu * 2 ** 45 + ch1_Fre * 2 ** 50 + 1 * 2 ** 78

        self.DWritePort(num_to_bytes_old0(data_buf1, 10))
        time.sleep(.005)

    def MW_SPI_Ctrl_OLD(self, board_ch, ch1_Fre, ch1_modu, ch1_atte, ch2_Fre, ch2_modu, ch2_atte, ch3_Fre, ch3_modu, ch3_atte, ch4_Fre, ch4_modu, ch4_atte):
        # 0, 268435455
        if ch1_Fre > 268535455 or ch1_Fre < 0:
            ch1_Fre = 0
            print('ch_Fre input Out of range')
        if ch2_Fre > 268535455 or ch2_Fre < 0:
            print('ch_Fre input Out of range')
            ch2_Fre = 0
        if ch1_modu > 100 or ch1_modu < 0 or ch2_modu > 100 or ch2_modu < 0:
            print('ch_Fre input Out of range')

        if ch1_atte > 30 or ch1_atte < 0 or ch2_atte > 30 or ch2_atte < 0:
            print('ch_Fre input Out of range')

        self.DWritePort(num_to_bytes(board_ch, 1) + b'\xb1')
        data_mw1 = 5 + ch2_atte * 2**4 + ch2_modu * 2**9 + ch2_Fre * 2 ** 16 + ch1_atte * 2 **38 + ch1_modu * 2 ** 43 + ch1_Fre * 2 ** 50
        data_mw2 = 5 + ch4_atte * 2**4 + ch4_modu * 2**9 + ch4_Fre * 2 ** 16 + ch3_atte * 2 **38 + ch3_modu * 2 ** 43 + ch3_Fre * 2 ** 50
        # self.DWritePort(b'\x00\x00')
        self.DWritePort(num_to_bytes(161, 1) + num_to_bytes_old0(data_mw1, 9))
        time.sleep(.01)

        self.DWritePort(num_to_bytes(162, 1) + num_to_bytes_old0(data_mw2, 9))
    # def AUXADC_rd(self):
    #     self.DWritePort(b'\x00\xAF')
    #     AUX_data = self.DReadPort(8)
    #     ch1_data = bytes_to_num(AUX_data[0: 4])
    #     ch2_data = bytes_to_num(AUX_data[4: 7])
    #     if ch1_data > 2**31-1:
    #         ch1_data_buf = (ch1_data - 2**32.0) / 2**32.0
    #     else:
    #         ch1_data_buf = ch1_data / 2**32.0
    #
    #     if ch2_data > 2**31-1:
    #         ch2_data_buf = (ch2_data - 2**32.0) / 2**32.0
    #     else:
    #         ch2_data_buf = ch2_data / 2**32.0
    #     return ch1_data_buf, ch2_data_buf

    # def error_check(self, data_num):
    #
    #     # 使用前需要确保系统处于IDLE状态
    #     self.DWritePort(b'\x00\x00')
    #     time.sleep(.1)
    #     self.DWritePort(b'\x00\x06')
    #
    #     self.DWritePort(num_to_bytes(data_num, 4))
    #     DAQ_data = b''
    #     DAQ_data += self.DReadPort(int((data_num) * 2))
    #     print(len(DAQ_data))
    #     data = []
    #
    #     for i in range(data_num):
    #         data_buf = bytes_to_num(DAQ_data[2 * i: 2 * i + 2])
    #         data.append(data_buf)
    #         if data_buf != data_num - i:
    #             print('!!!error!!!')
    #     print(data)

    def PLL_RD(self, ch_num, addr):
        self.DWritePort(num_to_bytes(ch_num, 1) + b'\x42')
        self.DWritePort(num_to_bytes(addr + 32768, 2))
        print(str_to_hexstr(self.DReadPort(4)))
        time.sleep(.1)

    def XADC_TEMP_RD(self, board_num):
        self.DWritePort(num_to_bytes(board_num, 1) + b'\xc4')
        time.sleep(0.1)
        # data = self.DReadPort(2)
        tmp = bytes_to_num(self.DReadPort(2)) * 503.975 / 4096 - 273.15
        # tmp = data * 0.5
        print('板卡温度为', tmp,'℃')
        return tmp

def csv_save(path, *args):
    dataframe = pd.DataFrame(*args)
    dataframe.to_csv(path, index=False, sep=',')

def ini_wr(Section, item, value):
    config = configparser.ConfigParser()
    config.read("Tensor_Master.ini")
    try:
        config.add_section(Section)
    except configparser.DuplicateSectionError:
        print("Section 'Match' already exists")

    config.set(Section, item, value)
    config.write(open("Tensor_Master.ini", "w"))

def ini_rd(Section, item):
    config = configparser.ConfigParser()
    config.read("Tensor_Master.ini")
    try:
        config.add_section("Section")
    except configparser.DuplicateSectionError:
        print("Section 'Match' already exists")

    try:
        Value = config.get(Section, item)
        return Value
    except:
        pass

class API_Multichannel(object):
    def __init__(self, portx="COM4"):

        self.SYS_config = config_mini(portx=portx)

        self.mw1_para = {'ch1_Fre': 2800000, 'ch1_modu': 15, 'ch1_atte': 0, 'ch2_Fre': 2800000, 'ch2_modu': 18,
                         'ch2_atte': 0}
        self.mw2_para = {'ch1_Fre': 2906625, 'ch1_modu': 20, 'ch1_atte': 30, 'ch2_Fre': 2982125, 'ch2_modu': 20,
                         'ch2_atte': 30}
        self.ch1_Fre = int((2750000000 - 2600000000) * 0.5)
        self.ch1_modu = 0
        self.ch1_atte = 0
        self.ch2_Fre = int((3090000000 - 2600000000) * 0.5)
        self.ch2_modu = 0
        self.ch2_atte = 0
        self.spr = 50
        self.raw_data_queue = queue.Queue(maxsize=5000)
        self.data_queue = queue.Queue(maxsize=5000)
        self.IIR_run_flag = True

    def connect_device(self):
        self.USB_START()

    def disconnect_device(self):
        self.USB_END()

    def USB_START(self):
        """
        开启USB设备
        设备识别码：DNVCS-API-TotalField-0001
        API-TotalField
        """
        self.open_device(vendor_id=self.vendor_id, product_id=self.product_id)

    def USB_END(self):
        """
        断开USB设备
        设备识别码：DNVCS-API-TotalField-0002
        API-TotalField
        """
        # 断开连接
        self.close_device()

    def De_fre_config(self, ch_num, Value):
        # LIA_config = {'type': 'De_fre', 'ch': 1, 'Value': 10.033*10**6}
        LIA_config = {'type': 'De_fre', 'ch': ch_num, 'Value': Value}
        self.SYS_config.play_info(LIA_config)

    def De_phase_config(self, ch_num, Value):
        # LIA_config = {'type': 'De_fre', 'ch': 1, 'Value': 0.0}
        LIA_config = {'type': 'De_phase', 'ch': ch_num, 'Value': Value}
        self.SYS_config.play_info(LIA_config)

    def Modu_fre_config(self, ch_num, Value):
        # LIA_config = {'type': 'De_fre', 'ch': 1, 'Value': 10.033*10**6}
        LIA_config = {'type': 'Modu_fre', 'ch': ch_num, 'Value': Value}
        self.SYS_config.play_info(LIA_config)

    def Modu_phase_config(self, ch_num, Value):
        # LIA_config = {'type': 'De_fre', 'ch': 1, 'Value': 0.0}
        LIA_config = {'type': 'Modu_phase', 'ch': ch_num, 'Value': Value}
        self.SYS_config.play_info(LIA_config)

    def sample_rate_config(self, Value):
        # LIA_config = {'type': 'sample_rate', 'Value': 10**3}
        LIA_config = {'type': 'sample_rate', 'Value': Value}
        self.SYS_config.play_info(LIA_config)

    def tc(self, Value):
        # LIA_config = {'type': 'tc', 'Value': 1.0}
        LIA_config = {'type': 'tc', 'Value': Value}
        self.SYS_config.play_info(LIA_config)

    def switch_set(self,num):
        """
        主控通讯方式选通
        设备识别码：DNVCS-API-Multichannel-0008
        API-Multichannel
        :param num: ？？？ int ？？？ ？？？ 0
        """
        self.SYS_config.SWITCH_SET(num)
        return 0

    def UACM_config(self,config_data,receive_num):
        """
        水声通信机配置,写入指令字，回执指令字字节数
        设备识别码：DNVCS-API-Multichannel-0010
        API-Multichannel
        :param config_data: 写入指令 str unlimmited unlimmited None
        :param receive_num: 回执指令字字节数 int unlimmited unlimmited 1
        """
        self.SYS_config.UACM_config(config_data,receive_num)
        return 0

    def UACM_send(self,data):
        """
        水声通信机发送信息
        设备识别码：DNVCS-API-Multichannel-0011
        API-Multichannel
        :param data: 写入数据 str unlimmited unlimmited None
        """
        self.SYS_config.UACM_send(data)
        return 0

    def speed_set(self,speed):
        """
        主控通讯数据率设置
        设备识别码：DNVCS-API-Multichannel-0009
        API-Multichannel
        :param speed: 读回锁相时输入500000，读回磁通门时输入100000 int in [500000,100000] 500000
        """
        self.SYS_config.speed_set(speed)
        return 0

    def DAC_play(self, board_num):
        """
        预配置字写入
        设备识别码：DNVCS-API-Multichannel-0008
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        """
        self.SYS_config.play(board_num)

    def daq_play(self, board_num, data_num, extract_ratio):
        """
        交流ADC读回
        设备识别码：DNVCS-API-Multichannel-0006
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param data_num: 数据采集点数 int between [0,10000] 10
        :param extract_ratio: 抽取率 float between [0,1] 0.1
        """
        DAQ_data = self.SYS_config.DAQ_play(board_num, data_num, extract_ratio)
        return DAQ_data

    def daq_plot(self):
        """
        交流ADC画图
        设备识别码：DNVCS-API-Multichannel-0007
        API-Multichannel
        """
        self.SYS_config.daq_plot()

    def auxdaq_play(self, board_num, data_num):
        """
        直流ADC读回
        设备识别码：DNVCS-API-Multichannel-0006
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param data_num: 数据采集点数 int between [0,10000] 10
        """
        AUXDAQ_data = self.SYS_config.AUXDAQ_play(board_num, data_num)
        return AUXDAQ_data

    def auxdaq_plot(self):
        """
        直流ADC画图
        设备识别码：DNVCS-API-Multichannel-0006
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param data_num: 数据采集点数 int between [0,10000] 10
        """
        self.SYS_config.auxdaq_plot()

    def flux_play(self, board_num, data_num):
        """
        磁通门数据读回
        设备识别码：DNVCS-API-Multichannel-0012
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param data_num: 数据采集点数 int between [0,10000] 10
        """
        DAQ_data = self.SYS_config.FLUX_play(board_num, data_num)
        return DAQ_data

    def flux_plot(self):
        """
        磁通门数据画图
        设备识别码：DNVCS-API-Multichannel-0013
        API-Multichannel
        """
        self.SYS_config.FLUX_plot()

    def iir_play(self, board_num, data_num, CW_mode=False):
        """
        读取某一个锁相通道返回值（固定点数）
        设备识别码：DNVCS-API-Multichannel-0001
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param data_num: 锁相板卡数据采集点数 int between [0,10000] 10
        :param CW_mode: ??? bool in [True,False] False
        """
        IIR_data = self.SYS_config.IIR_play(board_num, data_num, CW_mode)
        return IIR_data

    def iir_plot(self):
        """
        读取某一个锁相通道返回值（固定点数）
        设备识别码：DNVCS-API-Multichannel-0001
        API-Multichannel
        """
        self.SYS_config.IIR_plot()

    def five_CH_READ(self,datanum_nv,datanum_flux):
        """
        2通道锁相+3通道磁通门读回
        设备识别码：DNVCS-API-Multichannel-0001
        API-Multichannel
        :param datanum_nv: 锁相板卡数据采集点数 int between [0,10000] 10
        :param datanum_flux: 磁通门数据采集点数 int between [0,10000] 10
        """
        self.SYS_config.five_ch_read(datanum_nv,datanum_flux)

    def five_CH_PLOT(self):
        """
        2通道锁相+3通道磁通门画图
        设备识别码：DNVCS-API-Multichannel-0001
        API-Multichannel
        """
        self.SYS_config.five_ch_plot()

    def laser_SPI_ctrl(self, board_num, value):
        """
        激光电流控制
        设备识别码：DNVCS-API-Multichannel-0014
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 1
        :param value: 激光电流大小 float between [0,5] 1
        """
        board_num = int(board_num)
        value = float(value)
        self.SYS_config.CS_SPI_Ctrl(board_num, value)

    def MW_SPI_ctrl(self,board_num, ch1_Fre, ch1_modu, ch1_atte, ch2_Fre, ch2_modu, ch2_atte):
        """
        微波源控制
        设备识别码：DNVCS-API-Multichannel-0015
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param ch1_Fre: 微波频率 int between [0,4E9] 2.6E9
        :param ch1_modu: 调制深度 float between [0,1] 0
        :param ch1_atte: 衰减 int between [0,1E2] 1
        :param ch2_Fre: 微波频率 int between [0,4E9] 2.6E9
        :param ch2_modu: 调制深度 float between [0,1] 0
        :param ch2_atte: 衰减 int between [0,1E2] 1
        """
        self.SYS_config.MW_SPI_Ctrl(board_num, ch1_Fre, ch1_modu, ch1_atte, ch2_Fre, ch2_modu, ch2_atte)

    def set_freq(self, board_num, freq):
        """
        微波源频率控制
        设备识别码：DNVCS-API-Multichannel-0016
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param freq: 微波频率 int between [0,4E9] 2.6E9
        """
        self.ch1_Fre = int((int(freq) - 2600000000) * 0.5)
        # print("In set_freq:", freq,int(str(freq)+'0'), int(str(freq)+'0')-2600000000)
        self.ch2_Fre = int((3090000000 - 2600000000) * 0.5)
        self.SYS_config.MW_SPI_Ctrl(board_num, self.ch1_Fre, self.ch1_modu, self.ch1_atte, self.ch2_Fre, self.ch2_modu,
                                    self.ch2_atte)
        time.sleep(0.1)
        self.SYS_config.MW_SPI_Ctrl(board_num, self.ch1_Fre, self.ch1_modu, self.ch1_atte, self.ch2_Fre, self.ch2_modu,
                                    self.ch2_atte)
        print("Freqs:",self.ch1_Fre, self.ch1_modu, self.ch1_atte, self.ch2_Fre, self.ch1_modu, self.ch2_atte)
        time.sleep(0.1)

    def set_power(self, board_num, power):
        """
        微波功率控制
        设备识别码：DNVCS-API-Multichannel-0017
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2 0
        :param power: 衰减 int between [0,1E2] 1
        """
        self.ch1_atte = 30 - power
        self.ch2_atte = 30
        self.SYS_config.MW_SPI_Ctrl(board_num, self.ch1_Fre, self.ch1_modu, self.ch1_atte, self.ch2_Fre, self.ch2_modu,
                                    self.ch2_atte)
        time.sleep(0.1)
        self.SYS_config.MW_SPI_Ctrl(board_num, self.ch1_Fre, self.ch1_modu, self.ch1_atte, self.ch2_Fre, self.ch2_modu,
                                    self.ch2_atte)
        time.sleep(0.1)

    def set_fm_sens(self, board_num, val):
        """
        微波源FN_sens控制
        设备识别码：DNVCS-API-Multichannel-0018
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param val: 调制深度 float between [0,1] 0
        """
        val = int(val * 100)
        self.ch1_modu = val
        self.ch2_modu = 0
        self.SYS_config.MW_SPI_Ctrl(board_num, self.ch1_Fre, self.ch1_modu, self.ch1_atte, self.ch2_Fre, self.ch2_modu,
                                    self.ch2_atte)
        time.sleep(0.1)
        self.SYS_config.MW_SPI_Ctrl(board_num, self.ch1_Fre, self.ch1_modu, self.ch1_atte, self.ch2_Fre, self.ch2_modu,
                                    self.ch2_atte)
        time.sleep(0.1)

    def MW1_SPI_ctrl(self, board_num, *args):
        if len(args) == 0:
            #加载预设值
            # print('MW1:', self.mw1_para)
            ch1_Fre = int((self.mw1_para['ch1_Fre'] * 1000 - 2600000000) * 0.5)
            ch2_Fre = int((self.mw1_para['ch2_Fre'] * 1000 - 2600000000) * 0.5)
            ch3_Fre = int((self.mw2_para['ch1_Fre'] * 1000 - 2600000000) * 0.5)
            ch4_Fre = int((self.mw2_para['ch2_Fre'] * 1000 - 2600000000) * 0.5)
            self.SYS_config.MW_SPI_Ctrl(board_num, ch1_Fre, self.mw1_para['ch1_modu'], self.mw1_para['ch1_atte'],
                                        ch2_Fre, self.mw1_para['ch2_modu'], self.mw1_para['ch2_atte'],
                                        ch3_Fre, self.mw2_para['ch1_modu'], self.mw2_para['ch1_atte'],
                                        ch4_Fre, self.mw2_para['ch2_modu'], self.mw2_para['ch2_atte'])
        else:
            Fre = []
            modu = []
            atte = []
            print('args = ', args)
            mw_para = args[0]
            for i in mw_para:
                print(i)
                Fre.append(int((int(i[0]) - 2600000000) * 0.5))
                modu.append(i[1])
                atte.append(i[2])

            self.SYS_config.MW_SPI_Ctrl(board_num, Fre[0], modu[0], atte[0],
                                        Fre[1], modu[1], atte[1],
                                        Fre[2], modu[2], atte[2],
                                        Fre[3], modu[3], atte[3])

    def MW2_SPI_ctrl(self, board_num, ch1_Fre, ch1_modu=20, ch1_atte=0):
        # print('MW1:', self.mw1_para)
        ch1_Fre = int((ch1_Fre - 2600000000) * 0.5)
        ch2_Fre = int((self.mw1_para['ch2_Fre'] * 1000 - 2600000000) * 0.5)
        ch3_Fre = int((self.mw2_para['ch1_Fre'] * 1000 - 2600000000) * 0.5)
        ch4_Fre = int((self.mw2_para['ch2_Fre'] * 1000 - 2600000000) * 0.5)
        self.SYS_config.MW_SPI_Ctrl(board_num,
                                    ch2_Fre, self.mw1_para['ch2_modu'], self.mw1_para['ch2_atte'],
                                    ch3_Fre, self.mw2_para['ch1_modu'], self.mw2_para['ch1_atte'],
                                    ch1_Fre, ch1_modu, ch1_atte,
                                    ch4_Fre, self.mw2_para['ch2_modu'], self.mw2_para['ch2_atte'])

    def PID_play(self, board_num, data_num):
        """
        PID读出
        设备识别码：DNVCS-API-Multichannel-0006
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param data_num: 数据采集点数 int between [0,10000] 10
        """
        PID_data = self.SYS_config.PID_play(board_num, data_num)
        return PID_data

    def PID_plot(self):
        """
        PID画图
        设备识别码：DNVCS-API-Multichannel-0007
        API-Multichannel
        """
        self.SYS_config.PID_plot()

    def Laser_PID_play(self, board_num, data_num):
        """
        激光PID读出
        设备识别码：DNVCS-API-Multichannel-0004
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param data_num: 数据采集点数 int between [0,10000] 10
        """
        PID_data = self.SYS_config.Laser_PID_play(board_num, data_num)
        return PID_data

    def Laser_pid_plot(self):
        """
        激光PID画图
        设备识别码：DNVCS-API-Multichannel-0005
        API-Multichannel
        """
        self.SYS_config.Laser_PID_plot()

    def ALL_start(self, board_num):
        """
        锁相功能开启
        设备识别码：DNVCS-API-Multichannel-0016
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 1
        """
        self.SYS_config.all_start(board_num)

    def ALL_stop(self, board_num):
        """
        锁相功能关闭
        设备识别码：DNVCS-API-Multichannel-0017
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 1
        """
        self.SYS_config.all_stop(board_num)

    def pid_config(self, board_num, PID_ch_num, set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH):
        """
        设置PID参数
        设备识别码：DNVCS-API-Multichannel-0001
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 1
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
        # ch_num: int in [1, 2, 3, 4]
        # ch_coe = [set_point, output_offset, kp, ki, kd, PID_RD_RITIO, PID_EX_RATIO, PID_LIA_CH]
        # PID_LIA_CH = 0,1,3 0:LIA_X, 1:LIA_Y, 3:LIA_R
        self.SYS_config.PID_config(board_num, PID_ch_num, coe)

    def pid_enable(self, board_ch, ch_num):
        """
        PID模式启动
        设备识别码：DNVCS-API-Multichannel-0002
        API-Multichannel
        :param board_ch: 锁相ID int in [2,3,5,6,7,255] 2
        :param ch_num: PID通道 int in [1,2,3,4] 1
        """
        # ch_num: int in [1, 2]
        self.SYS_config.PID_enable(board_ch, ch_num)

    def pid_disable(self, board_ch, ch_num):
        """
        PID模式关闭
        设备识别码：DNVCS-API-Multichannel-0003
        API-Multichannel
        :param board_ch: 锁相ID int in [2,3,5,6,7,255] 2
        :param ch_num: PID通道 int in [1,2,3,4] 1
        """
        # ch_num: int in [1, 2]
        self.SYS_config.PID_disable(board_ch, ch_num)

    def XADC_TEMP_RD(self, board_ch):
        self.SYS_config.XADC_TEMP_RD(board_ch)

    def AcquireStartV3_PID(self, board_num, board_ch, data_num):
        data = self.SYS_config.AcquireStartV3_PID(board_num, board_ch, data_num)
        return data

    def AcquireStartV3_MagPID(self, board_num, board_ch, data_num):
        data = self.SYS_config.AcquireStartV3_MagPID(board_num, board_ch, data_num)
        return data

    def SetLockInFreq(self, freq, ch=-1):
        """
        锁相板卡调制频率设置
        设备识别码：DNVCS-API-Multichannel-0002
        API-Multichannel
        :param freq: 调制/解调频率 int between [1,1E6] 1E3
        :param ch: 通道ID，始于0，默认为全设置 int in [-1,0,1,2,3] 0
        """
        if ch == -1:
            [self.De_fre_config(1 + ii, freq) for ii in range(CHUNIT)]
            [self.Modu_fre_config(1 + ii, freq) for ii in range(CHUNIT)]

        elif 0 <= ch <= CHUNIT - 1:
            self.De_fre_config(1 + int(ch), freq)
            self.Modu_fre_config(1 + int(ch), freq)

    def SetLockInPhase(self, phase_ddc, ch=-1):
        """
        锁相板卡调制相位设置
        设备识别码：DNVCS-API-Multichannel-0003
        API-Multichannel
        :param phase_ddc: 相位，1-180度 unlimmited unlimmited unlimmited None
        :param ch: 通道ID，0为荧光，1为激光 int in [0,1] 0
        """
        if ch == -1:
            [self.De_phase_config(1 + ii, phase_ddc) for ii in range(CHUNIT)]
        elif 0 <= ch <= CHUNIT * 2 - 1:
            self.De_phase_config(1 + int(ch), phase_ddc)

    def SetLockInTimeConst(self, timeconst):
        """
        锁相时间常数设置
        设备识别码：DNVCS-API-Multichannel-0006
        API-Multichannel
        :param timeconst: 时间常熟 unlimmited unlimmited unlimmited 0.1
        """
        self.tc(timeconst)

    def SetDataSampleRate(self, daq_sample_rate):
        """
        设置采样率
        设备识别码：DNVCS-API-Multichannel-0008
        API-Multichannel
        :param daq_sample_rate: 采样率 int between [0,1000] 200
        """
        # 设置采样率
        self.spr = daq_sample_rate
        self.sample_rate_config(daq_sample_rate)

    def GetlockinChannels(self, board_num, data_num, CW_mode=False):
        """
        读取某一个锁相通道返回值（固定点数）
        设备识别码：DNVCS-API-Multichannel-0001
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 2
        :param data_num: 锁相板卡数据采集点数 int between [0,10000] 10
        :param CW_mode: ??? bool in [True,False] False
        """

        # print("IIR_DATA:",data)
        if (isinstance(board_num, list)):
            l = ["0"] * 8
            for bn in board_num:
                l[bn - 1] = '1'
            ch_num = int(''.join(l), 2)
            # ~ print("CH_NUM:",ch_num)
            data = self.iir_play(ch_num, data_num, CW_mode)
            return [[np.mean(data[board - 1][i][:12]) for i in range(len(data))] for board in board_num]
        else:
            data = self.iir_play(board_num, data_num, CW_mode)
            return [np.mean(data[board_num - 1][i][:12]) for i in range(len(data))]
        # return [np.mean(data[i]) for i in range(len(data))]

    def GetLockInChannels(self, board_num, poll_time=0.1):
        """
        读取锁相通道返回值（某一段时间内）
        设备识别码：DNVCS-API-Multichannel-0013
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 1
        :param poll_time: 锁相板卡数据采集时间 float between [0,100] 0.1
        """
        if (isinstance(board_num, list)):
            l = ["0"] * 8
            for bn in board_num:
                l[bn - 1] = '1'
            ch_num = int(''.join(l), 2)
            data = self.iir_play(ch_num, int(self.spr * poll_time))
            ch_data = [data[board - 1] for board in board_num]
        else:
            ch_data = self.iir_play(board_num, int(self.spr * poll_time))[board_num - 1]
        # return ch1xs, ch1ys, ch2xs, ch2ys,
        return ch_data

    def thread_IIR_play(self, board_num, data_num, background_flag=False, show_flag=True):
        """
        主控板卡版连续测磁模式线程
        设备识别码：DNVCS-API-Multichannel-0004
        API-Multichannel
        :param board_num: 锁相ID int in [2,3,5,6,7,255] 1
        :param data_num: 采集时间 int between [1,100000] 10
        :param background_flag: 是否挂在后台 bool in [Ture,False] False
        :param show_flag: 数据展示标识 bool in [Ture,False] True
        """
        self.board_num = board_num
        self.IIR_run_flag = True
        self.cursor = 0
        self.raw_data_byte = b''
        self.IIR_str = b''
        self.canvas_show_flag = show_flag
        self.show_data_queue = queue.Queue(maxsize=10000)  # 队列的大小
        self.IIR_start_time = time.time()

        ExpDataPath = '/ExpRealtimeDisplay/'
        dirs = [ExpDataPath]
        for di in dirs:
            if not os.path.exists(DATAPATH + di):
                os.mkdir(DATAPATH + di)

        thd_read = threading.Thread(target=self.thread_IIR_read, args=(data_num,), daemon=True)
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

    def thread_IIR_read(self, data_num):
        print('thread_read_pid start')
        self.SYS_config.DWritePort(b'\x00\x00')
        self.SYS_config.DWritePort(num_to_bytes(self.board_num, 1) + b'\x04')
        time.sleep(0.1)
        self.SYS_config.DWritePort(num_to_bytes(data_num, 4))  # 开启IIR连续采集(时长)
        while self.IIR_run_flag:
            time.sleep(0.08)  # 间隔0.08s采集一次
            data_str_tmp = self.SYS_config.DReadPort(self.spr/10 * 80 * 8)  # 设置每次获取的点数为采样率/10个点
            self.raw_data_queue.put(data_str_tmp)
            if(time.time() - self.IIR_start_time) > (data_num / self.spr):
                self.IIR_run_flag = False
        self.raw_data_queue.queue.clear()

    def thread_IIR_decode(self):
        self.iir_start_time = time.time()
        IIR_data = [[[] for _ in range(14)] for _ in range(8)]
        self.count = 0
        while self.IIR_run_flag:
            # self.IIR_str += self.raw_data_byte
            if (self.raw_data_queue.empty()):
                time.sleep(0.01)
            else:
                self.IIR_str += self.raw_data_queue.get()
                # print(self.IIR_str)
                while len(self.IIR_str) - self.cursor >= 80 * 8:
                    for bn in range(8):
                        for j in range(12):
                            data_buf = bytes_to_num(self.IIR_str[80 * bn + (j % 14) * 6:  80 * bn + (j % 14 + 1) * 6])
                            if data_buf > 2 ** 47 - 1:
                                data_buf = (data_buf - 2 ** 48.0) / 2 ** 48.0
                            else:
                                data_buf = data_buf / 2 ** 48.0
                            # data_buf = data_buf / 2**64.0

                            IIR_data[bn][j].append(data_buf * LIA_gain)

                        ch1_data = bytes_to_num(self.IIR_str[80 * bn + 72: 80 * bn + 76])
                        ch2_data = bytes_to_num(self.IIR_str[80 * bn + 76: 80 * bn + 80])
                        if(not (ch1_data==0 and ch2_data==0)):
                            # print("In error ch12")
                            self.cursor += 1
                            # continue
                        if ch1_data > 2 ** 15 - 1:
                            ch1_data_buf = (ch1_data - 2 ** 16.0) / 2 ** 16.0
                        else:
                            ch1_data_buf = ch1_data / 2 ** 16.0

                        if ch2_data > 2 ** 15 - 1:
                            ch2_data_buf = (ch2_data - 2 ** 16.0) / 2 ** 16.0
                        else:
                            ch2_data_buf = ch2_data / 2 ** 16.0
                        IIR_data[bn][12].append(ch1_data_buf)
                        IIR_data[bn][13].append(ch2_data_buf)
                    # print("IIR_data:",IIR_data)
                    self.cursor += 80 * 8
                    # if(ch1_data_buf == 0):
                    # print("IIR_data:",ch1_data_buf,ch2_data_buf)
                    # print("Byte_Data:",self.IIR_str[80: 80 + 72],self.IIR_str[80  + 72: 80  + 76],self.IIR_str[80  + 76: 80  + 80])
                    self.IIR_str = self.IIR_str[self.cursor:]
                    self.cursor = 0

                    self.count += 1
                    if(self.canvas_show_flag):
                        self.show_data_queue.put([self.count, [IIR_data[self.board_num-1][i][-1] for i in range(len(IIR_data))]])

                    if (len(IIR_data[self.board_num-1][0]) >= self.spr*600): # 每十分钟存储一次数据
                        ts = np.linspace(self.iir_start_time, time.time(), len(IIR_data[0]))
                        fn = DATAPATH + '/ExpRealtimeDisplay/' + gettimestr() + '_realtime.csv' # 连续测磁数据保存
                        write_to_csv(fn,[ts]+list(IIR_data[self.board_num-1]))
                        self.iir_start_time = time.time()
                        # del IIR_data[-1]
                        # ~ write_to_csv(fn,[ts]+list(IIR_data))
                        # # print(len(IIR_data[0]))
                        [[[] for _ in range(14)] for _ in range(8)]
        self.run_flag = False
        # 将未满600s的数据保存到文件中，避免数据丢失
        ts = np.linspace(self.iir_start_time, time.time(), len(IIR_data[self.board_num-1][0]))
        fn = DATAPATH + '/ExpRealtimeDisplay/' + gettimestr() + '_realtime.csv'
        write_to_csv(fn, [ts] + list(IIR_data[self.board_num-1]))

    def IIR_play_getpoints(self, ch_id=0, points=10):
        """
        主控板卡版连续测磁模式--多个数据点返回
        设备识别码：DNVCS-API-Multichannel-0005
        API-Multichannel
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
            time.sleep(points/(2*self.spr))
            return self.IIR_play_getpoints(ch_id,points)

    # def AcquireStartV3_MagPID(self, board_num, board_ch, data_num):
    #     data = self.SYS_config.AcquireStartV3_MagPID(board_num, board_ch, data_num)
    #     return data

    # def AcquireStopV3_PID(self, board_ch):
    #     self.SYS_config.AcquireStopV3_PID(board_ch)

class exp_AC_Gain_cal(object):
    def __init__(self, portx, board_num):
        self.LIA_config = API(portx)
        self.sampling_rate = 25 * 1e6
        self.wavesource_fre = 10000 # Hz
        self.ADC_extract_ratio = 16
        self.ADC_data_num = int(self.sampling_rate / (self.ADC_extract_ratio * self.wavesource_fre) * 10)
        self.board_num = board_num
        if self.board_num == 3:
            self.board_ch = 1
        elif self.board_num == 5:
            self.board_ch = 2
        elif self.board_num == 6:
            self.board_ch = 3
        elif self.board_num == 7:
            self.board_ch = 4
        elif self.board_num == 255:
            self.board_ch = 1

    def ADC_Gain_cal(self):
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        input()
        data = self.LIA_config.daq_play(self.board_num, self.ADC_data_num, self.ADC_extract_ratio)
        self.LIA_config.daq_plot()
        time1 = np.array(range(int(self.ADC_data_num))) / (self.sampling_rate / self.ADC_extract_ratio)
        path_ = 'data/' + str(time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())) + 'ADC_data.csv'
        csv_save(path_, {'time': time1, 'Board1_Ch1_data': data[6], 'Board1_Ch2_data': data[7],
                         'Board2_Ch1_data': data[4], 'Board2_Ch2_data': data[5],
                         'Board3_Ch1_data': data[2], 'Board3_Ch2_data': data[3],
                         'Board4_Ch1_data': data[0], 'Board4_Ch2_data': data[1]})
        if self.board_num == 3:
            print('Frequency = ', self.wavesource_fre, 'ch1_data_std = ', np.std(data[6]), 'ch2_data_std = ', np.std(data[7]))
        elif self.board_num == 5:
            print('Frequency = ', self.wavesource_fre, 'ch1_data_std = ', np.std(data[4]), 'ch2_data_std = ', np.std(data[5]))
        elif self.board_num == 6:
            print('Frequency = ', self.wavesource_fre, 'ch1_data_std = ', np.std(data[2]), 'ch2_data_std = ', np.std(data[3]))
        elif self.board_num == 7:
            print('Frequency = ', self.wavesource_fre, 'ch1_data_std = ', np.std(data[0]), 'ch2_data_std = ', np.std(data[1]))

    def LIA_Gain_cal(self):
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.1)
        self.LIA_config.De_fre_config(1, self.wavesource_fre)
        iir_sample_rate = 80  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)

        self.iir_data_num = 200
        a = time.time()
        board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num)
        b = time.time()
        print('the time span is ', b - a)
        # self.LIA_config.iir_plot()
        time1 = np.array(range(int(self.iir_data_num))) / (iir_sample_rate)
        path_ = 'data/' + str(time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())) + 'iir_data.csv'
        if self.board_num == 3:
            print('Frequency = ', self.wavesource_fre, 'ch1_data_mean = ', np.mean(board1_data[0]), 'ch2_data_mean = ', np.mean(board1_data[3]))
            csv_save(path_, {'time': time1, 'Board1_Ch1_Fre1_r': board1_data[0], 'Board1_Ch1_Fre1_y': board4_data[1], 'Board1_Ch1_Fre1_x': board4_data[2], 'Board1_Ch2_Fre1_r': board4_data[3], 'Board1_Ch2_Fre1_y': board4_data[4], 'Board1_Ch2_Fre1_x': board4_data[5]})
        elif self.board_num == 5:
            print('Frequency = ', self.wavesource_fre, 'ch1_data_mean = ', np.mean(board2_data[0]), 'ch2_data_mean = ', np.mean(board2_data[3]))
            csv_save(path_, {'time': time1, 'Board2_Ch1_Fre1_r': board2_data[0], 'Board2_Ch1_Fre1_y': board2_data[1], 'Board2_Ch1_Fre1_x': board2_data[2], 'Board2_Ch2_Fre1_r': board2_data[3], 'Board2_Ch2_Fre1_y': board2_data[4], 'Board2_Ch2_Fre1_x': board2_data[5]})
        elif self.board_num == 6:
            print('Frequency = ', self.wavesource_fre, 'ch1_data_mean = ', np.mean(board3_data[0]), 'ch2_data_mean = ', np.mean(board3_data[3]))
            csv_save(path_, {'time': time1, 'Board3_Ch1_Fre1_r': board3_data[0], 'Board3_Ch1_Fre1_y': board3_data[1], 'Board3_Ch1_Fre1_x': board3_data[2], 'Board3_Ch2_Fre1_r': board3_data[3], 'Board3_Ch2_Fre1_y': board3_data[4], 'Board3_Ch2_Fre1_x': board3_data[5]})
        elif self.board_num == 7:
            print('Frequency = ', self.wavesource_fre, 'ch1_data_mean = ', np.mean(board4_data[0]), 'ch2_data_mean = ', np.mean(board4_data[3]))
            csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})

    def MW_Control(self):
        self.LIA_config.MW1_SPI_ctrl(self.board_num)

    def CS_Control(self, Current):
        self.LIA_config.laser_SPI_ctrl(self.board_num, Current)

    def CW_Control(self, axes_ch, fig_show=False):
        # 进行CW谱线扫描，并优化相位
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: atte:13
        # self.CS_Control(0.)
        time.sleep(.1)
        # self.CS_Control(0.6)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.05)
        if axes_ch == 2 or axes_ch == 7:
            modu_Fre = ini_rd('CW', 'modu_fre_ch2')
        elif axes_ch == 3 or axes_ch == 6:
            modu_Fre = ini_rd('CW', 'modu_fre_ch3')
        elif axes_ch == 4 or axes_ch == 5:
            modu_Fre = ini_rd('CW', 'modu_fre_ch4')
        else:
            modu_Fre = ini_rd('CW', 'modu_fre_ch1')
        demodu_phase = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_demoduphase')
        self.LIA_config.Modu_fre_config(3, float(modu_Fre))
        self.LIA_config.De_fre_config(3, float(modu_Fre))
        De_phase = float(demodu_phase) / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(3, De_phase)

        axes_start = ini_rd('CW', 'axes' + str(axes_ch) + '_start')
        MW_fre = range(int(float(axes_start)), int(float(axes_start)) + 25000000, 100000)
        Flo_r = []
        Flo_y = []
        Flo_x = []
        Laser_r = []
        Laser_y = []
        Laser_x = []
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 8000  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        time.sleep(1)
        for i in MW_fre:
            print(i)
            self.LIA_config.MW2_SPI_ctrl(self.board_num, ch1_Fre=i, ch1_modu=18, ch1_atte=13)

            # input()
            self.iir_data_num = 8

            board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num, CW_mode=True)
            board_data = [board1_data, board2_data, board3_data, board4_data]
            # self.LIA_config.iir_plot()
            Flo_r_mean = np.mean(board_data[self.board_ch - 1][0])
            Flo_y_mean = np.mean(board_data[self.board_ch - 1][1])
            Flo_x_mean = np.mean(board_data[self.board_ch - 1][2])
            Laser_r_mean = np.mean(board_data[self.board_ch - 1][3])
            Laser_y_mean = np.mean(board_data[self.board_ch - 1][4])
            Laser_x_mean = np.mean(board_data[self.board_ch - 1][5])
            Flo_r.append(Flo_r_mean)
            Flo_y.append(Flo_y_mean)
            Flo_x.append(Flo_x_mean)
            Laser_r.append(Laser_r_mean)
            Laser_y.append(Laser_y_mean)
            Laser_x.append(Laser_x_mean)
        path_ = datapath + 'CW_data.csv'
             #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_, {'Frequency': MW_fre, 'Flo_r': Flo_r, 'Flo_y': Flo_y, 'Flo_x': Flo_x,
                         'Laser_r': Laser_r, 'Laser_y': Laser_y, 'Laser_x': Laser_x})
        # self.CS_Control(0.0)
        plt.plot(MW_fre, Flo_r, label='Flo_r')
        plt.plot(MW_fre, Flo_y, label='Flo_y')
        plt.plot(MW_fre, Flo_x, label='Flo_x')
        # plt.plot(MW_fre, Laser_r, label='Laser_r')
        # plt.plot(MW_fre, Laser_y, label='Laser_y')
        # plt.plot(MW_fre, Laser_x, label='Laser_x')
        path_1 = datapath + 'CW_data.png'
        plt.xlabel('MW_fre/Hz')
        plt.ylabel('Amp/1')
        plt.legend()
        plt.savefig(path_1)

        Flo_y_min = sorted(zip(Flo_y, MW_fre))[0][1]
        Flo_y_max = sorted(zip(Flo_y, MW_fre))[-1][1]
        ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_center', str((Flo_y_min + Flo_y_max)/2))
        # 计算谱线最大斜率
        max_index = MW_fre.index(Flo_y_min)
        min_index = MW_fre.index(Flo_y_max)
        # print('min_index = ', min_index)
        # print('max_index = ', max_index)
        linear_x = MW_fre[int((4*min_index + 2*max_index)/6): int((4*max_index + 2*min_index)/6)]
        linear_y = Flo_y[int((4*min_index + 2*max_index)/6): int((4*max_index + 2*min_index)/6)]
        # print('linear_x = ', linear_x)
        # print('linear_y = ', linear_y)
        try:
            z1 = np.polyfit(linear_x, linear_y, 1)  #一次多项式拟合，相当于线性拟合
            ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_slope', str(z1[0]))
        except:
            pass

        if fig_show:
            plt.show()
        plt.clf()

    def CW_8_TEST(self, CS_Value):
        self.CS_Control(CS_Value)
        time.sleep(20)
        for i in range(8):
            self.CW_Control(i + 1)
        self.CS_Control(0.0)

    # def CW_4_test(self, axes_chs=[2,3,5,8],step=100000, mod= [18, 18, 18, 18], atte=[13, 13, 13, 13], fig_show=False):
    #     # 进行CW谱线扫描，并优化相位
    #     # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
    #     # ch4: De_phase 22
    #     # ch4: atte:13
    #     # self.CS_Control(0.)
    #     time.sleep(.1)
    #     # self.CS_Control(0.6)
    #     ch_num= len(axes_chs)
    #     self.LIA_config.ALL_stop(self.board_num)
    #     self.LIA_config.tc(0.05)
    #     MW_Fre=[[] for i in range(ch_num)]
    #     ii = 1
    #     for axes_ch in axes_chs
    #         if axes_ch == 2 or axes_ch == 7:
    #             modu_Fre=ini_rd('CW', 'modu_fre_ch2')
    #         elif axes_ch == 3 or axes_ch == 6:
    #             modu_Fre=ini_rd('CW', 'modu_fre_ch3')
    #         elif axes_ch == 4 or axes_ch == 5:
    #             modu_Fre=ini_rd('CW', 'modu_fre_ch4')
    #         else:
    #             modu_Fre.append(ini_rd('CW', 'modu_fre_ch1'))
    #         demodu_phase = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_demoduphase')
    #         self.LIA_config.Modu_fre_config(ii, float(modu_Fre))
    #         self.LIA_config.De_fre_config(ii, float(modu_Fre))
    #         De_phase = float(demodu_phase) / (np.pi) * 180 # °
    #         self.LIA_config.De_phase_config(ii, De_phase)
    #
    #         axes_start = ini_rd('CW', 'axes' + str(axes_ch) + '_start')
    #         mf_list = range(int(float(axes_start)), int(float(axes_start)) + 25000000, step)
    #         num_mw = len(mf_list)
    #         MW_fre[ii]=mf_list
    #         ii=ii+1
    #     Flo_r = [[] for i in range(ch_num)]
    #     Flo_y = [[] for i in range(ch_num)]
    #     Flo_x = [[] for i in range(ch_num)]
    #     Laser_r = [[] for i in range(ch_num)]
    #     Laser_y = [[] for i in range(ch_num)]
    #     Laser_x = [[] for i in range(ch_num)]
    #     ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
    #     os.makedirs('data/' + ospath)
    #     datapath = 'data/' + ospath + '/'
    #     # 1. MW Channel / Mod. SQW Output (?)
    #     # 2. Board Num (y)
    #     # 3. CW Scanning Step (set to 1 MHz)
    #
    #     # input()
    #     iir_sample_rate = 8000  # Hz
    #     self.LIA_config.sample_rate_config(iir_sample_rate)
    #     self.LIA_config.ALL_stop(self.board_num)
    #     self.LIA_config.DAC_play(self.board_num)
    #     self.LIA_config.ALL_start(self.board_num)
    #     time.sleep(1)
    #     for ii in range(num_mw):
    #         print(MW_Fre[][ii])
    #         self.LIA_config.MW2_SPI_ctrl(self.board_num, ch1_Fre=MW_Fre[0][ii], ch1_modu=mod[0], ch1_atte=atte[0])
    #         if ch_num>=2
    #             self.LIA_config.MW2_SPI_ctrl(self.board_num, ch2_Fre=MW_Fre[1][ii], ch2_modu=mod[1], ch2_atte=atte[1])
    #         if ch_num>=3
    #             self.LIA_config.MW2_SPI_ctrl(self.board_num, ch3_Fre=MW_Fre[2][ii], ch3_modu=mod[2], ch3_atte=atte[2])
    #         if ch_num>=4
    #             self.LIA_config.MW2_SPI_ctrl(self.board_num, ch4_Fre=MW_Fre[3][ii], ch4_modu=mod[3], ch4_atte=atte[3])
    #         # input()
    #         self.iir_data_num = 8
    #
    #         board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num, CW_mode=True)
    #         board_data = [board1_data, board2_data, board3_data, board4_data]
    #         # self.LIA_config.iir_plot()
    #         for jj in range(ch_num):
    #             Flo_r_mean = np.mean(board_data[self.board_ch - 1][0+6*jj])
    #             Flo_y_mean = np.mean(board_data[self.board_ch - 1][1+6*jj])
    #             Flo_x_mean = np.mean(board_data[self.board_ch - 1][2+6*jj])
    #             Laser_r_mean = np.mean(board_data[self.board_ch - 1][3+6*jj])
    #             Laser_y_mean = np.mean(board_data[self.board_ch - 1][4+6*jj])
    #             Laser_x_mean = np.mean(board_data[self.board_ch - 1][5+6*jj])
    #             Flo_r[jj].append(Flo_r_mean)
    #             Flo_y[jj].append(Flo_y_mean)
    #             Flo_x[jj].append(Flo_x_mean)
    #             Laser_r[jj].append(Laser_r_mean)
    #             Laser_y[jj].append(Laser_y_mean)
    #             Laser_x[jj].append(Laser_x_mean)
    #             path_ = datapath + 'CW_ch'+str(jj+1)+'_data.csv'
    #             #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
    #             csv_save(path_, {'Frequency': MW_fre[jj], 'Flo_r': Flo_r[jj], 'Flo_y': Flo_y[jj], 'Flo_x': Flo_x[jj],
    #                              'Laser_r': Laser_r[jj], 'Laser_y': Laser_y[jj], 'Laser_x': Laser_x[jj]})
    #             # self.CS_Control(0.0)
    #             plt.plot(MW_fre[jj], Flo_r, label='Flo_r')
    #             plt.plot(MW_fre[jj], Flo_y, label='Flo_y')
    #             plt.plot(MW_fre[jj], Flo_x, label='Flo_x')
    #             # plt.plot(MW_fre, Laser_r, label='Laser_r')
    #             # plt.plot(MW_fre, Laser_y, label='Laser_y')
    #             # plt.plot(MW_fre, Laser_x, label='Laser_x')
    #             path_1 = datapath + 'CW_ch'+str(jj+1)+'_data.png'
    #             plt.xlabel('MW_fre/Hz')
    #             plt.ylabel('Amp/1')
    #             plt.legend()
    #             plt.savefig(path_1)
    #
    #     Flo_y_min = sorted(zip(Flo_y, MW_fre))[0][1]
    #     Flo_y_max = sorted(zip(Flo_y, MW_fre))[-1][1]
    #     ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_center', str((Flo_y_min + Flo_y_max)/2))
    #     # 计算谱线最大斜率
    #     max_index = MW_fre.index(Flo_y_min)
    #     min_index = MW_fre.index(Flo_y_max)
    #     # print('min_index = ', min_index)
    #     # print('max_index = ', max_index)
    #     linear_x = MW_fre[int((4*min_index + 2*max_index)/6): int((4*max_index + 2*min_index)/6)]
    #     linear_y = Flo_y[int((4*min_index + 2*max_index)/6): int((4*max_index + 2*min_index)/6)]
    #     # print('linear_x = ', linear_x)
    #     # print('linear_y = ', linear_y)
    #     z1 = np.polyfit(linear_x, linear_y, 1)  #一次多项式拟合，相当于线性拟合
    #     ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_slope', str(z1[0]))
    #     if fig_show:
    #         plt.show()
    #     plt.clf()

    def De_phase_Control(self, axes_ch):
        # 进行CW谱线扫描，并优化相位
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: atte:13
        # self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.8)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.02)
        if axes_ch == 2 or axes_ch == 7:
            modu_Fre = ini_rd('CW', 'modu_fre_ch2')
        elif axes_ch == 3 or axes_ch == 6:
            modu_Fre = ini_rd('CW', 'modu_fre_ch3')
        elif axes_ch == 4 or axes_ch == 5:
            modu_Fre = ini_rd('CW', 'modu_fre_ch4')
        else:
            modu_Fre = ini_rd('CW', 'modu_fre_ch1')
        modu_Fre = float(modu_Fre)
        self.LIA_config.Modu_fre_config(1, modu_Fre)
        self.LIA_config.De_fre_config(1, modu_Fre)
        De_phase = 0
        self.LIA_config.De_phase_config(1, De_phase)
        axes_start = ini_rd('CW', 'axes' + str(axes_ch) + '_start')
        MW_fre = range(int(float(axes_start)), int(float(axes_start)) + 25000000, 50000)
        Flo_r = []
        Flo_y = []
        Flo_x = []
        Laser_r = []
        Laser_y = []
        Laser_x = []
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 8000  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)

        for i in MW_fre:
            print(i)
            self.LIA_config.MW2_SPI_ctrl(self.board_num, ch1_Fre=i, ch1_modu=18, ch1_atte=13)
            time.sleep(.001)

            # input()
            self.iir_data_num = 5

            board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num, CW_mode=True)
            board_data = [board1_data, board2_data, board3_data, board4_data]
            # self.LIA_config.iir_plot()
            Flo_r_mean = np.mean(board_data[self.board_ch - 1][0])
            Flo_y_mean = np.mean(board_data[self.board_ch - 1][1])
            Flo_x_mean = np.mean(board_data[self.board_ch - 1][2])
            Laser_r_mean = np.mean(board_data[self.board_ch - 1][3])
            Laser_y_mean = np.mean(board_data[self.board_ch - 1][4])
            Laser_x_mean = np.mean(board_data[self.board_ch - 1][5])
            Flo_r.append(Flo_r_mean)
            Flo_y.append(Flo_y_mean)
            Flo_x.append(Flo_x_mean)
            Laser_r.append(Laser_r_mean)
            Laser_y.append(Laser_y_mean)
            Laser_x.append(Laser_x_mean)
        path_ = datapath + 'CW_data.csv'
        #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_, {'Frequency': MW_fre, 'Flo_r': Flo_r, 'Flo_y': Flo_y, 'Flo_x': Flo_x,
                         'Laser_r': Laser_r, 'Laser_y': Laser_y, 'Laser_x': Laser_x})
        # self.CS_Control(0.0)
        plt.plot(MW_fre, Flo_r, label='Flo_r')
        plt.plot(MW_fre, Flo_y, label='Flo_y')
        plt.plot(MW_fre, Flo_x, label='Flo_x')
        # plt.plot(MW_fre, Laser_r, label='Laser_r')
        # plt.plot(MW_fre, Laser_y, label='Laser_y')
        # plt.plot(MW_fre, Laser_x, label='Laser_x')
        path_1 = datapath + 'CW_data.png'
        plt.xlabel('MW_fre/Hz')
        plt.ylabel('Amp/1')
        plt.legend()
        plt.savefig(path_1)
        plt.show()
        plt.clf()
        Flo_y_max = sorted(zip(Flo_y, Flo_x))[-1][0]
        Flo_x_max = sorted(zip(Flo_y, Flo_x))[-1][1]
        modu_phase = np.arctan(Flo_x_max / Flo_y_max)
        ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_demoduphase', str(modu_phase))
        self.CS_Control(0.)


    def Modu_depth_Control(self):
        # 调制深度优化
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.6)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.02)
        Modu_fre = 2330.133283623823
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(1, De_phase)
        # self.LIA_config.Modu_fre_config(2, Modu_fre)
        # self.LIA_config.De_fre_config(2, Modu_fre)
        # self.LIA_config.Modu_fre_config(3, Modu_fre)
        # self.LIA_config.De_fre_config(3, Modu_fre)
        # self.LIA_config.Modu_fre_config(4, Modu_fre)
        # self.LIA_config.De_fre_config(4, Modu_fre)
        MW_fre = range(2745000000, 2765000000, 200000)

        SNR = []
        modu_depth = []
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 200  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)

        for j in range(30):
            Flo_r = []
            Flo_y = []
            Flo_x = []
            Laser_r = []
            Laser_y = []
            Laser_x = []
            ch1_modu_depth = j + 1
            modu_depth.append(ch1_modu_depth)
            board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, 200)
            board_data = [board1_data, board2_data, board3_data, board4_data]
            noise_std = np.std(board_data[self.board_ch - 1][1])

            for i in MW_fre:
                print(i)
                self.LIA_config.MW2_SPI_ctrl(self.board_num, ch1_Fre=i, ch1_modu=ch1_modu_depth)

                time.sleep(.002)

                # input()
                self.iir_data_num = 20

                board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num)
                board_data = [board1_data, board2_data, board3_data, board4_data]
                # self.LIA_config.iir_plot()
                Flo_r_mean = np.mean(board_data[self.board_ch - 1][0])
                Flo_y_mean = np.mean(board_data[self.board_ch - 1][1])
                Flo_x_mean = np.mean(board_data[self.board_ch - 1][2])
                Laser_r_mean = np.mean(board_data[self.board_ch - 1][3])
                Laser_y_mean = np.mean(board_data[self.board_ch - 1][4])
                Laser_x_mean = np.mean(board_data[self.board_ch - 1][5])
                Flo_r.append(Flo_r_mean)
                Flo_y.append(Flo_y_mean)
                Flo_x.append(Flo_x_mean)
                Laser_r.append(Laser_r_mean)
                Laser_y.append(Laser_y_mean)
                Laser_x.append(Laser_x_mean)

            signal = np.max(Flo_y)
            path_ = datapath + '/MW_MODU' + str(ch1_modu_depth) + 'CW_data.csv'
            #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
            csv_save(path_, {'Frequency': MW_fre, 'Flo_r': Flo_r, 'Flo_y': Flo_y, 'Flo_x': Flo_x,
                             'Laser_r': Laser_r, 'Laser_y': Laser_y, 'Laser_x': Laser_x})
            plt.plot(MW_fre, Flo_r, label='Flo_r')
            plt.plot(MW_fre, Flo_y, label='Flo_y')
            plt.plot(MW_fre, Flo_x, label='Flo_x')
            # plt.plot(MW_fre, Laser_r, label='Laser_r')
            # plt.plot(MW_fre, Laser_y, label='Laser_y')
            # plt.plot(MW_fre, Laser_x, label='Laser_x')
            path_1 = datapath + '/CW_data'+ 'modu_depth' + str(ch1_modu_depth) +'.png'
            plt.xlabel('MW_fre/Hz')
            plt.ylabel('Amp/1')
            plt.legend()
            plt.savefig(path_1)
            plt.clf()
            # plt.show()
            SNR.append(signal / noise_std)
        self.CS_Control(0.0)
        path_2 = datapath + '/modu_depth.csv'
        #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_2, {'ch1_modu_depth': modu_depth, 'SNR': SNR})

    def MW_atte_Control(self):
        # 微波功率优化
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.6)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.02)
        Modu_fre = 2330.133283623823
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(1, De_phase)
        # self.LIA_config.Modu_fre_config(2, Modu_fre)
        # self.LIA_config.De_fre_config(2, Modu_fre)
        # self.LIA_config.Modu_fre_config(3, Modu_fre)
        # self.LIA_config.De_fre_config(3, Modu_fre)
        # self.LIA_config.Modu_fre_config(4, Modu_fre)
        # self.LIA_config.De_fre_config(4, Modu_fre)
        MW_fre = range(2755000000, 2775000000, 200000)

        SNR = []
        attu = []
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 200  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)

        for j in range(30):
            Flo_r = []
            Flo_y = []
            Flo_x = []
            Laser_r = []
            Laser_y = []
            Laser_x = []
            ch1_attu = j
            attu.append(ch1_attu)
            board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, 200)
            board_data = [board1_data, board2_data, board3_data, board4_data]
            noise_std = np.std(board_data[self.board_ch - 1][1])

            for i in MW_fre:
                print(i)
                self.LIA_config.MW2_SPI_ctrl(self.board_num, ch1_Fre=i, ch1_modu=18, ch1_atte=ch1_attu)

                time.sleep(.002)

                # input()
                self.iir_data_num = 20

                board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num)
                board_data = [board1_data, board2_data, board3_data, board4_data]
                # self.LIA_config.iir_plot()
                Flo_r_mean = np.mean(board_data[self.board_ch - 1][0])
                Flo_y_mean = np.mean(board_data[self.board_ch - 1][1])
                Flo_x_mean = np.mean(board_data[self.board_ch - 1][2])
                Laser_r_mean = np.mean(board_data[self.board_ch - 1][3])
                Laser_y_mean = np.mean(board_data[self.board_ch - 1][4])
                Laser_x_mean = np.mean(board_data[self.board_ch - 1][5])
                Flo_r.append(Flo_r_mean)
                Flo_y.append(Flo_y_mean)
                Flo_x.append(Flo_x_mean)
                Laser_r.append(Laser_r_mean)
                Laser_y.append(Laser_y_mean)
                Laser_x.append(Laser_x_mean)

            signal = np.max(Flo_y)
            path_ = datapath + '/MW_MODU' + str(ch1_attu) + 'CW_data.csv'
            #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
            csv_save(path_, {'Frequency': MW_fre, 'Flo_r': Flo_r, 'Flo_y': Flo_y, 'Flo_x': Flo_x,
                             'Laser_r': Laser_r, 'Laser_y': Laser_y, 'Laser_x': Laser_x})
            plt.plot(MW_fre, Flo_r, label='Flo_r')
            plt.plot(MW_fre, Flo_y, label='Flo_y')
            plt.plot(MW_fre, Flo_x, label='Flo_x')
            # plt.plot(MW_fre, Laser_r, label='Laser_r')
            # plt.plot(MW_fre, Laser_y, label='Laser_y')
            # plt.plot(MW_fre, Laser_x, label='Laser_x')
            path_1 = datapath + '/CW_data'+ 'modu_depth' + str(ch1_attu) +'.png'
            plt.xlabel('MW_fre/Hz')
            plt.ylabel('Amp/1')
            plt.legend()
            plt.savefig(path_1)
            plt.clf()
            # plt.show()
            SNR.append(signal / noise_std)
        self.CS_Control(0.0)
        path_2 = datapath + '/modu_depth.csv'
        #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_2, {'ch1_attu': attu, 'SNR': SNR})

    def Laser_PID_Control(self):
        # 激光功率PID测试
        # 将微波定在非共振点处，测量激光PID开启前后的荧光DC值的STD值大小。
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.6)
        time.sleep(1)
        self.LIA_config.tc(0.1)
        Modu_fre = 2330.133283623823
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(1, De_phase)
        MW_fre = 2700000000

        SNR = []
        attu = []
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 50  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        # 先判定荧光电流大小
        # board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, 100)
        # board_data = [board1_data, board2_data, board3_data, board4_data]
        # Flo_mean = np.mean(board_data[self.board_ch - 1][24])
        # Laser_mean = np.mean(board_data[self.board_ch - 1][25])
        # print('Flo_mean = ', Flo_mean, 'Laser_mean', Laser_mean)
        # plt.plot(range(len(board_data[self.board_ch - 1][24])), board_data[self.board_ch - 1][24])
        # plt.plot(range(len(board_data[self.board_ch - 1][24])), board_data[self.board_ch - 1][25])
        # plt.show()
        PID_ch_num = 5  # 激光PID通道为5
        set_point = 0.16  # 需先测量得到荧光信号的DC值后确定
        output_offset = 0.57  # 将激光稳定在0.6 A
        # 探头3的PID参数：
        # kp = -0.015
        # ki = -0.009
        #
        # kd = -0.0000
        # kt = 1.0000000
        # 探头4的PID参数：
        kp = -0.015
        ki = -0.009

        kd = -0.0000
        kt = 1.0000000
        # kp = -0.000
        # ki = -0.000
        #
        # kd = -0.0000
        # kt = 1.0000000
        Cal_ex = 0
        RD_ex = 0
        PID_LIA_CH = 0
        PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
        self.LIA_config.pid_config(self.board_num, PID_ch_num, PID_coe)
        print('PID coe download')
        self.LIA_config.pid_enable(self.board_num, PID_ch_num)
        print('PID enable')
        board_data = self.LIA_config.AcquireStartV3_PID(self.board_num, self.board_ch, 400)  #self.board_num:3 5 6 7 self.board_ch:1 2 3 4
        print(board_data)
        # print('PID play')
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.0)
        print('data_std:', np.std(board_data[3][0][200:]))
        # path_ = datapath + 'Laser_PID_data.csv'
        # csv_save(path_, {'error':board_data[3][0], 'feedback': board_data[3][1]})
        self.LIA_config.Laser_pid_plot()

    def Mag_PID_Test1(self):
        # 测磁PID测试，将PID系数均设置为0，扫描CW谱线
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        # 开启测磁PID，首先开启激光PID。
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.6)
        time.sleep(1)
        # 分别设置tc，每个通道的调制解调
        # tc = 0.1
        self.LIA_config.tc(0.01)
        # 1通道调制解调
        Modu_fre = 2330.133283623823
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(1, De_phase)
        # 2通道调制解调
        Modu_fre = 1220.133283623823
        self.LIA_config.Modu_fre_config(2, Modu_fre)
        self.LIA_config.De_fre_config(2, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(2, De_phase)
        # 3通道调制解调
        Modu_fre = 3333.133283623823
        self.LIA_config.Modu_fre_config(3, Modu_fre)
        self.LIA_config.De_fre_config(3, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(3, De_phase)
        # 4通道调制解调
        Modu_fre = 5432.133283623823
        self.LIA_config.Modu_fre_config(4, Modu_fre)
        self.LIA_config.De_fre_config(4, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(4, De_phase)

        # 文件保存目录
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        # 写入参数
        iir_sample_rate = 50  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        # 开启激光PID
        PID_ch_num = 5  # 激光PID通道为5
        set_point = 0.16  # 需先测量得到荧光信号的DC值后确定
        output_offset = 0.57  # 将激光稳定在0.6 A
        kp = -0.015
        ki = -0.009

        kd = -0.0000
        kt = 1.0000000
        Cal_ex = 0
        RD_ex = 0
        PID_LIA_CH = 0
        PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
        self.LIA_config.pid_config(self.board_num, PID_ch_num, PID_coe)
        print('PID coe download')
        self.LIA_config.pid_enable(self.board_num, PID_ch_num)
        print('Laser PID enable')
        # 开启测磁PID
        # 测试：用PID模式扫描CW谱线
        MW_fre = range(2750000000, 2770000000, 100000)
        self.LIA_config.MW2_SPI_ctrl(self.board_num, ch1_Fre=2650000000, ch1_modu=18, ch1_atte=13)
        iir_data_r = []
        iir_data_x = []
        iir_data_y = []
        error_buf = []
        feedback_buf = []
        for i in MW_fre:
            # PID_ch_num = 1  # 磁测量PID通道为1
            set_point = 0  # 将输出稳定在过零点
            output_offset = (i-2600000000) * 524288
            other_ch_offset = (3000000000-2600000000) * 524288
            kp = -0.000
            ki = -0.000

            kd = -0.0000
            kt = 1.0000000
            Cal_ex = 156250
            RD_ex = 1
            PID_LIA_CH = 1

            PID_coe = [set_point, output_offset, kp, ki, kd, kt, RD_ex, Cal_ex, PID_LIA_CH]
            PID_coe1 = [set_point, other_ch_offset, kp, ki, kd, kt, RD_ex, Cal_ex, PID_LIA_CH]
            self.LIA_config.pid_config(self.board_num, 1, PID_coe)
            self.LIA_config.pid_config(self.board_num, 2, PID_coe1)
            self.LIA_config.pid_config(self.board_num, 3, PID_coe1)
            self.LIA_config.pid_config(self.board_num, 4, PID_coe1)
            self.LIA_config.pid_enable(self.board_num, 1)
            self.LIA_config.pid_enable(self.board_num, 2)
            self.LIA_config.pid_enable(self.board_num, 3)
            self.LIA_config.pid_enable(self.board_num, 4)
            print('PID coe download')
            board_data = self.LIA_config.AcquireStartV3_MagPID(self.board_num, self.board_ch, 30)  #self.board_num:3 5 6 7 self.board_ch:1 2 3 4
            print(board_data)
            iir_data_r.append(np.mean(board_data[3][0]))
            iir_data_x.append(np.mean(board_data[3][1]))
            iir_data_y.append(np.mean(board_data[3][2]))
            error_buf.append(np.mean(board_data[3][3]))
            feedback_buf.append(np.mean(board_data[3][3]))
        path_ = datapath + 'PID_CW_data.csv'
        #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_, {'Frequency': MW_fre, 'iir_data_r': iir_data_r, 'iir_data_x': iir_data_x, 'iir_data_y': iir_data_y,
                         'error_buf': error_buf, 'feedback_buf': feedback_buf})
        plt.plot(MW_fre, iir_data_r, label='Flo_r')
        plt.plot(MW_fre, iir_data_x, label='Flo_y')
        plt.plot(MW_fre, iir_data_y, label='Flo_x')
        # plt.plot(MW_fre, Laser_r, label='Laser_r')
        # plt.plot(MW_fre, Laser_y, label='Laser_y')
        # plt.plot(MW_fre, Laser_x, label='Laser_x')
        path_1 = datapath + 'CW_data.png'
        plt.xlabel('MW_fre/Hz')
        plt.ylabel('Amp/1')
        plt.legend()
        plt.savefig(path_1)
        plt.show()

        self.LIA_config.pid_disable(self.board_num, 1)
        self.LIA_config.pid_disable(self.board_num, 2)
        self.LIA_config.pid_disable(self.board_num, 3)
        self.LIA_config.pid_disable(self.board_num, 4)

        # print('PID play')
        self.LIA_config.pid_disable(self.board_num, 5)
        self.CS_Control(0.0)
        self.LIA_config.pid_disable(self.board_num, 1)
        self.LIA_config.ALL_stop(self.board_num)

    def Mag_PID_Test(self):
        # 激光功率PID测试
        # 将微波定在非共振点处，测量激光PID开启前后的荧光DC值的STD值大小。
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        # 开启测磁PID，首先开启激光PID。
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.6)
        time.sleep(1)
        # 分别设置tc，每个通道的调制解调
        # tc = 0.1
        self.LIA_config.tc(0.01)
        # 1通道调制解调
        Modu_fre = 2330.133283623823
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(1, De_phase)
        # 2通道调制解调
        Modu_fre = 1220.133283623823
        self.LIA_config.Modu_fre_config(2, Modu_fre)
        self.LIA_config.De_fre_config(2, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(2, De_phase)
        # 3通道调制解调
        Modu_fre = 3333.133283623823
        self.LIA_config.Modu_fre_config(3, Modu_fre)
        self.LIA_config.De_fre_config(3, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(3, De_phase)
        # 4通道调制解调
        Modu_fre = 5432.133283623823
        self.LIA_config.Modu_fre_config(4, Modu_fre)
        self.LIA_config.De_fre_config(4, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(4, De_phase)

        # 文件保存目录
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        # 写入参数
        iir_sample_rate = 50  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        # 开启激光PID
        PID_ch_num = 5  # 激光PID通道为5
        set_point = 0.16  # 需先测量得到荧光信号的DC值后确定
        output_offset = 0.57  # 将激光稳定在0.6 A
        kp = -0.015
        ki = -0.009

        kd = -0.0000
        kt = 1.0000000
        Cal_ex = 0
        RD_ex = 0
        PID_LIA_CH = 0
        PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
        self.LIA_config.pid_config(self.board_num, PID_ch_num, PID_coe)
        print('PID coe download')
        self.LIA_config.pid_enable(self.board_num, PID_ch_num)
        print('Laser PID enable')
        # 开启测磁PID
        # 测试：用PID模式扫描CW谱线
        MW_fre = range(2755000000, 2775000000, 200000)
        self.LIA_config.MW2_SPI_ctrl(self.board_num, ch1_Fre=2650000000, ch1_modu=18, ch1_atte=13)
        iir_data_r = []
        iir_data_x = []
        iir_data_y = []
        error_buf = []
        feedback_buf = []

        # PID_ch_num = 1  # 磁测量PID通道为1
        set_point = 0  # 将输出稳定在过零点
        output_offset = 2755000000 * 1048576  # 将激光稳定在0.6 A
        kp = -0.000
        ki = -0.000

        kd = -0.0000
        kt = 1.0000000
        Cal_ex = 156250
        RD_ex = 1
        PID_LIA_CH = 1
        PID_coe = [set_point, output_offset, kp, ki, kd, kt, RD_ex, Cal_ex, PID_LIA_CH]
        self.LIA_config.pid_config(self.board_num, 1, PID_coe)
        self.LIA_config.pid_config(self.board_num, 2, PID_coe)
        self.LIA_config.pid_config(self.board_num, 3, PID_coe)
        self.LIA_config.pid_config(self.board_num, 4, PID_coe)
        self.LIA_config.pid_enable(self.board_num, 1)
        self.LIA_config.pid_enable(self.board_num, 2)
        self.LIA_config.pid_enable(self.board_num, 3)
        self.LIA_config.pid_enable(self.board_num, 4)
        print('PID coe download')
        board_data = self.LIA_config.AcquireStartV3_MagPID(self.board_num, self.board_ch, 300)  #self.board_num:3 5 6 7 self.board_ch:1 2 3 4
        print(board_data)
        iir_data_r = board_data[3][0]
        iir_data_x = board_data[3][1]
        iir_data_y = board_data[3][2]
        error_buf = board_data[3][3]
        feedback_buf = board_data[3][4]
        plt.plot(range(len(iir_data_y)), iir_data_r)
        plt.plot(range(len(iir_data_y)), iir_data_x)
        plt.plot(range(len(iir_data_y)), iir_data_y)
        plt.plot(range(len(iir_data_y)), error_buf)
        plt.show()
        self.LIA_config.pid_disable(self.board_num, 1)
        self.LIA_config.pid_disable(self.board_num, 2)
        self.LIA_config.pid_disable(self.board_num, 3)
        self.LIA_config.pid_disable(self.board_num, 4)

            # print('PID play')
        self.LIA_config.pid_disable(self.board_num, 5)
        self.CS_Control(0.0)
        self.LIA_config.pid_disable(self.board_num, 1)
        self.LIA_config.ALL_stop(self.board_num)

    def Mag_PID_Control(self, axes_list=[8,5,3,2], sample_point=500, debug_ch=1):
        # 测磁PID测试，将PID系数均设置为0，扫描CW谱线
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        # 开启测磁PID，首先开启激光PID。
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        time.sleep(1)
        # 分别设置tc，每个通道的调制解调
        # tc = 0.1
        self.LIA_config.tc(0.2)
        ch_num = 1
        for axes_ch in axes_list:
            if axes_ch == 2 or axes_ch == 7:
                modu_Fre = ini_rd('CW', 'modu_fre_ch2')
            elif axes_ch == 3 or axes_ch == 6:
                modu_Fre = ini_rd('CW', 'modu_fre_ch3')
            elif axes_ch == 4 or axes_ch == 5:
                modu_Fre = ini_rd('CW', 'modu_fre_ch4')
            else:
                modu_Fre = ini_rd('CW', 'modu_fre_ch1')
            demodu_phase = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_demoduphase')
            print('board_ch', self.board_ch, 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_demoduphase')
            self.LIA_config.Modu_fre_config(ch_num, float(modu_Fre))
            self.LIA_config.De_fre_config(ch_num, float(modu_Fre))
            De_phase = float(demodu_phase) / (np.pi) * 180 # °
            self.LIA_config.De_phase_config(ch_num * 2 - 1, De_phase)
            ch_num += 1

        # 文件保存目录
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        # 写入参数
        iir_sample_rate = 50  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        attu = 13
        modu = 18
        # modu = 0
        MW_para = [[2979000000.0, modu, attu], [2909000000.0, modu, attu], [2809000000.0, modu, attu], [2784000000.0, modu, attu]]
        self.LIA_config.MW1_SPI_ctrl(self.board_num, MW_para)
        time.sleep(5)

        center = []
        for i in range(4):
            # PID_ch_num = 1  # 磁测量PID通道为1
            set_point = 0  # 将输出稳定在过零点
            axes_center = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_center')
            center.append(float(axes_center))
            output_offset = (center[-1] - 50000 - 2600000000) * 524288
            kp = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_kp'))
            ki = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_ki'))
            kd = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_kd'))
            kt = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_kt'))
            Cal_ex = 312499
            RD_ex = 0
            PID_LIA_CH = 1

            PID_coe = [set_point, output_offset, kp, ki, kd, kt, RD_ex, Cal_ex, PID_LIA_CH]
            print('PID_coe : ', PID_coe)
            self.LIA_config.pid_config(self.board_num, i+1, PID_coe)
        self.LIA_config.pid_enable(self.board_num, 1)
        self.LIA_config.pid_enable(self.board_num, 2)
        self.LIA_config.pid_enable(self.board_num, 3)
        self.LIA_config.pid_enable(self.board_num, 4)
        # time.sleep(1)
        print('PID coe download')
        board_data = self.LIA_config.AcquireStartV3_MagPID(self.board_num, self.board_ch, sample_point)  #self.board_num:3 5 6 7 self.board_ch:1 2 3 4
        # print(board_data)

        ch1_iir_data_r = board_data[self.board_ch - 1][0]
        ch1_iir_data_y = board_data[self.board_ch - 1][1]
        ch1_iir_data_x = board_data[self.board_ch - 1][2]
        ch1_error_buf = board_data[self.board_ch - 1][3]
        ch1_feedback_buf = board_data[self.board_ch - 1][4]
        print('ch1_feedback = ', board_data[self.board_ch - 1][4])

        ch2_iir_data_r = board_data[self.board_ch - 1][5]
        ch2_iir_data_y = board_data[self.board_ch - 1][6]
        ch2_iir_data_x = board_data[self.board_ch - 1][7]
        ch2_error_buf = board_data[self.board_ch - 1][8]
        ch2_feedback_buf = board_data[self.board_ch - 1][9]


        ch3_iir_data_r = board_data[self.board_ch - 1][10]
        ch3_iir_data_y = board_data[self.board_ch - 1][11]
        ch3_iir_data_x = board_data[self.board_ch - 1][12]
        ch3_error_buf = board_data[self.board_ch - 1][13]
        ch3_feedback_buf = board_data[self.board_ch - 1][14]

        ch4_iir_data_r = board_data[self.board_ch - 1][15]
        ch4_iir_data_y = board_data[self.board_ch - 1][16]
        ch4_iir_data_x = board_data[self.board_ch - 1][17]
        ch4_error_buf = board_data[self.board_ch - 1][18]
        ch4_feedback_buf = board_data[self.board_ch - 1][19]

        self.LIA_config.pid_disable(self.board_num, 1)
        self.LIA_config.pid_disable(self.board_num, 2)
        self.LIA_config.pid_disable(self.board_num, 3)
        self.LIA_config.pid_disable(self.board_num, 4)
        self.LIA_config.ALL_stop(self.board_num)
        # print(ch1_feedback_buf)
        # print(ch2_feedback_buf)
        # print(ch3_feedback_buf)
        # print(ch4_feedback_buf)
        path_ = datapath + 'magPID_data.csv'
        #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_, {'Time': np.array(range(len(ch1_iir_data_y))) / 80.0,
                         'ch1_iir_data_r': ch1_iir_data_r, 'ch1_iir_data_x': ch1_iir_data_x, 'ch1_iir_data_y': ch1_iir_data_y, 'ch1_error_buf': ch1_error_buf, 'ch1_feedback_buf': ch1_feedback_buf,
                         'ch2_iir_data_r': ch2_iir_data_r, 'ch2_iir_data_x': ch2_iir_data_x, 'ch2_iir_data_y': ch2_iir_data_y, 'ch2_error_buf': ch2_error_buf, 'ch2_feedback_buf': ch2_feedback_buf,
                         'ch3_iir_data_r': ch3_iir_data_r, 'ch3_iir_data_x': ch3_iir_data_x, 'ch3_iir_data_y': ch3_iir_data_y, 'ch3_error_buf': ch3_error_buf, 'ch3_feedback_buf': ch3_feedback_buf,
                         'ch4_iir_data_r': ch4_iir_data_r, 'ch4_iir_data_x': ch4_iir_data_x, 'ch4_iir_data_y': ch4_iir_data_y, 'ch4_error_buf': ch4_error_buf, 'ch4_feedback_buf': ch4_feedback_buf,
                         })

        iir_data_y = [ch1_iir_data_y, ch2_iir_data_y, ch3_iir_data_y, ch4_iir_data_y]
        error_data = [ch1_error_buf, ch2_error_buf, ch3_error_buf, ch4_error_buf]
        feedback_data = [ch1_feedback_buf, ch2_feedback_buf, ch3_feedback_buf, ch4_feedback_buf]
        plt.figure(1)
        ax1 = plt.subplot(311)
        ax1.plot(np.array(range(len(ch3_iir_data_y))) / 80.0, error_data[debug_ch - 1], label='error_buf')
        plt.legend()
        ax2 = plt.subplot(312)
        ax2.plot(np.array(range(len(ch2_iir_data_y))) / 80.0, feedback_data[debug_ch - 1], label='feedback_buf')
        # plt.legend()
        # ax3 = plt.subplot(313)
        # ax3.plot(np.array(range(len(ch2_iir_data_y))) / 80.0, iir_data_y[debug_ch - 1], label='iir_data_y')
        # ax5 = plt.subplot(515)
        # ax5.plot(np.array(range(len(ch2_iir_data_y))) / 80.0, ch2_iir_data_r, label='iir_data_y')
        path_1 = datapath + 'magPID_data.png'
        plt.xlabel('Time/s')
        plt.ylabel('Amp/1')
        plt.legend()
        plt.savefig(path_1)
        plt.show()
        plt.clf()

    def BW_TEST_Mag_PID_Control(self, axes_list=[8,5,3,2], sample_point=500, debug_ch=1, signal_Fre=10):
        # 测磁PID测试，将PID系数均设置为0，扫描CW谱线
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        # 开启测磁PID，首先开启激光PID。
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        time.sleep(1)
        # 分别设置tc，每个通道的调制解调
        # tc = 0.1
        self.LIA_config.tc(0.2)
        ch_num = 1
        for axes_ch in axes_list:
            if axes_ch == 2 or axes_ch == 7:
                modu_Fre = ini_rd('CW', 'modu_fre_ch2')
            elif axes_ch == 3 or axes_ch == 6:
                modu_Fre = ini_rd('CW', 'modu_fre_ch3')
            elif axes_ch == 4 or axes_ch == 5:
                modu_Fre = ini_rd('CW', 'modu_fre_ch4')
            else:
                modu_Fre = ini_rd('CW', 'modu_fre_ch1')
            demodu_phase = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch) + '_demoduphase')
            self.LIA_config.Modu_fre_config(ch_num, float(modu_Fre))
            self.LIA_config.De_fre_config(ch_num, float(modu_Fre) + signal_Fre)
            De_phase = float(demodu_phase) / (np.pi) * 180 # °
            self.LIA_config.De_phase_config(ch_num * 2 - 1, De_phase)
            ch_num += 1

        # 文件保存目录
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        # 写入参数
        iir_sample_rate = 50  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        attu = 13
        modu = 18
        # modu = 0
        MW_para = [[2979000000.0, modu, attu], [2909000000.0, modu, attu], [2809000000.0, modu, attu], [2784000000.0, modu, attu]]
        self.LIA_config.MW1_SPI_ctrl(self.board_num, MW_para)
        time.sleep(5)

        center = []
        for i in range(4):
            # PID_ch_num = 1  # 磁测量PID通道为1
            set_point = 0  # 将输出稳定在过零点
            axes_center = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_center')
            center.append(float(axes_center))
            output_offset = (center[-1] - 50000 - 2600000000) * 524288
            kp = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_kp'))
            ki = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_ki'))
            kd = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_kd'))
            kt = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_list[i]) + '_kt'))
            Cal_ex = 312499
            RD_ex = 0
            PID_LIA_CH = 1

            PID_coe = [set_point, output_offset, kp, ki, kd, kt, RD_ex, Cal_ex, PID_LIA_CH]
            print('PID_coe : ', PID_coe)
            self.LIA_config.pid_config(self.board_num, i+1, PID_coe)
        self.LIA_config.pid_enable(self.board_num, 1)
        self.LIA_config.pid_enable(self.board_num, 2)
        self.LIA_config.pid_enable(self.board_num, 3)
        self.LIA_config.pid_enable(self.board_num, 4)
        # time.sleep(1)
        print('PID coe download')
        board_data = self.LIA_config.AcquireStartV3_MagPID(self.board_num, self.board_ch, sample_point)  #self.board_num:3 5 6 7 self.board_ch:1 2 3 4
        # print(board_data)

        ch1_iir_data_r = board_data[self.board_ch - 1][0]
        ch1_iir_data_y = board_data[self.board_ch - 1][1]
        ch1_iir_data_x = board_data[self.board_ch - 1][2]
        ch1_error_buf = board_data[self.board_ch - 1][3]
        ch1_feedback_buf = board_data[self.board_ch - 1][4]
        print('ch1_feedback = ', board_data[self.board_ch - 1][4])

        ch2_iir_data_r = board_data[self.board_ch - 1][5]
        ch2_iir_data_y = board_data[self.board_ch - 1][6]
        ch2_iir_data_x = board_data[self.board_ch - 1][7]
        ch2_error_buf = board_data[self.board_ch - 1][8]
        ch2_feedback_buf = board_data[self.board_ch - 1][9]


        ch3_iir_data_r = board_data[self.board_ch - 1][10]
        ch3_iir_data_y = board_data[self.board_ch - 1][11]
        ch3_iir_data_x = board_data[self.board_ch - 1][12]
        ch3_error_buf = board_data[self.board_ch - 1][13]
        ch3_feedback_buf = board_data[self.board_ch - 1][14]

        ch4_iir_data_r = board_data[self.board_ch - 1][15]
        ch4_iir_data_y = board_data[self.board_ch - 1][16]
        ch4_iir_data_x = board_data[self.board_ch - 1][17]
        ch4_error_buf = board_data[self.board_ch - 1][18]
        ch4_feedback_buf = board_data[self.board_ch - 1][19]

        self.LIA_config.pid_disable(self.board_num, 1)
        self.LIA_config.pid_disable(self.board_num, 2)
        self.LIA_config.pid_disable(self.board_num, 3)
        self.LIA_config.pid_disable(self.board_num, 4)
        self.LIA_config.ALL_stop(self.board_num)
        # print(ch1_feedback_buf)
        # print(ch2_feedback_buf)
        # print(ch3_feedback_buf)
        # print(ch4_feedback_buf)
        path_ = datapath + 'magPID_data.csv'
        #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_, {'Time': np.array(range(len(ch1_iir_data_y))) / 80.0,
                         'ch1_iir_data_r': ch1_iir_data_r, 'ch1_iir_data_x': ch1_iir_data_x, 'ch1_iir_data_y': ch1_iir_data_y, 'ch1_error_buf': ch1_error_buf, 'ch1_feedback_buf': ch1_feedback_buf,
                         'ch2_iir_data_r': ch2_iir_data_r, 'ch2_iir_data_x': ch2_iir_data_x, 'ch2_iir_data_y': ch2_iir_data_y, 'ch2_error_buf': ch2_error_buf, 'ch2_feedback_buf': ch2_feedback_buf,
                         'ch3_iir_data_r': ch3_iir_data_r, 'ch3_iir_data_x': ch3_iir_data_x, 'ch3_iir_data_y': ch3_iir_data_y, 'ch3_error_buf': ch3_error_buf, 'ch3_feedback_buf': ch3_feedback_buf,
                         'ch4_iir_data_r': ch4_iir_data_r, 'ch4_iir_data_x': ch4_iir_data_x, 'ch4_iir_data_y': ch4_iir_data_y, 'ch4_error_buf': ch4_error_buf, 'ch4_feedback_buf': ch4_feedback_buf,
                         })

        iir_data_y = [ch1_iir_data_y, ch2_iir_data_y, ch3_iir_data_y, ch4_iir_data_y]
        error_data = [ch1_error_buf, ch2_error_buf, ch3_error_buf, ch4_error_buf]
        feedback_data = [ch1_feedback_buf, ch2_feedback_buf, ch3_feedback_buf, ch4_feedback_buf]
        plt.figure(1)
        ax1 = plt.subplot(311)
        ax1.plot(np.array(range(len(ch3_iir_data_y))) / 80.0, error_data[debug_ch - 1], label='error_buf')
        plt.legend()
        ax2 = plt.subplot(312)
        ax2.plot(np.array(range(len(ch2_iir_data_y))) / 80.0, feedback_data[debug_ch - 1], label='feedback_buf')
        # plt.legend()
        # ax3 = plt.subplot(313)
        # ax3.plot(np.array(range(len(ch2_iir_data_y))) / 80.0, iir_data_y[debug_ch - 1], label='iir_data_y')
        # ax5 = plt.subplot(515)
        # ax5.plot(np.array(range(len(ch2_iir_data_y))) / 80.0, ch2_iir_data_r, label='iir_data_y')
        path_1 = datapath + 'magPID_data.png'
        plt.xlabel('Time/s')
        plt.ylabel('Amp/1')
        plt.legend()
        plt.savefig(path_1)
        plt.show()
        plt.clf()

    def Laser_PID_Control_coe_select(self):
        # 激光功率PID测试
        # 将微波定在非共振点处，测量激光PID开启前后的荧光DC值的STD值大小。
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.6)
        time.sleep(1)
        self.LIA_config.tc(0.1)
        Modu_fre = 2330.133283623823
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(1, De_phase)
        MW_fre = 2700000000

        # SNR = []
        # attu = []
        # ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        # os.makedirs('data/' + ospath)
        # datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)
        for i in range(15):
            # input()
            iir_sample_rate = 50  # Hz
            self.LIA_config.sample_rate_config(iir_sample_rate)
            self.LIA_config.ALL_stop(self.board_num)
            self.LIA_config.DAC_play(self.board_num)
            self.LIA_config.ALL_start(self.board_num)
            # 先判定荧光电流大小
            # board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, 100)
            # board_data = [board1_data, board2_data, board3_data, board4_data]
            # Flo_mean = np.mean(board_data[self.board_ch - 1][24])
            # Laser_mean = np.mean(board_data[self.board_ch - 1][25])
            # print('Flo_mean = ', Flo_mean, 'Laser_mean', Laser_mean)
            # plt.plot(range(len(board_data[self.board_ch - 1][24])), board_data[self.board_ch - 1][24])
            # plt.plot(range(len(board_data[self.board_ch - 1][24])), board_data[self.board_ch - 1][25])
            # plt.show()
            PID_ch_num = 5  # 激光PID通道为5
            set_point = 0.16  # 需先测量得到荧光信号的DC值后确定
            output_offset = 0.57  # 将激光稳定在0.6 A
            # 探头3的PID参数：
            kp = -0.015
            ki = -0.009

            kd = -0.0000 - i * 0.002
            kt = 1.0000000
            print('kp ki kd = ', kp, ki, kd)
            # kp = -0.000
            # ki = -0.000
            #
            # kd = -0.0000
            # kt = 1.0000000
            Cal_ex = 0
            RD_ex = 0
            PID_LIA_CH = 0
            PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
            self.LIA_config.pid_config(self.board_num, PID_ch_num, PID_coe)
            print('PID coe download')
            self.LIA_config.pid_enable(self.board_num, PID_ch_num)
            print('PID enable')
            daq_num = 400
            board_data = self.LIA_config.AcquireStartV3_PID(self.board_num, self.board_ch, daq_num)  #self.board_num:3 5 6 7 self.board_ch:1 2 3 4
            print(board_data)
            # print('PID play')
            time.sleep(daq_num / 100)
            self.LIA_config.pid_disable(self.board_num, 5)
            self.LIA_config.ALL_stop(self.board_num)
            self.CS_Control(0.0)
            time.sleep(1)
            print('data_std:', np.std(board_data[3][0][200:]))
        # path_ = datapath + 'Laser_PID_data.csv'
        # csv_save(path_, {'error':board_data[3][0], 'feedback': board_data[3][1]})
        # self.LIA_config.Laser_pid_plot()

    def Laser_PID_Control_conftinue(self):
        # 激光功率PID测试
        # 将微波定在非共振点处，测量激光PID开启前后的荧光DC值的STD值大小。
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.6)
        # input()
        self.LIA_config.tc(0.1)
        Modu_fre = 2330.133283623823
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(1, De_phase)
        MW_fre = 2700000000

        SNR = []
        attu = []
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 50  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        # 先判定荧光电流大小
        # board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, 100)
        # board_data = [board1_data, board2_data, board3_data, board4_data]
        # Flo_mean = np.mean(board_data[self.board_ch - 1][24])
        # Laser_mean = np.mean(board_data[self.board_ch - 1][25])
        # print('Flo_mean = ', Flo_mean, 'Laser_mean', Laser_mean)
        # plt.plot(range(len(board_data[self.board_ch - 1][24])), board_data[self.board_ch - 1][24])
        # plt.plot(range(len(board_data[self.board_ch - 1][24])), board_data[self.board_ch - 1][25])
        # plt.show()
        PID_ch_num = 5  # 激光PID通道为5
        set_point = 0.14  # 需先测量得到荧光信号的DC值后确定
        output_offset = 0.57  # 将激光稳定在0.6 A
        # kp = -0.015
        # ki = -0.01
        #
        # kd = -0.0000
        # kt = 1.0000000
        kp = -0.000
        ki = -0.000

        kd = -0.0000
        kt = 1.0000000
        Cal_ex = 0
        RD_ex = 0
        PID_LIA_CH = 0
        PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
        self.LIA_config.pid_config(self.board_num, PID_ch_num, PID_coe)
        print('PID coe download')
        self.LIA_config.pid_enable(self.board_num, PID_ch_num)
        print('PID enable')
        self.board1_data, self.board2_data, self.board3_data, self.board4_data = self.LIA_config.Laser_PID_play(self.board_num, 2000)
        print('PID play')
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.0)
        path_ = datapath + 'Laser_PID_data.csv'
        csv_save(path_, {'error': self.board4_data[0], 'feedback': self.board4_data[1]})
        # self.LIA_config.Laser_pid_plot()

    def CW_8Control(self, CS_Value, axes_ch=[8, 5, 3, 2], phase_optimize=False, scan_point=250, Fre_span=100000):
        # CS_Value: 激光电流大小
        # axes_ch：扫描第几个峰
        # phase_optimize: False:加载已有相位参数，True：重新进行相位标定
        # scan_point:每张谱线扫描点数
        # Fre_span:每个点间隔的频率值，单位Hz
        self.CS_Control(CS_Value)
        # time.sleep(20)
        # 进行CW谱线扫描，需要先优化相位

        time.sleep(.1)
        # self.CS_Control(0.6)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.1)
        # 加载四个调制解调通道
        ch_num = 1
        MW_para = [[]for i in range(4)]
        MW_start = []
        for i in range(4):
            if axes_ch[i] == 2 or axes_ch[i] == 7:
                modu_Fre = ini_rd('CW', 'modu_fre_ch2')
            elif axes_ch[i] == 3 or axes_ch[i] == 6:
                modu_Fre = ini_rd('CW', 'modu_fre_ch3')
            elif axes_ch[i] == 4 or axes_ch[i] == 5:
                modu_Fre = ini_rd('CW', 'modu_fre_ch4')
            else:
                modu_Fre = ini_rd('CW', 'modu_fre_ch1')
            print('board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[i]) + '_demoduphase')
            if phase_optimize == False:
                demodu_phase = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[i]) + '_demoduphase')
            else:
                demodu_phase = 0
            self.LIA_config.Modu_fre_config(ch_num, float(modu_Fre))
            self.LIA_config.De_fre_config(ch_num, float(modu_Fre))
            De_phase = float(demodu_phase) / (np.pi) * 180 # °
            print('De_phase', De_phase)
            # self.LIA_config.De_phase_config(2 * ch_num, De_phase)
            self.LIA_config.De_phase_config(2 * ch_num - 1, De_phase)
            axes_start = float(ini_rd('CW', 'axes' + str(axes_ch[i]) + '_start'))
            MW_start.append(axes_start)
            MW_modu = 18
            MW_atte = 13
            MW_para[ch_num - 1] = [axes_start, MW_modu, MW_atte]
            ch_num += 1
        print('MW_para = ', MW_para)
        Flo_r = [[] for i in range(4)]
        Flo_y = [[] for i in range(4)]
        Flo_x = [[] for i in range(4)]
        Laser_r = [[] for i in range(4)]
        Laser_y = [[] for i in range(4)]
        Laser_x = [[] for i in range(4)]
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 8000  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        time.sleep(8)
        print('MW_para = ', MW_para)
        for i in range(scan_point):
            for m in range(4):
                MW_para[m][0] = MW_para[m][0] + Fre_span

            self.LIA_config.MW1_SPI_ctrl(self.board_num, MW_para)
            print('MW_para = ', MW_para)
            # time.sleep(.1)
            # input()
            self.iir_data_num = 8

            board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num, CW_mode=True)
            board_data = [board1_data, board2_data, board3_data, board4_data]
            # self.LIA_config.iir_plot()
            for n in range(4):
                Flo_r_mean = np.mean(board_data[self.board_ch - 1][0 + 6 * n])
                Flo_y_mean = np.mean(board_data[self.board_ch - 1][1 + 6 * n])
                Flo_x_mean = np.mean(board_data[self.board_ch - 1][2 + 6 * n])
                Laser_r_mean = np.mean(board_data[self.board_ch - 1][3 + 6 * n])
                Laser_y_mean = np.mean(board_data[self.board_ch - 1][4 + 6 * n])
                Laser_x_mean = np.mean(board_data[self.board_ch - 1][5 + 6 * n])
                Flo_r[n].append(Flo_r_mean)
                Flo_y[n].append(Flo_y_mean)
                Flo_x[n].append(Flo_x_mean)
                Laser_r[n].append(Laser_r_mean)
                Laser_y[n].append(Laser_y_mean)
                Laser_x[n].append(Laser_x_mean)

        path_ = datapath + 'CW1_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[0])), int(float(float(MW_start[0]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[0], 'ch1_Flo_y': Flo_y[0], 'ch1_Flo_x': Flo_x[0]})
        path_ = datapath + 'CW2_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[1])), int(float(float(MW_start[1]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[1], 'ch1_Flo_y': Flo_y[1], 'ch1_Flo_x': Flo_x[1]})
        path_ = datapath + 'CW3_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[2])), int(float(float(MW_start[2]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[2], 'ch1_Flo_y': Flo_y[2], 'ch1_Flo_x': Flo_x[2]})
        path_ = datapath + 'CW4_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[3])), int(float(float(MW_start[3]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[3], 'ch1_Flo_y': Flo_y[3], 'ch1_Flo_x': Flo_x[3]})
        # self.CS_Control(0.0)
        # print('Flo_y', Flo_y)
        # print('Flo_x', Flo_x)
        for i in range(4):
            print('Flo_r', Flo_r[i])
        for g in range(4):
            # 保存图片
            MW_FRE_range = range(int(float(MW_start[g])), int(float(float(MW_start[g]))) + Fre_span*scan_point, Fre_span)
            plt.plot(MW_FRE_range, Flo_r[g], label='Flo_r')
            plt.plot(MW_FRE_range, Flo_y[g], label='Flo_y')
            plt.plot(MW_FRE_range, Flo_x[g], label='Flo_x')
            # plt.plot(MW_fre, Laser_r, label='Laser_r')
            # plt.plot(MW_fre, Laser_y, label='Laser_y')
            # plt.plot(MW_fre, Laser_x, label='Laser_x')
            path_1 = datapath + 'CW' + str(g) + '_data.png'
            plt.xlabel('MW_fre/Hz')
            plt.ylabel('Amp/1')
            plt.legend()
            plt.savefig(path_1)
            #计算谱线最大斜率
            Flo_y_min = sorted(zip(Flo_y[g], MW_FRE_range))[0][1]
            Flo_y_max = sorted(zip(Flo_y[g], MW_FRE_range))[-1][1]
            ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[g]) + '_center', str((Flo_y_min + Flo_y_max)/2))
            # 计算谱线最大斜率
            max_index = MW_FRE_range.index(Flo_y_min)
            min_index = MW_FRE_range.index(Flo_y_max)
            print('min_index = ', min_index)
            print('max_index = ', max_index)
            linear_x = MW_FRE_range[int((4*min_index + 2*max_index)/6): int((4*max_index + 2*min_index)/6)]
            linear_y = Flo_y[g][int((4*min_index + 2*max_index)/6): int((4*max_index + 2*min_index)/6)]
            print('linear_x = ', linear_x)
            print('linear_y = ', linear_y)
            try:
                z1 = np.polyfit(linear_x, linear_y, 1)  #一次多项式拟合，相当于线性拟合
                ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[g]) + '_slope', str(z1[0]))
            except:
                pass

            if phase_optimize == True:
                modu_phase = np.arctan2(Flo_x[g][max_index], Flo_y[g][max_index])
                # if modu_phase < 0:
                #     modu_phase = np.pi/2 - modu_phase
                ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[g]) + '_demoduphase', str(modu_phase))
                print('phase cal', Flo_x[g][max_index], Flo_y[g][max_index], modu_phase)
            # plt.show()

            plt.clf()
        #     self.CS_Control(0.)
        # self.CS_Control(0.0)

    def PID_4CW(self, CS_Value, axes_ch=[8, 5, 3, 2], phase_optimize=False, scan_point=250, Fre_span=100000):
        self.CS_Control(CS_Value)
        # time.sleep(20)
        # 进行CW谱线扫描，需要先优化相位

        time.sleep(.1)
        # self.CS_Control(0.6)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.2)
        # 每次扫描四个峰，先对2358四个峰进行扫描，之后对1467四个峰进行扫描
        # 加载四个调制解调通道
        ch_num = 1
        MW_para = [[]for i in range(4)]
        MW_start = []
        for i in range(4):
            if axes_ch[i] == 2 or axes_ch[i] == 7:
                modu_Fre = ini_rd('CW', 'modu_fre_ch2')
            elif axes_ch[i] == 3 or axes_ch[i] == 6:
                modu_Fre = ini_rd('CW', 'modu_fre_ch3')
            elif axes_ch[i] == 4 or axes_ch[i] == 5:
                modu_Fre = ini_rd('CW', 'modu_fre_ch4')
            else:
                modu_Fre = ini_rd('CW', 'modu_fre_ch1')
            # print('board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[i]) + '_demoduphase')
            if phase_optimize == False:
                demodu_phase = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[i]) + '_demoduphase')
            else:
                demodu_phase = 0
            self.LIA_config.Modu_fre_config(ch_num, float(modu_Fre))
            self.LIA_config.De_fre_config(ch_num, float(modu_Fre))
            De_phase = float(demodu_phase) / (np.pi) * 180 # °
            # print('De_phase', De_phase)
            # self.LIA_config.De_phase_config(2 * ch_num, De_phase)
            self.LIA_config.De_phase_config(2 * ch_num - 1, De_phase)
            axes_start = float(ini_rd('CW', 'axes' + str(axes_ch[i]) + '_start'))
            MW_start.append(axes_start)
            MW_modu = 18
            MW_atte = 13
            MW_para[ch_num - 1] = [axes_start, MW_modu, MW_atte]
            ch_num += 1
        print('MW_para = ', MW_para)
        Flo_r = [[] for i in range(4)]
        Flo_y = [[] for i in range(4)]
        Flo_x = [[] for i in range(4)]
        Laser_r = [[] for i in range(4)]
        Laser_y = [[] for i in range(4)]
        Laser_x = [[] for i in range(4)]
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 8000  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        time.sleep(8)
        print('MW_para = ', MW_para)
        for i in range(scan_point):
            for m in range(4):
                MW_para[m][0] = MW_para[m][0] + Fre_span
                # PID_ch_num = 1  # 磁测量PID通道为1
                set_point = 0  # 将输出稳定在过零点
                axes_center = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[m]) + '_center')
                output_offset = (MW_para[m][0] - 2600000000) * 524288
                # print('offset = ', MW_para[m][0])
                kp = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[m]) + '_kp'))
                ki = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[m]) + '_ki'))
                kd = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[m]) + '_kd'))
                kt = float(ini_rd('Mag_PID', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[m]) + '_kt'))
                Cal_ex = 156249
                RD_ex = 1
                PID_LIA_CH = 1

                PID_coe = [set_point, output_offset, kp, ki, kd, kt, RD_ex, Cal_ex, PID_LIA_CH]
                # print('PID_coe : ', PID_coe)
                self.LIA_config.pid_config(self.board_num, m+1, PID_coe)
            self.LIA_config.pid_enable(self.board_num, 1)
            self.LIA_config.pid_enable(self.board_num, 2)
            self.LIA_config.pid_enable(self.board_num, 3)
            self.LIA_config.pid_enable(self.board_num, 4)
            # time.sleep(1)
            # print('PID coe download')
            board_data = self.LIA_config.AcquireStartV3_MagPID(self.board_num, self.board_ch, 10)  #self.board_num:3 5 6 7 self.board_ch:1 2 3 4
            # print(board_data)

            ch1_iir_data_r = board_data[self.board_ch - 1][0]
            ch1_iir_data_y = board_data[self.board_ch - 1][1]
            ch1_iir_data_x = board_data[self.board_ch - 1][2]
            ch1_error_buf = board_data[self.board_ch - 1][3]
            ch1_feedback_buf = board_data[self.board_ch - 1][4]

            ch2_iir_data_r = board_data[self.board_ch - 1][5]
            ch2_iir_data_y = board_data[self.board_ch - 1][6]
            ch2_iir_data_x = board_data[self.board_ch - 1][7]
            ch2_error_buf = board_data[self.board_ch - 1][8]
            ch2_feedback_buf = board_data[self.board_ch - 1][9]
            print('ch2_feedback = ', board_data[self.board_ch - 1][9])

            ch3_iir_data_r = board_data[self.board_ch - 1][10]
            ch3_iir_data_y = board_data[self.board_ch - 1][11]
            ch3_iir_data_x = board_data[self.board_ch - 1][12]
            ch3_error_buf = board_data[self.board_ch - 1][13]
            ch3_feedback_buf = board_data[self.board_ch - 1][14]

            ch4_iir_data_r = board_data[self.board_ch - 1][15]
            ch4_iir_data_y = board_data[self.board_ch - 1][16]
            ch4_iir_data_x = board_data[self.board_ch - 1][17]
            ch4_error_buf = board_data[self.board_ch - 1][18]
            ch4_feedback_buf = board_data[self.board_ch - 1][19]
            board_data = [[ch1_iir_data_r, ch1_iir_data_x, ch1_iir_data_y],
                          [ch2_iir_data_r, ch2_iir_data_x, ch2_iir_data_y],
                          [ch3_iir_data_r, ch3_iir_data_x, ch3_iir_data_y],
                          [ch4_iir_data_r, ch4_iir_data_x, ch4_iir_data_y]]

            self.LIA_config.MW1_SPI_ctrl(self.board_num, MW_para)
            print('MW_para = ', MW_para)
            # self.LIA_config.iir_plot()
            for n in range(4):
                Flo_r[n].append(np.mean(board_data[n][0]))
                Flo_y[n].append(np.mean(board_data[n][2]))
                Flo_x[n].append(np.mean(board_data[n][1]))

        self.LIA_config.pid_disable(self.board_num, 1)
        self.LIA_config.pid_disable(self.board_num, 2)
        self.LIA_config.pid_disable(self.board_num, 3)
        self.LIA_config.pid_disable(self.board_num, 4)
        self.LIA_config.ALL_stop(self.board_num)
        path_ = datapath + 'CW1_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[0])), int(float(float(MW_start[0]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[0], 'ch1_Flo_y': Flo_y[0], 'ch1_Flo_x': Flo_x[0]})
        path_ = datapath + 'CW2_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[1])), int(float(float(MW_start[1]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[1], 'ch1_Flo_y': Flo_y[1], 'ch1_Flo_x': Flo_x[1]})
        path_ = datapath + 'CW3_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[2])), int(float(float(MW_start[2]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[2], 'ch1_Flo_y': Flo_y[2], 'ch1_Flo_x': Flo_x[2]})
        path_ = datapath + 'CW4_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[3])), int(float(float(MW_start[3]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[3], 'ch1_Flo_y': Flo_y[3], 'ch1_Flo_x': Flo_x[3]})
        # self.CS_Control(0.0)
        # print('Flo_y', Flo_y)
        # print('Flo_x', Flo_x)
        for i in range(4):
            print('Flo_r', Flo_r[i])
        for g in range(4):
            # 保存图片
            MW_FRE_range = range(int(float(MW_start[g])), int(float(float(MW_start[g]))) + Fre_span*scan_point, Fre_span)
            plt.plot(MW_FRE_range, Flo_r[g], label='Flo_r')
            plt.plot(MW_FRE_range, Flo_y[g], label='Flo_y')
            plt.plot(MW_FRE_range, Flo_x[g], label='Flo_x')
            # plt.plot(MW_fre, Laser_r, label='Laser_r')
            # plt.plot(MW_fre, Laser_y, label='Laser_y')
            # plt.plot(MW_fre, Laser_x, label='Laser_x')
            path_1 = datapath + 'CW' + str(g) + '_data.png'
            plt.xlabel('MW_fre/Hz')
            plt.ylabel('Amp/1')
            plt.legend()
            plt.savefig(path_1)

            plt.clf()
        #     self.CS_Control(0.)
        # self.CS_Control(0.0)

    def Single_axes_CW_8Control(self, CS_Value, axes_ch=[8, 5, 3, 2], phase_optimize=False, scan_point=250, Fre_span=100000, axes_on=1):
        self.CS_Control(CS_Value)
        # time.sleep(20)
        # 进行CW谱线扫描，需要先优化相位

        time.sleep(.1)
        # self.CS_Control(0.6)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.05)
        # 每次扫描四个峰，先对2358四个峰进行扫描，之后对1467四个峰进行扫描
        # 加载四个调制解调通道
        ch_num = 1
        MW_para = [[]for i in range(4)]
        MW_start = []
        for i in range(4):
            if axes_ch[i] == 2 or axes_ch[i] == 7:
                modu_Fre = ini_rd('CW', 'modu_fre_ch2')
            elif axes_ch[i] == 3 or axes_ch[i] == 6:
                modu_Fre = ini_rd('CW', 'modu_fre_ch3')
            elif axes_ch[i] == 4 or axes_ch[i] == 5:
                modu_Fre = ini_rd('CW', 'modu_fre_ch4')
            else:
                modu_Fre = ini_rd('CW', 'modu_fre_ch1')
            print('board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[i]) + '_demoduphase')
            if phase_optimize == False:
                demodu_phase = ini_rd('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[i]) + '_demoduphase')
            else:
                demodu_phase = 0
            self.LIA_config.Modu_fre_config(ch_num, float(modu_Fre))
            self.LIA_config.De_fre_config(ch_num, float(modu_Fre))
            De_phase = float(demodu_phase) / (np.pi) * 180 # °
            print('De_phase', De_phase)
            # self.LIA_config.De_phase_config(2 * ch_num, De_phase)
            self.LIA_config.De_phase_config(2 * ch_num - 1, De_phase)
            axes_start = float(ini_rd('CW', 'axes' + str(axes_ch[i]) + '_start'))
            MW_start.append(axes_start)
            if i + 1 == axes_on:
                MW_modu = 18
                MW_atte = 13
            else:
                MW_modu = 0
                MW_atte = 13
            MW_para[ch_num - 1] = [axes_start, MW_modu, MW_atte]
            ch_num += 1
        print('MW_para = ', MW_para)
        Flo_r = [[] for i in range(4)]
        Flo_y = [[] for i in range(4)]
        Flo_x = [[] for i in range(4)]
        Laser_r = [[] for i in range(4)]
        Laser_y = [[] for i in range(4)]
        Laser_x = [[] for i in range(4)]
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 8000  # Hz
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        time.sleep(1)
        print('MW_para = ', MW_para)
        for i in range(scan_point):
            for m in range(4):
                MW_para[m][0] = MW_para[m][0] + Fre_span

            self.LIA_config.MW1_SPI_ctrl(self.board_num, MW_para)
            # time.sleep(.1)
            # input()
            self.iir_data_num = 8

            board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num, CW_mode=True)
            board_data = [board1_data, board2_data, board3_data, board4_data]
            # self.LIA_config.iir_plot()
            for n in range(4):
                Flo_r_mean = np.mean(board_data[self.board_ch - 1][0 + 6 * n])
                Flo_y_mean = np.mean(board_data[self.board_ch - 1][1 + 6 * n])
                Flo_x_mean = np.mean(board_data[self.board_ch - 1][2 + 6 * n])
                Laser_r_mean = np.mean(board_data[self.board_ch - 1][3 + 6 * n])
                Laser_y_mean = np.mean(board_data[self.board_ch - 1][4 + 6 * n])
                Laser_x_mean = np.mean(board_data[self.board_ch - 1][5 + 6 * n])
                Flo_r[n].append(Flo_r_mean)
                Flo_y[n].append(Flo_y_mean)
                Flo_x[n].append(Flo_x_mean)
                Laser_r[n].append(Laser_r_mean)
                Laser_y[n].append(Laser_y_mean)
                Laser_x[n].append(Laser_x_mean)

        path_ = datapath + 'CW1_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[0])), int(float(float(MW_start[0]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[0], 'ch1_Flo_y': Flo_y[0], 'ch1_Flo_x': Flo_x[0]})
        path_ = datapath + 'CW2_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[1])), int(float(float(MW_start[1]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[1], 'ch1_Flo_y': Flo_y[1], 'ch1_Flo_x': Flo_x[1]})
        path_ = datapath + 'CW3_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[2])), int(float(float(MW_start[2]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[2], 'ch1_Flo_y': Flo_y[2], 'ch1_Flo_x': Flo_x[2]})
        path_ = datapath + 'CW4_data.csv'
        csv_save(path_, {'Frequency': range(int(float(MW_start[3])), int(float(float(MW_start[3]))) + Fre_span * scan_point, Fre_span), 'ch1_Flo_r': Flo_r[3], 'ch1_Flo_y': Flo_y[3], 'ch1_Flo_x': Flo_x[3]})
        # self.CS_Control(0.0)
        # print('Flo_y', Flo_y)
        # print('Flo_x', Flo_x)
        for i in range(4):
            print('Flo_r', Flo_r[i])
        for g in range(4):
            # 保存图片
            MW_FRE_range = range(int(float(MW_start[g])), int(float(float(MW_start[g]))) + Fre_span*scan_point, Fre_span)
            plt.plot(MW_FRE_range, Flo_r[g], label='Flo_r')
            plt.plot(MW_FRE_range, Flo_y[g], label='Flo_y')
            plt.plot(MW_FRE_range, Flo_x[g], label='Flo_x')
            # plt.plot(MW_fre, Laser_r, label='Laser_r')
            # plt.plot(MW_fre, Laser_y, label='Laser_y')
            # plt.plot(MW_fre, Laser_x, label='Laser_x')
            path_1 = datapath + 'CW' + str(g) + '_data.png'
            plt.xlabel('MW_fre/Hz')
            plt.ylabel('Amp/1')
            plt.legend()
            plt.savefig(path_1)
            #计算谱线最大斜率
            Flo_y_min = sorted(zip(Flo_y[g], MW_FRE_range))[0][1]
            Flo_y_max = sorted(zip(Flo_y[g], MW_FRE_range))[-1][1]
            ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[g]) + '_center', str((Flo_y_min + Flo_y_max)/2))
            # 计算谱线最大斜率
            max_index = MW_FRE_range.index(Flo_y_min)
            min_index = MW_FRE_range.index(Flo_y_max)
            print('min_index = ', min_index)
            print('max_index = ', max_index)
            linear_x = MW_FRE_range[int((4*min_index + 2*max_index)/6): int((4*max_index + 2*min_index)/6)]
            linear_y = Flo_y[g][int((4*min_index + 2*max_index)/6): int((4*max_index + 2*min_index)/6)]
            print('linear_x = ', linear_x)
            print('linear_y = ', linear_y)
            try:
                z1 = np.polyfit(linear_x, linear_y, 1)  #一次多项式拟合，相当于线性拟合
                ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[g]) + '_slope', str(z1[0]))
            except:
                pass

            if phase_optimize == True:
                modu_phase = np.arctan2(Flo_x[g][max_index], Flo_y[g][max_index])
                # if modu_phase < 0:
                #     modu_phase = np.pi/2 - modu_phase
                ini_wr('CW', 'board_ch' + str(self.board_ch) + '_axes' + str(axes_ch[g]) + '_demoduphase', str(modu_phase))
                print('phase cal', Flo_x[g][max_index], Flo_y[g][max_index], modu_phase)
            # plt.show()

            plt.clf()
        #     self.CS_Control(0.)
        # self.CS_Control(0.0)

    def Sensitive_test(self):
        # 激光功率PID测试
        # 将微波定在非共振点处，测量激光PID开启前后的荧光DC值的STD值大小。
        # ch4: 2.755-2.775, 2.775-2.8, 2.8-2.835, 2.835-2.86, 2.9-2.92, 2.92-2.945, 2.945-2.97, 2.97-3.0
        # ch4: De_phase 22
        # ch4: modu:18
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.)
        time.sleep(.1)
        self.CS_Control(0.6)
        time.sleep(1)
        self.LIA_config.tc(0.1)
        Modu_fre = 2330.133283623823
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180 # °
        self.LIA_config.De_phase_config(1, De_phase)
        MW_fre = 2700000000

        SNR = []
        attu = []
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'
        # 1. MW Channel / Mod. SQW Output (?)
        # 2. Board Num (y)
        # 3. CW Scanning Step (set to 1 MHz)

        # input()
        iir_sample_rate = 50  # Hz
        self.iir_data_num = 400000
        self.LIA_config.sample_rate_config(iir_sample_rate)
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.DAC_play(self.board_num)
        self.LIA_config.ALL_start(self.board_num)
        self.LIA_config.MW1_SPI_ctrl(self.board_num)
        # 先判定荧光电流大小
        # board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, 100)
        # board_data = [board1_data, board2_data, board3_data, board4_data]
        # Flo_mean = np.mean(board_data[self.board_ch - 1][24])
        # Laser_mean = np.mean(board_data[self.board_ch - 1][25])
        # print('Flo_mean = ', Flo_mean, 'Laser_mean', Laser_mean)
        # plt.plot(range(len(board_data[self.board_ch - 1][24])), board_data[self.board_ch - 1][24])
        # plt.plot(range(len(board_data[self.board_ch - 1][24])), board_data[self.board_ch - 1][25])
        # plt.show()
        PID_ch_num = 5  # 激光PID通道为5
        set_point = 0.16  # 需先测量得到荧光信号的DC值后确定
        output_offset = 0.57  # 将激光稳定在0.6 A
        # 探头3的PID参数：
        kp = -0.015
        ki = -0.009

        kd = -0.0000
        kt = 1.0000000
        # 探头4的PID参数：

        # kp = -0.000
        # ki = -0.000
        #
        # kd = -0.0000
        # kt = 1.0000000
        Cal_ex = 0
        RD_ex = 0
        PID_LIA_CH = 0
        PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
        self.LIA_config.pid_config(self.board_num, PID_ch_num, PID_coe)
        print('PID coe download')
        self.LIA_config.pid_enable(self.board_num, PID_ch_num)
        print('PID enable')
        time.sleep(4)
        board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num, CW_mode=True)
        board_data = [board1_data, board2_data, board3_data, board4_data]
        # self.LIA_config.iir_plot()
        Flo_r_mean = np.mean(board_data[self.board_ch - 1][0])
        Flo_y_mean = np.mean(board_data[self.board_ch - 1][1])
        Flo_x_mean = np.mean(board_data[self.board_ch - 1][2])
        Laser_r_mean = np.mean(board_data[self.board_ch - 1][3])
        Laser_y_mean = np.mean(board_data[self.board_ch - 1][4])
        Laser_x_mean = np.mean(board_data[self.board_ch - 1][5])
        t = np.array(range(self.iir_data_num)) / iir_sample_rate
        path_ = datapath + '_data.csv'
        #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_, {'time': t, 'Laser_y': board_data[self.board_ch - 1][1]})
        self.CS_Control(0.0)
        plt.plot(t, board_data[self.board_ch - 1][1], label='Flo_r')
        path_1 = datapath + 'CW_data.png'
        plt.xlabel('MW_fre/Hz')
        plt.ylabel('Amp/1')
        plt.legend()
        plt.savefig(path_1)

        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        self.CS_Control(0.0)

    def DC_calibration(self):
        self.LIA_config.ALL_stop(self.board_num)
        self.LIA_config.tc(0.1)
        Modu_fre = 2.33 * 1e3
        self.LIA_config.Modu_fre_config(1, Modu_fre)
        self.LIA_config.De_fre_config(1, Modu_fre)
        Laser_power = np.array(range(0, 14, 1)) / 10.0

        Laser_mean = []
        FLo_mean = []

        for i in Laser_power:
            self.CS_Control(i)
            print(i)
            iir_sample_rate = 80  # Hz
            self.LIA_config.sample_rate_config(iir_sample_rate)
            self.LIA_config.ALL_stop(self.board_num)
            self.LIA_config.DAC_play(self.board_num)
            self.LIA_config.ALL_start(self.board_num)
            self.iir_data_num = 80

            board1_data, board2_data, board3_data, board4_data = self.LIA_config.iir_play(self.board_num, self.iir_data_num)
            # self.LIA_config.iir_plot()
            if self.board_num == 3:
                Laser_mean.append(np.mean(board1_data[24]))
                FLo_mean.append(np.mean(board1_data[25]))
            elif self.board_num == 5:
                Laser_mean.append(np.mean(board2_data[24]))
                FLo_mean.append(np.mean(board2_data[25]))
            elif self.board_num == 6:
                Laser_mean.append(np.mean(board3_data[24]))
                FLo_mean.append(np.mean(board2_data[25]))
            elif self.board_num == 7:
                Laser_mean.append(np.mean(board4_data[24]))
                FLo_mean.append(np.mean(board2_data[25]))
        path_ = 'data/' + str(time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())) + 'Laser_DC_data.csv'
        #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
        csv_save(path_, {'Laser_power': Laser_power, 'Laser_mean': Laser_mean, 'Flo_mean': FLo_mean})
        self.CS_Control(0.0)
        plt.plot(Laser_power, Laser_mean, label='Fluo')
        plt.plot(Laser_power, FLo_mean, label='Laser')
        plt.xlabel('Laser/A')
        plt.ylabel('Current/1')
        plt.legend()
        plt.show()

    def All_board_Mag_PID_Control(self, axes_list=[8,5,3,2], sample_point=500):
        # 调用前需保证board_num=255
        self.LIA_config.pid_disable(self.board_num, 5)
        self.LIA_config.ALL_stop(self.board_num)
        time.sleep(1)
        # 分别设置tc，每个通道的调制解调
        # tc = 0.1
        self.LIA_config.tc(0.2)
        board_list = [3, 5, 6, 7]
        for board_ch in range(4):
            ch_num = 1
            for axes_ch in axes_list:
                if axes_ch == 2 or axes_ch == 7:
                    modu_Fre = ini_rd('CW', 'modu_fre_ch2')
                elif axes_ch == 3 or axes_ch == 6:
                    modu_Fre = ini_rd('CW', 'modu_fre_ch3')
                elif axes_ch == 4 or axes_ch == 5:
                    modu_Fre = ini_rd('CW', 'modu_fre_ch4')
                else:
                    modu_Fre = ini_rd('CW', 'modu_fre_ch1')
                demodu_phase = ini_rd('CW', 'board_ch' + str(board_ch + 1) + '_axes' + str(axes_ch) + '_demoduphase')
                self.LIA_config.Modu_fre_config(ch_num, float(modu_Fre))
                self.LIA_config.De_fre_config(ch_num, float(modu_Fre))
                De_phase = float(demodu_phase) / (np.pi) * 180 # °
                self.LIA_config.De_phase_config(ch_num * 2 - 1, De_phase)
                ch_num += 1
            iir_sample_rate = 50  # Hz
            self.LIA_config.sample_rate_config(iir_sample_rate)
            self.board_num = board_list[board_ch]
            self.LIA_config.ALL_stop(self.board_num)
            self.LIA_config.DAC_play(self.board_num)
            self.LIA_config.ALL_start(self.board_num)
            attu = 13
            modu = 18
            # modu = 0
            MW_para = [[2979000000.0, modu, attu], [2909000000.0, modu, attu], [2809000000.0, modu, attu], [2784000000.0, modu, attu]]
            self.LIA_config.MW1_SPI_ctrl(self.board_num, MW_para)

        # 文件保存目录
        ospath = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        os.makedirs('data/' + ospath)
        datapath = 'data/' + ospath + '/'

        time.sleep(5)

        center = []
        for board_ch in range(4):
            for i in range(4):
                # PID_ch_num = 1  # 磁测量PID通道为1
                set_point = 0  # 将输出稳定在过零点
                axes_center = ini_rd('CW', 'board_ch' + str(board_ch + 1) + '_axes' + str(axes_list[i]) + '_center')
                center.append(float(axes_center))
                output_offset = (center[-1] + 30000 - 2600000000) * 524288
                kp = float(ini_rd('Mag_PID', 'board_ch' + str(board_ch + 1) + '_axes' + str(axes_list[i]) + '_kp'))
                ki = float(ini_rd('Mag_PID', 'board_ch' + str(board_ch + 1) + '_axes' + str(axes_list[i]) + '_ki'))
                kd = float(ini_rd('Mag_PID', 'board_ch' + str(board_ch + 1) + '_axes' + str(axes_list[i]) + '_kd'))
                kt = float(ini_rd('Mag_PID', 'board_ch' + str(board_ch + 1) + '_axes' + str(axes_list[i]) + '_kt'))
                Cal_ex = 312499
                RD_ex = 0
                PID_LIA_CH = 1

                PID_coe = [set_point, output_offset, kp, ki, kd, kt, RD_ex, Cal_ex, PID_LIA_CH]
                print('PID_coe : ', PID_coe)
                self.board_num = board_list[board_ch]
                self.LIA_config.pid_config(self.board_num, i+1, PID_coe)
                self.LIA_config.pid_enable(self.board_num, i+1)
        # time.sleep(1)
        print('PID coe download')
        board_data = self.LIA_config.AcquireStartV3_MagPID(255, 4, sample_point)  #self.board_num:3 5 6 7 self.board_ch:1 2 3 4
        # print(board_data)
        for board_ch in range(4):
            ch1_iir_data_r = board_data[board_ch][0]
            ch1_iir_data_y = board_data[board_ch][1]
            ch1_iir_data_x = board_data[board_ch][2]
            ch1_error_buf = board_data[board_ch][3]
            ch1_feedback_buf = board_data[board_ch][4]

            ch2_iir_data_r = board_data[board_ch][5]
            ch2_iir_data_y = board_data[board_ch][6]
            ch2_iir_data_x = board_data[board_ch][7]
            ch2_error_buf = board_data[board_ch][8]
            ch2_feedback_buf = board_data[board_ch][9]
            print('ch2_feedback = ', board_data[board_ch][9])

            ch3_iir_data_r = board_data[board_ch][10]
            ch3_iir_data_y = board_data[board_ch][11]
            ch3_iir_data_x = board_data[board_ch][12]
            ch3_error_buf = board_data[board_ch][13]
            ch3_feedback_buf = board_data[board_ch][14]

            ch4_iir_data_r = board_data[board_ch][15]
            ch4_iir_data_y = board_data[board_ch][16]
            ch4_iir_data_x = board_data[board_ch][17]
            ch4_error_buf = board_data[board_ch][18]
            ch4_feedback_buf = board_data[board_ch][19]
            print(center)
            # print(ch1_feedback_buf)
            # print(ch2_feedback_buf)
            # print(ch3_feedback_buf)
            # print(ch4_feedback_buf)
            path_ = datapath + 'board_ch' + str(board_ch + 1) + 'magPID_data.csv'
            #     csv_save(path_, {'time': time1, 'Board4_Ch1_Fre1_r': board4_data[0], 'Board4_Ch1_Fre1_y': board4_data[1], 'Board4_Ch1_Fre1_x': board4_data[2], 'Board4_Ch2_Fre1_r': board4_data[3], 'Board4_Ch2_Fre1_y': board4_data[4], 'Board4_Ch2_Fre1_x': board4_data[5]})
            csv_save(path_, {'Time': np.array(range(len(ch1_iir_data_y))) / 80.0,
                             'ch1_iir_data_r': ch1_iir_data_r, 'ch1_iir_data_x': ch1_iir_data_x, 'ch1_iir_data_y': ch1_iir_data_y, 'ch1_error_buf': ch1_error_buf, 'ch1_feedback_buf': ch1_feedback_buf,
                             'ch2_iir_data_r': ch2_iir_data_r, 'ch2_iir_data_x': ch2_iir_data_x, 'ch2_iir_data_y': ch2_iir_data_y, 'ch2_error_buf': ch2_error_buf, 'ch2_feedback_buf': ch2_feedback_buf,
                             'ch3_iir_data_r': ch3_iir_data_r, 'ch3_iir_data_x': ch3_iir_data_x, 'ch3_iir_data_y': ch3_iir_data_y, 'ch3_error_buf': ch3_error_buf, 'ch3_feedback_buf': ch3_feedback_buf,
                             'ch4_iir_data_r': ch4_iir_data_r, 'ch4_iir_data_x': ch4_iir_data_x, 'ch4_iir_data_y': ch4_iir_data_y, 'ch4_error_buf': ch4_error_buf, 'ch4_feedback_buf': ch4_feedback_buf,
                             })

            plt.figure(1)
            ax1 = plt.subplot(211)
            ax1.plot(np.array(range(len(ch3_iir_data_y))) / 80.0, ch1_error_buf, label='error_buf')
            ax2 = plt.subplot(212)
            ax2.plot(np.array(range(len(ch2_iir_data_y))) / 80.0, ch1_feedback_buf, label='feedback_buf')
            # ax3 = plt.subplot(313)
            # ax3.plot(np.array(range(len(ch2_iir_data_y))) / 80.0, ch1_iir_data_y, label='iir_data_y')
            path_1 = datapath + 'board_ch' + str(board_ch + 1) + 'magPID_data.png'
            plt.xlabel('MW_fre/Hz')
            plt.ylabel('Amp/1')
            plt.legend()
            plt.savefig(path_1)
            plt.show()
            plt.clf()
        board_num = [3,5,6,7]
        for i in board_num:
            self.LIA_config.pid_disable(i, 1)
            self.LIA_config.pid_disable(i, 2)
            self.LIA_config.pid_disable(i, 3)
            self.LIA_config.pid_disable(i, 4)

            # print('PID play')
            self.LIA_config.pid_disable(i, 5)
            # self.CS_Control(0.0)
            self.LIA_config.pid_disable(i, 1)
            self.LIA_config.ALL_stop(i)


def phase_correction_XY(Xch, Ych, data_flag=0):
    """
    For Lock-in based CW spectra.
    :param Xch:
    :param Ych:
    :param data_flag:
    :return:
    """
    xx = np.array(Xch)
    yy = np.array(Ych)
    # find peak
    ind = yy.argmin()
    # calculate phase
    phase = np.arctan(yy[ind] / xx[ind])
    # rotation
    xp = np.array(xx) * np.cos(phase) + np.array(yy) * np.sin(phase)
    yp = np.array(yy) * np.cos(phase) - np.array(xx) * np.sin(phase)
    if data_flag == 0:
        return xp, yp
    elif data_flag == 1:
        # in radius
        return phase

def cal_max_slope(x, y, cal_pnum=5):
    """
    Calculate the max slope of spectra.
    :param x:
    :param y:
    :param cal_pnum: fitting number of points.
    :return:
    """
    x = np.array(x)
    y = np.array(y)
    cal_pnum = int(cal_pnum)
    slope_result = []
    for i in range(len(x) - cal_pnum):
        # for i in range(sp + 1, ep + 1):
        slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(x[i:i + cal_pnum],
                                                                             y[i:i + cal_pnum])
        # print(x[i:i + cal_pnum],y[i:i + cal_pnum])
        slope_result.append(slope)
    slope_result = np.array(slope_result)
    # slope_result = abs(slope_result)
    max_ind = np.argmax(np.abs(slope_result))
    ind2 = int(max_ind + cal_pnum / 2)

    return slope_result[int(max_ind)], ind2, x[ind2], y[ind2]

def ExpSweepCW(board_num,FRQ1_LOW,FRQ1_HIGH,STEP):

    TENSOR_MASTER_API = API_Multichannel()
    TENSOR_MASTER_API.USB_START()
    Modu_fre = 11371
    # Modu_fre = 1
    De_phase=-25
    TENSOR_MASTER_API.switch_set(0)
    TENSOR_MASTER_API.speed_set(500000)
    TENSOR_MASTER_API.laser_SPI_ctrl(1,0.6)
    TENSOR_MASTER_API.SetLockInFreq(Modu_fre, -1)
    TENSOR_MASTER_API.SetLockInPhase( De_phase, -1)
    # TENSOR_MASTER_API.Modu_fre_config(1, Modu_fre)
    # TENSOR_MASTER_API.De_fre_config(1, Modu_fre)
    # # De_phase = 0.385851802342492 / (np.pi) * 180  # °/

    # TENSOR_MASTER_API.De_phase_config(1, De_phase)
    #
    # TENSOR_MASTER_API.Modu_fre_config(2, Modu_fre)
    # TENSOR_MASTER_API.De_fre_config(2, Modu_fre)
    # # De_phase = 0.385851802342492 / (np.pi) * 180  # °
    # TENSOR_MASTER_API.De_phase_config(2, De_phase)
    #
    # TENSOR_MASTER_API.Modu_fre_config(3, Modu_fre)
    # TENSOR_MASTER_API.De_fre_config(3, Modu_fre)
    # # De_phase = 0.385851802342492 / (np.pi) * 180  # °
    # TENSOR_MASTER_API.De_phase_config(3, De_phase)
    #
    # TENSOR_MASTER_API.Modu_fre_config(4, Modu_fre)
    # TENSOR_MASTER_API.De_fre_config(4, Modu_fre)
    # # De_phase = 0.385851802342492 / (np.pi) * 180  # °
    # TENSOR_MASTER_API.De_phase_config(4, De_phase)

    TENSOR_MASTER_API.SetLockInTimeConst(0.1)  # RC滤波器的时间常数
    # TENSOR_MASTER_API.tc(0.1)

    iir_sample_rate = 50  # Hz
    # TENSOR_MASTER_API.SetDataSampleRate(iir_sample_rate)
    TENSOR_MASTER_API.sample_rate_config(iir_sample_rate)

    print("DAQ start")
    TENSOR_MASTER_API.DAC_play(board_num) #brd_num
    TENSOR_MASTER_API.ALL_start(board_num)
    print("DAQ end")
    fs = []
    data_x = []
    data_y = []
    noise = []
    print("2499")
    TENSOR_MASTER_API.set_freq(1, 2800000000)
    TENSOR_MASTER_API.set_power(1,10)
    TENSOR_MASTER_API.set_fm_sens(1,0.15)
    for freq in range(FRQ1_LOW, FRQ1_HIGH, STEP):
        attu = 10
        modu = 15
        # MW_para = [[2979000000.0, modu, attu], [2909000000.0, modu, attu], [2809000000.0, modu, attu],
        #            [2784000000.0, modu, attu]]
        # MW_para = [[freq, modu, attu], [2909000000.0, modu, attu], [2809000000.0, modu, attu],
        #            [2784000000.0, modu, attu]]
        # TODO: 微波频率具体如何配置 ???
        ch1_Fre = int((freq - 2600000000) * 0.5)
        ch2_Fre = int((3090000000 - 2600000000) * 0.5)
        # TENSOR_MASTER_API.SYS_config.MW_SPI_Ctrl(board_num, ch1_Fre, modu, attu, ch1_Fre, modu, attu, ch1_Fre, modu, attu,ch1_Fre, modu, attu)
        # print("Freqs:",ch1_Fre, modu, attu, ch2_Fre, 0, 30)

        # TENSOR_MASTER_API.SYS_config.MW_SPI_Ctrl(board_num, ch1_Fre, modu, attu, ch2_Fre, 0, 30)
        # time.sleep(0.1)
        # TENSOR_MASTER_API.SYS_config.MW_SPI_Ctrl(board_num, ch1_Fre, modu, attu, ch2_Fre, 0, 30)
        # time.sleep(0.1)
        TENSOR_MASTER_API.set_freq(board_num,freq)
        # iir_data = TENSOR_MASTER_API.iir_play(board_num, 5)
        # print("IIR_data:",iir_data)
        # for  i in iir_data:
        #     print(i)
        # res = [np.mean(iir_data[board_num-1][i][:12]) for i in range(len(iir_data))]
        res = TENSOR_MASTER_API.GetlockinChannels(board_num, 5)
        # noise.append(np.std(iir_data[board_num - 1][1]))
        fs.append(freq)
        data_x.append(res[1])
        data_y.append(res[2])
        # print(f"Freq:{freq}  X:{res[1]}  Y:{res[2]} {res}   NOISE:{np.std(iir_data[board_num - 1][1])}")
        # TENSOR_MASTER_API.iir_plot()

    print("noise",noise)
    xp, yp = phase_correction_XY(data_x, data_y)  # 调相位，把信号调到X路上
    # max_slope, max_ind, xm, ym = cal_max_slope(fs, xp, cal_pnum=3)

    # use 5 points to calculate the slop
    max_slope, max_ind, xm, ym = cal_max_slope(fs, xp, cal_pnum=10)  # 计算最大斜率Ks，没有线性回归函数
    vpp = max(data_x) - min(data_x)
    amp = max(data_x)
    # 获取最大幅度频率点
    data_r = np.sqrt(np.array(data_x) ** 2 + np.array(data_y) ** 2)  # 计算各频率点的幅度
    max_amp_id = np.argmax(data_r)  # 最大幅度点位置
    max_amp = data_r[max_amp_id]  # 找到最幅度点 data_x data_y
    max_amp_freq = fs[max_amp_id]  # 最大幅度点频率
    print(('最大斜率:%0.3E, 对应频率：%0.3f， 峰峰值：%0.3f， 幅值：%0.6f' % (max_slope, xm, vpp, amp)))

    plt.figure()
    plt.plot(fs, data_x, label='x', marker='o')  # marker='o' 用于在数据点上添加圆圈标记
    plt.plot(fs, data_y, label='y', marker='x')  # marker='x' 用于在数据点上添加叉形标记
    plt.title('ExpSweepCW')
    plt.xlabel('Freq (Hz)')
    plt.ylabel('Signal')
    plt.legend()
    plt.show()

    TENSOR_MASTER_API.ALL_stop(board_num)
    TENSOR_MASTER_API.USB_END()

# if __name__ == 'main':
# ExpSweepCW(1,275000000,300000000,200000)
# # # ExpSweepCW(2,2600000000,3000000000,4000000)
# exit()