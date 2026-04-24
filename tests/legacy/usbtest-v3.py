import ctypes
from ctypes import c_int, c_uint8, c_uint16, c_void_p, POINTER, Structure, byref
import platform

# ===========================
# 定义 libusb 结构体与常量
# ===========================

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

LIBUSB_SUCCESS = 0

# ===========================
# 加载 DLL 并设置返回类型
# ===========================

libusb = ctypes.CDLL("interface/Lockin/usblib/module_64/libusb-1.0.dll")

libusb.libusb_init.argtypes = [POINTER(c_void_p)]
libusb.libusb_get_device_list.argtypes = [c_void_p, POINTER(POINTER(c_void_p))]
libusb.libusb_get_device_list.restype = ctypes.c_ssize_t
libusb.libusb_get_device_descriptor.argtypes = [c_void_p, POINTER(libusb_device_descriptor)]
libusb.libusb_exit.argtypes = [c_void_p]
libusb.libusb_free_device_list.argtypes = [POINTER(c_void_p), c_int]

# ===========================
# 主程序：查找设备
# ===========================

def find_usb_device(target_vid, target_pid):
    ctx = c_void_p()
    if libusb.libusb_init(byref(ctx)) != LIBUSB_SUCCESS:
        print("Failed to init libusb")
        return False

    devices = POINTER(c_void_p)()
    count = libusb.libusb_get_device_list(ctx, byref(devices))

    if count < 0:
        print("Failed to get device list")
        libusb.libusb_exit(ctx)
        return False

    found = False
    for i in range(count):
        dev = devices[i]
        desc = libusb_device_descriptor()
        ret = libusb.libusb_get_device_descriptor(dev, byref(desc))
        if ret != LIBUSB_SUCCESS:
            continue
        if desc.idVendor == target_vid and desc.idProduct == target_pid:
            print(f"✅ Found device: VID=0x{desc.idVendor:04X}, PID=0x{desc.idProduct:04X}")
            found = True
            break

    libusb.libusb_free_device_list(devices, 1)
    libusb.libusb_exit(ctx)

    if not found:
        print("❌ Device not found.")
    return found

# ===========================
# 测试用例：替换VID/PID
# ===========================

if __name__ == "__main__":
    # 示例：Cypress FX2 USB 芯片
    VID = 0x04B4
    PID = 0x00F1
    find_usb_device(VID, PID)
