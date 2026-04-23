from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
import sys
import os
import time
import re
import paramiko
import numpy as np
from PySide6.QtCore import QObject, Signal
from threading import Thread
import stat  # 添加这个

class RemoteNPYMonitor(QObject):
    # prefix, filename, data
    new_data_signal = Signal(str, str, np.ndarray)

    def __init__(self, hostname, username, password,
                 remote_dir, local_dir, device_index_dict=None, poll_interval=3.0):
        super().__init__()
        self.hostname = hostname
        self.username = username
        self.password = password
        self.remote_dir = remote_dir
        self.local_dir = local_dir
        self.device_index_dict = device_index_dict or {}  # 形如 {"flux1": 1, "nv2": 1}
        self.poll_interval = poll_interval

        self.running = False
        self.ssh = None
        self.sftp = None

    def start_monitoring(self):
        if self.running:
            return
        self.running = True
        self._connect()

        # 获取远端最新实验子目录
        exp_folder = self._get_latest_remote_subfolder(self.remote_dir)
        print(f"[Session] Found latest remote folder: {exp_folder}")

        # 设置 remote_dir 与 local_dir 为具体的子目录路径
        self.remote_dir = os.path.join(self.remote_dir, exp_folder) + '/'
        self.local_dir = self._create_local_sync_folder(self.local_dir, exp_folder) + '/'

        # 初始化设备索引（基于 remote_dir 下的内容）
        self._initialize_indices_from_remote()

        # 启动后台监控线程
        self.thread = Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop_monitoring(self):
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join()
        self._disconnect()

    def _connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(self.hostname, username=self.username, password=self.password)
        self.sftp = self.ssh.open_sftp()

    def _disconnect(self):
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()

    def _get_latest_remote_subfolder(self, parent_path):
        try:
            folders = []
            for item in self.sftp.listdir_attr(parent_path):
                if stat.S_ISDIR(item.st_mode):
                    folders.append((item.filename, item.st_mtime))
            if not folders:
                raise FileNotFoundError("No experiment subfolders found.")
            # 取最近修改时间最大的文件夹
            latest_folder = max(folders, key=lambda x: x[1])[0]
            return latest_folder
        except Exception as e:
            raise RuntimeError(f"Failed to identify latest remote folder: {e}")

    def _create_local_sync_folder(self, parent_path, subfolder):
        full_path = os.path.join(parent_path, subfolder)
        os.makedirs(full_path, exist_ok=True)
        return full_path

    def _initialize_indices_from_remote(self):
        try:
            filenames = self.sftp.listdir(self.remote_dir)
            for prefix in self.device_index_dict:
                pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)\.npy$")
                max_index = 0
                for fname in filenames:
                    match = pattern.match(fname)
                    if match:
                        idx = int(match.group(1))
                        if idx > max_index:
                            max_index = idx
                self.device_index_dict[prefix] = max_index + 1
                print(f"[Init] {prefix}: start from {self.device_index_dict[prefix]}")
        except Exception as e:
            print(f"[Init Error] {e}")
            for prefix in self.device_index_dict:
                self.device_index_dict[prefix] = 0

    def _monitor_loop(self):
        try:
            while self.running:
                updated = False
                for prefix, index in self.device_index_dict.items():
                    filename = f"{prefix}_{index}.npy"
                    # print(f'Trying to monitor {filename}..')
                    # remote_path = os.path.join(self.remote_dir, filename)
                    # local_path = os.path.join(self.local_dir, filename)
                    remote_path = self.remote_dir + filename
                    local_path = self.local_dir + filename
                    # print(f'Remote Path:{remote_path}, Local Path:{local_path}')
                    try:
                        self.sftp.stat(remote_path)
                        self.sftp.get(remote_path, local_path)
                        data = np.load(local_path)
                        self.new_data_signal.emit(prefix, filename, data)
                        self.device_index_dict[prefix] += 1
                        updated = True
                    except FileNotFoundError:
                        continue
                    except Exception as e:
                        print(f"[Error] {filename}: {e}")
                if not updated:
                    time.sleep(self.poll_interval)
        finally:
            self._disconnect()



class _MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.label = QLabel("等待数据中...")
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.monitor = RemoteNPYMonitor(
            hostname="169.254.51.251",
            username="pi",
            password="esr",
            remote_dir="/home/pi/test_npy_files/",
            local_dir="D:/Software Learning/20250619 RemoteDataTestDir/",
            device_index_dict={'NV1':0,'NV2':0,'flux1':0,'flux2':0,'flux3':0},
            poll_interval=2.5,
        )

        self.monitor.new_data_signal.connect(self.on_new_data)
        self.monitor.start_monitoring()

    def on_new_data(self, devname, filename, data):
        print(f'[{devname}] [{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))}] 探测到 {filename}，数据形状{data.shape}')
        self.label.setText(f"已下载: {filename}，数据形状: {data.shape}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = _MainWindow()
    win.show()
    sys.exit(app.exec())