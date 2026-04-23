# coding=UTF-8
#!/usr/bin/env python
import ctypes
import os
import platform
import sys
from typing import Union


class USBController:
    """
    USB 控制器封装类，用于加载动态链接库并提供 USB 读写接口。
    """

    def __init__(self, lib_dir: str = None):
        """
        初始化 USBController，并加载对应平台的动态链接库。

        :param lib_dir: 动态链接库所在目录，默认为当前脚本所在目录下的 module_64 子目录。
        :raises FileNotFoundError: 如果未找到动态库文件
        """
        if lib_dir is None:
            dirname = os.path.dirname(os.path.abspath(__file__))
            lib_dir = os.path.join(dirname, 'module_64')

        if sys.platform.startswith('linux'):
            lib_path = os.path.join(lib_dir, 'libUSBAPI.so')
        else:
            lib_path = os.path.join(lib_dir, 'USBAPI_x64')

        if not os.path.exists(lib_path):
            raise FileNotFoundError(f"DLL/so 文件未找到：{lib_path}")

        self.dll = ctypes.CDLL(lib_path)
        self._prepare_functions()

    def _prepare_functions(self):
        """设置部分函数的参数类型和返回类型"""
        self.dll.Read.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
        self.dll.Read.restype = ctypes.c_int

    def init(self) -> int:
        """
        初始化 libusb。
        :return: 返回 0 表示成功，其他值为错误码。
        """
        return self.dll.InitLibusb()

    def deinit(self) -> int:
        """
        反初始化 libusb。

        :return: 固定返回 0
        """
        self.dll.DinitLibusb()
        return 0

    def connect(self, vid: int, pid: int) -> int:
        """
        连接 USB 设备。

        :param vid: 设备的 Vendor ID
        :param pid: 设备的 Product ID
        :return: 返回 1 表示成功，其他值表示失败
        """
        return self.dll.Connect(vid, pid)

    def disconnect(self) -> int:
        """
        断开设备连接。

        :return: 返回 1 表示成功，其他值表示失败
        """
        return self.dll.DisConnect()

    def write(self, data: Union[str, bytes]) -> int:
        """
        向设备写入数据。

        :param data: 待发送的数据，可以是字符串或字节流
        :return: 返回 0 表示成功，其他值表示失败
        """
        if isinstance(data, str):
            data = data.encode('utf-8')

        buf = ctypes.create_string_buffer(data)
        length = ctypes.c_uint(len(data))
        return self.dll.Write(buf, length)

    def read(self, buffer_size: int = 8196) -> dict:
        """
        从设备读取数据。

        :param buffer_size: 缓冲区大小，默认 8196 字节
        :return: 包含读取结果和数据的字典，如 {"result": 8, "data": b'\x01\x02...'}；如果失败，result < 0
        """
        buffer = (ctypes.c_ubyte * buffer_size)()
        result = self.dll.Read(buffer, buffer_size)
        data = bytes(buffer[:result]) if result >= 0 else b""
        return {"result": result, "data": data}

__all__ = [
    "InitLibusb",
    "DinitLibusb",
    "Connect",
    "DisConnect",
    "Write",
    "Read",
]


#全局变量so句柄
dirname,filename = os.path.split(os.path.abspath(__file__))

# arch = platform.architecture()[0]
# if arch == "64bit":
path = None
if sys.platform.startswith('linux'):
    path = os.path.join(dirname, R'module_64/libUSBAPI.so')
    path = path.replace('\\', '/')
else:
    path = os.path.join(dirname, R'module_64/USBAPI_x64')
    path = path.replace('\\', '/')
if not os.path.exists(path):
    raise FileNotFoundError(f"DLL/so 文件未找到：{path}")
dll_obj = ctypes.CDLL(path)


# ************************************
#  Method:    InitLibusb libusb初始化
#  Returns:   result 执行结果，成功为0
#  Mark:      执行SDK其它功能前必须先进行此操作
# ***********************************
def InitLibusb()-> int:
    result = dll_obj.InitLibusb()
    print("Init_res:",result)
    return result

# ************************************
#  Method:    DinitLibusb libusb反初始化
#  Returns:   result 执行结果，成功为0
#  Mark:      执行SDK其它功能前必须先进行此操作
# ***********************************
def DinitLibusb()-> int:
    dll_obj.DinitLibusb()
    return 0


# ************************************
#  Method:    Connect 连接设备
#  Returns:   result 执行结果，成功为1，其他失败
#  Parameter: vid,pid:与设备USB信息相对应
#  Mark:      连接设备后，SDK将主动同步设备数据，需做1-2s左右延时操作
# ***********************************
def Connect(vid:int,pid:int) -> int:
    result = dll_obj.Connect(vid,pid)
    print("Connect_Res:",result)
    return result


# ************************************
#  Method:    DisConnect 断开连接
#  Returns:   result 执行结果，成功为1，其他失败
#  Parameter: str_device_name 由ASG_GetDevicesList函数获取的设备编号
# ***********************************
def DisConnect() -> int:
    result = dll_obj.DisConnect()
    return result


# ************************************
#  Method:    Write 写数据
#  Returns:   result 执行结果，成功为0
#  Parameter: send_buffer 发送的数据；len发送的数据长度
# ***********************************
def Write(send_buffer,len:ctypes.c_uint)->int:
    p_sendBuffer = ctypes.c_char_p(send_buffer)
    result = dll_obj.Write(p_sendBuffer,len)
    return result

# ************************************
#  Method:    Read 读数据
#  Returns:   result dict类型，{result读到的长度，bufferData数据}，result为负数表示异常
def Read()->dict:
    Read = dll_obj.Read
    Read.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
    Read.restype = ctypes.c_int
    recv_buffer_size = 8196  # 适当设置缓冲区大小
    recv_buffer = (ctypes.c_ubyte * recv_buffer_size)()
    result = Read(recv_buffer, recv_buffer_size)
    bufferData = bytes(recv_buffer[:result])
    return {"result":result,"data":bufferData}










