import os
import sys
import logging
import platform
import stat
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QTabWidget, QFormLayout, QSplitter, QMessageBox, QListWidget,QListWidgetItem,
    QFileDialog
)
from PySide6.QtCore import QTimer, Qt,QDateTime
import paramiko
import configparser
import subprocess
import re
import hashlib
import datetime
import time

SYSTEM_CONFIG = "config/system_config.ini"


def load_config(path):
    config = configparser.ConfigParser()
    config.read(path)
    return config
#
# class QTextEditLogger(logging.Handler):
#     def __init__(self, widget):
#         super().__init__()
#         self.widget = widget
#
#     def emit(self, record):
#         msg = self.format(record)
#         self.widget.append(msg)


class SyncManager:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read(SYSTEM_CONFIG)

        self.local_path = self.config.get('Path', 'local_code_path', fallback='./local_repo')
        self.remote_path = self.config.get('Path', 'remote_code_path', fallback='/home/user/remote_repo')
        self.local_data_path = self.config.get('Path', 'local_data_path', fallback='./local_data')
        self.remote_data_path = self.config.get('Path', 'remote_data_path', fallback='/home/user/remote_data')
        self.hostname = self.config.get('Connection', 'hostname', fallback='remote.server.com')
        self.username = self.config.get('Connection', 'username', fallback='username')
        self.password = self.config.get('Connection', 'password', fallback='password')
        self.exemptions = self.load_exemptions()
        self.SyncPanel = None
        self.SyncCodePanel = None

    def sync_date(self):
        hostname = self.hostname
        username = self.username
        password = self.password

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname, username=username, password=password)

            # 获取上位机时间
            local_dt = datetime.datetime.now()
            local_date = local_dt.strftime('%Y-%m-%d %H:%M:%S')
            command = f'sudo date -s \"{local_date}\"'

            # 执行同步命令
            stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
            stdin.write(password + '\\n')
            stdin.flush()
            stdout.channel.recv_exit_status()  # 等待命令完成

            # 获取同步后远端时间
            stdin2, stdout2, stderr2 = ssh.exec_command('date "+%Y-%m-%d %H:%M:%S"')
            remote_date = stdout2.read().decode().strip()

            ssh.close()
            return local_date, remote_date

        except Exception as e:
            print(f"同步时间失败: {e}")
            return local_date, None

    def save_config(self, config_path=SYSTEM_CONFIG):
        if self.SyncPanel is not None:
            self.SyncPanel.update_all_info()
        config = configparser.ConfigParser()
        config.read(config_path)  # 保留其他内容

        # 更新或创建 Connection 部分
        if not config.has_section("Connection"):
            config.add_section("Connection")
        config.set("Connection", "hostname", self.hostname)
        config.set("Connection", "username", self.username)
        config.set("Connection", "password", self.password)

        # 更新或创建 Path 部分
        if not config.has_section("Path"):
            config.add_section("Path")
        config.set("Path", "local_code_path", self.local_path)
        config.set("Path", "remote_code_path", self.remote_path)
        config.set("Path", "local_data_path", self.local_data_path)
        config.set("Path", "remote_data_path", self.remote_data_path)

        # 写回配置文件（保留 Exemptions 和其他 section 不变）
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            config.write(f)

    def load_exemptions(self):
        if self.config.has_section('Exemptions'):
            return [v for k, v in self.config.items('Exemptions') if v]
        return []

    def save_exemptions(self, exemptions):
        if not self.config.has_section('Exemptions'):
            self.config.add_section('Exemptions')
        for key in list(self.config['Exemptions']):
            self.config.remove_option('Exemptions', key)
        for i, val in enumerate(exemptions):
            self.config.set('Exemptions', f'exempt{i + 1}', val)
        with open(SYSTEM_CONFIG, 'w') as f:
            self.config.write(f)
        self.exemptions = exemptions

    def list_local_files(self):
        return self._list_files(self.local_path)

    def list_remote_files(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, username=self.username, password=self.password)
        sftp = ssh.open_sftp()
        file_list = self._list_files_remote(sftp, self.remote_path)
        sftp.close()
        ssh.close()
        return file_list

    def _list_files(self, base_path):
        file_list = []
        for root, _, files in os.walk(base_path):
            for f in files:
                if self._is_exempted(f):
                    continue
                full_path = os.path.relpath(os.path.join(root, f), base_path).replace("\\", "/")
                if not self._is_exempted(full_path):
                    file_list.append(full_path)
        return file_list

    def _list_files_remote(self, sftp, path):
        print(path)
        file_list = []
        for entry in sftp.listdir_attr(path):
            full_path = path + '/' + entry.filename
            if entry.st_mode & 0o040000:
                if self._is_exempted(entry.filename):
                    continue
                file_list.extend(self._list_files_remote(sftp, full_path))
            else:
                rel_path = os.path.relpath(full_path, self.remote_path).replace("\\", "/")
                if not self._is_exempted(rel_path):
                    file_list.append(rel_path)
        return file_list

    def _is_exempted(self, file_path):
        flag1 = (file_path.endswith(".pyc") or "__pycache__" in file_path)
        flag2 = any(file_path.startswith(exempt) for exempt in self.exemptions)
        return flag1 or flag2

    def _file_hash(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return ''

    def _remote_file_hash(self, sftp, remotepath):
        try:
            with sftp.open(remotepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return ''

    def _is_file_modified(self, sftp, fname_local, fname_remote):
        try:
            local_stat = os.stat(fname_local)
            remote_stat = sftp.stat(fname_remote)

            # 1. 如果大小不同，直接判断为修改
            if local_stat.st_size != remote_stat.st_size:
                return True, 'size'

            # 2. 如果 mtime 不同（可设阈值，如1秒），认为改动
            if abs(local_stat.st_mtime - remote_stat.st_mtime) > 0.1:
                return True, 'mtime'

            # 3. 若大小和 mtime 相同，才进行哈希对比
            # local_hash = self._file_hash(fname_local)
            # remote_hash = self._remote_file_hash(sftp, fname_remote)
            # return local_hash != remote_hash, 'hash'
        except Exception as e:
            print(f"检查文件失败: {fname_local}, {e}")
            return True, 'error'

    def compare(self):
        print('开始对比本地-远端文件：')
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, username=self.username, password=self.password)
        sftp = ssh.open_sftp()

        local_files = set(self.list_local_files())
        remote_files = set(self._list_files_remote(sftp, self.remote_path))

        print("完成远端文件对比。")
        only_local = sorted(list(local_files - remote_files))
        only_remote = sorted(list(remote_files - local_files))
        both = sorted(list(local_files & remote_files))



        modified_local, modified_remote = [], []
        for f in both:
            local_fname = os.path.join(self.local_path, f).replace('\\', '/')
            remote_fname = os.path.join(self.remote_path, f).replace("\\", "/")

            hash_start_time = time.time()
            local_hash = self._file_hash(local_fname)
            remote_hash = self._remote_file_hash(sftp, remote_fname)
            hash_stop_time = time.time()
            print(f, 'hash time=', hash_stop_time - hash_start_time)
            if local_hash != remote_hash:
                try:
                    local_mtime = os.path.getmtime(local_fname)
                    remote_mtime = sftp.stat(remote_fname).st_mtime
                    if local_mtime > remote_mtime:
                        modified_local.append(f)
                    else:
                        modified_remote.append(f)
                except Exception as e:
                    print(f"获取文件修改时间失败: {f}, 错误: {e}")
                    # 默认添加到本地修改列表
                    modified_local.append(f)

        sftp.close()
        ssh.close()

        self.SyncPanel.log(f'本地-远端文件对比完毕。找到本地新增文件{len(only_local)}个，远端新增文件{len(only_remote)}个，本地改动文件{len(modified_local)}个，远端改动文件{len(modified_remote)}个。')
        return only_local, only_remote, modified_local, modified_remote

    def should_upload(self, file_path:str):
        return not (file_path.endswith(".pyc") or "__pycache__" in file_path)

    def upload_files(self, files):
        # print('需上传文件：', files)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, username=self.username, password=self.password)
        sftp = ssh.open_sftp()
        for file in files:
            local_path = os.path.join(self.local_path, file).replace("\\", "/")
            remote_path = os.path.join(self.remote_path, file).replace("\\", "/")
            try:
                dir_path = os.path.dirname(remote_path)
                self._ensure_remote_dir(sftp, dir_path)
                sftp.put(local_path, remote_path)
            except Exception as e:
                print(f"上传失败: {file}, 错误: {e}")
        sftp.close()
        ssh.close()

    def download_files(self, files):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, username=self.username, password=self.password)
        sftp = ssh.open_sftp()
        for file in files:
            local_path = self.local_path + '/' + file
            local_dir = os.path.dirname(local_path)
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)
            remote_path = self.remote_path  + '/'  + file
            # print('remote path:', remote_path)
            # print('local path:', local_path)

            try:
                if os.path.exists(local_path):
                    try:
                        os.chmod(local_path, stat.S_IWRITE)  # 解除只读
                        os.remove(local_path)
                    except Exception as e:
                        print(f"⚠️ 无法删除旧文件: {local_path}, 错误: {e}")
                        continue  # 避免 get() 覆盖失败

                sftp.get(remote_path, local_path)
                print(f"✅ 成功下载: {file}")
            except Exception as e:
                print(f"❌ 下载失败: {file}, 错误: {e}")

        sftp.close()
        ssh.close()

    def _ensure_remote_dir(self, sftp, remote_dir):
        dirs = remote_dir.strip("/").split("/")
        path = ""
        for d in dirs:
            path += f"/{d}"
            try:
                sftp.stat(path)
            except IOError:
                sftp.mkdir(path)

    def test_ssh_connection(self):
        print(self.hostname, self.username, self.password)
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.hostname, username=self.username, password=self.password, timeout=0.5)
            ssh.close()
            return True, "SSH连接成功"
        except Exception as e:
            return False, f"SSH连接失败: {str(e)}"

    def list_remote_data_files(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, username=self.username, password=self.password)
        sftp = ssh.open_sftp()
        result = []
        result_dir = []

        def walk(path):
            for entry in sftp.listdir_attr(path):
                full_path = f"{path}/{entry.filename}"
                rel_path = os.path.relpath(full_path, self.remote_data_path).replace("\\", "/")
                if entry.st_mode & 0o040000:
                    walk(full_path)
                    # result_dir.append((rel_path, entry.st_mtime, True))
                    result.append((rel_path, entry.st_mtime, True))
                else:
                    result.append((rel_path, entry.st_mtime, False))

        walk(self.remote_data_path)
        sftp.close()
        ssh.close()
        return result

    def download_data_files(self, selected_files):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, username=self.username, password=self.password)
        sftp = ssh.open_sftp()

        for rel_path, remote_mtime, _ in selected_files:
            remote_full = os.path.join(self.remote_data_path, rel_path).replace("\\", "/")
            local_full = os.path.join(self.local_data_path, rel_path).replace("\\", "/")
            local_dir = os.path.dirname(local_full)

            print(local_full)

            if not os.path.exists(local_dir):
                os.makedirs(local_dir)

            if os.path.exists(local_full):
                local_mtime = os.path.getmtime(local_full)
                if local_mtime >= remote_mtime:
                    continue

            try:
                sftp.get(remote_full, local_full)
            except Exception as e:
                print(f"下载失败: {rel_path}, 错误: {e}")

        sftp.close()
        ssh.close()


class ExperimentApp(QWidget):
    def __init__(self):
        super().__init__()
        self.sync_manager = SyncManager()
        self.setWindowTitle("实验代码/数据同步程序")
        self.resize(1300, 850)

        # self.cpu_label = QLabel("CPU 使用率：0%")
        # self.mem_label = QLabel("内存占用：0%")
        self.device_status = {}

        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        # self.tabs.addTab(self.create_sync_panel(), "数据同步传输")
        # 用法示例：

        self.sync_panel = SyncPanel(self)
        self.tabs.addTab(self.sync_panel, "数据同步传输")
        # main_layout.addWidget(self.cpu_label)
        # main_layout.addWidget(self.mem_label)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self.sync_panel.set_buttons_enabled(False)

        self.update_timer = QTimer()
        # self.update_timer.timeout.connect(self.update_system_info)
        # self.update_timer.start(1000)/

    def create_sync_panel(self):
        panel = QWidget()
        layout = QFormLayout()

        self.sync_ip_input = QLineEdit()
        self.sync_ip_input.setPlaceholderText("请输入远端设备 IP 地址")

        self.code_path_label = QLabel("未选择")
        code_btn = QPushButton("选择代码目录")
        code_btn.clicked.connect(lambda: self.select_folder(self.code_path_label))

        self.data_path_label = QLabel("未选择")
        data_btn = QPushButton("选择数据目录")
        data_btn.clicked.connect(lambda: self.select_folder(self.data_path_label))

        sync_btn = QPushButton("开始同步")
        sync_btn.clicked.connect(self.start_sync)

        layout.addRow(QLabel("远端设备IP 地址："), self.sync_ip_input)
        layout.addRow(code_btn, self.code_path_label)
        layout.addRow(data_btn, self.data_path_label)
        layout.addRow(sync_btn)

        panel.setLayout(layout)
        return panel

    def select_folder(self, label):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            label.setText(folder)

    def start_sync(self):
        ip = self.sync_ip_input.text()
        code_path = self.code_path_label.text()
        data_path = self.data_path_label.text()
        if ip and code_path != "未选择" and data_path != "未选择":
            logging.info(f"同步启动：目标IP={ip}，代码路径={code_path}，数据路径={data_path}")
        else:
            logging.warning("请确保填写IP地址并选择了两个路径")





class SyncPanel(QWidget):
    def __init__(self, parent):
        super().__init__()

        self.config = load_config(SYSTEM_CONFIG)
        self.connected = False  # 用于控制按钮状态
        self.sync_manager = parent.sync_manager
        self.sync_manager.SyncPanel = self


        layout = QVBoxLayout()

        # IP 输入
        local_ip_layout = QHBoxLayout()
        local_ip_layout.addWidget(QLabel("本机 IP："))
        self.local_ip_input = QLineEdit()
        self.local_ip_input.setText(self.config.get("Connection", "localname", fallback=""))
        local_ip_layout.addWidget(self.local_ip_input)

        self.find_local_ip_btn = QPushButton("检测本机IP")
        self.find_local_ip_btn.clicked.connect(self.find_local_ip)
        local_ip_layout.addWidget(self.find_local_ip_btn)

        ip_layout = QHBoxLayout()
        ip_layout.addWidget(QLabel("远端设备 IP："))
        self.ip_input = QLineEdit()
        self.ip_input.setText(self.config.get("Connection", "hostname", fallback=""))
        ip_layout.addWidget(self.ip_input)

        self.find_ip_btn = QPushButton("检测远端设备IP")
        self.find_ip_btn.clicked.connect(self.find_pc_ip)
        ip_layout.addWidget(self.find_ip_btn)

        # self.check_btn = QPushButton("SSH连接测试")
        # self.check_btn.clicked.connect(self.check_ip_connection)
        # ip_layout.addWidget(self.check_btn)

        self.ssh_test_btn = QPushButton("测试SSH连接")
        self.ssh_test_btn.clicked.connect(self.test_ssh_connection_click)
        ip_layout.addWidget(self.ssh_test_btn)

        layout.addLayout(local_ip_layout)
        layout.addLayout(ip_layout)

        # 用户名和密码输入
        self.user_input = QLineEdit(self.config.get("Connection", "username", fallback="pi"))
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setText(self.config.get("Connection", "password", fallback="esr"))
        cred_layout = QHBoxLayout()
        cred_layout.addWidget(QLabel("用户名："))
        cred_layout.addWidget(self.user_input)
        cred_layout.addWidget(QLabel("密码："))
        cred_layout.addWidget(self.pwd_input)
        layout.addLayout(cred_layout)

        # 路径设置

        self.local_code_path = QLineEdit(self.config.get("Path", "local_code_path", fallback=""))
        self.remote_code_path = QLineEdit(self.config.get("Path", "remote_code_path", fallback=""))
        self.local_data_path = QLineEdit(self.config.get("Path", "local_data_path", fallback=""))
        self.remote_data_path = QLineEdit(self.config.get("Path", "remote_data_path", fallback=""))

        path_layout = QVBoxLayout()
        for label, field in [("本地代码路径", self.local_code_path), ("远程代码路径", self.remote_code_path),
                             ("本地数据路径", self.local_data_path), ("远程数据路径", self.remote_data_path)]:
            h = QHBoxLayout()
            h.addWidget(QLabel(label))
            h.addWidget(field)
            path_layout.addLayout(h)
        layout.addLayout(path_layout)

        self.save_config_btn = QPushButton("保存配置")
        self.save_config_btn.clicked.connect(self.save_config)
        layout.addWidget(self.save_config_btn)

        self.refresh_btn = QPushButton("浏览可同步数据")
        self.refresh_btn.clicked.connect(self.load_remote_files)
        layout.addWidget(self.refresh_btn)

        self.date_sync_btn = QPushButton("同步系统时间")
        self.date_sync_btn.clicked.connect(self.sync_date)
        layout.addWidget(self.date_sync_btn)

        self.splitter = QSplitter(Qt.Horizontal)
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QListWidget.MultiSelection)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.MultiSelection)

        self.splitter.addWidget(self.folder_list)
        self.splitter.addWidget(self.file_list)
        layout.addWidget(self.splitter)

        self.btn_layout = QHBoxLayout()
        self.download_folder_btn = QPushButton("下载选中文件夹")
        self.download_folder_btn.clicked.connect(self.download_selected_folders)
        self.btn_layout.addWidget(self.download_folder_btn)

        self.download_file_btn = QPushButton("下载选中文件")
        self.download_file_btn.clicked.connect(self.download_selected_files)
        self.btn_layout.addWidget(self.download_file_btn)

        layout.addLayout(self.btn_layout)

        # 状态显示
        self.status_output = QTextEdit()
        self.status_output.setReadOnly(True)
        layout.addWidget(self.status_output)

        self.setLayout(layout)

        self.platform = platform.system()
        self.log(f'当前软件平台:{self.platform}')

    def save_config(self):
        self.sync_manager.save_config()
        print('配置已保存。')
        with open(SYSTEM_CONFIG, 'r') as f:
            lines = f.readlines()
            for line in lines:
                print(line)

    def log(self, msg):
        self.status_output.append(msg)
        print(msg)

    def set_buttons_enabled(self, enabled):
        self.download_folder_btn.setEnabled(enabled)
        self.download_file_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.date_sync_btn.setEnabled(enabled)


    def sync_date(self, event=None):
        # === 获取上位机当前时间（格式为 yyyy-mm-dd hh:mm:ss）==
        local_date, remote_date = self.sync_manager.sync_date()
        self.log(f"同步后本机时间：{local_date}  同步后远端设备时间：{remote_date}")

    def find_local_ip(self):
        if self.platform == 'Linux':
            result = subprocess.run(['ifconfig'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                print("❌ 无法运行 ifconfig 命令")
                return None

            # 正则匹配169.254.x.x格式的IPv4地址
            ip_pattern = re.compile(r'inet\s+(169\.254\.\d+\.\d+)')
            stdout_result = result.stdout
            # print(stdout_result)
            matches = ip_pattern.findall(stdout_result)
            if matches:
                self.log(f"✅ 找到本机 link-local IP: {matches[0]}")
                self.local_ip_input.setText(matches[0])
                return matches[0]
            else:
                self.log("❌  未找到本机 link-local IP")
                return None
        elif self.platform == 'Windows':
            result = subprocess.run(['ipconfig'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                self.log("❌ 无法执行 ipconfig")
                return None

            # 匹配 169.254.x.x 的地址（在 IPv4 地址一行中）
            ip_pattern = re.compile(r'IPv4.*?:\s*(169\.254\.\d+\.\d+)')
            matches = ip_pattern.findall(result.stdout)
            if matches:
                self.log(f"✅ 找到本机 link-local IP: {matches[0]}")
                self.local_ip_input.setText(matches[0])
                return matches[0]
            else:
                self.log("❌ 未找到本机 link-local IP")
                return None

    def find_pc_ip(self):
        if self.platform == 'Linux':
            result = subprocess.run(['arp', '-n'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                self.log("❌ 无法执行 arp 命令。")
                return

            pattern = re.compile(r'(169\.254\.\d+\.\d+)\s+ether\s+([0-9a-f:]{17})', re.IGNORECASE)
            for line in result.stdout.splitlines():
                match = pattern.search(line)
                if match:
                    ip = match.group(1)
                    self.ip_input.setText(ip)
                    self.log(f"✅ 找到远端设备 IP: {ip}")
                    self.sync_manager.hostname = ip
                    return

            self.log("❌ 未发现符合条件的远端设备 IP")
        elif self.platform == 'Windows':
            result = subprocess.run(['arp', '-a'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                self.log("❌ 无法执行 arp 命令")
                return

            # 匹配 ARP 表中 169.254.x.x 地址
            # pattern = re.compile(r'(169\\.254\\.\\d+\\.\\d+)\\s+动态')
            # pattern = re.compile(r'*(169\\.254\\.\\d+\\.\\d+)*动态*')
            pattern = re.compile(r'(169\.254\.\d+\.\d+).*动态')
            for line in result.stdout.splitlines():
                match = pattern.search(line)
                if match:
                    ip = match.group(1)
                    self.ip_input.setText(ip)
                    self.log(f"✅ 找到远端设备 IP: {ip}")
                    self.sync_manager.hostname = ip
                    return

            self.log("❌ 未发现符合条件的远端设备 IP")

    def update_all_info(self):
        # 获取所有输入
        ip = self.ip_input.text().strip()
        username = self.user_input.text()
        password = self.pwd_input.text()
        local_code_path = self.local_code_path.text()
        remote_code_path = self.remote_code_path.text()
        local_data_path = self.local_data_path.text()
        remote_data_path = self.remote_data_path.text()

        # 更新远端sftp管理器
        self.sync_manager.hostname = ip
        self.sync_manager.username = username
        self.sync_manager.password = password
        self.sync_manager.local_path = local_code_path
        self.sync_manager.remote_path = remote_code_path
        self.sync_manager.local_data_path = local_data_path
        self.sync_manager.remote_data_path = remote_data_path

    def check_ip_connection(self):
        import paramiko
        ip = self.ip_input.text().strip()
        try:
            sock = paramiko.Transport((ip, 22))
            sock.close()
            self.log(f"✅ 可连接到上位机 {ip}:22")
        except Exception as e:
            self.log(f"❌ 无法连接到 {ip}: {e}")
            self.set_buttons_enabled(False)

    def test_ssh_connection_click(self):
        success, message = self.sync_manager.test_ssh_connection()
        QMessageBox.information(self, "连接测试", message)
        if success:
            self.set_buttons_enabled(True)
        else:
            self.set_buttons_enabled(False)

    def load_remote_files(self):
        self.update_all_info()
        self.folder_list.clear()
        self.file_list.clear()
        self.remote_data_files = self.sync_manager.list_remote_data_files()

        filtered = []
        for rel_path, remote_mtime, is_dir in self.remote_data_files:
            local_full = os.path.join(self.sync_manager.local_data_path, rel_path)
            if os.path.exists(local_full):
                local_mtime = os.path.getmtime(local_full)
                if local_mtime >= remote_mtime:
                    continue
            filtered.append((rel_path, remote_mtime, is_dir))

        # 排序
        filtered.sort(key=lambda x: (-x[1], not x[2]))

        for rel_path, mtime, is_dir in filtered:
            dt_str = QDateTime.fromSecsSinceEpoch(mtime).toString("yyyy-MM-dd hh_mm_ss")
            item = QListWidgetItem(f"{rel_path} | 更新时间: {dt_str}")
            item.setData(Qt.UserRole, (rel_path, mtime, is_dir))
            if is_dir:
                self.folder_list.addItem(item)
            else:
                self.file_list.addItem(item)
        self.log(f'已更新远端/本地数据文件夹信息，找到{len(filtered)}个可同步对象。')

    def download_selected_folders(self):
        selected_items = self.folder_list.selectedItems()
        folder_paths = [item.data(Qt.UserRole)[0] for item in selected_items]

        # 确保每个远端文件夹在本地都创建了对应目录（即使为空）
        for remote_folder in folder_paths:
            local_folder = self.sync_manager.local_data_path + '/' + remote_folder.replace('\\', '/')
            # print(local_folder)
            os.makedirs(local_folder, exist_ok=True)
            os.utime(local_folder, None)
        files_to_download = [x for x in self.remote_data_files if
                             not x[2] and any(x[0].startswith(f + "/") for f in folder_paths)]
        self.sync_manager.download_data_files(files_to_download)
        QMessageBox.information(self, "完成", f"成功下载文件夹下 {len(files_to_download)} 个文件。")
        self.load_remote_files()

    def download_selected_files(self):
        selected_items = self.file_list.selectedItems()
        files_to_download = [item.data(Qt.UserRole) for item in selected_items]
        self.sync_manager.download_data_files(files_to_download)
        QMessageBox.information(self, "完成", f"成功下载 {len(files_to_download)} 个数据文件。")
        self.load_remote_files()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ExperimentApp()
    window.show()
    sys.exit(app.exec())
