# import datetime
import os
import tkinter as tk
from tkinter import ttk
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import scipy
import numpy as np
from matplotlib.backends._backend_tk import NavigationToolbar2Tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
import queue
import threading
import time
import serial
import serial.tools.list_ports
import struct
from datetime import datetime

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['mathtext.fontset'] = 'cm'
plt.rcParams['axes.unicode_minus'] = False
matplotlib.use("TkAgg")

vref = 12.5  # 参考电压
gain = 1  # 增益

# 定义保存时间戳的文件
TIMESTAMP_FILE = "data/timestamps.txt"

def get_spr(time_data):
    return (len(time_data) - 1) / np.ptp(time_data)

class TimestampRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("时间记录器")

        # 初始化状态
        self.recording = False
        self.start_time = None
        self.middle_times = []  # 用于存储中间点的时间戳

        # 创建按钮
        self.start_stop_button = tk.Button(root, text="开始记录", command=self.toggle_recording)
        self.start_stop_button.pack(pady=20)

        # 创建中间点记录按钮，初始状态为禁用
        self.middle_button = tk.Button(root, text="中间点记录", command=self.record_middle_time, state=tk.DISABLED)
        self.middle_button.pack(pady=20)

    def toggle_recording(self):
        if not self.recording:
            # 开始记录
            self.start_time = datetime.now()
            self.recording = True
            self.start_stop_button.config(text="结束记录")
            self.middle_button.config(state=tk.NORMAL)  # 启用中间点记录按钮
            self.middle_times = []  # 清空之前的中间点记录
            print("开始记录时间:", self.format_timestamp(self.start_time))
        else:
            # 结束记录
            end_time = datetime.now()
            self.recording = False
            self.start_stop_button.config(text="开始记录")
            self.middle_button.config(state=tk.DISABLED)  # 禁用中间点记录按钮
            print("结束记录时间:", self.format_timestamp(end_time))

            # 保存时间戳到文件
            self.save_timestamps(self.start_time, end_time)

    def record_middle_time(self):
        """记录中间点时间"""
        middle_time = datetime.now()
        self.middle_times.append(middle_time)
        print("中间点记录时间:", self.format_timestamp(middle_time))

    def format_timestamp(self, timestamp):
        """格式化时间戳为 YMD-HMS 和 timestamp 两种格式"""
        ymd_hms = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        timestamp_ms = timestamp.timestamp()
        return f"YMD-HMS: {ymd_hms}, Timestamp: {timestamp_ms}"

    def save_timestamps(self, start_time, end_time):
        """保存起始、中间点和结束时间戳到文件"""
        with open(TIMESTAMP_FILE, "a") as file:
            file.write(f"Start: {self.format_timestamp(start_time)}\n")
            for i, middle_time in enumerate(self.middle_times, 1):
                file.write(f"Middle {i}: {self.format_timestamp(middle_time)}\n")
            file.write(f"Stop: {self.format_timestamp(end_time)}\n")
            file.write("-" * 40 + "\n")
        print("时间戳已保存到文件:", TIMESTAMP_FILE)

class RealTimeGraphApp:
    def __init__(self, port, root, data_queue):
        self.port = port
        self.root = root
        self.data_queue = data_queue
        self.data = []
        self.start_collect_time = time.time()

        self.vref = vref
        self.bps = 256000

        self.root.title("AcqCard-"+self.port)
        self.root.geometry("800x600")

        # 配置样式
        style = ttk.Style()
        style.theme_use('clam')  # 使用内置的主题作为基础
        primary_color = "#333333"  # 深灰色，用于按钮等控件
        secondary_color = "#000000"  # 中灰色，用于背景等
        text_color = "#FFFFFF"  # 白色，用于文本，提供足够对比
        background_color = "#F5F5F5"  # 亮灰色，用于整体背景，柔和不刺眼
        # 配置样式表
        style.configure('TFrame', background=background_color)
        style.configure('TButton', font=('Helvetica', 12), background=primary_color, foreground=text_color)
        style.configure('TLabel', background=background_color, font=('Helvetica', 10))
        style.configure('TEntry', foreground=secondary_color, font=('Helvetica', 10))
        # style.configure('TCombobox', foreground=secondary_color, font=('Helvetica', 10))
        # style = ttk.Style()
        style.configure('TCombobox', background='white', fieldbackground='black', foreground='white')
        style.configure('Vertical.TScrollbar', background=primary_color)

        # 配置特定的控件样式
        style.configure('TButton', font=('Arial', 12))
        style.map('TButton', background=[('active', secondary_color)], foreground=[('active', text_color)])
        style.map('TEntry', fieldbackground=[('focus', secondary_color)])
        style.map('TCombobox', fieldbackground=[('focus', secondary_color)])

        gs = GridSpec(2, 1, height_ratios=[2, 1])
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(gs[0])
        self.ax2 = self.fig.add_subplot(gs[1])
        self.ylab = "电压值 (V)"

        self.toolbar_frame = ttk.Frame(root)
        self.toolbar_frame.pack(side=tk.TOP, fill=tk.X)

        self.trim_buttons_frame = ttk.Frame(self.toolbar_frame)
        self.trim_buttons_frame.pack(side=tk.LEFT)

        self.reset_button = ttk.Button(self.toolbar_frame, text="Reset", command=self.reset_data)
        self.reset_button.pack(side=tk.RIGHT)

        for trim_amount in [10, 30, 100, 300, 1000, 3000, 10000]:
            button = ttk.Button(self.trim_buttons_frame, width=7,text=f">{trim_amount}", command=lambda amount=trim_amount: self.trim_data(amount))
            button.pack(side=tk.LEFT)

        # 第二行设置按钮
        self.order_frame = ttk.Frame(root)
        self.order_frame.pack(side=tk.TOP, fill=tk.X)
        self.con_collect_flag = False
        self.collect_button = ttk.Button(self.order_frame, text = "连续采集开始", command=self.con_collect)
        self.collect_button.pack(side=tk.LEFT)
        # 第二行显示模式

        self.single_button = ttk.Button(self.order_frame, text="确定", command=self.set_single)
        self.single_button.pack(side=tk.RIGHT)
        self.single_combobox = ttk.Combobox(self.order_frame, values=[1,10,100,1000,10000,100000, 1000000])
        self.single_combobox.pack(side=tk.RIGHT)
        self.single_combobox.current(0)  # 设置默认选项
        single_label = ttk.Label(self.order_frame, text="单点采集")
        single_label.pack(side=tk.RIGHT)

        self.mode = "电压"
        self.coef = 1
        button = ttk.Button(self.order_frame, text="确定", command=self.set_mode)
        button.pack(side=tk.RIGHT)
        self.mode_combobox = ttk.Combobox(self.order_frame, values=["磁场","电压"])
        self.mode_combobox.pack(side=tk.RIGHT)
        self.mode_combobox.current(1)  # 设置默认选项
        mode_label = ttk.Label(self.order_frame, text="显示模式")
        mode_label.pack(side=tk.RIGHT)

        self.order1_frame = ttk.Frame(root)
        self.order1_frame.pack(side=tk.TOP, fill=tk.X)
        self.bps_button = ttk.Button(self.order1_frame, text="确定", command=self.set_bps)
        self.bps_button.pack(side=tk.RIGHT)
        self.bps_combobox = ttk.Combobox(self.order1_frame, values=[256000,100000]) # 波特率预选值设置
        self.bps_combobox.pack(side=tk.RIGHT)
        self.bps_combobox.current(0)  # 设置默认选项
        bps_label = ttk.Label(self.order1_frame, text="   波特率")
        bps_label.pack(side=tk.RIGHT)

        self.vref_button = ttk.Button(self.order1_frame, text="确定", command=self.set_vref)
        self.vref_button.pack(side=tk.RIGHT)
        self.vref_combobox = ttk.Combobox(self.order1_frame, values=[12.5]) # 参考电压预选值设置
        self.vref_combobox.pack(side=tk.RIGHT)
        self.vref_combobox.current(0)  # 设置默认选项
        vref_label = ttk.Label(self.order1_frame, text="参考电压")
        vref_label.pack(side=tk.RIGHT)

        # 添加切换显示模式的按钮
        self.subtract_mean_flag = False
        self.subtract_mean_button = ttk.Button(self.order1_frame, text="变化量", command=self.toggle_subtract_mean)
        self.subtract_mean_button.pack(side=tk.LEFT)

        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.draw()

        # Moving the toolbar to the top of the canvas
        toolbar = NavigationToolbar2Tk(self.canvas, root)
        toolbar.update()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        self.save_time = time.time()
        if(not os.path.exists("data")):
            os.mkdir("data")
        self.save_path = f"data/{self.port}-{time.strftime('%Y%m%d-%H%M%S', time.localtime())}.csv"
        self.f = open(self.save_path, "a")

        # threading.Thread(target=self.generate_iir_data, daemon=True).start()
        threading.Thread(target=self.generate_noise_data, daemon=True).start()
        # threading.Thread(target=self.update_graph, daemon=True).start()
        # while True:
        #     time.sleep(1)
        # self.update_graph()
        self.update_graph_ser()

    def toggle_subtract_mean(self):
        self.subtract_mean_flag = not self.subtract_mean_flag
        if self.subtract_mean_flag:
            self.subtract_mean_button.config(text="原始数据")
        else:
            self.subtract_mean_button.config(text="变化量")

    def con_collect(self):
        if self.con_collect_flag:
            self.collect_button.config(text="连续采集开始")
            self.con_collect_flag = False
            self.ser.flushInput()
            self.ser.write(b"\xab" + int(format(1, '08x'), 16).to_bytes(4, 'big'))
        else:
            self.start_collect_time = time.time()
            self.collect_button.config(text="连续采集结束")
            self.con_collect_flag = True
            self.ser.flushInput()
            self.ser.write(b"\xab" + int(format(0, '08x'), 16).to_bytes(4, 'big'))

    def set_vref(self):
        vref = self.vref_combobox.get()
        self.vref = float(vref)

    def set_bps(self):
        bps = self.bps_combobox.get()
        print("In set bps:", bps)
        self.bps = int(bps)
        self.ser.close()
        self.ser_connect()

    def set_mode(self):
        mode = self.mode_combobox.get()
        if mode == "磁场":
            self.coef = 1E4
            self.ylab = "磁场值 (nT)"
        else:
            self.coef = 1
            self.ylab = "电压值 (V)"

    def set_single(self):
        points = int(self.single_combobox.get())
        frame_header = "11001100"  # 帧头帧尾校验
        frame_footer = "10001000"
        try:
            if not 0 <= points <= 999999:
                raise ValueError("Number must be between 0 and 999999")
            self.ser.flushInput()
            self.ser.write(b"\xab" + int(format(points, '08x'), 16).to_bytes(4, 'big'))
            # time.sleep(0.05)
            s = self.ser.read(15 * points).hex()
            ss = [s[i:i + 2] for i in range(0, len(s), 2)]
            binary_str = ""
            for bs in ss:
                # 将两个十六进制字符转换为一个字节（整数）
                byte_value = int(bs, 16)
                binary_str += bin(byte_value)[2:].zfill(8)
            for i in range(points):
                data_payload_with_frame = binary_str[i * 120: (i + 1) * 120]
                if (data_payload_with_frame[:8] == frame_header and data_payload_with_frame[-8:] == frame_footer):
                    payload_val = bytes(
                        [int(data_payload_with_frame[i:i + 8], 2) for i in range(0, len(data_payload_with_frame), 8)])
                    checkbyte = data_payload_with_frame[104:112]
                    a1, a2, a3 = data_payload_with_frame[32:40], data_payload_with_frame[
                                                                 64:72], data_payload_with_frame[96:104]
                    res = self.xor_binary_strings(a1, a2, a3)
                    # print(a1, a2, a3,res, checkbyte)
                    if (res == checkbyte):
                        pass
                    else:
                        raise ValueError
                    tmp_l = []
                    for i in range(3):
                        value = struct.unpack('>i', payload_val[4 * i + 1: 4 * (i + 1) + 1])[0]
                        voltage = value * self.vref / (2 ** 31 - 1) / gain  # 转换为电压值
                        tmp_l.append(voltage)
                    self.data_queue.put(tmp_l)
                else:
                    raise ValueError("HeaderFooter ERROR!!!")
        except Exception as e:
            print("In AcqCard_getpoints Error!!!", e)
            return self.set_single()

    def ser_connect(self):
        device_port = self.port
        if(not device_port):
            print("No device!!!")
        try:
            self.ser = serial.Serial(device_port, self.bps, timeout=1)
            self.ser.flushInput()
        except:
            print("Ser Connection Error!")
            time.sleep(1)
            self.ser_connect()

    def xor_binary_strings(self, s1, s2, s3):
        # 确保所有字符串长度相同
        length = max(len(s1), len(s2), len(s3))
        s1 = s1.zfill(length)
        s2 = s2.zfill(length)
        s3 = s3.zfill(length)

        # 将二进制字符串转换为整数
        i1 = int(s1, 2)
        i2 = int(s2, 2)
        i3 = int(s3, 2)

        # 对整数进行异或运算
        result_int = i1 ^ i2 ^ i3

        # 将结果整数转换回二进制字符串，并去除前导零（如果需要）
        result_bin = bin(result_int)[2:].zfill(length)

        return result_bin

    def generate_noise_data(self):
        frame_header = "11001100"  # 帧头帧尾校验
        frame_footer = "10001000"
        buffer = ""
        ser_count = 0
        self.ser_connect()
        while True:
            time.sleep(0.01)
            try:
                recv_data = self.ser.read(1024)
                s = recv_data.hex()
                ss = [s[i:i + 2] for i in range(0, len(s), 2)]
                binary_str = ""
                # print("Recv_d:",ser_count, ss)
                # print(len(ss),len(recv_data),len(s))
                for bs in ss:
                    # 将两个十六进制字符转换为一个字节（整数）
                    byte_value = int(bs, 16)
                    binary_str += bin(byte_value)[2:].zfill(8)

            except:
                print("Connectino Failed, Restart Now!")
                self.ser_connect()
                continue
            buffer += binary_str
            while buffer.find(frame_header) + 1:
                if not buffer.find(frame_footer) + 1:
                    break
                start_idx = buffer.find(frame_header)
                end_idx = buffer.find(frame_footer, start_idx+112, start_idx+120)
                if(start_idx>end_idx):
                    buffer = buffer[1:]
                    continue
                data_payload_with_frame = buffer[start_idx:end_idx + len(frame_footer)]
                # print("BUf:",data_payload_with_frame, len(data_payload_with_frame))
                buffer = buffer[end_idx + len(frame_footer):]  # 在做完帧头尾校验后抛出中间字符然后进入到下一轮读取中
                tmp_l = []
                if (len(data_payload_with_frame) == 120):
                    try:
                        # print(bytes([int(data_payload_with_frame[i:i+8], 2) for i in range(0, len(data_payload_with_frame), 8)]))
                        payload_val = bytes([int(data_payload_with_frame[i:i+8], 2) for i in range(0, len(data_payload_with_frame), 8)])
                        # print(payload_val)
                        checkbyte = data_payload_with_frame[104:112]
                        a1,a2,a3 = data_payload_with_frame[32:40],data_payload_with_frame[64:72],data_payload_with_frame[96:104]
                        res = self.xor_binary_strings(a1,a2,a3)
                        # print(a1, a2, a3,res, checkbyte)
                        if(res == checkbyte):
                            pass
                        else:
                            raise ValueError
                        for i in range(3):
                            value = struct.unpack('>i', payload_val[4 * i+1: 4 * (i + 1)+1])[0]
                            voltage = value * self.vref / (2 ** 31 - 1) / gain  # 转换为电压值
                            if(abs(voltage)>10):
                                raise ValueError
                            tmp_l.append(voltage)

                    except:
                        print("Error data:",data_payload_with_frame)
                    else:
                        ser_count += 1
                        if(not ser_count%1000):
                            print(time.time(), ser_count)
                        # if(not ser_count % 20):
                        # print(ser_count, tmp_l)
                        if(tmp_l):
                            # 2.24新增拉长时间戳
                            if(abs(self.start_collect_time - time.time()) > 2):
                                self.start_collect_time = time.time()
                            else:
                                self.start_collect_time += 0.001
                            if(ser_count>10):  # 过滤程序开始执行时的断点
                                tmp_l.append(self.start_collect_time)
                                self.data_queue.put(tmp_l)
                else:
                    print("Error buffer:",len(data_payload_with_frame),data_payload_with_frame,bytes([int(data_payload_with_frame[i:i+8], 2) for i in range(0, len(data_payload_with_frame), 8)]),start_idx,end_idx)

    def update_graph_ser(self):
        # try:
        # print("In while")
        while not self.data_queue.empty():
            # self.data.append(self.data_queue.get_nowait())
            data_tmp = self.data_queue.get()
            self.data.append(data_tmp)
            if (time.time() - self.save_time > 6000):
                self.save_time = time.time()
                self.f.close()
                self.save_path = f"data/{self.port}-{time.strftime('%Y%m%d-%H%M%S', time.localtime())}.csv"
                self.f = open(self.save_path, "a")
            self.f.write(f"{data_tmp[3]},{self.coef*data_tmp[0]},{self.coef*data_tmp[1]},{self.coef*data_tmp[2]}" + "\n")
            self.f.flush()
            # print("data:",self.data)
        # except queue.Empty:
        #     pass

        self.ax.clear()
        self.ax2.clear()
        ts = [v[3] for v in self.data]
        ts = [datetime.fromtimestamp(s) for s in ts]
        value1 = [v[0] for v in self.data]
        value2 = [v[1] for v in self.data]
        value3 = [v[2] for v in self.data]
        # value1,value2,value3 = zip(*self.data) if self.data else ([], [], [])
        # dt_object = [datetime.datetime.fromtimestamp(timestamp) for timestamp in timestamps]
        value1 = [self.coef * value for value in value1]
        value2 = [self.coef * value for value in value2]
        value3 = [self.coef * value for value in value3]
        # 显示模式分支
        if self.subtract_mean_flag:
            mean1 = np.mean(value1)
            mean2 = np.mean(value2)
            mean3 = np.mean(value3)
            value1 = [v - mean1 for v in value1]
            value2 = [v - mean2 for v in value2]
            value3 = [v - mean3 for v in value3]

        self.ax.plot(ts, value1, color='gray', linewidth=2,label="X")  # Enhanced graph line style
        self.ax.plot(ts, value2, color='b', linewidth=2,label="Y")  # Enhanced graph line style
        self.ax.plot(ts,value3, color='r', linewidth=2,label="Z")  # Enhanced graph line style
        # self.ax.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M%:%S'))
        # self.ax.gcf().autofmt_xdate()
        # self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.ax.tick_params(axis='both', which='major', labelsize=8, length=6, width=1)
        # 添加网格
        self.ax.grid(True, linestyle='--', alpha=0.7)
        self.ax.set_xlabel("Count")
        self.ax.set_ylabel(f"{self.ylab}")
        if(len(ts)>10):
            spr = 1000  # 固定采样率为1000
            # spr = get_spr([v[3] for v in self.data])
            # print("SPR:",spr)
            signal = [value1,value2,value3]
            fft_freqs = np.arange(0, len(ts) + 2) * spr / len(ts)
            fft_data = [np.abs(scipy.fftpack.fft(signal[i]))[:len(fft_freqs) // 2] for i in range(len(signal))]
            fft_freqs = fft_freqs[:len(fft_freqs) // 2]
            labels = ["X","Y","Z"]
            colors = ["gray","b","r"]
            for i in range(len(signal)):
                self.ax2.semilogy(fft_freqs, fft_data[i], color = colors[i],label = labels[i])
        self.ax2.tick_params(axis='both', which='major', labelsize=8, length=6, width=1)
        # 添加网格
        self.ax2.grid(True, linestyle='--', alpha=0.7)
        self.ax2.set_xlabel("Freq (Hz)")
        self.ax2.set_ylabel("Log10 (Ampl)")

        if(len(value1)):
            y_min, y_max = min([min(value1), min(value2),min(value3)]), max([max(value1), max(value2),max(value3)])
            step = (y_max - y_min) / 10  # 假设我们想要大约10个刻度
            # if step < 1:
            #     # 如果步长小于1，我们可以考虑保留更多的小数位
            #     step = round(step, 1)
            self.ax.set_yticks(np.arange(y_min, y_max + step, step))
        self.ax.legend()
        # self.ax2.legend()
        self.canvas.draw()
        self.data = self.data[-2000:]

        self.root.after(200, self.update_graph_ser)

    def trim_data(self, amount):
        self.data = self.data[amount:]

    def reset_data(self):
        self.data = []

def find_CH340_device():
    ports = list(serial.tools.list_ports.comports())
    l = []
    for port in ports:
        # port.description 通常包含设备的名称
        if "CH340" in port.description:
            l.append(port.device)
    return l

if __name__ == "__main__":
    ports = find_CH340_device()
    # ports = ["COM1"]
    print("ports:",ports)
    root = None
    if(ports):
        data_queue = queue.Queue()
        root = tk.Tk()
        app = RealTimeGraphApp(ports[0], root, data_queue)
        for i in range(1,len(ports)):
            data_queue1 = queue.Queue()
            root1 = tk.Toplevel(root)
            app = RealTimeGraphApp(ports[i], root1, data_queue1)
    if(root):
        ts_toplevel = tk.Toplevel(root)
        ts_toplevel.title("时间记录")
        app_ts = TimestampRecorder(ts_toplevel)
        root.mainloop()
