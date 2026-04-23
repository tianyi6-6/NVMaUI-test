import scipy
import scipy.signal
from scipy.signal import welch, get_window, filtfilt, butter, detrend, square, lfilter
from scipy.interpolate import interp1d
from scipy.stats import linregress
import math
import pandas as pd
import numpy as np
import time
from collections import deque
from bisect import bisect_right
import logging
import os

mpl_color_list = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
                     '#bcbd22', '#17becf']


def poly_detrend(x, y, deg=2):
    """
    多项式去基线

    参数：
        x   : 一维数组，自变量（如时间）
        y   : 一维数组，因变量（原始数据）
        deg : 多项式阶数（2 表示二次）

    返回：
        y_detrended : 去基线后的数据
        baseline_fit: 拟合的基线数据
    """
    # 多项式拟合
    coeffs = np.polyfit(x - x[0], y, deg)
    baseline_fit = np.polyval(coeffs, x - x[0])

    # 去基线
    y_detrended = y - baseline_fit

    return y_detrended

def moving_average_filter(data, n):
    """
    平均滤波器（滑动窗口），保持原始长度不变。

    参数:
        data : 1D ndarray
            输入时域数据
        fs : float
            采样率（Hz）
        window_time_sec : float
            滑动窗口宽度（秒），默认0.1秒

    返回:
        filtered_data : 1D ndarray
            平滑处理后的数据
    """
    if n < 1:
        raise ValueError("窗口长度必须 ≥ 1 样本")

    kernel = np.ones(n) / n  # 滤波器系数（均值核）
    # filtered = lfilter(kernel, 1, data)

    # 为保持相位对齐，可使用 symmetric padding + 滤波 + 去掉padding
    pad = (n - 1) // 2
    padded = np.pad(data, (pad, pad), mode='edge')
    filtered_full = lfilter(kernel, 1, padded)
    result = filtered_full[pad: pad + len(data)]

    return result

def format_dir(data_path):
    '''统一文件路径格式'''
    data_path = data_path.replace('\\', '/')
    if data_path[-1] != '/':
        data_path += '/'
    return data_path

def time_stamp_to_date(timestamp):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))

def getfnames(data_path, keyword):
    fnames = []
    data_path = format_dir(data_path)
    # print(data_path)
    for fname in os.listdir(data_path):
        if keyword in fname:
            fnames.append(data_path + fname)
    if len(fnames) == 0:
        fnames.append(None)
    return fnames

def read_noise_from_dir(data_path, format='.csv', remove_zero_ends=True):
    fnames = getfnames(data_path, format)
    time_data_all, t_mac_all, fluo_x_all, fluo_y_all, laser_x_all, laser_y_all, fluo_dc_all, laser_dc_all = [], [], [], [], [], [], [], []
    start_time = time.time()
    for fname in fnames:
        with open(fname, 'r') as f:
            lines = f.readlines()
            for line in lines:
                if '%' not in line:
                    t_mac, t_cal, fluo_x, fluo_y, laser_x, laser_y, fluo_dc, laser_dc = line.split(',')
                    time_data_all.append(float(t_cal))
                    t_mac_all.append(float(t_mac))
                    fluo_x_all.append(float(fluo_x))
                    fluo_y_all.append(float(fluo_y))
                    laser_x_all.append(float(laser_x))
                    laser_y_all.append(float(laser_y))
                    fluo_dc_all.append(float(fluo_dc))
                    laser_dc_all.append(float(laser_dc))
    end_time = time.time()
    print(f'文件夹{data_path},读取数据文件{len(fnames)}个，耗时{end_time - start_time} s')
    print(f'数据开始时间：{time_stamp_to_date(time_data_all[0])}')
    print(f'数据结束时间：{time_stamp_to_date(time_data_all[-1])}')
    return np.array(time_data_all), np.array(t_mac_all), np.array(fluo_x_all), np.array(fluo_y_all), np.array(laser_x_all), np.array(laser_y_all), np.array(fluo_dc_all), np.array(laser_dc_all)



def analyze_time_intervals(time_data, sample_rate, threshold):
    """
    分析时间间隔，返回时间间隔列表
    """
    dt = 1 / sample_rate
    time_intervals = [] # 返回一个列表，每个元素为(start_id, stop_id)，表示时间间隔的开始和结束索引
    start_id = 0
    for i in range(len(time_data) - 1):
        if time_data[i + 1] - time_data[i] > dt * threshold:
            time_intervals.append((start_id, i))
            start_id = i + 1
    time_intervals.append((start_id, len(time_data) - 1))
    return time_intervals

class MinAvgWindowSelector:
    def __init__(self, f, L, M, D):
        '''

        @param f: 待求解的一维数组
        @param L: 滑动窗口长度
        @param M: 滑动窗口个数
        @param D: 窗口间最小距离
        '''
        self.f = f
        self.L = L
        self.M = M
        self.N = len(f)
        self.D = D
        print('开始计算初始化窗口数据..')
        self.windows = self._get_all_windows()
        print('结束计算初始化窗口数据..')

    def _get_all_windows(self):
        """
        使用单调队列获取所有长度为 L 的窗口及其最小值
        返回一个列表：每个元素为 (start, end, min_val)
        """
        n = self.N
        L = self.L
        f = self.f
        dq = deque()
        min_windows = []
        for i in range(n):
            # 清理队列中超出范围的元素
            while dq and dq[0] <= i - L:
                dq.popleft()
            # 保持队列递增
            while dq and f[dq[-1]] >= f[i]:
                dq.pop()
            dq.append(i)
            # 当前窗口结束
            if i >= L - 1:
                start = i - L + 1
                end = i
                min_val = f[dq[0]]
                min_windows.append((start, end, min_val))
        return min_windows

    def solve(self):
        """
        动态规划求解最小平均值的 M 个不重叠窗口
        返回 (selected_windows, min_avg)
        """
        intervals = self.windows
        n = len(intervals)

        # 将 intervals 按结束位置排序
        intervals.sort(key=lambda x: x[1])

        # 提取所有窗口的 end 用于二分查找
        ends = [interval[1] for interval in intervals]
        # 使用二分查找构建不重叠窗口索引prev 表
        prev = []
        for i in range(n):
            # 找最后一个 end < 当前 start
            j = bisect_right(ends, intervals[i][0] - self.D)
            prev.append(j - 1)  # 如果找不到就是 -1
        print('完成构建索引表')

        # DP表：dp[i][k] 表示前i个窗口选k个的最小总min值
        dp = [[float('inf')] * (self.M + 1) for _ in range(n + 1)]
        path = [[-1] * (self.M + 1) for _ in range(n + 1)]
        dp[0][0] = 0

        for i in range(1, n + 1):
            for k in range(self.M + 1):
                # 不选当前窗口
                if dp[i - 1][k] < dp[i][k]:
                    dp[i][k] = dp[i - 1][k]
                    path[i][k] = path[i - 1][k]

                # 选当前窗口
                if k > 0:
                    j = prev[i - 1] + 1  # prev index + 1 (for dp index)
                    cost = intervals[i - 1][2]
                    if dp[j][k - 1] + cost < dp[i][k]:
                        dp[i][k] = dp[j][k - 1] + cost
                        path[i][k] = i - 1  # 记录选择了第 i-1 个窗口

        # 回溯选中的窗口
        selected = []
        i, k = n, self.M
        while k > 0 and i >= 0:
            idx = path[i][k]
            if idx == -1:
                break
            selected.append(intervals[idx])
            i = prev[idx] + 1
            k -= 1

        selected.reverse()
        min_avg = dp[n][self.M] / self.M if self.M > 0 else 0
        return selected, min_avg
    
def time_stamp_to_date(timestamp):
    """将时间戳转换为日期字符串。"""
    return time.strftime('%Y-%m-%d %H_%M_%S', time.localtime(timestamp))

def gettimestr():
    """获取当前时间字符串。"""
    return time.strftime('%Y-%m-%d %H_%M_%S', time.localtime(time.time()))

def get_sample_rate(time_data):
    """
    假设时间数据基于等间距采样，计算其采样率。
    """
    return len(time_data) / (time_data[-1] - time_data[0])

def rolling_std_fast(time_data, noise_data, window_size):
    """
    高效计算滚动标准差（Rolling Std）及对应时间点。

    参数：
        time_data (array-like): 时间数组，长度 N
        noise_data (array-like): 噪声数据数组，长度 N
        window_size (int): 窗口大小（单位：点数）

    返回：
        std_times (np.ndarray): 中心时间点数组
        rolling_stds (np.ndarray): 滚动标准差数组
    """
    time_data = np.asarray(time_data)
    noise_data = np.asarray(noise_data)

    if len(time_data) != len(noise_data):
        raise ValueError("time_data 和 noise_data 长度不一致")

    if window_size < 2:
        raise ValueError("window_size 必须大于1")

    df = pd.DataFrame({
        'time': time_data,
        'noise': noise_data
    })

    rolling_std_series = df['noise'].rolling(window=window_size, center=True).std()

    # 丢掉因为滚动窗口导致的NaN（开头和结尾），同步处理time
    valid_idx = rolling_std_series.notna()

    std_times = df['time'][valid_idx].values
    rolling_stds = rolling_std_series[valid_idx].values

    return std_times, rolling_stds

def remove_baseline(data, method):
    if method == "None":
        return data
    elif method == "Remove Baseline":
        return data - np.mean(data)
    elif method == "Linear Detrend":
        return detrend(data)

def remove_spike(data, threshold, window_size=9):
    """Use Median Filter to identfy, and Interpolate the spike"""
    if window_size % 2 == 0:
        window_size += 1
        logging.info(f'Window size is even, add 1 to make it odd: {window_size}')
    med_filtered = scipy.signal.medfilt(data, kernel_size=window_size)
    diff = np.abs(data - med_filtered)
    bad_mask = diff > threshold * np.std(data)
    data[bad_mask] = np.nan
    good_idx = ~np.isnan(data)
    data = np.interp(np.arange(len(data)), np.where(good_idx)[0], data[good_idx])
    return data

def cal_ASD(data, fs):
    window_length = int(math.floor(len(data) / 3))
    # print(window_length)

    pnum_in_freq_domain = int(pow(2, math.ceil(math.log(window_length, 2))))
    bm_win = get_window('blackmanharris', window_length)
    f, Pxx_den = welch(data, fs=fs,
                       window=bm_win,
                       noverlap=math.floor(window_length / 2),
                       nfft=pnum_in_freq_domain,
                       detrend=False
                       )

    axx = Pxx_den ** 0.5
    return f[1:], axx[1:]

def cal_FFT(data, fs):
    f = np.fft.rfftfreq(len(data), d=1.0 / fs)
    fft_data = np.abs(np.fft.rfft(data))
    return f, fft_data

def bandpass_filter(signal, fs, start_freq, stop_freq, filter_order=2):
    """
    对给定的时域信号进行带通滤波。

    :param time: 一维 numpy 数组，长度为 N，表示每个样本的采样时间（假设等间隔采样）
    :param signal: 一维 numpy 数组，长度为 N，对应 time 上的采样值
    :param start_freq: 带通滤波器的低截止频率（Hz）
    :param stop_freq: 带通滤波器的高截止频率（Hz）
    :param filter_order: 滤波器阶数（默认为 4）
    :return: 经过带通滤波后的信号，类型为 numpy 数组，长度与原信号相同
    """
    # 确定采样率（假设相邻采样点时间间隔相同）

    # dt = time[1] - time[0]         # 两个相邻时间点的间隔
    # fs = 1.0 / dt                  # 采样率（Hz）

    # 计算归一化截止频率（相对于 Nyquist 频率）
    nyquist = 0.5 * fs
    low_cut = start_freq / nyquist
    high_cut = stop_freq / nyquist

    # 设计 Butterworth 带通滤波器
    b, a = scipy.signal.butter(filter_order, [low_cut, high_cut], btype='band')

    # print(f'滤波器 N={len(signal)}, lc={low_cut}, hc={high_cut}')
    # 使用 filtfilt 进行零相位滤波，避免相位失真
    filtered_signal = filtfilt(b, a, signal)
    #
    # # 计算频响
    # w, h = scipy.signal.freqz(b, a, worN=4096 * 16)  # w is in radians/sample
    #
    # # 转换横轴单位为 Hz
    # freqs = w * fs / (2 * np.pi)
    # dB_data = 20 * np.log10(np.abs(h))
    #
    # # mask = (freqs>=1e-4) & (freqs<=1)
    # mask = (dB_data >= -6)
    #
    # # 画双对数图
    # plt.figure(figsize=(6, 4))
    # plt.semilogx(freqs[mask], dB_data[mask], label='Filter Freq. Response', color='black')
    #
    # plt.axvspan(1e-3, 0.5, alpha=0.2, color='yellow', label='1mHz - 0.5Hz')
    # # plt.fill_between(1e-3, 0.5, alpha=0.3, color='yellow', label='1mHz - 0.5Hz')
    # plt.axhline(-3, color='red', linestyle='--', label='-3dB')
    # # plt.semilogx(freqs[mask], np.abs(h[mask]), label='Magnitude')
    # plt.title(f'Butterworth Bandpass Filter Frequency Response\n{start_freq}–{stop_freq} Hz')
    # plt.xlabel('Frequency (Hz)')
    # plt.ylabel('Magnitude (dB)')
    # plt.legend()
    # plt.grid(which='both', linestyle='--', linewidth=0.5)
    # plt.tight_layout()
    # plt.show()

    return filtered_signal

def highpass_filter(fluo_data, sample_rate, lower_cutoff_freq, filter_order=2):
    """
    使用 Butterworth 高通滤波器对信号进行滤波
    
    :param fluo_data: 输入信号，类型为 numpy 数组
    :param sample_rate: 采样率（Hz）
    :param lower_cutoff_freq: 高通滤波器的截止频率（Hz）
    :param filter_order: 滤波器阶数（默认为 4）
    :return: 经过高通滤波后的信号，类型为 numpy 数组，长度与原信号相同
    """
    # 计算归一化截止频率（相对于 Nyquist 频率）
    nyquist = 0.5 * sample_rate
    cutoff = lower_cutoff_freq / nyquist

    # 设计 Butterworth 高通滤波器
    b, a = scipy.signal.butter(filter_order, cutoff, btype='high')

    # 使用 filtfilt 进行零相位滤波，避免相位失真
    filtered_signal = filtfilt(b, a, fluo_data)

    return filtered_signal

def lowpass_filter(fluo_data, sample_rate, upper_cutoff_freq, filter_order=2):
    """
    使用 Butterworth 低通滤波器对信号进行滤波
    
    :param fluo_data: 输入信号，类型为 numpy 数组
    :param sample_rate: 采样率（Hz）
    :param upper_cutoff_freq: 低通滤波器的截止频率（Hz）
    :param filter_order: 滤波器阶数（默认为 4）
    :return: 经过低通滤波后的信号，类型为 numpy 数组，长度与原信号相同
    """
    # 计算归一化截止频率（相对于 Nyquist 频率）
    nyquist = 0.5 * sample_rate
    cutoff = upper_cutoff_freq / nyquist

    # 设计 Butterworth 低通滤波器
    b, a = scipy.signal.butter(filter_order, cutoff, btype='low')

    # 使用 filtfilt 进行零相位滤波，避免相位失真
    filtered_signal = filtfilt(b, a, fluo_data)

    return filtered_signal


def get_optimize_coe(data1, data2):
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
    optcoe = cov / (np.std(col2) ** 2)
    # 返回最优系数以及相消前后噪声
    diff_data = col1 - optcoe * col2
    raw_noise = np.std(col1)
    opt_noise = np.std(diff_data)
    return optcoe, opt_noise, raw_noise