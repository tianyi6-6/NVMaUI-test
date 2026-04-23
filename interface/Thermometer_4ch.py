import ctypes
import time
from PySide6.QtCore import QObject, Signal
import platform

class Thermometer_4CH:
    def __init__(self, libusb_path: str, vendor_id=0x13a5, product_id=0x4321):
        # 根据系统平台加载 libusb
        system = platform.system()
        if system == 'Windows':
            libusb_path = libusb_path.replace('.so', '.dll')
        else:
            libusb_path = libusb_path.replace('.dll', '.so')
        self.libusb = ctypes.CDLL(libusb_path)
        self._init_libusb_api()

        self.vendor_id = vendor_id
        self.product_id = product_id
        self.ctx = ctypes.c_void_p()
        self.dev_handle = None

        self._init_device()

    def _init_libusb_api(self):
        self.libusb.libusb_init.restype = ctypes.c_int
        self.libusb.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]

        self.libusb.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p
        self.libusb.libusb_open_device_with_vid_pid.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

        self.libusb.libusb_claim_interface.restype = ctypes.c_int
        self.libusb.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]

        self.libusb.libusb_bulk_transfer.restype = ctypes.c_int
        self.libusb.libusb_bulk_transfer.argtypes = [
            ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_uint
        ]

        self.libusb.libusb_release_interface.restype = ctypes.c_int
        self.libusb.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]

        self.libusb.libusb_exit.restype = None
        self.libusb.libusb_exit.argtypes = [ctypes.c_void_p]

    def _init_device(self):
        if self.libusb.libusb_init(ctypes.byref(self.ctx)) < 0:
            raise RuntimeError("Failed to initialize libusb")
        self.dev_handle = self.libusb.libusb_open_device_with_vid_pid(self.ctx, self.vendor_id, self.product_id)
        if platform.system() == 'Linux':
            self.libusb.libusb_detach_kernel_driver(self.dev_handle, 0)

        if not self.dev_handle:
            self.libusb.libusb_exit(self.ctx)
            raise RuntimeError("Temp device not found!")

        if self.libusb.libusb_claim_interface(self.dev_handle, 0) != 0:
            self.libusb.libusb_exit(self.ctx)
            raise RuntimeError("Cannot claim interface")

    def read_temperatures(self):
        BUFFER_SIZE = 40
        ENDPOINT_IN = 0x81
        TIMEOUT_MS = 1000

        buf = (ctypes.c_ubyte * BUFFER_SIZE)()
        transferred = ctypes.c_int()
        attempts = 0

        while attempts < 10:
            r = self.libusb.libusb_bulk_transfer(
                self.dev_handle, ENDPOINT_IN,
                buf, BUFFER_SIZE,
                ctypes.byref(transferred),
                TIMEOUT_MS
            )
            if r == 0 and transferred.value >= 10:
                data = list(buf)[:transferred.value]
                raw0 = data[2]*256 + data[3]
                if raw0 != 0x7FFF:
                    if raw0 == 850 and attempts < 3:
                        attempts += 1
                        continue
                    v1 = raw0 / 10
                    v2 = (data[4]*256 + data[5]) / 10
                    v3 = (data[6]*256 + data[7]) / 10
                    v4 = (data[8]*256 + data[9]) / 10
                    timestamp = time.time()
                    return [v1, v2, v3, v4], timestamp
            else:
                time.sleep(0.2)
                attempts += 1

        raise RuntimeError("Failed to read valid temperature data after multiple attempts.")

    def close(self):
        if self.dev_handle:
            self.libusb.libusb_release_interface(self.dev_handle, 0)
        # if self.ctx:
        #     self.libusb.libusb_exit(self.ctx)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

class Thermometer_4CH_Backend(QObject):
    new_data = Signal(list, object)  # [v1, v2, v3, v4], timestamp

    def __init__(self, libusb_path):
        super().__init__()
        self.libusb_path = libusb_path
        self.device = None

    def connect_thermometer(self):
        try:
            self.device = Thermometer_4CH(self.libusb_path)
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def disconnect_thermometer(self):
        if self.device:
            self.device.close()
            self.device = None

    def read(self):
        if self.device:
            try:
                temps, ts = self.device.read_temperatures()
                # print(temps)
                # print(ts)
                self.new_data.emit(temps, ts)
            except Exception as e:
                print(f"Read error: {e}")


if __name__ == '__main__':
    LIBUSB_PATH = "D:/Software Learning/NVMagUI/interface/Lockin/usblib/module_64/libusb-1.0.so"
    thermo = Thermometer_4CH(libusb_path=LIBUSB_PATH)
    temps, ts = thermo.read_temperatures()
    print(f"Time: {ts}, Temperatures: {temps}")