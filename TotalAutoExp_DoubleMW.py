# coding=utf-8

import numpy as np
import copy
import os
import queue
import time
import matplotlib.pyplot as plt
import threading
import codecs
import configparser
from scipy.stats import linregress
import interface.Lockin.usblib as usb

_name_ = '202310版-A版-双微波单轴样机'

SYSTEM_CONFIG = "config/system_config.ini"
config = configparser.ConfigParser()
config.read(SYSTEM_CONFIG)
    
DataPath = config.get('Path', 'local_data_path') + time.strftime('%Y%m%d', time.localtime(time.time())) + '/'
DATAPATH = DataPath
if not os.path.exists(DataPath):
    os.mkdir(DataPath)

def gettimestr():
    import time
    return time.strftime('%Y-%m-%d %H_%M_%S', time.localtime(time.time()))


def write_to_csv(fname, data, header=None, row_to_col=True):
    import csv
    if header is not None:
        for id, col in enumerate(data):
            col.insert(0, header[id])
    with open(fname, 'w', newline='') as csvfile:
        if row_to_col:
            data = np.array(data).transpose()
        csvwriter = csv.writer(csvfile)
        csvwriter.writerows(data)
    return fname
    
def dict_save(dic, fn, *args, **kwargs):
    fhandle = open(fn, 'w')
    keys = dic.keys()
    for key in keys:
        fhandle.write('%s : %s\n' % (key, dic[key]))
    fhandle.close()


def dict_load(fn, *args, **kwargs):
    """加载上方程序中存的数据"""
    dict_res = {}
    # Todo:处理好列表和函数的加载
    lines = open(fn, 'rb').readlines()
    for i in range(len(lines)):
        res = lines[i].split(':')
        if len(res) < 2:
            continue
        # 去除上方key的空格
        key = res[0].strip()
        if '[' in res[1] and ']' in res[1]:
            # 读取list
            data = str_to_list(res[1])
        elif '<' in res[1] and '>' in res[1]:
            # 读取函数
            pass
        else:
            data = float(res[1])
        dict_res[key] = data
    return dict_res
    
def str_to_decimals(s):
    # for debug use
    return list(map(ord, s))


def str_to_hexstr(s, space=True):
    ss = ' '.join(['%02x' % b for b in s])
    return ss


def num_to_bytes_signed(num, bytenum, high_head=True):
    if high_head:
        return np.array([num], dtype='>u8').tobytes()[-bytenum:]
    else:
        return np.array([num], dtype='<u8').tobytes()[:bytenum]


def bytes_to_num(bytes_):
    num = int.from_bytes(bytes_, byteorder='big')
    return num


def num_to_bytes_old0(num, bytenum, high_head=True):
    bytes_ = b''
    while num > 255:
        bytes_ = bytes([int(num % 256)]) + bytes_
        num //= 256
    bytes_ = bytes([int(num % 256)]) + bytes_
    if len(bytes_) < bytenum:
        bytes_ = (bytenum - len(bytes_)) * b'\x00' + bytes_
    else:
        bytes_ = bytes_[len(bytes_) - bytenum:]
    if not high_head:
        bytes__ = ''
        for b in bytes_:
            bytes__ = b + bytes__
        return bytes__
    return bytes_


def num_to_bytes(num, bytenum, high_head=True):
    if high_head:
        # print('num:%d (2^(%.3f)) len:(%d)' % (num, np.log2(float(num)), bytenum))
        return np.array([num], dtype='>u8').tobytes()[-bytenum:]
    else:
        return np.array([num], dtype='<u8').tobytes()[:bytenum]


# LIA相关的参数
DAQ_gain = 1.0
LIA_gain = 0.17
# AUXDAQ_gian = 1.0
auxdaq_gain = 1.0 # DC measurment


class CP2013GM(object):
    def __init__(self, portx, bps=500000):
        self.portx = portx
        self.bps = bps
        # self.ser = serial.Serial(port=self.portx, baudrate=self.bps, bytesize=8, parity='N', stopbits=1, xonxoff=0, rtscts=0)  # Open the serial

    def DWritePort(self, text):
        # print("write!!!!",str_to_hexstr(text))
        result = usb.Write(text, len(text))
        return result

    def DReadPort(self, num):
        numcount = 0
        data_buf = b''
        while numcount < num:
            data_buf += usb.Read().get('data')
            numcount = len(data_buf)
            print(numcount)
        # print(str_to_hexstr(data_buf))
        return data_buf


class API(CP2013GM):
    def __init__(self, portx="COM6", bps=500000):
        CP2013GM.__init__(self, portx=portx, bps=bps)
        # CP2013GM.USB_START(self)
        self.ADC_sample_rate = 25.0 * np.power(10, 6)
        self.IIR_o_sample_rate = 25.0 * np.power(10, 6)  # orig IIR sample rate unit:Sps
        self.daq_sample_rate = 1.0 * 10 ** 3  # output sample rate unit:Sps
        self.De_fre = {'ch1': 1000, 'ch2': 2200, 'ch3': 3500, 'ch4': 4800}
        self.De_phase = {'ch1': 0.0, 'ch2': 0.0, 'ch3': 0.0, 'ch4': 0.0, 'ch5': 0.0, 'ch6': 0.0, 'ch7': 0.0, 'ch8': 0.0}
        self.Modu_fre = {'ch1': 1000, 'ch2': 2200, 'ch3': 3500, 'ch4': 4800}
        self.Modu_phase = {'ch1': 0, 'ch2': 180.0, 'ch3': 90.0, 'ch4': 0.0}
        self.AD_offset = {'ch1': -0.0, 'ch2': -0.0, 'ch3': -0, 'ch4': -0}
        self.DA_offset = {'ch1': 0.0, 'ch2': 0.0}
        self.mw_para = {'ch1_Fre': 2.6e9, 'ch1_fm_sens': 0, 'ch1_atte': 30,
                        'ch2_Fre': 2.6e9, 'ch2_fm_sens': 0, 'ch2_atte': 30,
                        'ch3_Fre': 2.6e9, 'ch3_fm_sens': 0, 'ch3_atte': 30,
                        'ch4_Fre': 2.6e9, 'ch4_fm_sens': 0, 'ch4_atte': 30,
                        }
        self.sample_rate = 1.0 * 10 ** 4
        self.tc = 0.002
        self.raw_data_queue = queue.Queue(maxsize=5000)
        self.data_queue = queue.Queue(maxsize=5000)
        # print('api1 ok')

    def SBZZ(self):
        path_ = 'PLL_WR_REG_OSC.txt'
        f = open(path_, 'r+')
        data = f.read()
        data_buf = data.split(',\n')
        # self.DWritePort(b'\x00\xAe')
        # time.sleep(1)
        # self.DWritePort(b'\x00\xAF')
        # time.sleep(1)
        self.DWritePort(b'\x00\xAC')
        time.sleep(1)
        self.DWritePort(b'\x00\xAD')
        time.sleep(1)
        for i in range(len(data_buf)):
            temp = int(data_buf[i], 16)
            buf = num_to_bytes(temp, 4)
            self.DWritePort(b'\x00\x41')
            self.DWritePort(buf)
            time.sleep(.1)
        time.sleep(5)

    def USB_START(self):
        """
        开启USB设备
        设备识别码：DNVCS-API-TotalField-0001
        API-TotalField
        """
        ret = usb.InitLibusb()
        if 0 != ret:
            print("INIT FAIL ,code:", ret)
        else:
            print("Init ok!")
        time.sleep(3)

        # 连接设备
        ret = usb.Connect(0x04B4, 0x00F1)
        if 0 != ret:
            print("Connect failed ,code:", ret)
        else:
            print("Connect ok!")
        time.sleep(3)

    def USB_END(self):
        """
        断开USB设备
        设备识别码：DNVCS-API-TotalField-0002
        API-TotalField
        """
        # 断开连接
        ret = usb.DisConnect()
        if 0 != ret:
            print("Disconnect failed ,code:", ret)
        else:
            print("Disconnect ok!")
        time.sleep(3)

        # 释放资源
        ret = usb.DinitLibusb()
        if 0 != ret:
            print("DinitLibusb failed ,code:", ret)
        else:
            print("DinitLibusb ok!")

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

        # DDC_para set
        # ([0])freq unit: Hz
        # ([1])phase unit: degree (from pi-->degree)
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
    
    def IIR_calibration(self, modu_freq, acq_time, sample_rate, timeconst):
        save_dir = DATAPATH + 'IIR_calibration/'
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)
            
        # modu_freq = 10371 # Hz
        # timeconst = 0.001 # s
        # sample_rate = spr # Hz
        
        # Set modu/demo frequency
        self.De_fre_config(1, modu_freq)
        self.Modu_fre_config(1, modu_freq)
        self.De_fre_config(2, modu_freq)
        self.Modu_fre_config(2, modu_freq)
        
        # Set const
        self.set_tc(timeconst)
        
        # Set sampling rate
        self.sample_rate_config(sample_rate)
        
        # configuration
        self.all_stop()
        self.play()
        self.all_start()
        
        start_time = time.time()
        IIR_data = self.IIR_play(data_num = int(sample_rate * acq_time))
        stop_time = time.time()
        print('Time consumption=%.2f s, acquisition time=%.2f s' % (stop_time - start_time, acq_time))
        time_data = np.arange(len(IIR_data[0])) / sample_rate
        
        print('[CH1-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[1]), np.mean(IIR_data[1])))
        print('[CH1-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[2]), np.mean(IIR_data[2])))
        print('[CH1-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[7]), np.mean(IIR_data[7])))
        print('[CH1-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[8]), np.mean(IIR_data[8])))
        
        print('[CH2-Freq1-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[4]), np.mean(IIR_data[4])))
        print('[CH2-Freq1-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[5]), np.mean(IIR_data[5])))
        print('[CH2-Freq2-X]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[10]), np.mean(IIR_data[10])))
        print('[CH2-Freq2-Y]  ptp=%.6f V  avg=%.6f V' % (np.ptp(IIR_data[11]), np.mean(IIR_data[11])))
        
        write_to_csv(save_dir + gettimestr() + '_IIR.csv', [time_data] + list(IIR_data))
        
        # plt.plot(x, IIR_data[0], label='Ch1_Fre1_r')
        plt.plot(time_data, IIR_data[1], label='Ch1_Fre1_y')
        plt.plot(time_data, IIR_data[2], label='Ch1_Fre1_x')
        # plt.plot(x, IIR_data[3], label='Ch2_Fre1_r')
        plt.plot(time_data, IIR_data[4], label='Ch2_Fre1_y')
        plt.plot(time_data, IIR_data[5], label='Ch2_Fre1_x')
        plt.xlabel('Time (s)')
        plt.ylabel('Signal (a.u)')
        plt.title('IIR calibration (GAIN=%.3f V)' % (LIA_gain))
        plt.legend()
        plt.tight_layout()
        plt.savefig(save_dir + gettimestr() + '_IIR.png')
        plt.show()
        
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
        print(len(DAQ_data))
        data = [[] for i in range(2)]

        for i in range(data_num):
            data_buf = 0
            for j in range(2):
                data_buf = bytes_to_num(DAQ_data[4 * i + (j % 2) * 2: 4 * i + (j % 2 + 1) * 2])
                print(data_buf)
                if data_buf > 32767:
                    data_buf = (data_buf - 65536) / 65536.0
                else:
                    data_buf = data_buf / 65536.0
                data[j].append(data_buf * DAQ_gain)

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
                if data_buf > 2 ** 23 - 1:
                    data_buf = (data_buf - 2 ** 24) / 2 ** 24
                else:
                    data_buf = data_buf / 2 ** 24
                data[j].append(data_buf * auxdaq_gain)

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
        # print(len(IIR_data))
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
        print("PID_data:", data, len(data))
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
        # print('111')
        self.DWritePort(b'\x00\xb3')
        time.sleep(0.05)
        # print('222')
        self.DWritePort(b'\x00\x00' + num_to_bytes(int(Value / 2.5 * 65536), 2))
        time.sleep(0.05)
        # print('333')
    
    def Auxdaq_Calibration(self, LIA_mini_API):
        save_dir = DATAPATH + 'Auxdaq_Calibration/'
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)
        acq_time = 2 # s
        auxdaq_fs = 250 # Hz
        start_curr = 0.3
        stop_curr = 0.9
        pnum_curr = 7
        curr_list = np.linspace(start_curr, stop_curr, pnum_curr)
        
        daq_data = [[], []]
        for curr in curr_list:
            LIA_mini_API.CS_SPI_Ctrl(curr)
            time.sleep(5)
            data = LIA_mini_API.auxDAQ_play(data_num=acq_time * auxdaq_fs)
            for i in range(2):
                daq_data[i].append(np.mean(data[i]))
            print(f'LD current=%.1f A  CH1=%.6f V CH2=%.6f V' % (curr, daq_data[0][-1], daq_data[1][-1]))
            # LIA_mini_API.auxdaq_plot()
        LIA_mini_API.CS_SPI_Ctrl(0)
        write_to_csv(save_dir + gettimestr() + '_Auxdaq_Calibration.csv', [curr_list] + daq_data)
        plt.plot(curr_list, daq_data[0], label='CH1-Fluorescence')
        plt.scatter(curr_list, daq_data[0])
        plt.plot(curr_list, daq_data[1], label='CH2-Laser')
        plt.scatter(curr_list, daq_data[1])
        plt.legend()
        plt.xlabel('LD current (A)')
        plt.ylabel('DC Signal (a.u)')
        plt.title('DC calibration (Gain=%.3f V)' % (auxdaq_gain))
        plt.tight_layout()
        plt.savefig(save_dir + gettimestr() + '_Auxdaq_Calibration.png')
        plt.show()
        # start_time = time.time()
        # auxDAQ_pnum = 1000
        # LIA_mini_API.auxDAQ_play(data_num=auxDAQ_pnum)
        # stop_time = time.time()
        # print('Time=', stop_time - start_time, 'Sampling Rate=', auxDAQ_pnum / (stop_time - start_time))
        # LIA_mini_API.auxdaq_plot()
    
    def DAQ_Calibration(self):
        save_dir = DATAPATH + 'DAQ_Calibration/'
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)
        extract_ratio = 24 # Sampling rate = 25MHz / (extract_ratio + 1)
        daq_fs = 25e6 / (extract_ratio + 1)
        # daq_data = self.DAQ_play(data_num=int(acq_time * daq_fs), extract_ratio=extract_ratio)
        daq_data = self.DAQ_play(data_num=500, extract_ratio=24)
        time_data = np.arange(len(daq_data[0])) / daq_fs
        write_to_csv(save_dir + gettimestr() + '_daq_data.csv', [time_data] + list(daq_data))
        
        print("CH1 ptp value: %.6f V   avg value: %.6f V" % (np.ptp(daq_data[0]), np.mean(daq_data[0])))
        print("CH2 ptp value: %.6f V   avg value: %.6f V" % (np.ptp(daq_data[1]), np.mean(daq_data[1])))
        # self.daq_plot()
        
        plt.plot(time_data, daq_data[0], label='CH1-Fluorescence')
        # plt.scatter(time_data, daq_data[0])
        plt.plot(time_data, daq_data[1], label='CH2-Laser')
        # plt.scatter(time_data, daq_data[1])
        plt.legend()
        plt.xlabel('Time (s)')
        plt.ylabel('DAQ Signal (a.u)')
        plt.title('DAQ calibration (Gain=%.3f V)' % (DAQ_gain))
        plt.tight_layout()
        plt.savefig(save_dir + gettimestr() + '_Auxdaq_Calibration.png')
        plt.show()
        
        
    # LIA_mini_API.daq_plot()
    # def PID_config(self, PID_ch_num, coe):
    #     """
    #     设置PID参数
    #     设备识别码：DNVCS-PID-TotalField-0001
    #     PID-TotalField
    #     :param PID_ch_num: PID通道 int in [1,2,3,4] 1
    #     :param coe: PID参数。。。 int in [-1,0,1,2,3] 0
    #     """
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
        if ch1_modu > 100 or ch1_modu < 0 or ch2_modu > 100 or ch2_modu < 0:
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
        print(len(DAQ_data))
        data = []

        for i in range(data_num):
            data_buf = bytes_to_num(DAQ_data[2 * i: 2 * i + 2])
            data.append(data_buf)
            if data_buf != data_num - i:
                print('!!!error!!!')
        print(data)

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

    def sample_rate_config(self, Value):
        # LIA_config = {'type': 'sample_rate', 'Value': 10**3}
        LIA_config = {'type': 'sample_rate', 'Value': Value}
        self.play_info(LIA_config)

    def set_tc(self, Value):
        # LIA_config = {'type': 'tc', 'Value': 1.0}
        LIA_config = {'type': 'tc', 'Value': Value}
        self.play_info(LIA_config)

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


def LIA_test():
    # LIA全测试函数
    for i in range(20):
        Modu_fre = 23500 + i * 20
        fpga.Modu_fre_config(1, Modu_fre)
        fpga.De_fre_config(1, Modu_fre)
        fpga.Modu_fre_config(2, Modu_fre)
        fpga.De_fre_config(2, Modu_fre)
        fpga.Modu_fre_config(3, Modu_fre)
        fpga.De_fre_config(3, Modu_fre)
        fpga.Modu_fre_config(4, Modu_fre)
        fpga.De_fre_config(4, Modu_fre)
        De_phase = 0.385851802342492 / (np.pi) * 180  # °
        fpga.De_phase_config(1, De_phase)
        MW_fre = 2700000000

        SNR = []
        attu = []
        iir_sample_rate = 50  # Hz
        fpga.sample_rate_config(iir_sample_rate)
        fpga.DEVICE_check()
        fpga.all_start()
        fpga.play()
        fpga.all_stop()
        eval(input())
    a = time.time()
    DAQ_data = fpga.auxDAQ_play(1000)
    print((time.time() - a))
    fpga.auxdaq_plot(1)
    DAQ_data = fpga.DAQ_play(1000, 10)
    fpga.daq_plot()
    IIR_data = fpga.IIR_play(100)
    # fpga.iir_plot()
    PID_ch_num = 1  # 激光PID通道为5
    set_point = 0.14  # 需先测量得到荧光信号的DC值后确定
    output_offset = int(2.7 * 1e9 - 2.6 * 1e9) * 0.5 * 1048576  # 将激光稳定在0.6 A
    kp = -0.00001
    ki = 0.0
    kd = 0.0
    kt = 1.0000000
    Cal_ex = 312499
    RD_ex = 0
    PID_LIA_CH = 0
    PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
    fpga.PID_config(1, PID_coe)
    fpga.PID_config(2, PID_coe)
    print('PID coe download')
    fpga.PID_enable(1)
    fpga.PID_enable(2)
    print('PID enable')
    data = fpga.PID_play(10)
    # fpga.PID_plot()
    print(('data rms = ', np.std(data[0]), np.std(data[1])))
    print('PID play')
    fpga.PID_disable(1)
    fpga.PID_disable(2)
    fpga.all_stop()


fpga = API(portx="COM6")
CHUNIT = 2


class Lockin(object):
    def __init__(self, *args, **kwargs):
        """
        锁相初始化函数
        设备识别码：DNVCS-Lockin-TotalField-0001
        Lockin-TotalField
        :param port: 端口号 int in [0,1] 0
        """
        self.fpga = fpga
        self.spr = 200
        self.tc = 0.1

        self.SetDataSampleRate(self.spr)
        self.SetLockInTimeConst(self.tc)

    def config_play(self):
        self.fpga.all_stop()
        print('lockin_stop,OK')
        self.fpga.play()
        print('Lockin_play,OK')
        self.fpga.all_start()
        print('Lockin_start,OK')

    def SetLockInFreq(self, freq, ch=-1, delay_flag=False, *args, **kwargs):
        """
        锁相板卡调制频率设置
        设备识别码：DNVCS-Lockin-TotalField-0002
        Lockin-TotalField
        :param freq: 调制/解调频率 int between [1,1E6] 1E3
        :param ch: 通道ID，始于0，默认为全设置 int in [-1,0,1,2,3] 0
        :param delay_flag: 延迟执行Flag bool in [True,False] True
        """
        if ch == -1:
            [self.fpga.De_fre_config(1 + ii, freq) for ii in range(CHUNIT)]
            [self.fpga.Modu_fre_config(1 + ii, freq) for ii in range(CHUNIT)]

        elif 0 <= ch <= CHUNIT - 1:
            self.fpga.De_fre_config(1 + int(ch), freq)
            self.fpga.Modu_fre_config(1 + int(ch), freq)
        if not delay_flag:
            self.fpga.all_stop()
            self.fpga.play()
            self.fpga.all_start()

    def SetLockInPhase(self, phase_ddc, ch=-1, delay_flag=False, *args, **kwargs):
        """
        锁相板卡调制相位设置
        设备识别码：DNVCS-Lockin-TotalField-0003
        Lockin-TotalField
        :param phase_ddc: 相位，1-180度 unlimmited unlimmited unlimmited None
        :param ch: 通道ID，0为荧光，1为激光 int in [0,1] 0
        :param delay_flag: 延迟执行Flag bool in [True,False] True
        """
        if ch == -1:
            [self.fpga.De_phase_config(1 + ii, phase_ddc) for ii in range(CHUNIT)]
        elif 0 <= ch <= CHUNIT * 2 - 1:
            self.fpga.De_phase_config(1 + int(ch), phase_ddc)
        if not delay_flag:
            self.fpga.all_stop()
            self.fpga.play()
            self.fpga.all_start()

    def SetLockInTimeConst(self, timeconst, ch=-1, delay_flag=False, *args, **kwargs):
        """
        锁相时间常数设置
        设备识别码：DNVCS-Lockin-TotalField-0006
        Lockin-TotalField
        :param timeconst: 时间常熟 unlimmited unlimmited unlimmited None
        :param ch: 通道，始于0，默认为全设置 int in [-1,0,1,2,3] 0
        :param delay_flag: 延迟执行Flag bool in [True,False] True
        """
        self.fpga.set_tc(timeconst)
        if not delay_flag:
            self.fpga.all_stop()
            self.fpga.play()
            self.fpga.all_start()

    def GetLockInTimeConst(self, ch=0):
        """
        获取某通道时间常数
        设备识别码：DNVCS-Lockin-TotalField-0007
        Lockin-TotalField
        :param ch: 通道，始于0，默认为全设置 int in [-1,0,1,2,3] 0
        """
        return self.fpga.tc

    def GetDCSignal(self):
        sig_ch1, sig_ch2 = self.fpga.DAQ_play(250)
        return np.mean(sig_ch1), np.mean(sig_ch2)

    def SetDataSampleRate(self, daq_sample_rate, delay_flag=False, *args, **kwargs):
        """
        设置采样率
        设备识别码：DNVCS-Lockin-TotalField-0008
        Lockin-TotalField
        :param daq_sample_rate: 采样率 int between [0,10000] 200
        :param delay_flag: 延迟执行Flag bool in [True,False] True
        """
        # 设置采样率
        self.spr = daq_sample_rate
        self.fpga.sample_rate_config(daq_sample_rate)
        if not delay_flag:
            self.fpga.all_stop()
            self.fpga.play()
            self.fpga.all_start()

    def GetDataSampleRate(self):
        """
        获取采样率
        设备识别码：DNVCS-Lockin-TotalField-0009
        Lockin-TotalField
        """
        return self.spr

    def GetDAQChannel(self, pnum):
        """
        Acquire DAQ data of 2 channels.
        """
        return self.fpga.auxDAQ_play(pnum)

    def GetLockInChannel(self):
        ch1rs, ch1ys, ch1xs, ch2rs, ch2ys, ch2xs = self.fpga.IIR_play(1)[:6]
        return ch1xs[0], ch1ys[0], ch2xs[0], ch2ys[0]

    def GetLockInChannels(self, poll_time=0.1):
        """
        读取锁相通道返回值（某一段时间内）
        设备识别码：DNVCS-Lockin-TotalField-0013
        Lockin-TotalField
        :param poll_time: 锁相板卡数据采集时间 float between [0,100] 0.1
        """
        # ch1rs, ch1ys, ch1xs, ch2rs, ch2ys, ch2xs = fpga.IIR_play(int(self.spr * poll_time * 1.1))[:6]
        ch_data = self.fpga.IIR_play(int(self.spr * poll_time))
        # return ch1xs, ch1ys, ch2xs, ch2ys,
        return ch_data

    def Laser_pid_config(self, kp, ki, kd, set_point, offset, PID_LIA_CH):
        ch_coe = [set_point, output_offset, kp, ki, kd, PID_LIA_CH]
        # ch1rs, ch1ys, ch1xs, ch2rs, ch2ys, ch2xs = fpga.IIR_play(int(self.spr * poll_time * 1.1))[:6]
        ch_data = self.fpga.PID_config(5, ch_coe)
        # return ch1xs, ch1ys, ch2xs, ch2ys,
        return ch_data

    def GetLockInChannels_AllData(self, poll_time=0.1):
        """
        读取锁相通道返回值（某一段时间内）
        设备识别码：DNVCS-Lockin-TotalField-0055
        Lockin-TotalField
        :param poll_time: 锁相板卡数据采集时间 float between [0,100] 0.1
        """
        # return fpga.IIR_play(int(self.spr * poll_time * 1.1))[:12]
        data = self.fpga.IIR_play(int(self.spr * poll_time * 1.1))[:12]
        return [np.mean(data[i]) for i in range(len(data))]  # 4.18 将返回数据修改为符合canvas_setplot条件的格式

    def AcquireStart(self, *args, **kwargslf):
        self.fpga.IIR_continuous_acq_start()
        self.p_start = 0

    def GetAcquireChannels(self, poll_time=0.1, get_time_stamps=False, **kwargs):
        '''
        在连续采集模式下，获取一定时长的LIA时域数据。
        需要通过AcquireStartV1开启连续采集，AcquireStopV1停止连续采集。

        :param poll_time: 从缓存中提取的数据时长
        :param get_time_stamps: 是否返回根据采样率和采样点数计算的时间戳数据
        :return:
        '''
        pnum = int(poll_time * self.spr)
        if get_time_stamps:
            ts = np.arange(self.p_start, self.p_start + pnum, 1) / self.spr
            return ts, self.fpga.IIR_play(data_num=pnum)
        return self.fpga.IIR_play(data_num=pnum)

    def AcquireStop(self, *args, **kwargslf):
        self.fpga.IIR_continuous_acq_stop()
        self.p_start = 0

    def SetPIDParameters(self, ch_num, set_point=0, output_offset=2870000000, kp=-2e-5, ki=-2e-5, kd=-2e-5, kt=1,
                         PID_RD_RITIO=5, PID_EX_RATIO=80000, PID_LIA_CH=0):

        # 设置PID参数, updated at 2022-06-22
        # param ch_num: 通道数
        # param set_point: 输出参考值
        # param output_offset: 初始波源输出频率(Hz)
        # param kp:
        # param ki:
        # param kd:
        # param PID_RD_RITIO:PID读回抽取率
        # param PID_EX_RATIO:PID运算抽取率
        #       PID实际读回速度等于 50MHz/(PID读回抽取率*PID运算抽取率)
        # param PID_LIA_CH:PID参考通道 0:LIA_X, 1:LIA_Y, 3:LIA_R，默认参考x
        # return:

        output_offset = int((output_offset - 2.6e9) * 0.5 * 1048576)
        # PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
        coe = [set_point, output_offset, kp, ki, kd, kt, PID_RD_RITIO, PID_EX_RATIO, PID_LIA_CH]
        # print(coe)
        self.fpga.PID_config(ch_num, coe)
        self.pidspr = 25000000.0 / ((PID_RD_RITIO + 1.0) * (PID_EX_RATIO + 1.0))

    def PID_Enable(self):
        # 开启PID,全开全关
        # @return:
        [self.fpga.PID_enable(1 + ii) for ii in range(CHUNIT)]

    def PID_Disable(self, ch_num=-1):

        # 关闭PID，最好全开全关
        # @param ch_num: -1:全关
        # @return:
        if ch_num == -1:
            [self.fpga.PID_disable(1 + ii) for ii in range(CHUNIT)]
        else:
            self.fpga.PID_disable(1 + ch_num)

    def AcquireStartV2_PID(self, *args, **kwargslf):  # 开启PID模式连续采集功能
        #:return:
        if not self.fpga.run_flag:
            # print 'PID acquire start'
            self.fpga.AcquireStartV2_PID()
        self.pnum_index = 0

    def AcquireStopV2_PID(self, *args, **kwargslf):
        # 停止读数
        if self.fpga.run_flag:
            # print ("PID acquire stop.")
            self.fpga.AcquireStopV2_PID()

    def GetLockInChannels_PID(self, poll_time=0.1):
        '''
        进行PID模式下的LIA定时采集。
        :param poll_time: 采集时间长度，s
        :return: data: 16列数据，[1-4]列为CH1的x,y,error,feedbac，[2-4]列为CH2，以此类推
        '''
        # 下载数据速度需要快于数据读取速度，以保证连续读数
        pnum = int(poll_time * self.pidspr)
        print(('pid_pnum=', pnum))
        pid_data, aux_ch1_data, aux_ch2_data = self.fpga.SYS_config.PID_play(pnum)

        # 读XY数据,读PID结果
        data = []
        for i in range(AINPUTN):
            # 截取待下载数据
            for j in range(3):
                data.append(list(np.array(pid_data[i][j + 1])))
            # data.append(list(np.array(pid_data[i][4]) * 4194304000.0))

            # inv: output_offset = int((output_offset - 2.6e9) * 0.5 * 1048576)
            data.append(list(np.array(pid_data[i][4]) / 1048576 * 2 + 2.6e9))
        return data + [aux_ch1_data] + [aux_ch2_data]

    def GetAcquireChannelsV2_PID(self, poll_time=0.1, get_time_stamps=False, **kwargs):
        '''
        PID连续采集模式数据下载函数。
        *返回格式：16列数据，0-3列为频率1结果，依次为y,x,误差项，反馈输出(当前波源输出频率，Hz)，频率2,3,4依次类推
        :param poll_time:
        :param get_time_stamps:
        :param kwargs:
        :return:
        '''
        # 下载数据速度需要快于数据读取速度，以保证连续读数
        pnum = int(poll_time * self.pidspr)
        while len(self.fpga.aux_data[-1]) <= pnum:
            time.sleep(0.02)

        # 读XY数据,读PID结果
        data = []
        aux_data = [[], []]
        for ii in range(AINPUTN):
            # 截取待下载数据
            x = np.array(self.fpga.data[ii * 4][:pnum])
            y = np.array(self.fpga.data[ii * 4 + 1][:pnum])
            err = np.array(self.fpga.data[ii * 4 + 2][:pnum])
            feedback = np.array(self.fpga.data[ii * 4 + 3][:pnum]) * 2 ** 29 + 2.6e9
            # print 'len(x)=', len(x), 'len(y)=', len(y), 'len(err)=', len(err), 'len(feedack)=', len(feedback)
            data.append(list(x))
            data.append(list(y))
            data.append(list(err))
            data.append(list(feedback))
            # 移除已下载数据，重设可变数组长度
            # while fpga.realtime_acquiring_state != ACQ_IDLE:
            #     continue
            # fpga.realtime_acquiring_state = ACQ_READ
            # 修改数组删除逻辑
            for ch_id in range(4):
                del self.fpga.data[ii * 4 + ch_id][:pnum]
            # fpga.realtime_acquiring_state = ACQ_IDLE
        for ii in range(2):
            aux_data[ii] = aux_data[ii] + list(self.fpga.aux_data[ii][:pnum])
            del self.fpga.aux_data[ii][:pnum]
        if get_time_stamps:
            ts = np.arange(self.pnum_index, self.pnum_index + pnum, 1)
            self.pnum_index += pnum
            return ts.tolist(), data + aux_data
        else:
            self.pnum_index += pnum
            return data + aux_data

    def GetAcquireChannelsV3_PID(self, poll_time=0.1, **kwargs):
        '''
        PID连续采集模式数据下载函数。
        *返回格式：19列数据，0-3列为频率1结果，依次为x,y,误差项，反馈输出(当前波源输出频率，kHz)，频率2,3,4依次类推;
        17, 18列为DC直流信号；19列为时间戳（暂时不返回）
        :param poll_time:
        :param kwargs:
        :return:
        '''
        # 注意！下载数据速度需要快于数据读取速度，以保证连续读数。可监控队列容量观察效果
        poll_pnum = int(self.pidspr * poll_time)
        data = list(np.zeros((16, poll_pnum)))
        aux_data = list(np.zeros((2, poll_pnum)))
        # 等待知道数据被读取
        while self.fpga.data_queue.qsize() < poll_pnum:
            continue
        # pnum = self.fpga.data_queue.qsize()
        for i in range(poll_pnum):
            res_data = self.fpga.data_queue.get()
            for j in range(16):
                data[j][i] = res_data[j]
            for j in range(2):
                aux_data[j][i] = res_data[16 + j]
        self.pnum_index += poll_pnum
        return data + aux_data
        # return data + aux_data + [self.fpga.data_queue.qsize()] * poll_pnum # 临时调试用写法，用于验证采集线程性能


class Laser(object):
    def __init__(self, current=0.4, *args, **kwargs):
        """
        设备初始化函数
        设备识别码：DNVCS-Laser-TotalField-0001
        Laser-TotalField
        :param port: 端口号 int in [0,1] 0
        """
        self.current = current
        self.fpga = fpga

    def set_current(self, cur):
        """
        设置激光功率
        设备识别码：DNVCS-Laser-TotalField-0002
        Laser-TotalField
        :param cur: 电流大小（A） int in [0,5] 0
        """
        # # 设置激光电流，单位A
        self.fpga.CS_SPI_Ctrl(cur)
        self.current = cur

    def get_power(self):
        return self.current


class WaveSource(object):
    def __init__(self, port=0, *args, **kwargs):
        """
        设备初始化函数
        设备识别码：DNVCS-WaveSource-TotalField-0001
        MW-TotalField
        :param port: 端口号 int in [0,1] 0
        """
        self.fpga = fpga
        self.mw_id = int(port)

    def mw_play(self):
        # 'ch1_Fre':2.6e9, 'ch1_fm_sens':0, 'ch1_atte':30,
        # print('mw play:', self.fpga.mw_para)
        self.fpga.MW_SPI_Ctrl(self.fpga.mw_para['ch1_Fre'], self.fpga.mw_para['ch1_fm_sens'], self.fpga.mw_para['ch1_atte'],
                         self.fpga.mw_para['ch2_Fre'], self.fpga.mw_para['ch2_fm_sens'],
                         self.fpga.mw_para['ch2_atte'], )

    def stop_output(self, all_ch=False, *args, **kwargs):
        """
        停止输出
        设备识别码：DNVCS-WaveSource-TotalField-0002
        MW-TotalField
        :param all_ch: 端口号 bool in [True,False] True
        """
        if all_ch:
            self.fpga.MW_SPI_Ctrl(2.6e9, 0, 30, 2.6e9, 0, 30)
        elif self.mw_id == 1:
            self.fpga.MW_SPI_Ctrl(self.fpga.mw_para['ch1_Fre'], self.fpga.mw_para['ch1_fm_sens'],
                             self.fpga.mw_para['ch1_atte'],
                             2.6e9, 0, 30)
        elif self.mw_id == 0:
            self.fpga.MW_SPI_Ctrl(2.6e9, 0, 30,
                             self.fpga.mw_para['ch2_Fre'], self.fpga.mw_para['ch2_fm_sens'],
                             self.fpga.mw_para['ch2_atte'])

    def start_output(self, *args, **kwargs):
        """
        开始输出
        设备识别码：DNVCS-WaveSource-TotalField-0003
        MW-TotalField
        """
        self.mw_play()

    def set_freq(self, freq, delay_flag=False):
        """
        设置微波频率
        设备识别码：DNVCS-WaveSource-TotalField-0005
        MW-TotalField
        :param freq: 频率 int between [0,4E9] 2.6E9
        """
        if 2.6e9 <= freq <= 3.2e9 or freq == 0:
            freq = int(freq)
            # freq = int((freq - 2600000000) * 0.5) #修改了MW_SPI_Ctrl，此处不再处理
            if self.mw_id == 0:
                self.fpga.mw_para['ch1_Fre'] = freq
                # self.fpga.mw_para['ch2_Fre'] = int(2.6e9)
            if self.mw_id == 1:
                # self.fpga.mw_para['ch1_Fre'] = int(2.6e9)
                self.fpga.mw_para['ch2_Fre'] = freq
            if not delay_flag:
                self.mw_play()
                time.sleep(0.01)
                self.mw_play()
            return True
        print('freq error!!!')
        return False

    def set_doubleCH_freq(self, freq1, freq2, delay_flag=False):
        """
        设置双通道微波频率
        设备识别码：DNVCS-WaveSource-TotalField-0005
        MW-TotalField
        :param freq1: CH1频率 int between [0,4E9] 2.6E9
        :param freq2: CH2频率 int between [0,4E9] 2.6E9
        """
        if 2.6e9 <= freq1 <= 3.2e9 or freq1 == 0:
            freq1 = int(freq1)
            freq2 = int(freq2)
            self.fpga.mw_para['ch1_Fre'] = freq1
            self.fpga.mw_para['ch2_Fre'] = freq2
            if not delay_flag:
                self.mw_play()
                time.sleep(0.01)
                self.mw_play()

    def get_freq(self):
        """
        获取微波频率
        设备识别码：DNVCS-WaveSource-TotalField-0006
        MW-TotalField
        """
        if self.mw_id == 0:
            return self.fpga.mw_para['ch1_Fre']
        else:
            return self.fpga.mw_para['ch2_Fre']

    def set_power(self, power, delay_flag=False, ch=-1):
        """
        设置微波功率
        设备识别码：DNVCS-WaveSource-TotalField-0007
        MW-TotalField
        :param power: 功率 int between [0,1E3] 1
        """
        if 0 <= power <= 30:
            power = int(30 - power)
            if self.mw_id == 0:
                self.fpga.mw_para['ch1_atte'] = power
            if self.mw_id == 1:
                self.fpga.mw_para['ch2_atte'] = power
            if not delay_flag:
                self.mw_play()
            return True
        return False

    def set_doubleCH_power(self, power1, power2, delay_flag=False):
        """
        设置双通道微波功率
        设备识别码：DNVCS-WaveSource-TotalField-0005
        MW-TotalField
        :param power1: CH1功率 int between [0,1E3] 0
        :param power2: CH2功率 int between [0,1E3] 0
        """
        if 0 <= power1 <= 30 and 0 <= power2 <=30:
            power1 = int(30 - power1)
            power2 = int(30 - power2)
            self.fpga.mw_para['ch1_atte'] = power1
            self.fpga.mw_para['ch2_atte'] = power2
        if not delay_flag:
            self.mw_play()
            time.sleep(0.01)
            self.mw_play()

    def get_power(self, ch=0):
        """
        获取微波功率
        设备识别码：DNVCS-WaveSource-TotalField-0008
        MW-TotalField
        """
        if self.mw_id == 0:
            return 30 - self.fpga.mw_para['ch1_atte']
        if self.mw_id == 1:
            return 30 - self.fpga.mw_para['ch2_atte']

    def set_fm_sens(self, val, delay_flag=False, ch=-1):
        """
        设置微波调制深度
        设备识别码：DNVCS-WaveSource-TotalField-0009
        MW-TotalField
        :param val: ？？？ float between [0,1] 0
        """
        if 0 <= val <= 1:
            val = int(val * 100)
            if self.mw_id == 0:
                self.fpga.mw_para['ch1_fm_sens'] = val
            if self.mw_id == 1:
                self.fpga.mw_para['ch2_fm_sens'] = val
            if not delay_flag:
                self.mw_play()
            return True
        return False

    def set_doubleCH_fm_sens(self, val1, val2, delay_flag=False):
        """
        设置双通道微波调制深度
        设备识别码：DNVCS-WaveSource-TotalField-0005
        MW-TotalField
        :param val1: ？？？ float between [0,1] 0
        :param val2: ？？？ float between [0,1] 0
        """
        if 0 <= val1 <= 1:
            val1 = int(val1 * 100)
            val2 = int(val2 * 100)
            self.fpga.mw_para['ch1_fm_sens'] = val1
            self.fpga.mw_para['ch2_fm_sens'] = val2
            if not delay_flag:
                self.mw_play()
                time.sleep(0.01)
                self.mw_play()

    def get_fm_sens(self, ch=0):
        if self.mw_id == 0:
            return self.fpga.mw_para['ch1_fm_sens']
        if self.mw_id == 1:
            return self.fpga.mw_para['ch2_fm_sens']


class DoubleWaveSource(object):
    def __init__(self, *args, **kwargs):
        """
        设备初始化函数
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0001
        DoubleMW-TotalField
        """
        self.fpga = fpga

    def mw_play(self):
        # 'ch1_Fre':2.6e9, 'ch1_fm_sens':0, 'ch1_atte':30,
        # print('mw play:', self.fpga.mw_para)
        self.fpga.MW_SPI_Ctrl(self.fpga.mw_para['ch1_Fre'], self.fpga.mw_para['ch1_fm_sens'], self.fpga.mw_para['ch1_atte'],
                         self.fpga.mw_para['ch2_Fre'], self.fpga.mw_para['ch2_fm_sens'],
                         self.fpga.mw_para['ch2_atte'], )

    def stop_output(self, ch_id=0, all_ch=False, *args, **kwargs):
        """
        停止输出
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0002
        DoubleMW-TotalField
        :param ch_id: 通道ID int in [0,1] 0
        :param all_ch: 双通道标识 bool in [True,False] True
        """
        if all_ch:
            self.fpga.MW_SPI_Ctrl(2.6e9, 0, 30, 2.6e9, 0, 30)
        elif ch_id == 1:
            self.fpga.MW_SPI_Ctrl(self.fpga.mw_para['ch1_Fre'], self.fpga.mw_para['ch1_fm_sens'],
                             self.fpga.mw_para['ch1_atte'],
                             2.6e9, 0, 30)
        elif ch_id == 0:
            self.fpga.MW_SPI_Ctrl(2.6e9, 0, 30,
                             self.fpga.mw_para['ch2_Fre'], self.fpga.mw_para['ch2_fm_sens'],
                             self.fpga.mw_para['ch2_atte'])

    def start_output(self, *args, **kwargs):
        """
        开始输出
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0003
        DoubleMW-TotalField
        """
        self.mw_play()

    def set_freq(self, freq,ch_id=0, delay_flag=False):
        """
        设置微波频率
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0005
        DoubleMW-TotalField
        :param freq: 频率 int between [0,4E9] 2.6E9
        :param ch_id: 通道ID int in [0,1] 0
        """
        if 2.6e9 <= freq <= 3.2e9 or freq == 0:
            freq = int(freq)
            # freq = int((freq - 2600000000) * 0.5) #修改了MW_SPI_Ctrl，此处不再处理
            if ch_id == 0:
                self.fpga.mw_para['ch1_Fre'] = freq
                # self.fpga.mw_para['ch2_Fre'] = int(2.6e9)
            if ch_id == 1:
                # self.fpga.mw_para['ch1_Fre'] = int(2.6e9)
                self.fpga.mw_para['ch2_Fre'] = freq
            if not delay_flag:
                self.mw_play()
                time.sleep(0.01)
                self.mw_play()
            return True
        print('freq error!!!')
        return False

    def set_all_freq(self, freq1, freq2, delay_flag=False):
        """
        设置微波频率
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0005
        DoubleMW-TotalField
        :param freq1: 频率（通道1） int between [0,4E9] 2.6E9
        :param freq2: 频率（通道2） int between [0,4E9] 2.6E9
        """
        if (2.6e9 <= freq1 <= 3.2e9 or freq1 == 0)and(2.6e9 <= freq2 <= 3.2e9 or freq2 == 0):
            freq1 = int(freq1)
            freq2 = int(freq2)
            # freq = int((freq - 2600000000) * 0.5) #修改了MW_SPI_Ctrl，此处不再处理
            self.fpga.mw_para['ch1_Fre'] = freq1
            self.fpga.mw_para['ch2_Fre'] = freq2
            if not delay_flag:
                self.mw_play()
                time.sleep(0.01)
                self.mw_play()
            return True
        print('freq error!!!')
        return False

    def get_freq(self):
        """
        获取微波频率
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0006
        DoubleMW-TotalField
        """
        f1,f2 = self.fpga.mw_para['ch1_Fre'],self.fpga.mw_para['ch2_Fre']
        print("MW_Freq:",f1,f2)
        return f1,f2

    def set_power(self, power, ch_id=0,delay_flag=False, ch=-1):
        """
        设置微波功率
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0007
        DoubleMW-TotalField
        :param power: 功率 int between [0,1E3] 1
        :param ch_id: 通道ID int in [0,1] 0
        """
        if 0 <= power <= 30:
            power = int(30 - power)
            if ch_id == 0:
                self.fpga.mw_para['ch1_atte'] = power
            if ch_id == 1:
                self.fpga.mw_para['ch2_atte'] = power
            if not delay_flag:
                self.mw_play()
            return True
        return False

    def set_all_power(self, power1, power2, delay_flag=False):
        """
        设置微波频率
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0005
        DoubleMW-TotalField
        :param power1: 功率（通道1） int between [0,30] 0
        :param power2: 功率（通道2） int between [0,30] 0
        """
        if (0 <= power1 <= 30) and (0<= power2<=30):
            power1 = int(30 - power1)
            power2 = int(30 - power2)
            self.fpga.mw_para['ch1_atte'] = power1
            self.fpga.mw_para['ch2_atte'] = power2
            if not delay_flag:
                self.mw_play()
            return True
        return False

    def get_power(self):
        """
        获取微波功率
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0008
        DoubleMW-TotalField
        """
        p1,p2 = 30 - self.fpga.mw_para['ch1_atte'], 30 - self.fpga.mw_para['ch2_atte']
        print("MW_Power:",p1,p2)
        return p1,p2

    def set_fm_sens(self, val, ch_id=0, delay_flag=False, ch=-1):
        """
        设置微波调制深度
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0009
        DoubleMW-TotalField
        :param val: 调制深度 float between [0,1] 0
        :param ch_id: 通道ID int in [0,1] 0
        """
        if 0 <= val <= 1:
            val = int(val * 100)
            if ch_id == 0:
                self.fpga.mw_para['ch1_fm_sens'] = val
            if ch_id == 1:
                self.fpga.mw_para['ch2_fm_sens'] = val
            if not delay_flag:
                self.mw_play()
            return True
        return False

    def set_all_fm_sens(self, val1, val2, delay_flag=False):
        """
        设置微波调制深度
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0009
        DoubleMW-TotalField
        :param val1: 调制深度（通道1） float between [0,1] 0
        :param val2: 调制深度（通道2） float between [0,1] 0
        """
        if (0 <= val1 <= 1)and(0 <= val2 <=1):
            val1 = int(val1 * 100)
            val2 = int(val2 * 100)
            self.fpga.mw_para['ch1_fm_sens'] = val1
            self.fpga.mw_para['ch2_fm_sens'] = val2
            if not delay_flag:
                self.mw_play()
            return True
        return False

    def get_fm_sens(self):
        """
        获取微波调制深度
        设备识别码：DNVCS-DoubleWaveSource-TotalField-0010
        DoubleMW-TotalField
        """
        v1,v2 = self.fpga.mw_para['ch1_fm_sens'],self.fpga.mw_para['ch2_fm_sens']
        print("MW_fm_sens:",v1,v2)
        return v1,v2


# 微波通道数
device_channel = 2

# device_channel = 1

# 通道标号
CH_FLUO = 0
CH_LASER = 1

# 数据列标号
COL = ['X', 'Y']
CH_X = 0
CH_Y = 1


def EXPDIR(ExpDataPath, dict_to_save=None):
    """执行实验文件夹检查及参数保存功能"""
    dirs = [ExpDataPath]
    for di in dirs:
        if not os.path.exists(DATAPATH + di):
            os.mkdir(DATAPATH + di)
    if dict_to_save is not None:
        dict_save(dict_to_save, time.strftime(DATAPATH + ExpDataPath + '%Y-%m-%d %H_%M_%S',
                                              time.localtime(time.time())) + '.ini')


class exp(object):
    def __init__(self):
        super(exp, self).__init__()
        self.lockin = Lockin()
        self.wavesource = [WaveSource(port=0), WaveSource(port=1)]
        self.laser = Laser()
        self.run_flag = False
        self.loop_run_flag = False
        self.parameter = {}
        self.parameter.update({
            # 需要注册该函数以实际2D扫描时的计数
            'exp_count_function': None,
            'exp_run_function': self.ExpSweepCW,
            'single_mode': 0,
            'single_mode_id': 0,
            'mw_off': 0,

            'laser_power': 0.5,
            # 'volt_to_tesla_coe': 6.2390e-5,

            'lockin_coupling': 0,
            'lockin_imd_50': 0,
            'lockin_samp_rate': 1000,
            # 'therm_res_volt': 0,

            'para_Bx': 36.2,
            'para_By': 17.3,
            'para_Bz': 69.5,
            'para_Dgs': 2.8692,

            'set_Bx': 0,
            'set_By': 0,
            'set_Bz': 0,
            'three_freq': 1,
            'realtime_acquiring_time': 10,
            'realtime_time_limitation': 0,
            'realtime_slice_time': 20,

            'laser_start_phase': 0,
            'laser_stop_phase': 180,
            'laser_step_phase': 5,

            'fluo_start_phase': 0,
            'fluo_stop_phase': 180,
            'fluo_step_phase': 5,

            'mw_fluo_start_freq': 2.92e9,
            'mw_fluo_stop_freq': 2.96e9,
            'mw_fluo_step_freq': 0.2e6,
            'RD_RATIO': 1,
            'EX_RATIO': 1,

        })

        self.MatrixA = []
        self.data_f = []
        self.data_y = []
        self.data_test = []
        self.data_max_slope_freq = []
        self.loop_time = 0
        self.data_optimization = []
        self.data_cw = []
        self.data_time_domain = []
        # 注：GUI函数注册dict
        self.exp_type_list = {
            'ExpSweepCW': self.ExpSweepCW,  # updated
            'ExpRealtimeDisplay': self.ExpRealtimeDisplay,  # updated
        }
        # TODO：设备参数数量和函数中的命名可能不对应，还没有来得及检查
        for ii in range(device_channel):
            lock_str = 'lock_ch%d' % ii
            mw_str = 'mw_ch%d' % ii
            self.parameter.update({
                lock_str + '_freq': 138123,
                lock_str + '_tc': 0.01,
                lock_str + '_flu_phase': 0,
                lock_str + '_las_phase': 0,
                mw_str + '_start_freq': 2870000000.0,
                mw_str + '_stop_freq': 3000000000.0,
                mw_str + '_step_freq': 1000000.0,
                mw_str + '_power': -25.,
                # mw_str + '_trigger_mode': 2,
                mw_str + '_fm_devi': 0.75,
                'channel%d_slope' % ii: 1,
                'coe%d' % ii: 1,
                'kp_%d' % ii: -2e-5,
                'ki_%d' % ii: -2e-5,
                'kd_%d' % ii: -2e-5,
            })
        print(self.parameter)
        # load parameters from config
        # print('params setting initialized.')
        # self.params_setting = self.GetUIParameter()
        print('loading params.')
        self.LoadParams()
        time.sleep(0.1)
        print("laser debugging")
        self.laser.set_power(self.parameter['laser_power'])

        # 设备初始化
        # lockin
        self.lockin.SetDataSampleRate(self.parameter['lockin_samp_rate'], delay_flag=True)
        for i in range(2):
            self.lockin.SetLockInFreq(self.parameter['lock_ch%d_freq' % i], i, delay_flag=True)
            self.lockin.SetLockInTimeConst(self.parameter['lock_ch%d_tc' % i], i, delay_flag=True)
            self.lockin.SetLockInPhase(self.parameter['lock_ch%d_flu_phase' % i], 2 * i + CH_FLUO, delay_flag=True)
            self.lockin.SetLockInPhase(self.parameter['lock_ch%d_las_phase' % i], 2 * i + CH_LASER, delay_flag=True)
        self.lockin.config_play()
        # mw
        for i in range(2):
            self.wavesource[i].set_freq(self.parameter['mw_ch%d_start_freq' % i], delay_flag=True)
            self.wavesource[i].set_power(self.parameter['mw_ch%d_power' % i], delay_flag=True)
            self.wavesource[i].set_fm_sens(self.parameter['mw_ch%d_fm_devi' % i], delay_flag=True)
            self.wavesource[i].mw_play()
        # self.wavesource[1].mw_play()

        # Laser

        print('set laser power as', self.parameter['laser_power'])
        self.laser.set_power(self.parameter['laser_power'])
        # time.sleep(10)
        # # fpga.auxDAQ_play(2000)
        #
        # PID_ch_num = (self.parameter['laser_PID_ch_num'])  # 激光PID通道为5
        # set_point = (self.parameter['laser_set_point'])  # 需先测量得到荧光信号的DC值后确定
        # output_offset = (self.parameter['laser_output_offset']) # 将激光稳定在0.6 A
        # kp = (self.parameter['laser_kp'])
        # ki = (self.parameter['laser_ki'])
        # kd = (self.parameter['laser_kd'])
        # # ki = -0.003
        # #
        # # kd = -0.0001
        # kt = (self.parameter['laser_kt'])
        # Cal_ex = (self.parameter['laser_Cal_ex'])
        # RD_ex = (self.parameter['laser_RD_ex'])
        # PID_LIA_CH = (self.parameter['PID_LIA_CH'])
        # PID_coe = [set_point, output_offset, kp, ki, kd, kt, Cal_ex, RD_ex, PID_LIA_CH]
        # fpga.PID_config(PID_ch_num, PID_coe)
        # fpga.PID_enable(PID_ch_num)
        # time.sleep(5)
        # data = fpga.Laser_PID_play(100)
        # print(data[0])
        # print(data[1])
        # print(data[2])
        # # fpga.Laser_PID_plot()
        # fpga.PID_disable(5)

    def LoadParams(self):
        '''
            Load experiment parameters from configuration file.
            '''
        fpath = r'D:\work_xwt\Integration_7th_version_cc_2channel\Integration_7th_version\config\paraui.ini'
        import os
        if not os.path.exists(fpath): return
        with open(fpath, "r") as file:
            tex = file.readline()
            while len(tex) > 0:
                it1, it2 = tex.split(',')
                # print 'getting value:', it1
                self.parameter[it1] = float(it2)
                tex = file.readline()

    def SetParameter(self, item, value):
        try:
            self.parameter[item] = value
        except KeyError:
            pass

    # def GetUIParameter(self):
    #     """
    #     '*' for combo box;
    #     '%' for integer text input;
    #     others for float.
    #     Example:
    #     para = {
    #         'lockin_freq': (0, 1, 100000),
    #         'lockin_amplitide': (1., 0., 1.),
    #         'lockin_phase': (0., 0., 360.),
    #         '*lockin_time_const': self.tc_option,
    #         '*lockin_sensitivity': self.sens_option,
    #         '*lockin_reference': ['External', 'Internal'],
    #         '*lockin_coupling': ['AC', 'DC'],
    #         '*lockin_sampling_rate': self.spr_options,
    #     }
    #     :return:
    #     """
    #     p1 = {'Update Rate': [self.parameter['Update Rate'], 0, 2, lambda x: x, '/'], }
    #     for ii in range(device_channel):
    #         # print(self.lockin[ii].device_id)
    #         lock_str = 'lock_ch%d' % ii
    #         mw_str = 'mw_ch%d' % ii
    #         p1.update({
    #             # lock_str + '_freq': [self.parameter[lock_str + '_freq'], 1, 10e3,
    #             #                      partial(self.lockin.SetLockInFreq, ch=ii), 'Unit:Hz'],
    #             lock_str + '_freq': [self.parameter[lock_str + '_freq'], 1, 1e6,
    #                                  partial(self.lockin.SetLockInFreq, ch=ii), 'Unit:Hz'],
    #             lock_str + '_tc': [self.parameter[lock_str + '_tc'], 0., 1.,
    #                                partial(self.lockin.SetLockInTimeConst, ch=ii), 'Unit:s'],
    #             lock_str + '_flu_phase': [self.parameter[lock_str + '_flu_phase'], -360., 360.,
    #                                       partial(self.lockin.SetLockInPhase, ch=2 * ii), 'Unit:deg'],
    #             lock_str + '_las_phase': [self.parameter[lock_str + '_las_phase'], -360., 360.,
    #                                       partial(self.lockin.SetLockInPhase, ch=2 * ii + 1), 'Unit:deg'],
    #             mw_str + '_start_freq': [self.parameter[mw_str + '_start_freq'], 12.5e6, 6400e6,
    #                                      self.wavesource.set_freq, 'Unit:Hz'],
    #             mw_str + '_stop_freq': [self.parameter[mw_str + '_stop_freq'], 12.5e6, 6400e6, lambda x: x, 'Unit:Hz'],
    #             mw_str + '_step_freq': [self.parameter[mw_str + '_step_freq'], 0.1, 1e9, lambda x: x, 'Unit:Hz'],
    #             mw_str + '_power': [self.parameter[mw_str + '_power'], -75, 10, self.wavesource.set_power,
    #                                 'Unit:dBm'],
    #             # mw_str + '_trigger_mode': [self.parameter[mw_str + '_trigger_mode'], 0, 9,
    #             #                            self.wavesource[ii].set_trigger_mode, '9:FM'],
    #             # mw_str + '_fm_devi': [self.parameter[mw_str + '_fm_devi'], 0, 8e6,
    #             #                       self.wavesource[ii].set_fm_devi, 'Unit:Hz'],
    #             # mw_str + '_trigger_mode': [self.parameter[mw_str + '_trigger_mode'], 0, 4,
    #             #                            self.wavesource.set_fm_mode, '9:FM'],
    #             mw_str + '_fm_devi': [self.parameter[mw_str + '_fm_devi'], 0, 1,
    #                                   self.wavesource.set_fm_sens, 'Unit:Hz'],
    #
    #             # 'dc_pwr_volt': [self.parameter['dc_pwr_volt'], 0, 30., lambda x: dev.pwr.set_voltage(2, x), 'Unit:V'],
    #             # 'dc_pwr_curr': [self.parameter['dc_pwr_curr'], 0, 3., lambda x: dev.pwr.set_current(2, x)],
    #             # 'volt_to_tesla_coe': [self.parameter['volt_to_tesla_coe'], 0, 1e9,
    #             #                       lambda x: self.SetParameter('volt_to_tesla_coe', x)],
    #             # 'thermal_resistance_voltage': [self.parameter['therm_res_volt'], 0, 0.5,
    #             #                                lambda x: dev.pwr.set_voltage(3, x), 'Unit:V'],
    #             'coe%d' % ii: [self.parameter['coe%d' % ii], -1e99, 1e99,
    #                            lambda x: self.SetParameter('coe%d' % ii, x), '1'],
    #         })
    #     p1.update({
    #         # 用于自定义函数的参数传递
    #         'mw_off': [self.parameter['mw_off'], 0, 1, lambda x: self.SetParameter('mw_off', x), '0 or 1'],
    #         'three_freq': [self.parameter['three_freq'], 0, 1, lambda x: self.SetParameter('three_freq', x), '0 or 1'],
    #         'single_mode': [self.parameter['single_mode'], 0, 1, lambda x: self.SetParameter('single_mode', x),
    #                         '0 or 1'],
    #         'single_mode_id': [self.parameter['single_mode_id'], 0, (device_channel - 1),
    #                            lambda x: self.SetParameter('single_mode_id', x), '0 to %d' % (device_channel - 1)],
    #         'lockin_samp_rate': [self.parameter['lockin_samp_rate'], 1, 1e6,
    #                              self.lockin.SetDataSampleRate, 'Unit:Sa/s'],
    #         # 'lockin_coupling': [self.parameter['lockin_coupling'], 0, 1,
    #         #                     partial(self.lockin.SetLockInCoupling, sigins=-1), '0:AC'],
    #         # 'lockin_imd_50': [self.parameter['lockin_imd_50'], 0, 1,
    #         #                   partial(self.lockin.set_imp50, sigins=-1), '0:1M'],
    #         'laser_power': [self.parameter['laser_power'], -1, 1, lambda x: self.laser.set_power(x), 'W'],
    #         'realtime_acquiring_time': [100, 1, 1e4, lambda x: self.SetParameter('realtime_acquiring_time', x),
    #                                     'Unit:0.1s'],
    #         'realtime_time_limitation': [0, -10, 10, lambda x : self.SetParameter('realtime_time_limitation', x),
    #                                     '0 or 1'],
    #         'RD_RATIO': [0, -1e100, 1e100, lambda x : self.SetParameter('RD_RATIO', x),
    #                                     ''],
    #         'EX_RATIO': [0, -1e100, 1e100, lambda x: self.SetParameter('EX_RATIO', x),
    #                      ''],
    #         # 'set_Bx': [0, -5, 5, partial(self.power.set_magnetic_field, chn=1), 'Unit:Gs'],
    #         # 'set_By': [0, -5, 5, partial(self.power.set_magnetic_field, chn=2), 'Unit:Gs'],
    #         # 'set_Bz': [0, -5, 5, partial(self.power.set_magnetic_field, chn=3), 'Unit:Gs'],
    #         'para_Bx': [0, -1e100, 1e100, lambda x: self.SetParameter('para_Bx', x), 'Unit:Gs'],
    #         'para_By': [0, -1e100, 1e100, lambda x: self.SetParameter('para_By', x), 'Unit:Gs'],
    #         'para_Bz': [0, -1e100, 1e100, lambda x: self.SetParameter('para_Bz', x), 'Unit:Gs'],
    #         'para_Dgs': [0, -1e100, 1e100, lambda x: self.SetParameter('para_Dgs', x), 'Unit:GHz'],
    #         'time_para1': [0, -1e100, 1e100, lambda x: self.SetParameter('time_para1', x)],
    #         'time_para2': [0, -1e100, 1e100, lambda x: self.SetParameter('time_para2', x)],
    #         'cw_para1': [0, -1e100, 1e100, lambda x: self.SetParameter('cw_para1', x)],
    #         'cw_para2': [0, -1e100, 1e100, lambda x: self.SetParameter('cw_para2', x)],
    #         'cw_para3': [0, -1e100, 1e100, lambda x: self.SetParameter('cw_para3', x)],
    #         'cw_para4': [0, -1e100, 1e100, lambda x: self.SetParameter('cw_para4', x)],
    #         'cw_para5': [0, -1e100, 1e100, lambda x: self.SetParameter('cw_para5', x)],
    #         'cw_para6': [0, -1e100, 1e100, lambda x: self.SetParameter('cw_para6', x)],
    #         'phase_para1': [0, -1e100, 1e100, lambda x: self.SetParameter('phase_para1', x)],
    #         'phase_para2': [0, -1e100, 1e100, lambda x: self.SetParameter('phase_para2', x)],
    #         'Res_freq_1': [2.87, 2.5, 3.5, lambda x: self.SetParameter('Res_freq_1', x), 'Unit:GHz'],
    #         'Res_freq_2': [2.87, 2.5, 3.5, lambda x: self.SetParameter('Res_freq_2', x), 'Unit:GHz'],
    #         'Res_freq_3': [2.87, 2.5, 3.5, lambda x: self.SetParameter('Res_freq_3', x), 'Unit:GHz'],
    #         'Res_freq_4': [2.87, 2.5, 3.5, lambda x: self.SetParameter('Res_freq_4', x), 'Unit:GHz'],
    #         'Res_freq_5': [2.87, 2.5, 3.5, lambda x: self.SetParameter('Res_freq_5', x), 'Unit:GHz'],
    #         'Res_freq_6': [2.87, 2.5, 3.5, lambda x: self.SetParameter('Res_freq_6', x), 'Unit:GHz'],
    #         'Res_freq_7': [2.87, 2.5, 3.5, lambda x: self.SetParameter('Res_freq_7', x), 'Unit:GHz'],
    #         'Res_freq_8': [2.87, 2.5, 3.5, lambda x: self.SetParameter('Res_freq_8', x), 'Unit:GHz'],
    #         'Threshold_freq_1': [0.1, 0, 1, lambda x: self.SetParameter('Threshold_freq_1', x), 'Unit:V'],
    #         'Threshold_freq_2': [0.1, 0, 1, lambda x: self.SetParameter('Threshold_freq_2', x), 'Unit:V'],
    #         'Threshold_freq_3': [0.1, 0, 1, lambda x: self.SetParameter('Threshold_freq_3', x), 'Unit:V'],
    #         'Threshold_freq_4': [0.1, 0, 1, lambda x: self.SetParameter('Threshold_freq_4', x), 'Unit:V'],
    #         'Threshold_freq_5': [0.1, 0, 1, lambda x: self.SetParameter('Threshold_freq_5', x), 'Unit:V'],
    #         'Threshold_freq_6': [0.1, 0, 1, lambda x: self.SetParameter('Threshold_freq_6', x), 'Unit:V'],
    #         'Threshold_freq_7': [0.1, 0, 1, lambda x: self.SetParameter('Threshold_freq_7', x), 'Unit:V'],
    #         'Threshold_freq_8': [0.1, 0, 1, lambda x: self.SetParameter('Threshold_freq_8', x), 'Unit:V'],
    #         'laser_start_phase': [0, 0, 360, lambda x: self.SetParameter('laser_start_phase', x)],
    #         'laser_stop_phase': [0, 0, 360, lambda x: self.SetParameter('laser_stop_phase', x)],
    #         'laser_step_phase': [0, 0, 360, lambda x: self.SetParameter('laser_step_phase', x)],
    #         'fluo_start_phase': [0, 0, 360, lambda x: self.SetParameter('fluo_start_phase', x)],
    #         'fluo_stop_phase': [0, 0, 360, lambda x: self.SetParameter('fluo_stop_phase', x)],
    #         'fluo_step_phase': [0, 0, 360, lambda x: self.SetParameter('fluo_step_phase', x)],
    #         'mw_fluo_start_freq': [2.92e9, 2.6e9, 3.1e9, lambda x: self.SetParameter('mw_fluo_start_freq', x)],
    #         'mw_fluo_stop_freq': [2.92e9, 2.6e9, 3.1e9, lambda x: self.SetParameter('mw_fluo_stop_freq', x)],
    #         'mw_fluo_step_freq': [2.92e9, 2.6e9, 3.1e9, lambda x: self.SetParameter('mw_fluo_step_freq', x)],
    #         'realtime_slice_time': [20, 0, 86400, lambda x: self.SetParameter('mw_fluo_step_freq', x)],
    #         'channel0_slope': [self.parameter['channel0_slope'], -1e99, 1e99,
    #                            lambda x: self.SetParameter('channel0_slope', x), 'Unit:V/Hz'],
    #         'channel1_slope': [self.parameter['channel1_slope'], -1e99, 1e99,
    #                            lambda x: self.SetParameter('channel1_slope', x), 'Unit:V/Hz'],
    #         'channel2_slope': [self.parameter['channel2_slope'], -1e99, 1e99,
    #                            lambda x: self.SetParameter('channel2_slope', x), 'Unit:V/Hz'],
    #         'channel3_slope': [self.parameter['channel3_slope'], -1e99, 1e99,
    #                            lambda x: self.SetParameter('channel3_slope', x), 'Unit:V/Hz'],
    #         'kp_0': [self.parameter['kp_0'], -1e99, 1e99, lambda x: self.SetParameter('kp_0', x), '1'],
    #         'kp_1': [self.parameter['kp_1'], -1e99, 1e99, lambda x: self.SetParameter('kp_1', x), '1'],
    #         'kp_2': [self.parameter['kp_2'], -1e99, 1e99, lambda x: self.SetParameter('kp_2', x), '1'],
    #         'kp_3': [self.parameter['kp_3'], -1e99, 1e99, lambda x: self.SetParameter('kp_3', x), '1'],
    #         'ki_0': [self.parameter['ki_0'], -1e99, 1e99, lambda x: self.SetParameter('ki_0', x), '1'],
    #         'ki_1': [self.parameter['ki_1'], -1e99, 1e99, lambda x: self.SetParameter('ki_1', x), '1'],
    #         'ki_2': [self.parameter['ki_2'], -1e99, 1e99, lambda x: self.SetParameter('ki_2', x), '1'],
    #         'ki_3': [self.parameter['ki_3'], -1e99, 1e99, lambda x: self.SetParameter('ki_3', x), '1'],
    #         'kd_0': [self.parameter['kd_0'], -1e99, 1e99, lambda x: self.SetParameter('kd_0', x), '1'],
    #         'kd_1': [self.parameter['kd_1'], -1e99, 1e99, lambda x: self.SetParameter('kd_1', x), '1'],
    #         'kd_2': [self.parameter['kd_2'], -1e99, 1e99, lambda x: self.SetParameter('kd_2', x), '1'],
    #         'kd_3': [self.parameter['kd_3'], -1e99, 1e99, lambda x: self.SetParameter('kd_3', x), '1'],
    #     })
    #     # if hasattr(dev, 'laser'): p1.update(
    #     #     {'laser_power': [self.parameter['laser_power'], -1, 5., dev.laser.set_power, 'Unit:W(-1 for shutdown)']})
    #     #
    #     # if hasattr(dev, 'gen'):
    #     #     if hasattr(dev.gen, '__name__') == 'ESR_4CH_AWG_V201910':
    #     #         p1.update(
    #     #             {'laser_power': [self.parameter['laser_power'], -1, 5., dev.laser.set_power,
    #     #                              'Unit:W(-1 for shutdown)']})
    #     # p1.update(self.wavesource.GetParameterAndOptions())
    #     return p1

    def create_data_dir(self, exp_name, time_dir_flag=False, exp_info_flag=True):
        '''
            创建数据保存目录。

            :param exp_name: 数据文件夹名称。
            :param time_dir_flag: 是否单独为每次实验创建独立文件夹。
            :return:
            '''
        ExpDataPath = exp_name + '/'
        if not os.path.exists(DataPath + ExpDataPath):
            os.mkdir(DataPath + ExpDataPath)
        save_dir = DataPath + ExpDataPath
        time_str = gettimestr()
        if time_dir_flag:
            time_dir = time_str + '_%s/' % exp_name
            os.mkdir(DataPath + ExpDataPath + time_dir)
            save_dir = DataPath + ExpDataPath + time_dir
        dict_save(self.parameter, time.strftime(save_dir + '%Y-%m-%d %H_%M_%S',
                                                time.localtime(time.time())) + '_' + exp_name + '.ini')
        if exp_info_flag:
            return save_dir, save_dir + time_str + '_' + exp_name + '_log.txt'
        return save_dir

    def logg_exp_info(self, logg_fn, exp_info_txt):
        '''
            输出实验信息。

            :param logg_fn: 日志文件路径。
            :param exp_info_txt: 输出实验信息。
            :return:
            '''
        print(exp_info_txt)
        codecs.open(logg_fn, 'a+', encoding='utf-8').write(exp_info_txt + '\n')

    def LoadConfig(self):
        logg(str(self.parameter))

    def Start(self):
        self.ClearData()
        # 实验模块依赖关系：由于实验模块需要使用连续波实验模块，故置运行标签为True
        self.run_flag = True
        self.wavesource.start_output()
        time.sleep(0.5)

        # 后台运行实验函数
        thd_exp = threading.Thread(target=self.parameter['exp_run_function'])
        thd_exp.setDaemon(True)
        thd_exp.start()
        # config save
        dict_save(self.parameter, time.strftime(DATAPATH + '%Y-%m-%d %H_%M_%S',
                                                time.localtime(time.time())) + '.ini')

    def Stop(self):
        self.run_flag = False
        self.loop_run_flag = False
        time.sleep(1.)
        print('Exp stopped.')

    def SetAllPlotData(self, plot_state=-1, *args):
        import copy, gc
        if plot_state == -1:
            # self.plot_data = copy.deepcopy([[args[i]] + args[i + 1] for i in range(0, len(args) - 1, 2)])
            self.plot_data = [[args[i]] + args[i + 1] for i in range(0, len(args) - 1, 2)]
        else:
            # self.plot_data[plot_state] = copy.deepcopy([args[0]] + args[1])
            self.plot_data[plot_state] = [args[0]] + args[1]
        gc.collect()

    def ClearData(self):
        self.ClearPlotData()

    def ClearPlotData(self):
        self.plot_data = [[], [], []]

    def set_fluo_phase(self, phase, ch):
        '''
            设置荧光信号解调相位。
            :param phase: 待设置相位参数
            :param ch: 待设置LIA解调通道，in [0, 1, 2, 3]
            :return:
            '''
        self.lockin.SetLockInPhase(phase, ch=2 * ch + CH_FLUO)

    def set_laser_phase(self, phase, ch):
        '''
            设置激光信号解调相位。
            :param phase: 待设置相位参数
            :param ch: 待设置LIA解调通道，in [0, 1, 2, 3]
            :return:
            '''
        self.lockin.SetLockInPhase(phase, ch=2 * ch + CH_LASER)

    def init_data_buf(self):
        self.data = [[] for ii in range(device_channel * 2)]
        return self.data

    def Freq_CW_test(self, start_f, step_f, stop_f, sg_mode, ch, save_fn=None, save_data_flag=True, plot_flag=True,
                     save_dir=None):  # 12.29-ZN 改变save_dir 仅用于Modu_Freq_Optimization
        """
            CW谱扫描函数，需设置起始频率、步长、截止频率，ch*2为荧光路数据
            @param start_f: 起始频率
            @param step_f: 步长
            @param stop_f: 终止频率
            @param save_data_flag: 存储数据
            @return: 一阶微分谱
            """

        # TODO：样例代码，注意LIA在202309改版之后返回的数据格式已改变，需要逐步修正剩余的函数，本函数待测试
        data_x, data_y = [], []
        fs = []
        ff = start_f

        data_all = [[] for i in range(14)]  # data_all[[]]

        # 单微波模式时只打开设置的通道的微波
        ch_id = ch
        # modu_den= self.parameter['lock_ch%d'%ch_id+'_flu_phase']
        # print 'ch_id:', ch_id
        while ff < stop_f:
            if not self.run_flag:
                break
            fs.append(ff)
            self.wavesource[ch_id].set_freq(ff)
            # self.wavesource[ch_id].set_fm_sens(val=modu_den)
            # TODO:数据的对应关系需要再检查一下
            res_all = self.lockin.GetLockInChannels_AllData(0.1)
            # res_all = [[0] for i in range(16)]
            time.sleep(0.1)

            # acquire all data
            for i in range(len(res_all)):
                data_all[i].append(np.mean(res_all[i]))

            data_x.append(np.mean(res_all[ch_id * 6 + 1]))
            data_y.append(np.mean(res_all[ch_id * 6 + 1 + 1]))

            # data_x.append(np.mean(res_all[ 1]))
            # data_y.append(np.mean(res_all[1 + 1]))

            print('freq:', ff, 'x:', data_x[-1], 'y:', data_y[-1])
            # 分别保存吸收谱和一阶微分谱

            ff += step_f
        # phase correction & slope calculation
        # res = []
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

        if save_data_flag:
            if (not save_dir):
                timestr = gettimestr()
                # dict_save(self.parameter, time.strftime(save_fn + timestr + '_CW.ini'))
                save_fig_fn = DATAPATH + timestr + '_CW_fig.png' if save_fn is None else save_fn + timestr + '_CW_fig.png'
                save_fig_fn_all = save_fig_fn.replace('fig.png', 'fig_allch.png')
                save_fn_all = DATAPATH + timestr + '_CW_allch.csv' if save_fn is None else save_fn + timestr + '_CW_allch.csv'
                save_fn = DATAPATH + timestr + '_CW_test.csv' if save_fn is None else save_fn + timestr + '_CW_test.csv'

                # Save fig
                if plot_flag:
                    total_1ch_raw_output(save_fig_fn, fs, [data_x, data_y], xlabel='Freq. (Hz)', ylabel='Signal (V)',
                                         legends=['X', 'Y'])
                    # total_allch_raw_output(save_fig_fn_all, fs, data_all, xlabel='Freq. (Hz)', ylabel='Signal (V)')

                print(save_fn)
                for i in range(len(data_all)):
                    print(len(data_all[i]))
                write_to_csv(save_fn, [fs, data_x, data_y, xp, yp])
            else:
                timestr = gettimestr()
                # dict_save(self.parameter, time.strftime(save_fn + timestr + '_CW.ini'))
                save_fig_fn = save_dir + timestr + '_CW_fig.png' if save_fn is None else save_fn + timestr + '_CW_fig.png'
                save_fig_fn_all = save_fig_fn.replace('fig.png', 'fig_allch.png')
                save_fn_all = save_dir + timestr + '_CW_allch.csv' if save_fn is None else save_fn + timestr + '_CW_allch.csv'
                save_fn = save_dir + timestr + '_CW_test.csv' if save_fn is None else save_fn + timestr + '_CW_test.csv'

                # Save fig
                if plot_flag:
                    total_1ch_raw_output(save_fig_fn, fs, [data_x, data_y], xlabel='Freq. (Hz)', ylabel='Signal (V)',
                                         legends=['X', 'Y'])
                    # total_allch_raw_output(save_fig_fn_all, fs, data_all, xlabel='Freq. (Hz)', ylabel='Signal (V)')

                print(save_fn)
                for i in range(len(data_all)):
                    print(len(data_all[i]))
                write_to_csv(save_fn, [fs, data_x, data_y, xp, yp])
            # write_to_csv(save_fn_all, [fs , data_all])

        return [fs, data_x, data_y, max_slope, xm, max_amp, max_amp_freq]

    def CW_test(self, start_f, step_f, stop_f, sg_mode, ch, save_fn=None, save_data_flag=True, plot_flag=True):
        """
            CW谱扫描函数，需设置起始频率、步长、截止频率，ch*2为荧光路数据
            @param start_f: 起始频率
            @param step_f: 步长
            @param stop_f: 终止频率
            @param save_data_flag: 存储数据
            @return: 一阶微分谱
            """

        # TODO：样例代码，注意LIA在202309改版之后返回的数据格式已改变，需要逐步修正剩余的函数，本函数待测试
        data_x, data_y = [], []
        fs = []
        ff = start_f

        data_all = [[] for i in range(14)]  # data_all[[]]

        # 单微波模式时只打开设置的通道的微波
        ch_id = ch
        # modu_den= self.parameter['lock_ch%d'%ch_id+'_flu_phase']
        # print 'ch_id:', ch_id
        while ff < stop_f:
            if not self.run_flag:
                break
            fs.append(ff)
            self.wavesource[ch_id].set_freq(ff)
            # self.wavesource[ch_id].set_fm_sens(val=modu_den)
            # TODO:数据的对应关系需要再检查一下
            res_all = self.lockin.GetLockInChannels_AllData(0.1)
            # res_all = [[0] for i in range(16)]
            time.sleep(0.1)

            # acquire all data
            for i in range(len(res_all)):
                data_all[i].append(np.mean(res_all[i]))

            data_x.append(np.mean(res_all[ch_id * 6 + 1]))
            data_y.append(np.mean(res_all[ch_id * 6 + 1 + 1]))

            # data_x.append(np.mean(res_all[ 1]))
            # data_y.append(np.mean(res_all[1 + 1]))

            print('freq:', ff, 'x:', data_x[-1], 'y:', data_y[-1])
            # 分别保存吸收谱和一阶微分谱

            ff += step_f
        # phase correction & slope calculation
        # res = []
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

        if save_data_flag:
            timestr = gettimestr()
            # dict_save(self.parameter, time.strftime(save_fn + timestr + '_CW.ini'))
            save_fig_fn = DATAPATH + timestr + '_CW_fig.png' if save_fn is None else save_fn + timestr + '_CW_fig.png'
            save_fig_fn_all = save_fig_fn.replace('fig.png', 'fig_allch.png')
            save_fn_all = DATAPATH + timestr + '_CW_allch.csv' if save_fn is None else save_fn + timestr + '_CW_allch.csv'
            save_fn = DATAPATH + timestr + '_CW_test.csv' if save_fn is None else save_fn + timestr + '_CW_test.csv'

            # Save fig
            if plot_flag:
                total_1ch_raw_output(save_fig_fn, fs, [data_x, data_y], xlabel='Freq. (Hz)', ylabel='Signal (V)',
                                     legends=['X', 'Y'])
                # total_allch_raw_output(save_fig_fn_all, fs, data_all, xlabel='Freq. (Hz)', ylabel='Signal (V)')

            print(save_fn)
            for i in range(len(data_all)):
                print(len(data_all[i]))
            write_to_csv(save_fn, [fs, data_x, data_y, xp, yp])
            # write_to_csv(save_fn_all, [fs , data_all])

        return [fs, data_x, data_y, max_slope, xm, max_amp, max_amp_freq]

    def channels_diff(self, ch1, ch2, coe):
        arr = np.array(ch1) - np.array(ch2) * coe
        return arr.tolist()

    def get_coe_and_diff_by_R(self, datas, return_std=True):
        """
            通过CH1X...CH2Y等4组数据得到coe
            :param datas:
            :return:
            """
        col1 = np.array(datas[0])
        col2 = np.array(datas[1])
        col3 = np.array(datas[2])
        col4 = np.array(datas[3])
        # 得到R分量
        r1 = np.sqrt(col1 ** 2 + col2 ** 2)
        r2 = np.sqrt(col3 ** 2 + col4 ** 2)
        diff_coe = r1.std() / r2.std()
        # 计算相消结果
        diff_x = self.channels_diff(col1, col3, diff_coe)
        diff_y = self.channels_diff(col2, col4, diff_coe)
        # diff_x = np.array(diff_x)
        # diff_y = np.array(diff_y)
        if return_std:
            return np.std(diff_x), np.std(diff_y), diff_coe
        else:
            return diff_x, diff_y, diff_coe

    def optimize_coe(self, datas):
        """
        计算？？？
        设备识别码：DNVCS-Lockin-DataStore-0057
        DataStore
        :param datas: 2d数组，x1、y1、x2、y2； list unlimmited unlimmited None
        """
        col1 = np.array(datas[0])
        col2 = np.array(datas[1])
        col3 = np.array(datas[2])
        col4 = np.array(datas[3])

        start_coe = 1
        res_coe_std = [[], []]
        start = -100.0
        step = 50.0
        sweep_num = 5

        origin_start = start
        while step > 0.001:
            # print(u'步长=%0.3f, 目前位置=%0.3f' % (step, start))
            for i in range(sweep_num):
                # X1/X2,Y1/Y2,2通道情形
                # d1 = self.channels_diff(data[0], data[2], 1, start_coe * (start + step * i))
                # d2 = self.channels_diff(data[1], data[3], 1, start_coe * (start + step * i))
                # res = np.mean([np.std(d1), np.std(d2)])
                # print(u'系数：%0.3f，STD：%0.4EV' % (1, start_coe))

                # 默认信号被调到X通道
                d1 = self.channels_diff(col1, col3, start_coe * (start + step * i))
                res = np.std(d1)
                res_coe_std[0].append(start_coe * (start + step * i))
                res_coe_std[1].append(res)

            ind = np.argmin(res_coe_std[1])
            start = np.max([res_coe_std[0][ind] / start_coe - step, origin_start])
            step = 2 * step / sweep_num

        # 返回最优系数以及相消后噪声
        optcoe = res_coe_std[0][ind]
        diff_x = self.channels_diff(col1, col3, optcoe)
        diff_y = self.channels_diff(col2, col4, optcoe)

        return np.std(diff_x), np.std(diff_y), optcoe

    def get_optimize_coe(self, data1, data2):
        """
        计算两列数据相消系数及噪声。
        设备识别码：DNVCS-Lockin-DataStore-0056
        DataStore
        :param data1: 待降噪数据 list unlimmited unlimmited None
        :param data2: 辅助相消数据 list unlimmited unlimmited None
        """
        '''
            计算两列数据相消系数及噪声。
            相消形式：cancelled_data = data1 - optcoe * data2

            :param data1: 待降噪数据
            :param data2: 辅助相消数据
            :return:
                - optcoe - 相消系数
                - opt_noise - 相消后噪声
                - raw_noise - 相消前噪声
            '''
        col1 = np.array(data1)
        col2 = np.array(data2)
        # 计算辅助数据
        mean_col1 = np.mean(col1)
        mean_col2 = np.mean(col2)
        # 计算协方差
        cov = 0
        for i in range(len(col1)):
            cov += (col1[i] - mean_col1) * (col2[i] - mean_col2)
        cov = cov / len(col1)
        try:
            optcoe = cov / (np.std(col2) ** 2)
        except:
            optcoe = 0
        # optcoe = np.std(col1)/np.std(col2)
        # 返回最优系数以及相消前后噪声
        diff_data = col1 - optcoe * col2
        raw_noise = np.std(col1)
        opt_noise = np.std(diff_data)
        print('频率： 相消前噪声：%e  相消后噪声：%e  相消系数：%e  相消比：%f\n' %
              (raw_noise, opt_noise, optcoe, raw_noise / opt_noise))
        fn = DATAPATH + "NoiseAcquire/"
        if(not os.path.exists(fn)):
            os.makedirs(fn)
        write_to_csv(fn + gettimestr() + '_optCoe.csv', [raw_noise, opt_noise, optcoe, raw_noise / opt_noise])
        # return optcoe, opt_noise, raw_noise, diff_data
        return raw_noise, optcoe, opt_noise, diff_data

    def phase_rotation(self, freq, mw_id, ch_id):
        # 新增于2019-12-09，旋转相位令信号集中到x通道
        for mid in range(4):
            if mid != mw_id:
                self.wavesource[mid].SetRFOn(False)
        self.wavesource[mw_id].SetRFOn(True)
        self.wavesource[mw_id].set_freq(freq)
        phases = list(range(0, 180, 5))
        datax = []
        datay = []
        dataz = []
        ph = []
        for phase in phases:
            ph.append(phase)
            for ii in range(4):
                self.lockin.SetLockInPhase(phase, ch=ii)
            time.sleep(0.2)
            res_all = self.lockin.GetLockInChannels(0.1)
            res = [np.mean(res_all[ch_id * 2]), np.mean(res_all[ch_id * 2 + 8])]
            datax.append(res[0])
            datay.append(res[1])
            dataz.append(np.abs(res[0] / np.sqrt(res[0] ** 2 + res[1] ** 2)))
            print('phase:', phase, 'x:', res[0], 'y:', res[1])
        pid = np.argmax(dataz)
        print('optimized phase:', pid)
        return ph, dataz

    def ExpRealtimeDisplay(self, save_fn=None, para_ini=True, ext_call=False, time_length=0.2):
        """
            单通道实时输出函数，需设定微波通道id
            :param save_fn:
            :param para_ini:初始化参数，True时设置微波功率
            :param ext_call:
            :return:
            """
        # TODO：样例代码，注意LIA在202309改版之后返回的数据格式已改变，需要逐步修正剩余的函数，本函数待测试

        ExpDataPath = 'ExpRealtimeDisplay/' + gettimestr() + '/'
        EXPDIR(ExpDataPath, self.parameter)

        # 关闭其他微波

        # freqs = [2.6e9 for i in range(len(self.wavesource))]
        # powers = [0 for i in range(len(self.wavesource))]

        # for ch_id in range(2):
        # self.wavesource[ch_id].set_freq(freqs[ch_id])
        # self.wavesource[ch_id].set_power(powers[ch_id])
        # self.wavesource[ch_id].start_output()
        mw_id = int(self.parameter['single_mode_id'])

        for ch_id in range(device_channel):
            if ch_id != mw_id:
                self.wavesource[ch_id].set_freq(self.parameter['mw_ch%d_start_freq' % ch_id])
                self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
                self.wavesource[ch_id].start_output()
            else:
                self.wavesource[ch_id].set_freq(self.parameter['Res_freq_%d' % ch_id])
                self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
                self.wavesource[ch_id].start_output()

        self.lockin.AcquireStart()
        self.run_flag = True

        # 1.18
        try:
            while self.run_flag:
                result = self.lockin.GetAcquireChannels(time_length)
                ts = np.linspace(0, time_length, len(result[0]))
                # print("result:",result)
                # print("LEN:",len(ts), len(result))

                if save_fn is None:
                    fn = DATAPATH + ExpDataPath + gettimestr() + '_realtime.csv'
                else:
                    fn = DATAPATH + gettimestr() + '_' + save_fn + '_realtime.csv'

                write_to_csv(fn, [ts] + list(result))
        except (KeyboardInterrupt, Exception) as e:
            print("KeyBoard")
            # self.lockin.AcquireStop()

            if save_fn is None:
                fn = DATAPATH + ExpDataPath + gettimestr() + '_realtime.csv'
            else:
                fn = DATAPATH + gettimestr() + '_' + save_fn + '_realtime.csv'

            write_to_csv(fn, [ts] + list(result))
            self.lockin.AcquireStop()
            LIA_mini_API.USB_END()
            if not ext_call:
                self.Stop()

        # while self.run_flag:
        #     ts, result = self.lockin.GetAcquireChannels(poll_time=0.2, get_time_stamps=True)
        #     xs += ts
        #     dat += result[0]
        #     # print(len(xs), len(dat))
        # self.lockin.AcquireStop()
        # if save_fn is None:
        #     fn = DATAPATH + gettimestr() + '_realtime.csv'
        # else:
        #     fn = DATAPATH + gettimestr() + '_' + save_fn + '_realtime.csv'
        # write_to_csv(fn, [xs] + [dat])
        #
        # if not ext_call:
        #     self.Stop()

    def ExpRealtimeDisplayDoubleMW(self, poll_time=0.2, save_fn=None, para_ini=True, ext_call=False):
        """
            无限时双微波输出磁场测量函数
            2023-06-12
            :param save_fn:
            :param para_ini:初始化参数，True时设置微波功率
            :param ext_call:
            :return:
            """
        # TODO：样例代码，注意LIA在202309改版之后返回的数据格式已改变，需要逐步修正剩余的函数，本函数待测试
        ExpDataPath = 'ExpRealtimeDisplayDoubleMW/'
        EXPDIR(ExpDataPath, self.parameter)

        # 设置各通道微波
        for ch_id in range(2):
            # self.wavesource.set_freq(self.parameter['Res_freq_%d' % (ch_id + 1)] * 1E9,ch=ch_id)
            self.wavesource[ch_id].set_freq(self.parameter['Res_freq_%d' % (ch_id + 1)] * 1E9)  # ch_id 0 1
            # self.wavesource.set_power(self.parameter['mw_ch%d_power' % ch_id], ch=ch_id)
            self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
            print(('set MW_ch%d freqneyc as %f GHz, power %f dBm' % (
                ch_id, self.parameter['Res_freq_%d' % (ch_id + 1)], self.parameter['mw_ch%d_power' % ch_id])))

        user_coe = [self.parameter['coe0'], self.parameter['coe1']]
        da = [[] for i in range(6)]
        self.lockin.AcquireStart()
        i = 0
        meas_count = 0
        data_proc = [[] for ii in
                     range(11)]  # 最终存储数据，格式为：时间戳、采样时间、0通道荧光电压、0通道激光电压、0通道相消电压、1通道荧光电压、1通道激光电压、1通道相消电压、0通道磁场、1通道磁场、双微波磁场
        spr = self.parameter['lockin_samp_rate']
        buffer_len = int(spr) * self.parameter['realtime_acquiring_time']  #
        self.run_flag = True
        while self.run_flag:
            # 数据采集
            ts, result = self.lockin.GetAcquireChannels(poll_time=0.2, get_time_stamps=True)
            # 时间和数据长度处理
            ts = np.array(ts)
            # x += list(ts)
            data_min_len = len(ts)
            tsystem = time.time()
            realtime = tsystem + ts[:data_min_len] - ts[:data_min_len][-1]
            data_proc[0] += list(realtime)
            data_proc[1] += list(ts) + (poll_time * (t % (int(poll_time * self.spr))))
            t = t + 1

            for ch_id in range(2):
                da[ch_id * 3] = result[ch_id * 2][:data_min_len]
                da[ch_id * 3 + 1] = result[ch_id * 2 + 1][:data_min_len]
                da[ch_id * 3 + 2] = self.channels_diff(result[ch_id * 2][:data_min_len],
                                                       result[ch_id * 2 + 1][:data_min_len], user_coe[ch_id])

            # 计算双微波磁场并存储
            data_proc[8] += list((np.array(da[2])) / self.parameter['channel0_slope'])  # 这里channel0_slope代表0通道电压磁场转化系数
            data_proc[9] += list((np.array(da[5])) / self.parameter['channel1_slope'])  # 这里channel1_slope代表1通道电压磁场转化系数
            data_proc[10] += list(
                (np.array(da[2]) - np.array(da[5])) / self.parameter['channel2_slope'])  # 这里channel2_slope代表双微波电压磁场转化系数

            for kk in range(6):
                data_proc[kk + 2] += list(da[kk][-data_min_len:])

            if i % 50 == 0:
                print((tsystem, i))
            i = i + 1
            print(len(data_proc[-1]))
            print('buffer_len:', buffer_len)

            if len(data_proc[-1]) > buffer_len:
                fname = DATAPATH + ExpDataPath + gettimestr() + '_traffic_monitor_%d.csv' % meas_count
                print(('Fluo CH1 ptp:', np.ptp(data_proc[8])))
                print(('Fluo CH2 ptp:', np.ptp(data_proc[9])))
                write_to_csv(fname, data_proc, row_to_col=True)

                # fn = DATAPATH + ExpDataPath+ gettimestr() +  '_Realtime_magnetData_%d.csv'% meas_count
                # write_to_csv(fn, data_proc[8:])
                t = 0
                da = [[] for i in range(6)]
                data_proc = [[] for ii in range(11)]
                meas_count += 1
                print(fname)
                # self.run_flag = False
        self.lockin.AcquireStop()
        if not ext_call:
            self.Stop()

    def FreqOptimizationExpSweepCW(self, save_fn=None, para_ini=True, plot_flag=False, ext_call=False,
                                   save_dir=None):  # 12.29-ZN-改变save_dir，仅用于Modu_Freq_Optimization
        """
            :param save_fn:
            :param para_ini:初始化参数，True时设置微波功率
            :param ext_call:
            :return:
            @param plot_flag:
            """

        dict_save(self.parameter, time.strftime(DATAPATH + '%Y-%m-%d %H_%M_%S',
                                                time.localtime(time.time())) + '.ini')
        print('ExpSweepCW:')

        for i in range(2):
            self.wavesource[i].set_freq(self.parameter['mw_ch%d_start_freq' % i], delay_flag=True)
            self.wavesource[i].set_power(self.parameter['mw_ch%d_power' % i], delay_flag=True)
            self.wavesource[i].set_fm_sens(self.parameter['mw_ch%d_fm_devi' % i], delay_flag=True)
            self.wavesource[i].mw_play()

        mw_id = int(self.parameter['single_mode_id'])
        sg_mode = int(self.parameter['single_mode'])
        print('set MW on')
        # if sg_mode:
        #     self.wavesource[mw_id].start_output()
        #     self.wavesource[1 - mw_id].stop_output()

        time.sleep(0.5)
        if para_ini:
            for ch_id in range(device_channel):
                if sg_mode and ch_id != mw_id:  # choose ch_id==mw_id
                    continue
                print('mw_ch%d_power:(dBm)' % ch_id, self.parameter['mw_ch%d_power' % ch_id])
                # self.wavesource[ch_id].set_freq(self.parameter['mw_ch%d_start_freq' % ch_id])
                # The power is changed, so I have to rechange the power
                # self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])

        # CW测试
        self.run_flag = True
        # self.plot_flag = True
        cwres = self.Freq_CW_test(self.parameter['mw_ch%d_start_freq' % mw_id],
                                  self.parameter['mw_ch%d_step_freq' % mw_id],
                                  self.parameter['mw_ch%d_stop_freq' % mw_id], sg_mode, mw_id, plot_flag=True,
                                  save_fn=save_fn, save_dir=save_dir)

        print('set MW off')
        self.wavesource[0].stop_output(all_ch=True)

        # 求出CW最大斜率以及对应的微波频率
        time.sleep(0.2)
        if not save_dir:
            if save_fn is None:
                fn = DATAPATH + gettimestr() + '_cw.csv'
            else:
                fn = DATAPATH + gettimestr() + '_' + save_fn + '_cw.csv'
            write_to_csv(fn, [cwres[3:]])
        else:
            if save_fn is None:
                fn = save_dir + gettimestr() + '_cw.csv'
            else:
                fn = save_dir + gettimestr() + '_' + save_fn + '_cw.csv'
            write_to_csv(fn, [cwres[3:]])

        if not ext_call:
            self.Stop()
        return cwres

    def ExpSweepCW(self, save_fn=None, para_ini=True, plot_flag=False, ext_call=False):
        """
            :param save_fn:
            :param para_ini:初始化参数，True时设置微波功率
            :param ext_call:
            :return:
            @param plot_flag:
            """

        dict_save(self.parameter, time.strftime(DATAPATH + '%Y-%m-%d %H_%M_%S',
                                                time.localtime(time.time())) + '.ini')
        print('ExpSweepCW:')

        # for i in range(2):
        # self.wavesource[i].set_freq(self.parameter['mw_ch%d_start_freq' % i], delay_flag=True)
        # self.wavesource[i].set_power(self.parameter['mw_ch%d_power' % i], delay_flag=True)
        # self.wavesource[i].set_fm_sens(self.parameter['mw_ch%d_fm_devi' % i], delay_flag=True)
        # self.wavesource[i].mw_play()

        mw_id = int(self.parameter['single_mode_id'])
        sg_mode = int(self.parameter['single_mode'])
        print('set MW on')
        # if sg_mode:
        #     self.wavesource[mw_id].start_output()
        #     self.wavesource[1 - mw_id].stop_output()

        time.sleep(0.5)
        if para_ini:
            for ch_id in range(device_channel):
                if sg_mode and ch_id != mw_id:  # choose ch_id==mw_id
                    continue
                print('mw_ch%d_power:(dBm)' % ch_id, self.parameter['mw_ch%d_power' % ch_id])
                # self.wavesource[ch_id].set_freq(self.parameter['mw_ch%d_start_freq' % ch_id])
                # The power is changed, so I have to rechange the power
                # self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])

        if not sg_mode:
            for ch_id in range(device_channel):
                self.wavesource[i].set_freq(self.parameter['mw_ch%d_start_freq' % ch_id], delay_flag=True)
                self.wavesource[i].set_power(self.parameter['mw_ch%d_power' % ch_id], delay_flag=True)
                self.wavesource[i].set_fm_sens(self.parameter['mw_ch%d_fm_devi' % ch_id], delay_flag=True)
                self.wavesource[i].mw_play()
                # time.sleep(0.01)
                # self.wavesource[i].mw_play()
                # CW测试
                self.run_flag = True
                # self.plot_flag = True
                cwres = self.CW_test(self.parameter['mw_ch%d_start_freq' % ch_id],
                                     self.parameter['mw_ch%d_step_freq' % ch_id],
                                     self.parameter['mw_ch%d_stop_freq' % ch_id], sg_mode, ch_id, plot_flag=True,
                                     save_fn=save_fn)

                print('set MW off')
                self.wavesource[ch_id].stop_output(all_ch=True)

                # 求出CW最大斜率以及对应的微波频率
                time.sleep(0.2)

                if save_fn is None:
                    fn = DATAPATH + gettimestr() + '_cw.csv'
                else:
                    fn = DATAPATH + gettimestr() + '_' + save_fn + '_cw.csv'
                write_to_csv(fn, [cwres[3:]])
        else:
            self.wavesource[mw_id].set_freq(self.parameter['mw_ch%d_start_freq' % mw_id], delay_flag=True)
            self.wavesource[mw_id].set_power(self.parameter['mw_ch%d_power' % mw_id], delay_flag=True)
            self.wavesource[mw_id].set_fm_sens(self.parameter['mw_ch%d_fm_devi' % mw_id], delay_flag=True)
            self.wavesource[mw_id].mw_play()
            # CW测试
            self.run_flag = True
            # self.plot_flag = True
            cwres = self.CW_test(self.parameter['mw_ch%d_start_freq' % mw_id],
                                 self.parameter['mw_ch%d_step_freq' % mw_id],
                                 self.parameter['mw_ch%d_stop_freq' % mw_id], sg_mode, mw_id, plot_flag=True,
                                 save_fn=save_fn)

            print('set MW off')
            self.wavesource[mw_id].stop_output(all_ch=True)

            # 求出CW最大斜率以及对应的微波频率
            time.sleep(0.2)

            if save_fn is None:
                fn = DATAPATH + gettimestr() + '_cw.csv'
            else:
                fn = DATAPATH + gettimestr() + '_' + save_fn + '_cw.csv'
            write_to_csv(fn, [cwres[3:]])

        if not ext_call:
            self.Stop()

        return cwres

    def ExpDAQTest(self, pnum=125, mw_start_freq=2.6e9, mw_stop_freq=3.1e9, freq_num=501, save_dir=None,
                   save_data_flag=True,
                   plot_flag=True, time_dir_flag=True, ext_call=False):
        '''
            观察DAQ直采信号的变化。
            :param start_curr:
            :param stop_curr:
            :param step_curr:
            :param pnum:
            :param save_dir:
            :param save_data_flag:
            :param plot_flag:
            :param time_dir_flag:
            :param ext_call:
            :return:
            '''
        # 直流采集ADC，采样率为250Hz
        exp_name = r'ExpDAQTest'
        if save_dir is None:
            save_dir, exp_info_fn = self.create_data_dir(exp_name=exp_name,
                                                         time_dir_flag=time_dir_flag, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + '_' + exp_name + '_log.txt'
        all_data = []
        daq_data = [[] for i in range(3)]

        mw_freq_list = np.linspace(mw_start_freq, mw_stop_freq, freq_num)

        for freq_id, freq in enumerate(mw_freq_list):
            for ch_id in range(device_channel):
                self.wavesource[ch_id].set_freq(freq)

            # 1. 采集DAQ模式下数据
            time.sleep(0.5)
            signal_data = self.lockin.GetDAQChannel(pnum)
            time_data = np.linspace(0, pnum / (250), pnum)
            all_data.append([signal_data, time_data])
            vpp_ch1 = np.mean(signal_data[0])
            vpp_ch2 = np.mean(signal_data[1])
            self.logg_exp_info(exp_info_fn, 'input_1=%e\ninput_2=%e\n'
                               % (vpp_ch1, vpp_ch2))
            daq_data[0].append(freq)
            daq_data[1].append(vpp_ch1)
            daq_data[2].append(vpp_ch2)
            if save_data_flag:
                time_str = gettimestr()
                save_fn = save_dir + time_str + '_DAQ.csv'
                write_to_csv(save_fn, [time_data] + signal_data)
                if plot_flag:
                    save_fig_fn = save_dir + time_str + '_DAQ.png'
                    total_1ch_raw_output(save_fig_fn, time_data, signal_data, xlabel='Time (us)',
                                         ylabel='Signal (normalized)', legends=['Input-1', 'Input-2'])
        # DAQ_data=np.array(daq_data)
        if save_data_flag:
            time_str = gettimestr()
            save_data_fn = save_dir + time_str + '_DAQ_data.csv'
            write_to_csv(save_data_fn, daq_data)
            if plot_flag:
                save_data_fig_fn = save_dir + time_str + '_DAQ_data.png'
                total_1ch_raw_output(save_data_fig_fn, daq_data[0], [daq_data[1], daq_data[2]], xlabel='Frequency (Hz)',
                                     ylabel='Signal (normalized)', legends=['Input-1', 'Input-2'])
        if not ext_call:
            self.Stop()
            self.is_running = False

    def Microwaveset(self):
        self.wavesource[0].set_power(3.0e1)
        # self.wavesource[1].set_power(0)
        self.wavesource[0].set_freq(2.935e9)
        # self.wavesource[1].set_freq(2.6e9)

    def ExpNoiseAcquiring(self, time_length, mw_mode='off', sig_ch=0, sig_col=0, save_dir=None, save_data_flag=True,
                          plot_flag=True, ext_call=False):
        '''
            2021-12-27
            :param time_length: 采集时间长度，单位s
            :param mode: 噪声测试模式
                'off'：所有通道微波关闭输出
                'fixed_params': 微波按默认实验参数输出
            :param sig_ch':相消用信号通道，0=1通道，1=2通道
            :param sig_col:相消用信号列，0=X信号列，1=Y信号列
            :param save_dir: 数据保存地址，为None时在默认路径保存
            :return:
            '''
        # 建立数据存储文件夹
        if save_dir is None:
            ExpDataPath = 'ExpNoiseAcquiring/'
            dirs = [ExpDataPath]
            for di in dirs:
                if not os.path.exists(DataPath + di):
                    os.mkdir(DataPath + di)
            save_dir = DataPath + ExpDataPath
        exp_info_txt = ''
        exp_info_txt += 'sig_channel: %d(0=1,1=2)\nsig_col:%d(0=x,1=y)\nmw_mode=%s' % (sig_ch, sig_col, mw_mode)
        dict_save(self.parameter, time.strftime(save_dir + '%Y-%m-%d %H_%M_%S',
                                                time.localtime(time.time())) + '.ini')
        # 设置微波输出模式
        if mw_mode == 'off':
            # self.set_all_mw(state='off')
            freqs = [2.6e9 for i in range(len(self.wavesource))]
            powers = [0 for i in range(len(self.wavesource))]

        elif mw_mode == 'fixed_params':
            # self.set_all_mw(state='on')
            if freqs is None:
                freqs = [2.6e9 for i in range(len(self.wavesource))]
        # #
        # for ch_id in range(2):
        # self.wavesource[ch_id].set_freq(freqs[ch_id])
        # self.wavesource[ch_id].set_power(powers[ch_id])

        self.wavesource[0].set_power(3.0e1)
        self.wavesource[1].set_power(0)
        self.wavesource[0].set_freq(2.8095e9)
        self.wavesource[1].set_freq(2.6e9)

        # 获取数据
        print('Start acquiring data: %.1f (s)' % time_length)
        res_all = self.lockin.GetLockInChannels(time_length)[:14]
        # for i in range(len(res_all)):
        # print(i, len(res_all[i]))
        time_data = np.linspace(0, time_length, len(res_all[0]))
        print('Time-domain data acquired.')

        opt_coe_list = [[] for i in range(device_channel)]
        opt_noise_list = [[] for i in range(device_channel)]
        raw_noise_list = [[] for i in range(device_channel)]
        diff_data_list = [[] for i in range(device_channel)]

        # 按四路解调频率分别进行相消
        for ch_id in range(device_channel):
            # signal_data = res_all[ch_id * 2 + sig_ch + (sig_col) * 8]  # Signal
            # ref_data = res_all[ch_id * 2 + (1 - sig_ch) + (sig_col) * 8]  # Reference

            # ch1xs = res_all[ch_id * 6 + 2]
            # ch1ys = res_all[ch_id * 6 + 1]
            # ch2xs = res_all[ch_id * 6 + 5]
            # ch2ys = res_all[ch_id * 6 + 5]

            # signal_data = res_all[ch_id * 6 + sig_ch + sig_col ]
            # ref_data  = res_all[ch_id * 1 + (1-sig_ch) + (1-sig_col) ]
            signal_data = res_all[ch_id * 6 + 1]
            ref_data = res_all[ch_id * 6 + 4]

            raw_noise, optcoe, opt_noise, diff_data = self.get_optimize_coe(signal_data, ref_data)
            print('频率%d： 相消前噪声：%e  相消后噪声：%e  相消系数：%e  相消比：%f\n' %
                  (ch_id, raw_noise, opt_noise, optcoe, raw_noise / opt_noise))
            diff_data_list[ch_id].append(diff_data)
            opt_coe_list[ch_id].append(optcoe)
            opt_noise_list[ch_id].append(opt_noise)
            raw_noise_list[ch_id].append(raw_noise)

            # x = res_all[ch_id * 2 + sig_ch + (sig_col) * 8]
            # y = res_all[ch_id * 2 + sig_ch + (1 - sig_col) * 8]
            # x = res_all[ch_id * 2 + sig_ch + (sig_col) ]
            # y = res_all[ch_id * 2 + sig_ch + (1 - sig_col) ]
            x = res_all[ch_id * 6 + 2]
            y = res_all[ch_id * 6 + 1]
            r = np.sqrt(np.array(x) ** 2 + np.array(y) ** 2)
            print('[CH%d] vpp_r=%e  vpp_x=%e  vpp_y=%e\n' % (ch_id, np.ptp(r), np.ptp(x), np.ptp(y)))

        if save_data_flag:
            timestr = gettimestr()
            save_td_fn = save_dir + timestr + '_time_domain.csv'
            save_coeff_fn = save_dir + timestr + '_coeff.csv'
            save_fig_fn = save_dir + timestr + '.png'
            save_fig_fn_all = save_dir + timestr + '_allch.png'
            codecs.open(save_dir + timestr + '_results.txt', 'w+', encoding='utf-8').write(exp_info_txt)
            write_to_csv(save_td_fn, [time_data] + list(res_all) + list(diff_data_list[0]) + list(diff_data_list[1]))
            write_to_csv(save_coeff_fn, opt_coe_list + opt_noise_list + raw_noise_list)
            if plot_flag:
                total_allch_cancellation_plot_2channel(save_fig_fn, time_data, res_all, sig_ch, sig_col, opt_coe_list)
                total_DoubleMW_allch_raw_output(save_fig_fn_all, time_data, res_all, xlabel='Time (s)',
                                                ylabel='Signal (V)')
        if not ext_call:
            self.Stop()
        return opt_coe_list, opt_noise_list, raw_noise_list

    # def ExpLockinFreqOptimizationNoiseAcquiring(self)
    # '''
    # 2021-12-27
    # :param time_length: 采集时间长度，单位s
    # :param mode: 噪声测试模式
    # 'off'：所有通道微波关闭输出
    # 'fixed_params': 微波按默认实验参数输出
    # :param sig_ch':相消用信号通道，0=1通道，1=2通道
    # :param sig_col:相消用信号列，0=X信号列，1=Y信号列
    # :param save_dir: 数据保存地址，为None时在默认路径保存
    # :return:
    # '''
    # # 建立数据存储文件夹
    # if save_dir is None:
    # ExpDataPath = 'ExpNoiseAcquiring/'
    # dirs = [ExpDataPath]
    # for di in dirs:
    # if not os.path.exists(DataPath + di):
    # os.mkdir(DataPath + di)
    # save_dir = DataPath + ExpDataPath
    # exp_info_txt = ''
    # exp_info_txt += 'sig_channel: %d(0=1,1=2)\nsig_col:%d(0=x,1=y)\nmw_mode=%s' % (sig_ch, sig_col, mw_mode)
    # dict_save(self.parameter, time.strftime(save_dir + '%Y-%m-%d %H_%M_%S',
    # time.localtime(time.time())) + '.ini')
    # # 设置微波输出模式
    # if mw_mode == 'off':
    # # self.set_all_mw(state='off')
    # freqs = [2.6e9 for i in range(len(self.wavesource))]
    # powers = [0 for i in range(len(self.wavesource))]

    # elif mw_mode == 'fixed_params':
    # # self.set_all_mw(state='on')
    # if freqs is None:
    # freqs = [2.6e9 for i in range(len(self.wavesource))]
    # #
    # # for ch_id in range(2):
    # # self.wavesource[ch_id].set_freq(freqs[ch_id])
    # # self.wavesource[ch_id].set_power(powers[ch_id])

    # # self.set_laser_phase(phase=335, ch=0)

    # self.wavesource[0].set_power(3.0e1)
    # self.wavesource[1].set_power(0)
    # self.wavesource[0].set_freq(2.8870e9)
    # self.wavesource[1].set_freq(2.6e9)
    # # self.set_laser_phase(335, ch=0)

    # # 获取数据
    # print('Start acquiring data: %.1f (s)' % time_length)
    # res_all = self.lockin.GetLockInChannels(time_length)[:14]
    # # for i in range(len(res_all)):
    # # print(i, len(res_all[i]))
    # time_data = np.linspace(0, time_length, len(res_all[0]))
    # print('Time-domain data acquired.')

    # opt_coe_list = [[] for i in range(device_channel)]
    # opt_noise_list = [[] for i in range(device_channel)]
    # raw_noise_list = [[] for i in range(device_channel)]
    # diff_data_list = [[] for i in range(device_channel)]

    # # 按四路解调频率分别进行相消
    # for ch_id in range(device_channel):
    # # signal_data = res_all[ch_id * 2 + sig_ch + (sig_col) * 8]  # Signal
    # # ref_data = res_all[ch_id * 2 + (1 - sig_ch) + (sig_col) * 8]  # Reference

    # # ch1xs = res_all[ch_id * 6 + 2]
    # # ch1ys = res_all[ch_id * 6 + 1]
    # # ch2xs = res_all[ch_id * 6 + 5]
    # # ch2ys = res_all[ch_id * 6 + 5]

    # # signal_data = res_all[ch_id * 6 + sig_ch + sig_col ]
    # # ref_data  = res_all[ch_id * 1 + (1-sig_ch) + (1-sig_col) ]
    # signal_data = res_all[ch_id * 6 + 1]
    # ref_data = res_all[ch_id * 6 + 4]

    # optcoe, opt_noise, raw_noise, diff_data = self.get_optimize_coe(signal_data, ref_data)
    # print('频率%d： 相消前噪声：%e  相消后噪声：%e  相消系数：%e  相消比：%f\n' %
    # (ch_id, raw_noise, opt_noise, optcoe, raw_noise / opt_noise))
    # diff_data_list[ch_id].append(diff_data)
    # opt_coe_list[ch_id].append(optcoe)
    # opt_noise_list[ch_id].append(opt_noise)
    # raw_noise_list[ch_id].append(raw_noise)

    # # x = res_all[ch_id * 2 + sig_ch + (sig_col) * 8]
    # # y = res_all[ch_id * 2 + sig_ch + (1 - sig_col) * 8]
    # # x = res_all[ch_id * 2 + sig_ch + (sig_col) ]
    # # y = res_all[ch_id * 2 + sig_ch + (1 - sig_col) ]
    # x = res_all[ch_id * 6 + 2]
    # y = res_all[ch_id * 6 + 1]
    # r = np.sqrt(np.array(x) ** 2 + np.array(y) ** 2)
    # print('[CH%d] vpp_r=%e  vpp_x=%e  vpp_y=%e\n' % (ch_id, np.ptp(r), np.ptp(x), np.ptp(y)))

    # if save_data_flag:
    # timestr = gettimestr()
    # save_td_fn = save_dir + timestr + '_time_domain.csv'
    # save_coeff_fn = save_dir + timestr + '_coeff.csv'
    # save_fig_fn = save_dir + timestr + '.png'
    # save_fig_fn_all = save_dir + timestr + '_allch.png'
    # codecs.open(save_dir + timestr + '_results.txt', 'w+', encoding='utf-8').write(exp_info_txt)
    # write_to_csv(save_td_fn, [time_data] + list(res_all) + list(diff_data_list[0]) + list(diff_data_list[1]))
    # write_to_csv(save_coeff_fn, opt_coe_list + opt_noise_list + raw_noise_list)
    # if plot_flag:
    # total_allch_cancellation_plot_2channel(save_fig_fn, time_data, res_all, sig_ch, sig_col, opt_coe_list)
    # total_DoubleMW_allch_raw_output(save_fig_fn_all, time_data, res_all, xlabel='Time (s)',
    # ylabel='Signal (V)')
    # if not ext_call:
    # self.Stop()
    # return opt_coe_list, opt_noise_list, raw_noise_list

    def ExpFluoPhaseOptimization(self, mode='full', scan_mode='fixed params', signal_col=0, mw_freq=2.87e9,
                                 start_phase=0, stop_phase=180, phase_pnum=37,
                                 save_dir=None, save_data_flag=True, time_dir_flag=True, plot_flag=True,
                                 ext_call=False):
        '''
            2021-12-28，荧光相位优化，将LIA解调所得的两列信号调到一列上。

            :param ch_id_list: 待优化通道id数组。
            :param mode: 荧光相位优化模式
                'full': 按完整流程进行优化，先扫CW谱获取幅度最大点，再进行相位扫描。
                'simplified': 按简化流程进行优化，按传入参数设置微波频率，再进行相位扫描。
            :param scan_mode: 荧光相位扫描模式
                'fixed params': 按默认参数扫描荧光相位。
                'passed params': 按传入参数扫描荧光相位。
            :param signal_col: 预计将优化到最大值的信号列，0=X信号列，1=Y信号列
            :param mw_freq: 传入微波频率参数，单位Hz，scan_mode='passed params'时生效
            :param save_dir: 数据保存路径
            :param save_data_flag: 判定是否保存优化数据
            :param plot_flag: 判定是否对优化数据进行作图
            :param ext_call: 判定是否为外部调用
            :return:
            '''
        # 创建数据存储目录
        if save_dir is None:
            save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpFluoPhaseOptimization',
                                                         time_dir_flag=time_dir_flag, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + '_logg.txt'

        # 相位扫描范围
        if scan_mode == 'fixed_params':
            # 按实验参数扫描相位
            start_phase = self.parameter['fluo_start_phase']
            stop_phase = self.parameter['fluo_stop_phase']
            phase_pnum = int(
                (self.parameter['fluo_stop_phase'] - self.parameter['fluo_start_phase'] + 0.0) / self.parameter[
                    'fluo_step_phase']) + 1
        elif scan_mode == 'passed params':
            # 按传入参数扫描相位
            pass
        phase_list = np.linspace(start_phase, stop_phase, phase_pnum)

        # 荧光相位优化，各通道独立进行
        opt_phase_list = []
        for i in range(2):
            self.wavesource[i].set_freq(self.parameter['mw_ch%d_start_freq' % i], delay_flag=True)
            self.wavesource[i].set_power(self.parameter['mw_ch%d_power' % i], delay_flag=True)
            self.wavesource[i].set_fm_sens(self.parameter['mw_ch%d_fm_devi' % i], delay_flag=True)
            self.wavesource[i].mw_play()

        mw_id = int(self.parameter['single_mode_id'])
        sg_mode = int(self.parameter['single_mode'])
        print('set MW on')

        for ch_id in range(1):
            if mode == 'full':
                # 以默认单通道微波id参数扫频，单独获取一张CW谱，得到幅度最大点微波频率
                # res = self.CW_test(start_f=self.parameter['mw_ch%d_start_freq' % mw_id], step_f=self.parameter['mw_ch%d_step_freq' % mw_id],
                #  stop_f=self.parameter['mw_ch%d_stop_freq' % mw_id], sg_mode=1, ch=mw_id, save_fn=save_dir, save_data_flag=save_data_flag, plot_flag=plot_flag)
                self.run_flag = True
                res = self.CW_test(self.parameter['mw_ch%d_start_freq' % ch_id],
                                   self.parameter['mw_ch%d_step_freq' % ch_id],
                                   self.parameter['mw_ch%d_stop_freq' % ch_id], sg_mode, ch_id, plot_flag=True,
                                   save_fn=save_dir)
                mw_freq = res[6]
                self.logg_exp_info(exp_info_fn, 'Max Amp Freq:%f  Max Amp:%f' % (mw_freq, res[5]))
            elif mode == 'simplified':
                # 按默认参数设置微波
                pass

            data, data_aff, ratio_list = [], [], []
            # 仅开启对应波源，并将频率设置到最大点上
            # todo: SPI success rate low?
            # self.set_all_mw(state='single', single_id=ch_id)
            # self.wavesource[ch_id].set_freq(mw_freq)

            for mw_id in range(device_channel):
                if mw_id != ch_id:
                    # self.wavesource[mw_id].SetRFOn(False)
                    self.wavesource[mw_id].stop_output()
                else:
                    # self.wavesource[mw_id].SetRFOn(False)
                    self.wavesource[mw_id].stop_output()
                    time.sleep(0.5)
                    # self.wavesource[mw_id].SetRFOn(True)
                    self.wavesource[mw_id].start_output()
                    time.sleep(0.5)

            self.wavesource[ch_id].set_freq(mw_freq)
            time.sleep(0.2)
            self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
            time.sleep(0.2)

            for ph_id, phase in enumerate(phase_list):
                # self.wavesource[ch_id].set_freq(mw_freq)
                # self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])

                self.set_fluo_phase(phase, ch_id)

                res_all = self.lockin.GetLockInChannels(0.1)
                data.append(np.mean(res_all[ch_id * 2 + 1]))
                data_aff.append(np.mean(res_all[ch_id * 2 + 2]))
                ratio_list.append(np.sqrt(data[-1] ** 2 / (data_aff[-1] ** 2 + data[-1] ** 2)))
            opt_phase_id = np.argmax(ratio_list)
            opt_phase = phase_list[opt_phase_id]
            self.logg_exp_info(exp_info_fn, '通道%d最优荧光相位：%.1f  signal:%f  zero:%f  ratio:%.3f' \
                               % (
                                   ch_id, opt_phase, data[opt_phase_id], data_aff[opt_phase_id],
                                   ratio_list[opt_phase_id]))

            # self.set_fluo_phase(opt_phase, ch_id)
            # self.CW_test(self.parameter['mw_ch%d_start_freq' % ch_id],
            #              self.parameter['mw_ch%d_step_freq' % ch_id],
            #              self.parameter['mw_ch%d_stop_freq' % ch_id], sg_mode, ch_id, plot_flag=True,
            #              save_fn=save_dir)

            opt_phase_list.append(opt_phase)
            if save_data_flag:
                timestr = gettimestr()
                save_fn = save_dir + timestr + '_fluo_phase_ch%d.csv' % ch_id
                save_fig_fn = save_dir + timestr + '_fluo_phase_ch%d.png' % ch_id
                save_fig_fn_ratio = save_dir + timestr + '_fluo_phase_ratio_ch%d.png' % ch_id
                write_to_csv(save_fn, [list(phase_list), data, data_aff, ratio_list])
                if plot_flag:
                    # total_1ch_raw_output(save_fig_fn, phase_list, [data, data_aff], xlabel='Phase ($^\circ$)',
                    #                      ylabel='Signal (V)',
                    #                      legends=[COL[signal_col], COL[1 - signal_col]])
                    total_1ch_raw_output(save_fig_fn_ratio, phase_list, [ratio_list], xlabel='Phase ($^\circ$)',
                                         ylabel=r'Ratio')
        if not ext_call:
            self.Stop()
        return opt_phase

    # def ExpFluoPhaseOptimization(self,  mode='full', scan_mode='fixed params', signal_col=0, mw_freq=2.87e9,
    #                              start_phase=0, stop_phase=180, phase_pnum=37,
    #                              save_dir=None, save_data_flag=True, time_dir_flag=False, plot_flag=True,
    #                              ext_call=False):
    #     '''
    #     2021-12-28，荧光相位优化，将LIA解调所得的两列信号调到一列上。
    #
    #     :param ch_id_list: 待优化通道id数组。
    #     :param mode: 荧光相位优化模式
    #         'full': 按完整流程进行优化，先扫CW谱获取幅度最大点，再进行相位扫描。
    #         'simplified': 按简化流程进行优化，按传入参数设置微波频率，再进行相位扫描。
    #     :param scan_mode: 荧光相位扫描模式
    #         'fixed params': 按默认参数扫描荧光相位。
    #         'passed params': 按传入参数扫描荧光相位。
    #     :param signal_col: 预计将优化到最大值的信号列，0=X信号列，1=Y信号列
    #     :param mw_freq: 传入微波频率参数，单位Hz，scan_mode='passed params'时生效
    #     :param save_dir: 数据保存路径
    #     :param save_data_flag: 判定是否保存优化数据
    #     :param plot_flag: 判定是否对优化数据进行作图
    #     :param ext_call: 判定是否为外部调用
    #     :return:
    #     '''
    #     # 创建数据存储目录
    #     if save_dir is None:
    #         save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpFluoPhaseOptimization',
    #                                                      time_dir_flag=time_dir_flag, exp_info_flag=True)
    #     else:
    #         exp_info_fn = save_dir + gettimestr() + '_logg.txt'
    #
    #     # 相位扫描范围
    #     if scan_mode == 'fixed_params':
    #         # 按实验参数扫描相位
    #         start_phase = self.parameter['fluo_start_phase']
    #         stop_phase = self.parameter['fluo_stop_phase']
    #         phase_pnum = int(
    #             (self.parameter['fluo_stop_phase'] - self.parameter['fluo_start_phase'] + 0.0) / self.parameter[
    #                 'fluo_step_phase']) + 1
    #     elif scan_mode == 'passed params':
    #         # 按传入参数扫描相位
    #         pass
    #     phase_list = np.linspace(start_phase, stop_phase, phase_pnum)
    #
    #     # 荧光相位优化，各通道独立进行
    #     opt_phase_list = []
    #     for i in range(2):
    #         self.wavesource[i].set_freq(self.parameter['mw_ch%d_start_freq' % i], delay_flag=True)
    #         self.wavesource[i].set_power(self.parameter['mw_ch%d_power' % i], delay_flag=True)
    #         self.wavesource[i].set_fm_sens(self.parameter['mw_ch%d_fm_devi' % i], delay_flag=True)
    #         self.wavesource[i].mw_play()
    #
    #     mw_id = int(self.parameter['single_mode_id'])
    #     sg_mode = int(self.parameter['single_mode'])
    #     print('set MW on')
    #
    #     for ch_id in range(1):
    #         if mode == 'full':
    #             # 以默认单通道微波id参数扫频，单独获取一张CW谱，得到幅度最大点微波频率
    #             # res = self.CW_test(start_f=self.parameter['mw_ch%d_start_freq' % mw_id], step_f=self.parameter['mw_ch%d_step_freq' % mw_id],
    #             #  stop_f=self.parameter['mw_ch%d_stop_freq' % mw_id], sg_mode=1, ch=mw_id, save_fn=save_dir, save_data_flag=save_data_flag, plot_flag=plot_flag)
    #             self.run_flag = True
    #             res = self.CW_test(self.parameter['mw_ch%d_start_freq' % mw_id],
    #                                  self.parameter['mw_ch%d_step_freq' % mw_id],
    #                                  self.parameter['mw_ch%d_stop_freq' % mw_id], sg_mode, mw_id, plot_flag=True,
    #                                  save_fn=save_dir)
    #             mw_freq = res[6]
    #             self.logg_exp_info(exp_info_fn, 'Max Amp Freq:%f  Max Amp:%f' % (mw_freq, res[5]))
    #         elif mode == 'simplified':
    #             # 按默认参数设置微波
    #             pass
    #
    #         data, data_aff, ratio_list = [], [], []
    #         # 仅开启对应波源，并将频率设置到最大点上
    #         # todo: SPI success rate low?
    #         # self.set_all_mw(state='single', single_id=ch_id)
    #         # self.wavesource[ch_id].set_freq(mw_freq)
    #
    #         for mw_id in range(device_channel):
    #             if mw_id != ch_id:
    #                 # self.wavesource[mw_id].SetRFOn(False)
    #                 self.wavesource[mw_id].stop_output()
    #             else:
    #                 # self.wavesource[mw_id].SetRFOn(False)
    #                 self.wavesource[mw_id].stop_output()
    #                 time.sleep(0.5)
    #                 # self.wavesource[mw_id].SetRFOn(True)
    #                 self.wavesource[mw_id].start_output()
    #                 time.sleep(0.5)
    #
    #         self.wavesource[ch_id].set_freq(mw_freq)
    #         time.sleep(0.2)
    #         self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
    #         time.sleep(0.2)
    #
    #         for ph_id, phase in enumerate(phase_list):
    #             # self.wavesource[ch_id].set_freq(mw_freq)
    #             # self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
    #
    #             self.set_fluo_phase(phase, ch_id)
    #
    #             res_all = self.lockin.GetLockInChannels(0.1)
    #             data.append(np.mean(res_all[ch_id * 2 + CH_FLUO + 8 * signal_col]))
    #             data_aff.append(np.mean(res_all[ch_id * 2 + CH_FLUO + 8 * (1 - signal_col)]))
    #             ratio_list.append(np.sqrt(data[-1] ** 2 / (data_aff[-1] ** 2 + data[-1] ** 2)))
    #         opt_phase_id = np.argmax(ratio_list)
    #         opt_phase = phase_list[opt_phase_id]
    #         self.logg_exp_info(exp_info_fn, '通道%d最优荧光相位：%.1f  signal:%f  zero:%f  ratio:%.3f' \
    #                            % (
    #                                ch_id, opt_phase, data[opt_phase_id], data_aff[opt_phase_id],
    #                                ratio_list[opt_phase_id]))
    #         opt_phase_list.append(opt_phase)
    #         if save_data_flag:
    #             timestr = gettimestr()
    #             save_fn = save_dir + timestr + '_fluo_phase_ch%d.csv' % ch_id
    #             save_fig_fn = save_dir + timestr + '_fluo_phase_ch%d.png' % ch_id
    #             save_fig_fn_ratio = save_dir + timestr + '_fluo_phase_ratio_ch%d.png' % ch_id
    #             write_to_csv(save_fn, [list(phase_list), data, data_aff, ratio_list])
    #             if plot_flag:
    #                 total_1ch_raw_output(save_fig_fn, phase_list, [data, data_aff], xlabel='Phase ($^\circ$)',
    #                                      ylabel='Signal (V)',
    #                                      legends=[COL[signal_col], COL[1 - signal_col]])
    #                 # total_1ch_raw_output(save_fig_fn_ratio, phase_list, [ratio_list], xlabel='Phase ($^\circ$)',
    #                 #                     ylabel=r'Ratio')
    #     if not ext_call:
    #         self.Stop()
    #     return opt_phase_list

    def ExpLaserPhaseOptimization(self, time_length=10, scan_mode='fixed params', signal_col=0,
                                  start_phase=0, stop_phase=180, phase_pnum=10,
                                  save_dir=None, save_data_flag=True, time_dir_flag=False, plot_flag=True,
                                  ext_call=False):
        '''
            2021-12-30，激光相位优化，通过相消倍率获取最优相位。
            采集荧光数据时将所有微波输出通道调到[2.6GHz，0dBm]。

            :param time_length: 单次激光相位所需采集时间长度
            :param scan_mode: 激光相位扫描模式
                'fixed params': 按默认参数扫描参考激光相位。
                'passed params': 按传入参数扫描参考激光相位。
            :param signal_col: 预计将优化到最大值的信号列，0=X信号列，1=Y信号列
            :param save_dir: 数据保存路径
            :param save_data_flag: 判定是否保存优化数据
            :param plot_flag: 判定是否对优化数据进行作图
            :param ext_call: 判定是否为外部调用
            :return:
            '''

        # 创建数据存储目录
        if save_dir is None:
            save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpLaserPhaseOptimization',
                                                         time_dir_flag=True, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + '_logg.txt'

        phase_list = np.linspace(start_phase, stop_phase, phase_pnum)

        opt_coe = [[] for i in range(device_channel)]
        opt_noise = [[] for i in range(device_channel)]
        raw_noise = [[] for i in range(device_channel)]
        optimized_phase = [[] for i in range(device_channel)]
        cancelled_noise = [[] for i in range(device_channel)]
        cancelled_ratio = [[] for i in range(device_channel)]
        # 开始扫描数据
        for ph_id, phase in enumerate(phase_list):
            # 设置各解调频率激光路相位
            for ch_id in range(device_channel):
                self.set_laser_phase(phase, ch=ch_id)
            # 进行数据采集与相消
            opt_coe_list, opt_noise_list, raw_noise_list = self.ExpNoiseAcquiring(time_length=time_length,
                                                                                  mw_mode='off', sig_ch=0,
                                                                                  sig_col=signal_col,
                                                                                  save_dir=save_dir,
                                                                                  save_data_flag=save_data_flag,
                                                                                  plot_flag=plot_flag, ext_call=True)
            for ch_id in range(device_channel):
                opt_coe[ch_id].append(opt_coe_list[ch_id][0])
                opt_noise[ch_id].append(opt_noise_list[ch_id][0])
                raw_noise[ch_id].append(raw_noise_list[ch_id][0])
                # 保存各通道数据
                self.logg_exp_info(exp_info_fn,
                                   'CH%d:laser_phase:%f  noise:%e  cancelled_noise:%e  coeff:%e  ratio:%f' %
                                   (ch_id, phase, raw_noise[ch_id][-1], opt_noise[ch_id][-1], opt_coe[ch_id][-1],
                                    raw_noise[ch_id][-1] / opt_noise[ch_id][-1]))
        # 获取最优相消相位，以相消后最小噪声为标准/以相消比为标准
        for ch_id in range(device_channel):
            opt_ch_id = np.argmin(opt_noise[ch_id])
            optimized_phase[ch_id] = phase_list[opt_ch_id]
            cancelled_noise[ch_id] = opt_noise[ch_id][opt_ch_id]
            cancelled_ratio[ch_id] = raw_noise[ch_id][opt_ch_id] / opt_noise[ch_id][opt_ch_id]
            self.logg_exp_info(exp_info_fn, '\nCH%d:(noise)optimized_phase:%f  noise:%e  cancelled_noise:%e  ratio:%f' %
                               (ch_id, phase_list[opt_ch_id], raw_noise[ch_id][opt_ch_id], opt_noise[ch_id][opt_ch_id],
                                raw_noise[ch_id][opt_ch_id] / opt_noise[ch_id][opt_ch_id]))
            opt_ch_id = np.argmax(np.array(raw_noise[ch_id]) / np.array(opt_noise[ch_id]))
            self.logg_exp_info(exp_info_fn, '\nCH%d:(ratio)optimized_phase:%f  noise:%e  cancelled_noise:%e  ratio:%f' %
                               (ch_id, phase_list[opt_ch_id], raw_noise[ch_id][opt_ch_id], opt_noise[ch_id][opt_ch_id],
                                raw_noise[ch_id][opt_ch_id] / opt_noise[ch_id][opt_ch_id]))
        if save_data_flag:
            timestr = gettimestr()
            save_fn = save_dir + timestr + '_laser_phase.csv'
            save_fig_fn_ratio = save_dir + timestr + '_laser_phase_ratio_ch%d.png' % ch_id
            write_to_csv(save_fn, [list(phase_list), raw_noise[0], opt_noise[0], opt_coe[0], raw_noise[1], opt_noise[1],
                                   opt_coe[1]])
            # if plot_flag:
            #     for ch_id in range(device_channel):
            #         save_fig_fn = save_dir + timestr + '_laser_phase_ch%d.png' % ch_id
            #         total_1ch_raw_output(save_fig_fn, phase_list, [raw_noise[ch_id], opt_noise[ch_id]],
            #                              xl4abel='Phase ($^\circ$)', ylabel='Signal (V)',
            #                              legends=['CH%d-noise' % ch_id, 'CH%d-cancelled noise' % ch_id])
        if not ext_call:
            self.Stop()
            return cancelled_noise, optimized_phase, cancelled_ratio

    def ExpLockinFreqOptimization(self, scan_mode='fixed params', signal_col=0,
                                  start_Modu_freq=50000.0, stop_Modu_freq=100000.0, Modu_freq_pnum=10,
                                  save_dir=None, save_data_flag=True, time_dir_flag=False, plot_flag=True,
                                  ext_call=False):

        # 创建数据存储目录
        if save_dir is None:
            save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpLockinfreqOptimization',
                                                         time_dir_flag=True, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + '_logg.txt'
        exp_info_fs = save_dir + gettimestr() + '_max_test.txt'

        # freq_list = np.linspace(start_Modu_freq, stop_Modu_freq,Modu_freq_pnum)
        freq_list = np.logspace(start_Modu_freq, stop_Modu_freq, Modu_freq_pnum)

        data_all = []

        with open(save_dir + "ExpLockinfreqOptimization_test.csv", "w") as f:

            # 开始扫描数据
            for freq_id, freq in enumerate(freq_list):
                for ch_id in range(device_channel):
                    self.lockin.SetLockInFreq(freq, ch_id)

                fluo_opt_path = save_dir + '/ExpFluoPhaseOptimization/' + str(freq) + "/"
                if (not os.path.exists(fluo_opt_path)):
                    os.makedirs(fluo_opt_path)
                fluo_opt_phase = self.ExpFluoPhaseOptimization(start_phase=-90, stop_phase=90, phase_pnum=37,
                                                               save_dir=fluo_opt_path)
                time.sleep(0.5)

                self.set_fluo_phase(fluo_opt_phase, ch=0)
                cw_path = save_dir + '/ExpSweepCW/' + str(freq) + "/"
                if (not os.path.exists(cw_path)):
                    os.makedirs(cw_path)
                cwres = self.FreqOptimizationExpSweepCW(save_dir=cw_path)
                time.sleep(0.5)

                Noise_path = save_dir + '/ExPNoiseAcquring/' + str(freq) + "/"
                if (not os.path.exists(Noise_path)):
                    os.makedirs(Noise_path)
                opt_coe_list, opt_noise_list, raw_noise_list = mexp.ExpNoiseAcquiring(time_length=10,
                                                                                      save_dir=Noise_path)
                time.sleep(0.5)

                # laser_opt_path = save_dir+"ExpLaserPhaseOptimization/"+str(freq)+'/'
                # if(not os.path.exists(laser_opt_path)):
                # os.makedirs(laser_opt_path)
                # opt_noise, laser_opt_phase, cancelled_ratio = self.ExpLaserPhaseOptimization(
                # time_length=10, start_phase=0, stop_phase=360,phase_pnum=73,
                # save_dir=laser_opt_path)
                SNR = cwres[3] / opt_noise_list
                print('%e\n%e' % (SNR[0], SNR[1]))

                # # 保存各通道数据
                # self.logg_exp_info(exp_info_fn, 'freq:%d  Ks:%e  cancelled noise:%e  SNR:%e  Fluo_phase :%f  Laser_phase:%f Cancelled_ratio:%f'
                # % (freq, cwres[3], opt_noise[0], SNR[0], fluo_opt_phase, laser_opt_phase[0], cancelled_ratio[0]))
                # data_all.append([freq, cwres[3], opt_noise[0], SNR[0], fluo_opt_phase, laser_opt_phase[0], cancelled_ratio[0]])
                # f.write(','.join([str(s) for s in data_all[-1]])+'\n')
                # f.flush()
                # # freq_list.append(freq)

                # max_SNR_id = np.argmax(max([sep_data[3] for sep_data in data_all]))
                # self.logg_exp_info(exp_info_fs, 'Max_Modu_freq:%d  Max_Ks:%e  cancelled noise:%e  Max_SNR:%e  Fluo_phase :%f  Laser_phase:%f Cancelled_ratio:%f'
                # % (data_all[max_SNR_id][0], data_all[max_SNR_id][1], data_all[max_SNR_id][2],
                # data_all[max_SNR_id][3], data_all[max_SNR_id][4], data_all[max_SNR_id][5], data_all[max_SNR_id][6]))

                # 保存各通道数据
                self.logg_exp_info(exp_info_fn, 'freq:%d  Ks:%e  cancelled noise:%e  SNR:%e  Fluo_phase :%f'
                                   % (freq, cwres[3], opt_noise_list[0][0], SNR[0], fluo_opt_phase))
                data_all.append([freq, cwres[3], opt_noise_list[0][0], SNR[0], fluo_opt_phase])
                f.write(','.join([str(s) for s in data_all[-1]]) + '\n')
                f.flush()
                # freq_list.append(freq)

            max_SNR_id = np.argmax(max([sep_data[3] for sep_data in data_all]))
            self.logg_exp_info(exp_info_fs,
                               'Max_Modu_freq:%d  Max_Ks:%e  cancelled noise:%e  Max_SNR:%e  Fluo_phase :%f'
                               % (data_all[max_SNR_id][0], data_all[max_SNR_id][1], data_all[max_SNR_id][2],
                                  data_all[max_SNR_id][3], data_all[max_SNR_id][4]))

            if not ext_call:
                self.Stop()

    def ExpDoubleMWResFrequencyOPM(self, time_length=20.0, save_fn=None, para_ini=True, ext_call=False):
        """
            小范围双微波共振频率选择优化
            :param save_fn:
            :param para_ini:初始化参数，True时设置微波功率
            :param ext_call:
            :return:
            """
        ExpDataPath = 'ExpDoubleMWResFrequencyOPM/'
        dirs = [ExpDataPath]
        for di in dirs:
            if not os.path.exists(DATAPATH + di):
                os.mkdir(DATAPATH + di)
        dict_save(self.parameter, time.strftime(DATAPATH + ExpDataPath + '%Y-%m-%d %H_%M_%S',
                                                time.localtime(time.time())) + '.ini')

        # 微波扫描参数空间范围
        start_fre_1 = self.parameter['mw_fluo_start_freq']
        stop_fre_1 = self.parameter['mw_fluo_stop_freq']
        fre_pnum_1 = 2
        freq_list_1 = np.linspace(start_fre_1, stop_fre_1, fre_pnum_1)

        start_fre_2 = self.parameter['mw_fluo_start_freq'] + 145.0E6
        stop_fre_2 = self.parameter['mw_fluo_stop_freq'] + 145.0E6
        fre_pnum_2 = 2
        freq_list_2 = np.linspace(start_fre_2, stop_fre_2, fre_pnum_2)

        # 循环设置微波频率，测相同时间的数据
        for jj in range(len(freq_list_1)):
            for kk in range(len(freq_list_2)):
                # 设置使用微波的通道，并关闭其他通道微波
                ch_id_list = [0, 1]
                for ch_id in ch_id_list:
                    if ch_id == 0:
                        self.wavesource[ch_id].set_freq(freq_list_1[jj])
                        self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
                        print(('set MW_ch%d_frequency as %f' % (ch_id, freq_list_1[jj])))
                    else:
                        self.wavesource[ch_id].set_freq(freq_list_2[kk])
                        self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
                        print(('set MW_ch%d_frequency as %f' % (ch_id, freq_list_2[kk])))
                for ii in [2, 3]:
                    self.wavesource[ii].SetRFOn(False)

                user_coe = [self.parameter['coe0'], self.parameter['coe1']]

                # 获取数据
                print(('Start acquiring data: %.1f (s)' % time_length))
                res_all = self.lockin.GetLockInChannels(time_length)
                time_data = np.linspace(0, time_length, len(res_all[0]))

                da = [[] for ii in range(8)]
                da[0] = time_data
                for ch_id in range(2):
                    da[ch_id * 3 + 1] = res_all[ch_id * 2]  # Signal
                    da[ch_id * 3 + 2] = res_all[ch_id * 2 + 1]  # Reference
                    da[ch_id * 3 + 3] = self.channels_diff(da[ch_id * 3 + 1], da[ch_id * 3 + 2],
                                                           user_coe[ch_id])  # cancel
                # 计算分别相消后双微波信号相加结果
                da[7] += list((np.array(da[3]) - np.array(da[6])))

                if save_fn is None:
                    fn = DATAPATH + gettimestr() + '_realtime_MW1=%fHz_MW2=%fHz.csv' % (
                        freq_list_1[jj], freq_list_2[kk])
                else:
                    fn = DATAPATH + gettimestr() + '_' + save_fn + '_realtime_MW1=%fHz_MW2=%fHz.csv' % (
                        freq_list_1[jj], freq_list_2[kk])
                write_to_csv(fn, da)

        if not ext_call:
            self.Stop()

    def ExpPIDmeas1axis(self, ext_call=False):
        """
            PID单通道读取数据
            @param ext_call:
            @return:
            """
        ExpDataPath = 'ExpPIDmeas1axis/'
        dirs = [ExpDataPath]
        for di in dirs:
            if not os.path.exists(DATAPATH + di):
                os.mkdir(DATAPATH + di)
        dict_save(self.parameter, time.strftime(DATAPATH + ExpDataPath + '%Y-%m-%d %H_%M_%S',
                                                time.localtime(time.time())) + '.ini')

        # 开启特定通道微波
        ch_id = int(self.parameter['single_mode_id'])
        self.wavesource[ch_id].set_freq(self.parameter['mw_ch%d_start_freq' % ch_id])
        self.wavesource[ch_id].set_power(self.parameter['mw_ch%d_power' % ch_id])
        for ii in range(device_channel):
            if ii != ch_id:
                self.wavesource[ii].SetRFOn(False)
        spr = self.lockin.GetDataSampleRate()

        # 为防止出错，4个通道PID需全开
        set_point = []
        output_offset = []
        kp = []
        ki = []
        kd = []
        for ii in range(device_channel):
            # 输出参考点,默认参考值为0,默认参考通道为x
            set_point.append(0)
            # 初始输出频率
            output_offset.append(self.parameter['mw_ch%d_start_freq' % ii] / 1e3)
            # PID参数
            kp.append(self.parameter['kp_%d'] % ii)
            ki.append(self.parameter['ki_%d'] % ii)
            ki.append(self.parameter['kd_%d'] % ii)
            self.lockin.SetPIDParameters(1 + ii, set_point[ii], output_offset[ii], kp=kp[ii], ki=ki[ii],
                                         kd=kd[ii])
        self.lockin.PID_Enable()
        self.lockin.AcquireStartV2_PID(wait_trig=True)

        # 读数据
        i = 0
        # 频率偏移数据:格式为：绝对时间、相对时间、频率偏移
        mag_data = [[] for ii in range(3)]
        # 原始数据:格式为第一列时间，往后每四列为一个通道的x,y,误差项,反馈项
        raw_data = [[] for ii in range(17)]
        stsystem = time.time()
        meas_count = 0
        buffer_len = int(spr) * 20
        while self.run_flag:
            ts, result = self.lockin.GetAcquireChannelsV2_PID(poll_time=0.2, get_time_stamps=True)
            ts = np.array(ts) / spr
            # x += list(ts)
            # x = np.append(x,ts)
            # 时间数据
            data_min_len = len(ts)
            tsystem = time.time()
            realtime = tsystem + ts[:data_min_len] - ts[:data_min_len][-1]
            mag_data[0] += list(realtime)
            mag_data[1] += list(ts)
            raw_data[0] += list(ts)
            # 处理得到频率偏移
            err = result[ch_id * 4 + 2]
            feedback = result[ch_id * 4 + 3]
            # 信号输出偏移项
            freq_err1 = np.array(err) / self.parameter['channel%d_slope' % ch_id]
            # 频率设定偏移项
            freq_err2 = np.array(feedback) - output_offset
            # 总偏移项(Hz)
            freq_err = (freq_err1 + freq_err2) * 1e3
            mag_data[3] += list(freq_err)

            for ii in range(16):
                raw_data[ii + 1] += list(result[ii])

            if i % 50 == 0:
                print(tsystem, i)
            i = i + 1

            if len(mag_data[-1]) > buffer_len:
                # fn = DATAPATH + gettimestr() + '_realtime_3Axis_data.csv' if save_fn is None else save_fn
                fname = DATAPATH + ExpDataPath + gettimestr() + '_traffic_monitor_%d.csv' % meas_count
                write_to_csv(fname, mag_data, row_to_col=True)
                fnraw = DATAPATH + ExpDataPath + gettimestr() + '_traffic_monitor_%d_rawdata.csv' % meas_count
                write_to_csv(fnraw, raw_data, row_to_col=True)
                mag_data = [[] for ii in range(5)]
                raw_data = [[] for ii in range(17)]
                meas_count += 1
                print(fname)

        self.lockin.PID_Disable()
        if not ext_call:
            self.Stop()

    # def ExpSweep4CW(self, save_dir=None, save_data_flag=True, time_dir_flag=False, plot_flag=True, ext_call=False):
    # '''
    # 四通道同步CW扫频函数。

    # :param save_dir:
    # :param save_data_flag:
    # :param time_dir_flag:
    # :param plot_flag:
    # :param ext_call:
    # :return:
    # '''
    # # 创建数据存储目录
    # if save_dir is None:
    # save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpSweep4CW',
    # time_dir_flag=time_dir_flag, exp_info_flag=True)
    # else:
    # exp_info_fn = save_dir + gettimestr() + '_logg.txt'
    # current_freq_list = [0, 0, 0, 0]
    # freq_data = [[] for i in range(4)]
    # res_fluo_data = [[] for i in range(16)]

    # algo_run_flag = True  # 运行状态标识符
    # search_cnt = 0

    # while algo_run_flag:
    # # 获取更新频率后数据
    # # print 'search cnt:', search_cnt
    # algo_run_flag = False
    # for ch_id in range(4):  # 更新频率
    # current_freq_list[ch_id] = self.parameter['mw_ch%d_start_freq' % ch_id] + self.parameter['mw_ch%d_step_freq' % ch_id] * search_cnt
    # if current_freq_list[ch_id] >= self.parameter['mw_ch%d_stop_freq' % ch_id]:
    # current_freq_list[ch_id] = self.parameter['mw_ch%d_stop_freq' % ch_id]
    # else:
    # algo_run_flag = True
    # freq_data[ch_id].append(current_freq_list[ch_id])

    # self.set_all_mw(freqs=current_freq_list)
    # # time.sleep(6 * self.lockin.GetLockInTimeConst())
    # res = self.lockin.GetLockInChannel()
    # for i in range(16):
    # res_fluo_data[i].append(res[i])
    # search_cnt += 1
    # print 'search cnt:', search_cnt

    # if save_data_flag:
    # timestr = gettimestr()
    # save_fn = save_dir + timestr + '_4CW.csv'
    # save_fig_fn_all = save_dir + timestr + '_4CW_all.png'
    # write_to_csv(save_fn, freq_data + res_fluo_data)
    # for ch_id in range(4):
    # total_1ch_raw_output(save_dir + timestr + '_4CW_%d.csv' % (ch_id+1), [res_fluo_data[ch_id * 2], res_fluo_data[ch_id * 2 + 8]], xlabel='Freq. (Hz)', ylabel='Signal (V)',
    # legends=['X', 'Y'])
    # total_allch_raw_output_v1(save_fig_fn_all, freq_data, res_fluo_data, xlabel='Freq. (Hz)', ylabel='Signal (V)')

    # if not ext_call:
    # self.Stop()

    def ExpSweep4FCW(self, peak_id, mw_id_list, max_freq_drift=2e7, coarse_step=1.5e6, fine_step=6e5,
                     cw_sweep_range=18e6, cw_sweep_step=5e5, single_sweep_range=1e6, single_sweep_step=1.5e4,
                     single_pnum_limit=5, binary_search_converge_range=6e4, slope_fit_cnt=2,
                     save_dir=None, save_data_flag=True, time_dir_flag=False, plot_flag=True, return_mode='all',
                     ext_call=False):
        '''
            多通道快速扫频程序。
            默认信号已调到X通道上。

            :param ch_id: LIA解调通道，[0,1,2,3]
            :param proc_id: 各通道当前算法执行进度数组, int array[4]
                -1: 迭代扫描进程终止
                0: 获取共振峰大致范围
                1: 获取共振峰中心位置
                2: 二分法获取谱线中心位置精确值
                3: 计算最大斜率
            :param current_freq: 当前设置频率，Hz
            :param search_cnt: 当前已搜索频点次数
            :param val: LIA通道返回数值数组，float array[4], Hz
                [proc 0]
            :param center_freq_list: 扫描频率起点数组，float array[4], Hz
            :param cw_threshold: 共振峰阈值，Hz
            :param max_freq_drift: 扫频中允许当前设置频率偏离起始频点的最大范围，Hz
            :param coarse_step: 大步长扫频步进，Hz
            :param fine_step: 小步长扫频步进，Hz
                [proc 1]
            :param start_freq_list: 共振峰频率细扫起点，float array[4]，Hz
            :param cw_sweep_range: 共振峰频率扫描范围，Hz
            :param cw_sweep_step: 共振峰频率扫描步长，Hz
            :param res_freq_data: 有效频率数组，float array[4]，Hz
            :param res_fluo_data: 有效信号数组，float array[4]，Hz
            :param zero_freq_list: 零点频率存储数组，float array[4]，Hz
                [proc 2]
            :param left_freq_list: 二分法左侧端点数组，float array[4]，Hz
            :param right_freq_list: 二分法右侧端点数组，float array[4]，Hz
            :param single_sweep_range: 二分法区间初始长度，Hz
            :pram binary_search_converge_range: 二分法收敛判断长度，Hz
                [proc 3]
            :param single_sweep_step: 计算斜率用频率差值，Hz
            :param final_freq_list: 最终零点频率，float array[4]，Hz
            :param lin_data_list: 计算斜率用幅度，float array[4]，Hz
            :param max_slope_list: 最大斜率，float array[4]，Hz
            :param slope_fit_cnt: 斜率拟合所需点，共2 * slope_fit_cnt + 1个
            :return:
            '''
        # 创建数据存储目录
        if save_dir is None:
            save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpSweep4FCW',
                                                         time_dir_flag=time_dir_flag, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + '_logg.txt'
        proc_id = [0, 0, 0, 0]  # 初始进程状态
        center_freq_list = [self.parameter['Res_freq_%d' % peak_id[i]] * 1e9 for i in range(4)]  # 初始待扫描频率
        cw_threshold = [self.parameter['Threshold_freq_%d' % peak_id[i]] for i in range(4)]  # 共振峰检测阈值
        for ch_id in range(4):
            if ch_id not in mw_id_list:
                center_freq_list[ch_id] = 2.6e9
        current_freq_list = copy.deepcopy(center_freq_list)  # 当前待更新频率

        val_list = [0, 0, 0, 0]  # 待更新数值
        search_cnt = 0
        start_freq_list = [0, 0, 0, 0]  # 共振峰初始扫频起点
        res_freq_data, res_fluo_data, res_polar_data, zero_freq_list = [[], [], [], []], [[], [], [], []], [[], [], [],
                                                                                                            []], [[],
                                                                                                                  [],
                                                                                                                  [],
                                                                                                                  []]  # 零点计算用辅助数组
        current_val = [0, 0, 0, 0]  # 粗扫定位信号值
        zero_cnt = [0, 0, 0, 0]
        overbound_cnt = [0, 0, 0, 0]
        search_direction = [-1, -1, -1, -1]
        expand_cnt = [[1, 1], [1, 1], [1, 1], [1, 1]]  # 搜索次数统计
        left_freq_list, right_freq_list = [0, 0, 0, 0], [0, 0, 0, 0]  # 二分法辅助数组
        lin_data_list = [[], [], [], []]  # 斜率计算用辅助数组
        final_freq_list = [0, 0, 0, 0]  # 最终零点频率
        max_slope_list = [0, 0, 0, 0]  # 零点频率对应最大斜率
        algo_run_flag = True  # 运行状态标识符
        all_search_val_data, all_search_freq_data = [[], [], [], []], [[], [], [], []]

        while algo_run_flag:
            # 获取更新频率后数据
            # print 'search cnt:', search_cnt
            algo_run_flag = False
            print('search_cnt:', search_cnt, 'freq_list:', current_freq_list)
            t1 = time.time()
            self.set_all_mw(freqs=current_freq_list)
            self.set_all_mw(freqs=current_freq_list)
            # time.sleep(6 * self.lockin.GetLockInTimeConst())
            res = self.lockin.GetLockInChannel()
            # res = self.lockin.GetLockInChannel()
            t2 = time.time()
            val_list = [res[ch_id * 2 + 0] for ch_id in range(4)]
            for ch_id in range(4):
                # print('ch%d[step%d]' %(ch_id+1, proc_id[ch_id]))
                all_search_val_data[ch_id].append(val_list[ch_id])
                all_search_freq_data[ch_id].append(current_freq_list[ch_id])
                current_freq = current_freq_list[ch_id]
                if ch_id not in mw_id_list:
                    continue
                # 储存搜索全过程数据
                # 迭代扫描进程终止
                if proc_id[ch_id] == -1:
                    continue
                # 迭代扫描已结束
                elif proc_id[ch_id] == 4:
                    continue
                # 1. 获取共振峰大致范围
                if proc_id[ch_id] == 0:
                    if np.abs(val_list[ch_id]) >= cw_threshold[ch_id]:  # 成功确定共振峰范围，进入下一迭代阶段
                        proc_id[ch_id] = 1
                        start_freq_list[ch_id] = current_freq
                        current_val[ch_id] = val_list[ch_id]
                        res_freq_data[ch_id].append(current_freq)
                        res_fluo_data[ch_id].append(val_list[ch_id])
                        res_polar_data[ch_id].append(int(val_list[ch_id] / np.abs(val_list[ch_id])))
                        current_freq = start_freq_list[ch_id]
                    else:  # 未定位共振峰范围，继续搜索
                        current_freq = center_freq_list[ch_id] + (-1) ** ((search_cnt + 1) // 2 % 2) * (
                                search_cnt + 3) // 4 * coarse_step \
                                       + ((search_cnt + 1) % 2) * fine_step
                    if np.abs(current_freq - center_freq_list[ch_id]) > max_freq_drift:  # 搜索范围越界，终止搜索
                        proc_id[ch_id] = -1
                # 2. 获取共振峰中心位置
                elif proc_id[ch_id] == 1:
                    # print len(res_freq_data[0]), len(res_polar_data[0]), len(res_fluo_data[0]), len(zero_freq_list[0])
                    sid = (search_direction[ch_id] + 1) // 2
                    res_freq_data[ch_id].append(current_freq)
                    res_fluo_data[ch_id].append(val_list[ch_id])
                    if np.abs(val_list[ch_id]) > cw_threshold[ch_id]:  # 判断频点属于共振峰区间内
                        res_polar_data[ch_id].append(int(val_list[ch_id] / np.abs(val_list[ch_id])))
                    else:  # 幅度绝对值过低，无法判断频点是否属于共振峰区间内
                        res_polar_data[ch_id].append(res_polar_data[ch_id][-1])
                    if res_polar_data[ch_id][-1] == res_polar_data[ch_id][-2]:  # 统计极性不改变的时间长度
                        overbound_cnt[ch_id] += 1
                    else:  # 成功搜索到零点
                        zero_cnt[ch_id] += 1
                        if sid == 0:  # 向左搜索
                            zero_freq_list[ch_id].insert(0, (res_freq_data[ch_id][-1] + res_freq_data[ch_id][-2]) / 2.0)
                        elif sid == 1:  # 向右搜索
                            zero_freq_list[ch_id].append((res_freq_data[ch_id][-1] + res_freq_data[ch_id][-2]) / 2.0)
                        overbound_cnt[ch_id] = 0

                    if zero_cnt[ch_id] >= 5 or overbound_cnt[ch_id] >= single_pnum_limit:  # 单侧搜索结束
                        search_direction[ch_id] += 2  # 更新搜索方向
                        overbound_cnt[ch_id] = 0
                        if search_direction[ch_id] > 1:  # 整体搜索结束
                            if zero_cnt[ch_id] != 5:
                                proc_id[ch_id] = -1  # 谱线形态与预期不符，终止算法
                            else:
                                proc_id[ch_id] = 2  # 谱线形态与预期相符，继续执行算法，更新二分查找参数
                                left_freq_list[ch_id] = zero_freq_list[ch_id][2] - single_sweep_range / 2.0
                                right_freq_list[ch_id] = zero_freq_list[ch_id][2] + single_sweep_range / 2.0
                                current_freq = zero_freq_list[ch_id][2]
                        else:
                            current_freq = start_freq_list[ch_id] + cw_sweep_step
                            res_freq_data[ch_id].append(res_freq_data[ch_id][0])
                            res_polar_data[ch_id].append(res_polar_data[ch_id][0])
                            res_fluo_data[ch_id].append(res_fluo_data[ch_id][0])
                    else:  # 单侧搜索继续
                        expand_cnt[ch_id][sid] += 1
                        current_freq = start_freq_list[ch_id] + search_direction[ch_id] * expand_cnt[ch_id][
                            sid] * cw_sweep_step
                # 3. 二分法获取谱线中心位置精确值
                elif proc_id[ch_id] == 2:
                    if right_freq_list[ch_id] - left_freq_list[ch_id] <= binary_search_converge_range:  # 二分查找结果收敛
                        final_freq_list[ch_id] = current_freq
                        current_freq = current_freq - single_sweep_step * slope_fit_cnt  # 斜率拟合用点数
                        lin_data_list[ch_id].append(val_list[ch_id])
                        proc_id[ch_id] = 3
                    else:  # 继续执行二分查找
                        if val_list[ch_id] * res_polar_data[ch_id][-1] > 0:
                            right_freq_list[ch_id] = current_freq
                        else:
                            left_freq_list[ch_id] = current_freq
                        current_freq = (left_freq_list[ch_id] + right_freq_list[ch_id]) / 2.0
                # 4. 计算最大斜率
                elif proc_id[ch_id] == 3:
                    lin_data_list[ch_id].append(val_list[ch_id])
                    current_freq += single_sweep_step
                    # todo:在不影响运算精度的前提下，提高已知频点利用率
                    if np.abs(current_freq - final_freq_list[ch_id]) < 1e3:  # 跳过当前频点
                        current_freq += single_sweep_step
                        lin_data_list[ch_id].append(lin_data_list[ch_id][0])
                    if len(lin_data_list[ch_id]) == 2 * slope_fit_cnt + 2:  # 已完成计算斜率所需频点测量
                        # print [single_sweep_step * i for i in range(2 * slope_fit_cnt + 1)]
                        # print lin_data_list[ch_id][1:]
                        slope, intercept, r_value, p_value, std_err = linregress(
                            [single_sweep_step * (-slope_fit_cnt + i) for i in range(2 * slope_fit_cnt + 1)],
                            lin_data_list[ch_id][1:])
                        max_slope_list[ch_id] = slope
                        final_freq_list[ch_id] = -intercept / slope + final_freq_list[ch_id]
                        proc_id[ch_id] = 4

                # 更新数据
                current_freq_list[ch_id] = current_freq
                if proc_id[ch_id] != -1 and proc_id[ch_id] != 4:
                    algo_run_flag = True
            search_cnt += 1
            t3 = time.time()
            print('control: %f (s)  algorithm: %f (s)' % (t2 - t1, t3 - t2))

        if save_data_flag:
            timestr = gettimestr()
            save_fn_sol = save_dir + timestr + '_FCW_sol.csv'
            save_fn = save_dir + timestr + '_FCW.csv'
            save_fig_fn = save_dir + timestr + '_FCW.png'
            write_to_csv(save_fn_sol, [list(max_slope_list)] + [list(final_freq_list)])
            write_to_csv(save_fn, list(all_search_freq_data) + list(all_search_val_data))
            if plot_flag or max_slope_list[0] == 0 or max_slope_list[1] == 0 or max_slope_list[2] == 0 or \
                    max_slope_list[3] == 0:  # 作图展示搜索过程
                # for ch_id in range(4):
                # if ch_id not in mw_id_list:
                # continue
                # plt.clf()
                # plt.scatter(all_search_freq_data[ch_id], all_search_val_data[ch_id], color='black')
                # indexs = np.argsort(all_search_freq_data[ch_id])
                # plot_freq_data = [all_search_freq_data[ch_id][indexs[i]] for i in range(len(indexs))]
                # plot_val_data = [all_search_val_data[ch_id][indexs[i]] for i in range(len(indexs))]
                # plt.plot(plot_freq_data, plot_val_data)
                # if start_freq_list[ch_id]!=0:
                # plt.scatter(start_freq_list[ch_id], [0], color='brown')
                # if len(lin_data_list[ch_id]) == 2:
                # plt.plot([final_freq_list[ch_id] - single_sweep_step, final_freq_list[ch_id] + single_sweep_step],
                # lin_data_list[ch_id], color='orange')
                # plt.plot([zero_freq_list[ch_id][2] - single_sweep_range / 2.0,
                # zero_freq_list[ch_id][2] + single_sweep_range / 2.0], [0, 0], color='purple')
                # for i in range(len(res_fluo_data[ch_id])):
                # if res_polar_data[ch_id][i] > 0:
                # plt.scatter(res_freq_data[ch_id][i], res_fluo_data[ch_id][i], color='red')
                # else:
                # plt.scatter(res_freq_data[ch_id][i], res_fluo_data[ch_id][i], color='green')

                # plt.xlabel('MW Freq. (Hz)')
                # plt.ylabel('Signal (V)')
                # plt.grid()
                # plt.tight_layout()
                # plt.savefig(save_dir + timestr + '_FCW_peak_%d_mw_%d.png' % (peak_id[ch_id], ch_id+1))
                total_allch_FCW_plot(save_fig_fn, peak_id, mw_id_list, all_search_freq_data, all_search_val_data,
                                     start_freq_list, lin_data_list, final_freq_list,
                                     single_sweep_step, single_sweep_range, zero_freq_list, res_freq_data,
                                     res_fluo_data, res_polar_data, slope_fit_cnt, max_slope_list)
            logg_str = ''
            for ch_id in range(4):
                logg_str += 'CH%d: Res_Freq=%d kHz  Max_Slope=%e V/Hz\n' % (
                    ch_id + 1, int(final_freq_list[ch_id] / 1000.), max_slope_list[ch_id])
            self.logg_exp_info(exp_info_fn, logg_str)
        if not ext_call:
            self.Stop()
        if return_mode == 'all':
            return search_cnt, final_freq_list, lin_data_list, max_slope_list, all_search_freq_data, all_search_val_data, res_freq_data, res_fluo_data, res_polar_data, start_freq_list, zero_freq_list
        elif return_mode == 'freq_slope':
            return final_freq_list, max_slope_list

    def ExpSweep8FCW(self, max_freq_drift=2e7, coarse_step=1.5e6, fine_step=6e5,
                     cw_sweep_range=18e6, cw_sweep_step=4e5, single_sweep_range=1e6, single_sweep_step=8e4,
                     single_pnum_limit=6, slope_fit_cnt=2, save_dir=None, save_data_flag=True, time_dir_flag=False,
                     plot_flag=True,
                     ext_call=False):
        '''
            8通道快速扫频程序，参数说明见ExpSweep8FCW函数。
            依次对共振峰[1,3,5,7]、[2,4,6,8]两组峰进行同步扫频。

            [微波通道-共振峰对应关系]
                -共振峰1,2：FM001-CH1
                -共振峰3,4：FM001-CH2
                -共振峰5,6：FM002-CH1
                -共振峰7,8：FM002-CH2
            :return:
            '''
        # 创建数据存储目录
        if save_data_flag and (save_dir is None):
            save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpSweep8FCW',
                                                         time_dir_flag=time_dir_flag, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + '_logg.txt'
        # 待存储数据
        freq_sol, slope_sol = np.zeros(8), np.zeros(8)
        res_freq_data, res_fluo_data, res_polar_data, zero_freq_list = [None] * 8, [None] * 8, [None] * 8, [
            None] * 8  # 零点计算用辅助数组
        lin_data_list = [None] * 8  # 斜率计算用辅助数组
        all_search_val_data, all_search_freq_data = [None] * 8, [None] * 8  # 扫描全过程
        start_freq_list = [None] * 8  # 变步长扫频初步确定共振峰区间频点
        # 分别进行两次扫描
        for peak_group_id in range(2):
            _search_cnt, _final_freq_list, _lin_data_list, _max_slope_list, \
            _all_search_freq_data, _all_search_val_data, _res_freq_data, _res_fluo_data, _res_polar_data, \
            _start_freq_list, _zero_freq_list = self.ExpSweep4FCW(
                peak_id=[peak_group_id + 1, peak_group_id + 3, peak_group_id + 5, peak_group_id + 7],
                mw_id_list=[0, 1, 2, 3], max_freq_drift=max_freq_drift, coarse_step=coarse_step, fine_step=fine_step,
                cw_sweep_range=cw_sweep_range, cw_sweep_step=cw_sweep_step,
                single_sweep_range=single_sweep_range, single_sweep_step=single_sweep_step,
                single_pnum_limit=single_pnum_limit, slope_fit_cnt=slope_fit_cnt, save_data_flag=True,
                save_dir=save_dir, time_dir_flag=False, plot_flag=plot_flag, ext_call=True)
            for ch_id in range(4):
                ii = ch_id * 2 + peak_group_id
                # 更新当前已获取共振频率与斜率数据
                freq_sol[ii] = _final_freq_list[ch_id]
                slope_sol[ii] = _max_slope_list[ch_id]
                # 更新作图用辅助数据
                res_freq_data[ii] = _res_freq_data[ch_id]
                res_fluo_data[ii] = _res_fluo_data[ch_id]
                res_polar_data[ii] = _res_polar_data[ch_id]
                zero_freq_list[ii] = _zero_freq_list[ch_id]
                lin_data_list[ii] = _lin_data_list[ch_id]
                all_search_val_data[ii] = _all_search_val_data[ch_id]
                all_search_freq_data[ii] = _all_search_freq_data[ch_id]
                start_freq_list[ii] = _start_freq_list[ch_id]
        exception_flag = False
        logg_str = ''
        for ch_id in range(8):  # 存储各峰信息
            logg_str += 'Peak%d: Res_Freq=%d kHz  Max_Slope=%e V/Hz\n' % (
                ch_id + 1, int(freq_sol[ch_id] / 1000.), slope_sol[ch_id])
            if slope_sol[ch_id] == 0:  # 有峰未正常返回值
                exception_flag = True
        self.logg_exp_info(exp_info_fn, logg_str)
        # 数据存储与作图
        if save_data_flag:
            timestr = gettimestr()
            save_fn = save_dir + timestr + '_8CW_sol.csv'
            save_fn_all = save_dir + timestr + '_8CW_all.csv'
            save_fig_fn_all = save_dir + timestr + '_8CW_all.png'
            # write_to_csv(save_fn, [freq_sol] + [slope_sol])
            write_to_csv(save_fn_all, all_search_freq_data + all_search_val_data)
            if plot_flag or exception_flag:
                total_allch_8FCW_plot(save_fig_fn_all, all_search_freq_data, all_search_val_data,
                                      start_freq_list, lin_data_list, freq_sol,
                                      single_sweep_step, single_sweep_range, zero_freq_list, res_freq_data,
                                      res_fluo_data, res_polar_data, slope_fit_cnt, slope_sol)

        if not ext_call:
            self.Stop()
        return freq_sol, slope_sol

    def ExpRealtimeDisplay4FreqPID(self, pid_mode='FCW', save_dir=None, time_dir_flag=True, ext_call=False):
        '''
            实时PID反馈4频率检测程序。

            :param pid_mode: 工作模式
                'FCW': 通过快速扫频（4组峰）确认初始频率与斜率后，进入工作状态
                '8FCW': 通过快速扫频（8组峰）确认初始频率与斜率后，进入工作状态
                'fixed'：直接按默认参数进入工作状态
            :param save_dir:
            :param time_dir_flag:
            :param ext_call:
            :return:
            '''
        if save_dir is None:
            save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpRealtimeDisplay4FreqPID',
                                                         time_dir_flag=time_dir_flag, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + '_logg.txt'
        real_time_limitation = int(self.parameter['realtime_time_limitation'])  # 实时采集开关
        self.set_all_mw(state='on')  # 开启微波
        channel_slope = [self.parameter['channel%d_slope' % ch_id] for ch_id in range(4)]
        init_freq = [self.parameter['mw_ch%d_start_freq' % ch_id] / 1000 for ch_id in range(4)]
        peak_id_list = [2, 3, 5, 8]
        self.logg_exp_info(exp_info_fn,
                           'peak:%d %d %d %d\n' % (peak_id_list[0], peak_id_list[1], peak_id_list[2], peak_id_list[3]))
        if pid_mode == 'fixed':  # 选用默认共振频率与斜率
            pass
        elif pid_mode == 'FCW':  # 选用快速扫频获取共振频率与斜率(4)
            final_freq_list, max_slope_list = self.ExpSweep4FCW(peak_id=peak_id_list, mw_id_list=[0, 1, 2, 3],
                                                                max_freq_drift=2e7, coarse_step=1.8e6, fine_step=6.5e5,
                                                                cw_sweep_range=18e6, cw_sweep_step=3e5,
                                                                single_sweep_range=1e6, single_sweep_step=1.8e4,
                                                                single_pnum_limit=7, slope_fit_cnt=2,
                                                                save_dir=save_dir, save_data_flag=True,
                                                                time_dir_flag=False, plot_flag=True,
                                                                return_mode='freq_slope', ext_call=True)
            for ch_id in range(4):  # 更新初始参数
                channel_slope[ch_id] = max_slope_list[ch_id]
                init_freq[ch_id] = final_freq_list[ch_id] / 1000.
        elif pid_mode == '8FCW':  # 选用快速扫频获取共振频率与斜率(8)
            print('Searching Resonant Freqs.')

            freq_8_peaks, slope_8_peaks = self.ExpSweep8FCW(max_freq_drift=2e7, coarse_step=1.8e6, fine_step=6.5e5,
                                                            cw_sweep_range=18e6, cw_sweep_step=3e5,
                                                            single_sweep_range=1e6, single_sweep_step=1.8e4,
                                                            single_pnum_limit=7, slope_fit_cnt=2, save_dir=save_dir,
                                                            save_data_flag=True, time_dir_flag=False, plot_flag=True,
                                                            ext_call=True)
            final_freq_list = [freq_8_peaks[peak_id - 1] for peak_id in peak_id_list]
            max_slope_list = [slope_8_peaks[peak_id - 1] for peak_id in peak_id_list]
            for ch_id in range(4):  # 更新初始参数
                channel_slope[ch_id] = max_slope_list[ch_id]
                init_freq[ch_id] = final_freq_list[ch_id] / 1000.
        log_str = ''  # 记录斜率数据
        for ch_id in range(4):
            log_str += 'CH_%d_slope=%E\nCH_%d_start_freq=%E\n' % (ch_id, channel_slope[ch_id], ch_id, init_freq[ch_id])
        self.logg_exp_info(exp_info_fn, log_str)
        # 设定PID参数
        set_point = []
        output_offset = []
        kp = []
        ki = []
        kd = []
        RD_RATIO = self.parameter['RD_RATIO']
        EX_RATIO = self.parameter['EX_RATIO']
        for ch_id in range(device_channel):
            print(('set PID channel %d' % (ch_id + 1)))
            # 输出参考点,默认参考值为0,默认参考通道为x
            set_point.append(0)
            # 初始输出频率
            output_offset.append(init_freq[ch_id])
            # PID参数
            # min step of kp/ki/kd is 0.0000000005
            kp.append(self.parameter['kp_%d' % ch_id])
            ki.append(self.parameter['ki_%d' % ch_id])
            kd.append(self.parameter['kd_%d' % ch_id])
            self.lockin.SetPIDParameters(1 + ch_id, set_point[ch_id], output_offset[ch_id], kp=kp[ch_id], ki=ki[ch_id],
                                         kd=kd[ch_id], PID_RD_RITIO=RD_RATIO, PID_EX_RATIO=EX_RATIO, PID_LIA_CH=0)

        # PID采样率
        spr = 50000000.0 / ((RD_RATIO + 1.0) * (EX_RATIO + 1.0))

        # 读数据
        i = 0
        # 合成的频率偏移数据:格式为：相对时间、4个频率偏移
        freq_data = [[] for ii in range(5)]
        # 原始数据:格式为第一列时间，往后每四列为一个通道的x,y,误差项,反馈项
        raw_data = [[] for ii in range(17)]
        meas_count = 0
        buffer_len = int(spr) * self.parameter['realtime_slice_time']
        err = [[] for i in range(device_channel)]
        feedback = [[] for i in range(device_channel)]
        freq_err1 = [[] for i in range(device_channel)]
        freq_err2 = [[] for i in range(device_channel)]
        freq_err = [[] for i in range(device_channel)]
        start_time = time.time()
        t_pre = start_time
        self.logg_exp_info(exp_info_fn, 'start_time_stamp=%.3f\n' % start_time)
        print('Start PID Acquiring Mode.')
        # 开启PID采集
        self.lockin.PID_Enable()
        self.lockin.AcquireStartV2_PID(wait_trig=True)
        while self.run_flag:
            ts, result = self.lockin.GetAcquireChannelsV2_PID(poll_time=0.2, get_time_stamps=True)
            # for ch_id in range(device_channel):
            #     print 'result ch_id%d:' % ch_id, len(result[ch_id])
            ts = np.array(ts) / spr
            # 时间数据
            freq_data[0] += list(ts)
            raw_data[0] += list(ts)
            # 处理得到频率偏移
            for ch_id in range(device_channel):
                err[ch_id] = result[ch_id * 4 + 2]
                feedback[ch_id] = result[ch_id * 4 + 3]
                # 信号输出偏移项
                freq_err1[ch_id] = np.array(err[ch_id]) / channel_slope[ch_id]
                # 频率设定偏移项
                freq_err2[ch_id] = (np.array(feedback[ch_id]) - output_offset[ch_id]) * 1000
                # 总偏移项
                freq_err[ch_id] = freq_err1[ch_id] + freq_err2[ch_id]
                freq_data[1 + ch_id] += list(freq_err[ch_id])

            for ii in range(16):
                raw_data[ii + 1] += list(result[ii])

            t_now = time.time()

            if t_now - t_pre >= 10:
                print('time:', t_now - start_time)
                t_pre = t_now

            if len(freq_data[-1]) > buffer_len or (
                    real_time_limitation == 1 and time.time() - start_time >= self.parameter[
                'realtime_acquiring_time']):
                time_str = gettimestr()
                # fn = DATAPATH + gettimestr() + '_realtime_3Axis_data.csv' if save_fn is None else save_fn
                fname = save_dir + time_str + '_magnetometer_%d.csv' % meas_count
                # write_to_csv(fname, mag_data, row_to_col=True)
                fnfreq = save_dir + time_str + '_magnetometer_freqdata_%d.csv' % meas_count
                write_to_csv(fnfreq, freq_data, row_to_col=True)
                fnraw = save_dir + time_str + '_magnetometer_rawdata_%d.csv' % meas_count
                write_to_csv(fnraw, raw_data, row_to_col=True)
                freq_data = [[] for ii in range(5)]
                raw_data = [[] for ll in range(17)]
                # 判断是否为限时采集工作模式
                if real_time_limitation == 1 and time.time() - start_time >= self.parameter['realtime_acquiring_time']:
                    self.run_flag = False
                meas_count += 1
                print(fname)
        self.lockin.AcquireStopV2_PID()
        self.lockin.PID_Disable()
        if not ext_call:
            self.Stop()

    def ExpPIDparaopt(self, param_dict=None, pid_mode='8FCW', save_dir=None, time_dir_flag=True, slice_time_length=40,
                      ext_call=False):
        '''
            PID参数扫描程序。以等比数列格式进行kp、ki、kd组合区间扫描。
            :param ext_call:
            :return:
            '''
        # 数据保存路径
        if save_dir is None:
            save_dir, exp_info_fn = self.create_data_dir(exp_name='ExpPIDparaopt',
                                                         time_dir_flag=time_dir_flag, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + 'ExpPIDparaopt_logg.txt'
        self.set_all_mw(state='on')  # 开启微波

        # 1. 初始化斜率与共振频率
        channel_slope = [self.parameter['channel%d_slope' % ch_id] for ch_id in range(4)]
        init_freq = [self.parameter['mw_ch%d_start_freq' % ch_id] for ch_id in range(4)]

        peak_id_list = [2, 3, 5, 8]
        self.logg_exp_info(exp_info_fn,
                           'peak: %d %d %d %d\n' % (peak_id_list[0], peak_id_list[1], peak_id_list[2], peak_id_list[3]))
        if pid_mode == 'FCW':  # 选用快速扫频获取共振频率与斜率（4组峰）
            print('Searching Resonant Freqs. (4 peaks)')
            final_freq_list, max_slope_list = self.ExpSweep4FCW(peak_id=peak_id_list, mw_id_list=[0, 1, 2, 3],
                                                                max_freq_drift=2e7, coarse_step=1.8e6, fine_step=6.5e5,
                                                                cw_sweep_range=18e6, cw_sweep_step=3e5,
                                                                single_sweep_range=1e6, single_sweep_step=1.8e4,
                                                                single_pnum_limit=7, slope_fit_cnt=2,
                                                                save_dir=save_dir, save_data_flag=True,
                                                                time_dir_flag=False, plot_flag=True,
                                                                return_mode='freq_slope', ext_call=True)
            for ch_id in range(4):  # 更新初始参数
                channel_slope[ch_id] = max_slope_list[ch_id]
                init_freq[ch_id] = final_freq_list[ch_id] / 1000.
        elif pid_mode == '8FCW':  # 选用快速扫频获取共振频率与斜率（8组峰）
            print('Searching Resonant Freqs. (8 peaks)')
            freq_8_peaks, slope_8_peaks = self.ExpSweep8FCW(max_freq_drift=2e7, coarse_step=1.8e6, fine_step=6.5e5,
                                                            cw_sweep_range=18e6, cw_sweep_step=3e5,
                                                            single_sweep_range=1e6, single_sweep_step=1.8e4,
                                                            single_pnum_limit=7, slope_fit_cnt=2,
                                                            save_dir=save_dir, save_data_flag=True, time_dir_flag=False,
                                                            plot_flag=True, ext_call=True)
            for ch_id in range(4):
                channel_slope[ch_id] = slope_8_peaks[peak_id_list[ch_id] - 1]
                init_freq[ch_id] = freq_8_peaks[peak_id_list[ch_id] - 1] / 1000.

        # 2. 获取PID扫描参数列表

        # 使用默认参数进行扫描
        # plist = np.logspace(np.log10(self.parameter['kp_sweep_start_value']), np.log10(self.parameter['kp_sweep_stop_value']), np.log10(int(self.parameter['kp_sweep_pnum']))) * -1
        # ilist = np.logspace(np.log10(self.parameter['ki_sweep_start_value']), np.log10(self.parameter['ki_sweep_stop_value']), np.log10(int(self.parameter['ki_sweep_pnum']))) * -1
        # dlist = np.logspace(np.log10(self.parameter['kd_sweep_start_value']), np.log10(self.parameter['kd_sweep_stop_value']), np.log10(int(self.parameter['kd_sweep_pnum']))) * -1
        # if param_dict is not None:     # 传入参数字典非空，采用传入参数进行扫描
        plist, ilist, dlist = param_dict['plist'], param_dict['ilist'], param_dict['dlist']
        print(plist, ilist, dlist)
        # 单点采样时长
        time_len = slice_time_length
        self.logg_exp_info(exp_info_fn, 'time slice length=%f\n' % time_len)

        # 统计实验总长度
        exp_cnt = 0
        # 3. PID参数扫描主程序
        for pp in plist:
            for ii in ilist:
                for dd in dlist:
                    print('p:', pp, 'i:', ii, 'd:', dd)
                    if not self.run_flag:
                        break
                    # todo：为防止潜在设置错误问题，此处重复发送两次设置微波命令
                    # 设定微波参数：按循环实验执行开始前标定的斜率设置
                    self.set_all_mw(state='on', freqs=np.array(init_freq) * 1e3)  # init_freq单位为kHz，set_all_mw方法单位为Hz
                    self.set_all_mw(state='on', freqs=np.array(init_freq) * 1e3)  # init_freq单位为kHz，set_all_mw方法单位为Hz
                    # 设定PID参数
                    set_point = []
                    output_offset = []
                    kp = []
                    ki = []
                    kd = []
                    RD_RITIO = self.parameter['RD_RATIO']
                    EX_RATIO = self.parameter['EX_RATIO']
                    for ch_id in range(device_channel):
                        print(('set PID channel%d' % ch_id))
                        # 输出参考点,默认参考值为0,默认参考通道为x
                        set_point.append(0)
                        # 初始输出频率
                        output_offset.append(init_freq[ch_id])
                        print(output_offset)
                        # PID参数
                        # min step of kp/ki/kd is 0.0000000005
                        kp.append(pp)
                        ki.append(ii)
                        kd.append(dd)
                        self.lockin.SetPIDParameters(1 + ch_id, set_point[ch_id], output_offset[ch_id], kp=kp[ch_id],
                                                     ki=ki[ch_id],
                                                     kd=kd[ch_id], PID_RD_RITIO=RD_RITIO, PID_EX_RATIO=EX_RATIO,
                                                     PID_LIA_CH=0)

                    # PID采样率
                    spr = 50000000.0 / ((RD_RITIO + 1.0) * (EX_RATIO + 1.0))
                    # 开启PID采集
                    self.lockin.PID_Enable()
                    self.lockin.AcquireStartV2_PID(wait_trig=True)

                    # 读数据
                    # 频率偏移数据:格式为：相对时间、4个频率偏移
                    freq_data = [[] for i in range(5)]
                    # 原始数据:格式为第一列时间，往后每四列为一个通道的x,y,误差项,反馈项
                    raw_data = [[] for i in range(17)]
                    err = [[] for i in range(device_channel)]
                    feedback = [[] for i in range(device_channel)]
                    freq_err1 = [[] for i in range(device_channel)]
                    freq_err2 = [[] for i in range(device_channel)]
                    freq_err = [[] for i in range(device_channel)]

                    while len(freq_data[-1]) / spr < time_len:
                        ts, result = self.lockin.GetAcquireChannelsV2_PID(poll_time=0.2, get_time_stamps=True)
                        ts = np.array(ts) / spr
                        # 时间数据
                        freq_data[0] += list(ts)
                        raw_data[0] += list(ts)
                        # 处理得到频率偏移
                        for ch_id in range(device_channel):
                            err[ch_id] = result[ch_id * 4 + 2]
                            feedback[ch_id] = result[ch_id * 4 + 3]
                            # 信号输出偏移项
                            freq_err1[ch_id] = np.array(err[ch_id]) / channel_slope[ch_id]
                            # 频率设定偏移项
                            freq_err2[ch_id] = (np.array(feedback[ch_id]) - output_offset[ch_id]) * 1000
                            # 总偏移项
                            freq_err[ch_id] = freq_err1[ch_id] + freq_err2[ch_id]
                            freq_data[1 + ch_id] += list(freq_err[ch_id])

                        for i in range(16):
                            raw_data[i + 1] += list(result[i])
                    # 退出PID模式
                    self.lockin.AcquireStopV2_PID()
                    self.lockin.PID_Disable()
                    # 数据保存
                    time_str = gettimestr()
                    self.logg_exp_info(exp_info_fn, 'exp_cnt=%d\ntime_str=\'%s\'\nP=%E\nI=%E\nD=%E\n\n' % (
                        exp_cnt, time_str, pp, ii, dd))
                    fnfreq = save_dir + time_str + '_freqdata_P=%E_I=%E_D=%E_%d.csv' % (pp, ii, dd, exp_cnt)
                    write_to_csv(fnfreq, freq_data)
                    fnraw = save_dir + time_str + '_rawdata_P=%E_I=%E_D=%E_%d.csv' % (pp, ii, dd, exp_cnt)
                    write_to_csv(fnraw, raw_data, row_to_col=True)
                    exp_cnt += 1

        if not ext_call:
            self.Stop()

    def ExpPIDSweepInitFreq(self, param_dict=None, offset_freq_list=None, pid_mode='8FCW', update_init_freq=False,
                            save_dir=None, time_dir_flag=True, slice_time_length=10, ext_call=False):
        '''
            PID参数扫描程序。
            在线性区间内改变初始扫描频点，观察时域响应。
            :param param_list: 传入PID参数列表，
            :param offset_freq_list: 初始频率偏移量列表, float[]
            :param pid_mode: 选择确定初始共振频率/斜率的工作模式，FCW/8FCW
            :param update_init_freq: 是否在每次实验结束时重设初始频率
            :param save_dir: 文件保存路径
            :param time_dir_flag:
            :param slice_time_length: 单次采集时间长度
            :param ext_call:
            :return:
                '''
        exp_name = 'ExpPIDSweepInitFreq'
        # 数据保存路径
        if save_dir is None:
            save_dir, exp_info_fn = self.create_data_dir(exp_name=exp_name,
                                                         time_dir_flag=time_dir_flag, exp_info_flag=True)
        else:
            exp_info_fn = save_dir + gettimestr() + exp_name + '_log.txt'
        self.set_all_mw(state='on')  # 开启微波

        # 1. 初始化斜率与共振频率
        channel_slope = [self.parameter['channel%d_slope' % ch_id] for ch_id in range(4)]
        init_freq = [self.parameter['mw_ch%d_start_freq' % ch_id] / 1000. for ch_id in range(4)]  # 单位为kHz

        peak_id_list = [2, 3, 5, 8]
        self.logg_exp_info(exp_info_fn,
                           'peak: %d %d %d %d\n' % (peak_id_list[0], peak_id_list[1], peak_id_list[2], peak_id_list[3]))
        if pid_mode == 'FCW':  # 选用快速扫频获取共振频率与斜率（4组峰）
            print('Searching Resonant Freqs. (4 peaks)')
            final_freq_list, max_slope_list = self.ExpSweep4FCW(peak_id=peak_id_list, mw_id_list=[0, 1, 2, 3],
                                                                max_freq_drift=2e7, coarse_step=1.8e6, fine_step=6.5e5,
                                                                cw_sweep_range=18e6, cw_sweep_step=3e5,
                                                                single_sweep_range=1e6, single_sweep_step=1.8e4,
                                                                single_pnum_limit=7, slope_fit_cnt=2,
                                                                save_dir=save_dir, save_data_flag=True,
                                                                time_dir_flag=False, plot_flag=True,
                                                                return_mode='freq_slope', ext_call=True)
            for ch_id in range(4):  # 更新初始参数
                channel_slope[ch_id] = max_slope_list[ch_id]
                init_freq[ch_id] = final_freq_list[ch_id] / 1000.
        elif pid_mode == '8FCW':  # 选用快速扫频获取共振频率与斜率（8组峰）
            print('Searching Resonant Freqs. (8 peaks)')
            freq_8_peaks, slope_8_peaks = self.ExpSweep8FCW(max_freq_drift=2e7, coarse_step=1.8e6, fine_step=6.5e5,
                                                            cw_sweep_range=18e6, cw_sweep_step=3e5,
                                                            single_sweep_range=1e6, single_sweep_step=1.8e4,
                                                            single_pnum_limit=7, slope_fit_cnt=2,
                                                            save_dir=save_dir, save_data_flag=True, time_dir_flag=False,
                                                            plot_flag=True, ext_call=True)
            for ch_id in range(4):
                channel_slope[ch_id] = slope_8_peaks[peak_id_list[ch_id] - 1]
                init_freq[ch_id] = freq_8_peaks[peak_id_list[ch_id] - 1] / 1000.
        log_str = ''
        for ch_id in range(4):
            log_str += 'CH_%d_slope=%E\nCH_%d_start_freq=%E\n' % (ch_id, channel_slope[ch_id], ch_id, init_freq[ch_id])
        self.logg_exp_info(exp_info_fn, log_str)
        # 单点采样时长
        time_len = slice_time_length
        self.logg_exp_info(exp_info_fn, 'time slice length=%f\n' % time_len)

        # 使用默认参数进行扫描
        # plist = np.logspace(np.log10(self.parameter['kp_sweep_start_value']),
        # np.log10(self.parameter['kp_sweep_stop_value']),
        # np.log10(int(self.parameter['kp_sweep_pnum']))) * -1
        # ilist = np.logspace(np.log10(self.parameter['ki_sweep_start_value']),
        # np.log10(self.parameter['ki_sweep_stop_value']),
        # np.log10(int(self.parameter['ki_sweep_pnum']))) * -1
        # dlist = np.logspace(np.log10(self.parameter['kd_sweep_start_value']),
        # np.log10(self.parameter['kd_sweep_stop_value']),
        # np.log10(int(self.parameter['kd_sweep_pnum']))) * -1
        if param_dict is not None:  # 传入参数字典非空，采用传入参数进行扫描
            plist, ilist, dlist = param_dict['plist'], param_dict['ilist'], param_dict['dlist']
        # 设置默认offset频率数组
        if offset_freq_list is None:
            offset_freq_list = np.linspace(-10 * 1e4, 10 * 1e4, 21)
        # 统计实验总长度
        exp_cnt = 0
        # 3. PID参数扫描主程序
        for pp in plist:
            for ii in ilist:
                for dd in dlist:  # 扫描PID参数组合
                    for offset_freq in offset_freq_list:
                        if not self.run_flag:
                            break
                        # todo：为防止潜在设置错误问题，此处重复发送两次设置微波命令
                        # 设定微波参数：按循环实验执行开始前标定的斜率设置
                        self.set_all_mw(state='on', freqs=np.array(
                            init_freq) * 1e3 + offset_freq)  # init_freq单位为kHz，set_all_mw方法单位为Hz
                        self.set_all_mw(state='on', freqs=np.array(
                            init_freq) * 1e3 + offset_freq)  # init_freq单位为kHz，set_all_mw方法单位为Hz
                        # 设定PID参数
                        set_point = []
                        output_offset = []
                        kp = []
                        ki = []
                        kd = []
                        RD_RITIO = self.parameter['RD_RATIO']
                        EX_RATIO = self.parameter['EX_RATIO']
                        for ch_id in range(device_channel):
                            # 输出参考点,默认参考值为0,默认参考通道为x
                            set_point.append(0)
                            # 设置初始输出频率
                            output_offset.append(init_freq[ch_id] + offset_freq / 1000.)  # 此处单位为kHz
                            # PID参数
                            # min step of kp/ki/kd is 0.0000000005
                            kp.append(pp)
                            ki.append(ii)
                            kd.append(dd)
                            self.lockin.SetPIDParameters(1 + ch_id, set_point[ch_id], output_offset[ch_id],
                                                         kp=kp[ch_id],
                                                         ki=ki[ch_id],
                                                         kd=kd[ch_id], PID_RD_RITIO=RD_RITIO, PID_EX_RATIO=EX_RATIO,
                                                         PID_LIA_CH=0)
                            print(('set PID channel%d: output_offset=%E kHz' % (ch_id, output_offset[-1])))

                        # PID采样率
                        spr = 50000000.0 / ((RD_RITIO + 1.0) * (EX_RATIO + 1.0))
                        # 开启PID采集
                        # todo: 调用PID_Enable方法后系统即开始PID工作状态，可能无法捕捉到完整的阶跃响应波形
                        self.lockin.PID_Enable()
                        result = self.lockin.GetLockInChannels_PID(poll_time=slice_time_length)
                        ts = list(np.arange(0, len(result[0])) / spr)

                        # 频率偏移数据:格式为：相对时间、4个频率偏移
                        freq_data = [[] for i in range(5)]
                        # 原始数据:格式为第一列时间，往后每四列为一个通道的x,y,误差项,反馈项
                        raw_data = [[] for i in range(17)]
                        err = [[] for i in range(device_channel)]
                        feedback = [[] for i in range(device_channel)]
                        freq_err1 = [[] for i in range(device_channel)]
                        freq_err2 = [[] for i in range(device_channel)]
                        freq_err = [[] for i in range(device_channel)]

                        freq_data[0] = ts
                        for ch_id in range(device_channel):
                            err[ch_id] = result[ch_id * 4 + 2]  # V
                            feedback[ch_id] = result[ch_id * 4 + 3]
                            # 信号输出偏移项
                            freq_err1[ch_id] = np.array(err[ch_id]) / channel_slope[ch_id]
                            # 频率设定偏移项
                            freq_err2[ch_id] = (np.array(feedback[ch_id]) - output_offset[ch_id]) * 1000
                            # 总偏移项
                            freq_err[ch_id] = freq_err1[ch_id] + freq_err2[ch_id]
                            freq_data[1 + ch_id] += list(freq_err[ch_id])
                        raw_data[0] = ts
                        for i in range(16):
                            raw_data[i + 1] += list(result[i])

                        # 退出PID模式
                        self.lockin.PID_Disable()

                        if update_init_freq:  # 判断是否根据PID反馈值更新当前频率，取最后10个点作平均
                            for ch_id in range(device_channel):
                                init_freq[ch_id] = init_freq[ch_id] + np.mean(freq_data[1 + ch_id][-10:]) / 1000
                        # 数据保存
                        time_str = gettimestr()
                        log_str = 'exp_cnt=%d\ntime_str=\'%s\'\nP=%E\nI=%E\nD=%E\n' % (exp_cnt, time_str, pp, ii, dd)
                        for ch_id in range(4):
                            log_str += 'init_freq_%d=%E\noffset_freq_%d=%E\n' % (
                                ch_id, init_freq[ch_id], ch_id, offset_freq / 1000.)
                        self.logg_exp_info(exp_info_fn, log_str)
                        fnfreq = save_dir + time_str + '_freqdata_P=%E_I=%E_D=%E_%d.csv' % (pp, ii, dd, exp_cnt)
                        write_to_csv(fnfreq, freq_data)
                        fnraw = save_dir + time_str + '_rawdata_P=%E_I=%E_D=%E_%d.csv' % (pp, ii, dd, exp_cnt)
                        write_to_csv(fnraw, raw_data, row_to_col=True)
                        exp_cnt += 1

        if not ext_call:
            self.Stop()


def cmd_dc_calibrate(api, args):
    print("DC Calibration.")
    api.Auxdaq_Calibration(api)

def cmd_daq_calibrate(api, args):
    print("DAQ Calibration.")
    api.DAQ_Calibration()

def cmd_iir_calibrate(api, args):
    print("IIR Calibration.")
    api.ExpDAQTest(pnum=args.pnum)

def cmd_laser(api, args):
    print("Laser control.")
    if 0 <= args.current <= 1.5:
        api.CS_SPI_Ctrl(args.current)
    else:
        print("❌ Laser current exceeds valid boundary [0 ~ 1.5A].")

def cmd_mw(api, args):
    print("MW control.")
    api.MW_SPI_Ctrl(args.ch1_freq, args.ch1_modu, args.ch1_atte,
                    args.ch2_freq, args.ch2_modu, args.ch2_atte)

def cmd_dc(api, args):
    print("DC mode")
    start_time = time.time()
    api.auxDAQ_play(data_num=args.samples)
    stop_time = time.time()
    print("Time =", stop_time - start_time,
          "Actual Sampling Rate =", args.samples / (stop_time - start_time))
    api.auxdaq_plot()

def cmd_daq(api, args):
    print("DAQ mode")
    api.DAQ_play(data_num=args.samples, extract_ratio=args.extract)
    api.daq_plot()

def cmd_iir(api, args):
    print("IIR mode")
    api.IIR_play(data_num=args.samples)
    api.IIR_plot()

def cmd_iir_config(api, args):
    print("IIR Config")
    api.set_tc(args.tc)
    api.sample_rate_config(args.sample_rate)
    api.De_fre_config(1, args.ch1_freq)
    api.Modu_fre_config(1, args.ch1_freq)
    api.De_fre_config(2, args.ch2_freq)
    api.Modu_fre_config(2, args.ch2_freq)
    api.all_stop()
    api.play()
    api.all_start()

def build_parser():
    parser = argparse.ArgumentParser(description="LIA Mini Command Line Control")
    subparsers = parser.add_subparsers(title="commands", dest="command")

    subparsers.add_parser("DC_Calibrate", help="Run DC calibration").set_defaults(func=cmd_dc_calibrate)
    subparsers.add_parser("DAQ_Calibrate", help="Run DAQ calibration").set_defaults(func=cmd_daq_calibrate)

    p = subparsers.add_parser("IIR_Calibrate", help="Run IIR calibration")
    p.add_argument("pnum", type=int, help="Pulse number")
    p.set_defaults(func=cmd_iir_calibrate)

    p = subparsers.add_parser("Laser", help="Control laser current")
    p.add_argument("current", type=float, help="Laser current (0~1.5A)")
    p.set_defaults(func=cmd_laser)

    p = subparsers.add_parser("MW", help="Control microwave SPI parameters")
    p.add_argument("ch1_freq", type=int)
    p.add_argument("ch1_modu", type=int)
    p.add_argument("ch1_atte", type=int)
    p.add_argument("ch2_freq", type=int)
    p.add_argument("ch2_modu", type=int)
    p.add_argument("ch2_atte", type=int)
    p.set_defaults(func=cmd_mw)

    p = subparsers.add_parser("DC", help="Start auxDAQ with sampling")
    p.add_argument("samples", type=int)
    p.set_defaults(func=cmd_dc)

    p = subparsers.add_parser("DAQ", help="DAQ sampling and plotting")
    p.add_argument("samples", type=int)
    p.add_argument("extract", type=int)
    p.set_defaults(func=cmd_daq)

    p = subparsers.add_parser("IIR", help="IIR filter mode")
    p.add_argument("samples", type=int)
    p.set_defaults(func=cmd_iir)

    p = subparsers.add_parser("IIR_Config", help="Configure IIR parameters and start DAC")
    p.add_argument("tc", type=float, help="Time constant")
    p.add_argument("sample_rate", type=float, help="Sample rate")
    p.add_argument("ch1_freq", type=float, help="Channel 1 modulation frequency")
    p.add_argument("ch2_freq", type=float, help="Channel 2 modulation frequency")
    p.set_defaults(func=cmd_iir_config)

    return parser

if __name__ == '__main__':
    import argparse
    import sys


    # LIA_mini_API = API("COM1")
    # LIA_mini_API.USB_START()
    # LIA_mini_API.all_start()

    # parser = build_parser()
    # args = parser.parse_args()

    # if hasattr(args, 'func'):
        # args.func(LIA_mini_API, args)
    # else:
        # parser.print_help()

    # LIA_mini_API.USB_END()
    # exit()

    LIA_mini_API = API('COM1')
    LIA_mini_API.USB_START()
    LIA_mini_API.all_start()
    
    LIA_mini_API.CS_SPI_Ctrl(0)
    time.sleep(1)
     
    argv = sys.argv[1:]
    print(argv)
    if len(argv) > 0:
        if argv[0] == 'DC_Calibrate':
            print('DC Calibration.')
            LIA_mini_API.Auxdaq_Calibration(LIA_mini_API)
        elif argv[0] == 'DAQ_Calibrate':
            print('DAQ Calibration.')
            LIA_mini_API.DAQ_Calibration()
        elif argv[0] == 'IIR_Calibrate':
            print('IIR Calibration.')
            pnum = int(argv[1])
            LIA_mini_API.ExpDAQTest(pnum=pnum)
        elif argv[0] == 'Laser':
            print('Laser control.')
            laser_curr = float(argv[1])
            if 0<=laser_curr<=1.5:
                LIA_mini_API.CS_SPI_Ctrl(laser_curr)
            else:
                print('Exceeds Valid Boundary.')
        elif argv[0] == 'MW':
            print('MW control.')
            # ch1_Fre_buf, ch1_modu, ch1_atte, ch2_Fre_buf, ch2_modu, ch2_atte
            ch1_Fre = int(argv[1])
            ch1_modu = int(argv[2])
            ch1_atte = int(argv[3])
            ch2_Fre = int(argv[4])
            ch2_modu = int(argv[5])
            ch2_atte = int(argv[6])
            LIA_mini_API.MW_SPI_Ctrl(ch1_Fre, ch1_modu, ch1_atte, ch2_Fre, ch2_modu, ch2_atte)
        elif argv[0] == 'DC':
            print('DC acquisition')
            start_time = time.time()
            auxDAQ_pnum = int(argv[1])
            LIA_mini_API.auxDAQ_play(data_num=auxDAQ_pnum)
            stop_time = time.time()
            print('Time=', stop_time - start_time, 'Actual Sampling Rate=', auxDAQ_pnum / (stop_time - start_time))
            LIA_mini_API.auxdaq_plot()
        elif argv[0] == 'DAQ':
            print('DAQ acquisition')
            data_num = int(argv[1])
            extract_ratio = int(argv[2])
            print(f'data_num={data_num}, extract_ratio={extract_ratio}')
            LIA_mini_API.DAQ_play(data_num=data_num, extract_ratio=extract_ratio)
            print('Data acquired.')
            LIA_mini_API.daq_plot()
        elif argv[0] == 'IIR':
            print('IIR acquisition')
            data_num = int(argv[1])
            print(f'data_num={data_num}')
            LIA_mini_API.IIR_play(data_num=data_num)
            LIA_mini_API.IIR_plot()
        elif argv[0] == 'IIR_Config':
            print('IIR config')
            timeconst = float(argv[1])
            sample_rate = float(argv[2])
            ch1_modu_freq = float(argv[3])
            ch2_modu_freq = float(argv[4])
            # Set const
            LIA_mini_API.set_tc(timeconst)
            # Set sampling rate
            LIA_mini_API.sample_rate_config(sample_rate)
            LIA_mini_API.De_fre_config(1, ch1_modu_freq)
            LIA_mini_API.Modu_fre_config(1, ch1_modu_freq)
            LIA_mini_API.De_fre_config(2, ch2_modu_freq)
            LIA_mini_API.Modu_fre_config(2, ch2_modu_freq)
            LIA_mini_API.De_fre_config(3, ch2_modu_freq)
            LIA_mini_API.Modu_fre_config(3, ch2_modu_freq)
            # dac_play
            LIA_mini_API.all_stop()
            LIA_mini_API.play()
            LIA_mini_API.all_start()
        elif argv[0] == 'exit':
            pass
    #
    LIA_mini_API.USB_END()
    exit()
    # ---------
    # DC calibration
    # LIA_mini_API.Auxdaq_Calibration(LIA_mini_API) 
    
    # DAQ calibration
    # LIA_mini_API.DAQ_Calibration()
    
    # IIR calibration
    # LIA_mini_API.IIR_calibration(modu_freq=10371, acq_time=5, sample_rate=3000, timeconst=0.001)
    
    # ----------
    
    # LIA_mini_API.USB_END()
    # exit()
    # 1. DC measurement
    # start_time = time.time()
    # auxDAQ_pnum = 1000
    # LIA_mini_API.auxDAQ_play(data_num=auxDAQ_pnum)
    # stop_time = time.time()
    # print('Time=', stop_time - start_time, 'Sampling Rate=', auxDAQ_pnum / (stop_time - start_time))
    # LIA_mini_API.auxdaq_plot()
    
    # 2. DAQ measurement
    # LIA_mini_API.DAQ_play(data_num=500, extract_ratio=1)
    # LIA_mini_API.daq_plot()
    
    # 3. IIR measurement
    # LIA_mini_API.IIR_play(data_num=1000)
    # LIA_mini_API.IIR_plot()
    
    
    # LIA_mini_API.De_fre_config(1,1)
    # LIA_mini_API.mag_rd()
    # LIA_mini_API.DS18B20_TEMP_RD()

    # exit()
    ###################################
    mexp = exp()

    # mexp.wavesource[0].set_power(3.0e1)
    # mexp.wavesource[1].set_power(0)
    # mexp.wavesource[0].set_freq(2.74e9)
    mexp.ExpSweepCW()
    # mexp.wavesource[1].set_freq(2.6e9)
    # cwres = mexp.Microwaveset()
    # LIA_mini_API.thread_IIR_play(200)

    # EXPDIR('/ExpLaserPIDTest/',mexp.parameter)
    # while(1):
    # cwres=mexp.ExpSweepCW()
    # ~ # cwres=mexp.ExpNoiseAcquiring(time_length=10,mw_mode='on');
    time.sleep(0.5)
    exit()

    # LIA_mini_API.PID_disable(5)
    # LIA_mini_API.all_stop()
    # LIA_mini_API.play()
    # # LIA_mini_API.all_start()
    # for i in range(10):
    # time.sleep(.1)/
    # LIA_mini_API.CS_SPI_Ctrl(1.2)
    # time.sleep(1)/
    # data = LIA_mini_API.auxDAQ_play(100)
    # print('ch1;', np.mean(data[0]),'ch2;', np.mean(data[1]))
    # LIA_mini_API.auxdaq_plot()
    # for i in range(10): 
    kp = -0.000
    # kp = -0.000
    ki = -0.000
    # ki = -0.000
    kd = -0.000
    kt = 1.0
    output_offset = 1.2
    set_point = 0.1
    PID_LIA_CH = 1
    cal_rate = 0
    rd_rate = 0
    ch_coe = [set_point, output_offset, kp, ki, kd, kt, rd_rate, cal_rate, PID_LIA_CH]
    LIA_mini_API.PID_config(5, ch_coe)
    LIA_mini_API.PID_enable(5)
    time.sleep(300)
    # data_laserpid=LIA_mini_API.Laser_PID_play(250000)
    # print("STD",np.std(data_laserpid[0][2000:]))
    write_to_csv(DATAPATH + '/ExpLaserPIDTest/' + gettimestr() + '_data.csv', data_laserpid)
    # # LIA_mini_API.Laser_PID_plot()

    # mexp.run_flag=True
    # opt_coe_list, opt_noise_list, raw_noise_list=mexp.ExpNoiseAcquiring(10000)
    # data = LIA_mini_API.auxDAQ_play(100)
    # print('ch1;', np.mean(data[0]),'ch2;', np.mean(data[1]))
    exit()

    LIA_mini_API.PID_disable(5)
    kp = -0.006
    # kp = -0.000
    ki = -0.0035
    # ki = -0.000
    kd = -0.000
    kt = 1.0
    output_offset = 0.9
    set_point = 0.098
    PID_LIA_CH = 1
    cal_rate = 0
    rd_rate = 0
    ch_coe = [set_point, output_offset, kp, ki, kd, kt, rd_rate, cal_rate, PID_LIA_CH]
    LIA_mini_API.PID_config(5, ch_coe)
    LIA_mini_API.PID_enable(5)
    data_laserpid = LIA_mini_API.Laser_PID_play(250000)
    # print("STD",np.std(data_laserpid[0][2000:]))
    write_to_csv(DATAPATH + '/ExpLaserPIDTest/' + gettimestr() + '_data.csv', data_laserpid)
    LIA_mini_API.Laser_PID_plot()
    mexp.run_flag = True
    # opt_coe_list, opt_noise_list, raw_noise_list=mexp.ExpNoiseAcquiring(10000)
    LIA_mini_API.USB_END()
    # laser = Laser()
    # laser.set_power(cur=0.2)

    # for i in range(100):
    #     time.sleep(0.2)
    #     fpga.MW_SPI_Ctrl(2.85e9 + i * 1e6, 4, 0, 2.95e9, 4, 0)

    # mexp.run_flag = True
    # print('device initialized.')
    # argv = sys.argv[1:]
    # mexp.lockin.SetLockInModuPhase(180, ch=1)  # ch=0:CH0   ch=1:CH1  phase range:[0, 360]
    # if len(argv) > 0:
    #     if argv[0] == 'Noise':
    #         print('ExpNoise')
    #         time_length = float(argv[1])
    #         mexp.ExpNoiseAcquiring(time_length=time_length)
    #     elif argv[0] == 'CW':
    #         print('CW')
    #         mexp.ExpSweepCW(plot_flag=True)
    #     elif argv[0] == 'DAQ':  # pnum=2047
    #         print('DAQ')
    #         pnum = int(argv[1])
    #         mexp.ExpDAQTest(pnum=pnum)
    #     elif argv[0] == 'Laser':
    #         print('Laser')
    #         laser_power = float(argv[1])
    #         mexp.laser.set_power(laser_power)
    #     exit()
