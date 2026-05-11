# NVMagUI — 金刚石NV色心磁探测器自动化实验控制程序

基于 PySide6 + pyqtgraph 构建的专业科学仪器控制软件，用于**金刚石NV色心磁探测实验**的自动化控制与数据采集。

## 项目简介

**NVMagUI**（NV Magnetometry UI）是一套完整的金刚石NV色心磁探测器自动化实验控制程序，提供从设备连接、参数配置、数据采集到实时可视化的全流程支持。

### 核心亮点

✅ **多设备协同** — 集成锁相放大器、微波源、激光器、超声电机等多种硬件设备
✅ **可视化工作流** — 类似 ComfyUI 的拖拽式节点编程，灵活编排实验流程
✅ **实时数据采集** — 支持 CW 谱、IIR 模式、DC/AC 示波器等多种采集模式
✅ **状态机管理** — 完善的设备状态流转控制
✅ **数据持久化** — 自动分类保存实验数据与日志
✅ **多设备支持** — 支持多台设备样机独立配置（dev1-dev6）
✅ **模块化设计** — 清晰的代码结构，便于扩展和维护

---

## 物理背景

### NV色心磁探测原理

金刚石中的氮-空位（NV）色心是一种极具潜力的量子传感体系，可用于高灵敏度磁场测量：

1. **激光激发** — 532nm 激光照射 NV 色心，使其进入激发态
2. **微波操控** — 施加 2.6~3.1 GHz 的共振微波（典型 2.87 GHz）
3. **荧光探测** — 采集 NV 色心的荧光信号，通过锁相放大提取调制信息
4. **磁场测量** — 通过 CW 谱或 IIR 模式反推磁场大小

### 实验设备清单

| 设备 | 用途 | 通信接口 | 驱动文件 |
|------|------|----------|----------|
| 锁相放大器（LIA） | 荧光信号解调采集 | USB / RS485 / 以太网 | `interface/Lockin/LIA_Mini_DoubleMW.py` |
| 双通道微波源 | 施加共振微波 | 受控于 LIA | - |
| 激光器 | NV 色心激发 | 电源控制 | - |
| 可编程电源 | 激光器电流控制 | USB / RS232 | `interface/UDP3305S.py` |
| Rigol DP832电源 | 三通道可编程电源 | USB / RS232 | `interface/DP832.py` |
| 超声电机 | 样品旋转 | 串口 | `interface/usm20.py` |
| 4通道温度计 | 温度监控 | USB | `interface/Thermometer_4ch.py` |
| 磁通门磁力计 | 磁场参考测量 | 串口 | `interface/1ksps_fluxgate_magnetometer.py` |

### 依赖库

```
numpy>=1.21.0
PySide6>=6.8.0
pyqtgraph>=0.13.0
psutil>=5.9.0
configparser>=5.3.0
pyserial>=3.5
pyinstaller>=6.0.0
pillow>=10.0.0
matplotlib>=3.7.0
```

**平台特定依赖**:
- Windows: `ctypes`（内置）
- Linux: `libusb1>=2.0.0`

---

## 功能特性

### 核心功能模块

| 功能面板 | 功能描述 | 实现文件 |
|----------|----------|----------|
| **设备管理** | USB设备连接、配置下发、状态监控 | `Exp_UI.py` |
| **示波器模式-AC** | 交流信号实时采集与显示 | `daq_panel.py` |
| **示波器模式-DC** | 直流信号实时采集与显示 | `dc_panel.py` |
| **锁相放大器模式-IIR** | IIR滤波后数据采集 | `iir_panel.py` |
| **锁相放大器模式-IIR+DC** | IIR+DC混合模式数据采集 | `iir_dc_panel.py` |
| **CW谱数据采集** | 连续波谱扫描与记录 | `cw_panel.py` |
| **直流CW谱数据采集** | 直流模式 CW 谱采集 | `dc_cw_panel.py` |
| **全光谱数据采集** | 完整光谱扫描采集 | `ultra_cw_panel.py` |
| **PID控制模式** | 闭环 PID 控制 | `pid_panel.py` |
| **激光解调相消相位优化** | 解调相位自动优化 | `laser_phase_optimization_panel.py` |
| **自定义实验-节点工作流** | 可视化工作流编排 | `workflow_extension/workflow_tab.py` |

### 工作流系统特性

- 🎨 **可视化拖拽编排** — 类似 ComfyUI 的图形化编程
- 🔄 **DAG 拓扑执行** — 自动依赖解析、拓扑排序
- 📊 **实时数据可视化** — pyqtgraph 流式绘图
- 💾 **工程管理** — 保存/加载/导出 JSON
- 🧩 **可扩展节点** — 注册制节点系统
- ⏪ **撤销/重做** — 完整的编辑历史管理
- 📑 **多工作流页签** — 支持同时管理多个独立工作流
- 🔢 **高精度数值输入** — 避免浮点精度丢失
- 🎯 **参数联动** — 设备参数自动更新
- 📁 **智能路径处理** — 自动识别相对/绝对路径

### 数据采集模式

| 模式 | 采样率 | 数据格式 | 适用场景 |
|------|--------|----------|----------|
| **CW谱** | 可配置（1-1000点） | X/Y双通道 | 磁场谱扫描 |
| **IIR** | 1-100kHz | 时间序列 | 高速实时监测 |
| **DAQ** | 1-100kHz | 时间序列 | 示波器模式 |
| **DC** | 1-100kHz | 时间序列 | 直流信号监测 |
| **全光谱** | 可配置 | 多通道数据 | 完整光谱分析 |

---

## 项目架构

### 目录结构

```
NVMagUI_v20260507/
├── Exp_UI.py              # 主程序入口（默认设备）
├── Exp_UI_dev1.py         # 样机1启动入口
├── Exp_UI_dev2.py         # 样机2启动入口
├── Exp_UI_dev3.py         # 样机3启动入口
├── Exp_UI_dev4.py         # 样机4启动入口
├── Exp_UI_dev6.py         # 样机6启动入口
├── General.py             # 通用工具与虚拟设备
├── manager.py             # 状态机管理器
├── requirements.txt       # Python 依赖
├── build_exe.py           # PyInstaller 打包脚本
│
├── workflow_extension/    # ⭐ 自定义工作流扩展模块
│   ├── models.py          # 数据模型（Node/Edge/Graph）
│   ├── node_registry.py   # 节点注册系统
│   ├── builtins.py        # 内置节点注册
│   ├── engine.py          # 工作流执行引擎
│   ├── serializer.py      # 序列化（JSON）
│   ├── undo_system.py     # 撤销/重做系统
│   ├── workflow_tab.py    # 工作流Tab页面
│   ├── canvas/            # 画布系统（模块化重构）
│   │   ├── scene.py       # 场景管理
│   │   ├── view.py        # 视图交互
│   │   ├── items/         # 画布元素
│   │   │   ├── edge_item.py    # 连接线项
│   │   │   └── node_item.py    # 节点项
│   │   └── widgets/       # 自定义控件
│   │       ├── high_precision_spinbox.py  # 高精度数值输入
│   │       ├── title_edit_filter.py        # 标题编辑过滤器
│   │       └── wheel_combo_box.py          # 滚轮下拉框
│   └── node/              # 节点实现
│       ├── device_select_nodes.py   # 设备选择节点
│       ├── device_init_node.py      # 设备初始化节点
│       ├── cw_nodes.py             # CW谱采集节点
│       ├── iir_nodes.py            # IIR谱采集节点
│       ├── all_optical_nodes.py    # 全光谱采集节点
│       ├── ultramotor_nodes.py     # 超声电机节点
│       └── data_visualization_nodes.py  # 数据可视化节点
│
├── interface/             # 硬件设备接口层
│   ├── Lockin/            # 锁相放大器接口
│   │   ├── LIA_Mini_DoubleMW.py              # USB版本
│   │   ├── LIA_Mini_DoubleMW_RS485.py       # RS485版本
│   │   ├── LIA_Mini_DoubleMW_Ethernet_20250717.py  # 以太网版本
│   │   ├── LIA_Mini_DoubleMW_RS485_IIR_optimized_20250629.py  # RS485优化版
│   │   ├── LIA_Tensor_5CH.py                # 5通道版本
│   │   └── usblib/           # USB驱动库
│   ├── UDP3305S.py        # UDP3305S可编程电源
│   ├── UDP3305S_RS232.py  # UDP3305S RS232版本
│   ├── DP832.py           # Rigol DP832 电源
│   ├── DP832_RS232.py     # Rigol DP832 RS232版本
│   ├── Thermometer_4ch.py # 4通道温度计
│   ├── usm20.py           # 超声电机USM20
│   ├── Ultramotor_USM20.py # 超声电机备用接口
│   ├── 1ksps_fluxgate_magnetometer.py  # 磁通门磁力计
│   └── ds1307_rtc_clk.py  # RTC时钟
│
├── config/                # 配置文件
│   ├── exp_config.ini     # 实验参数配置（默认）
│   ├── system_config.ini  # 系统连接配置（默认）
│   ├── power_config.ini   # 电源配置
│   ├── sync_config.ini    # 同步配置
│   ├── exp_config_dev1.ini # 样机1实验配置
│   ├── exp_config_dev2.ini # 样机2实验配置
│   ├── exp_config_dev3.ini # 样机3实验配置
│   ├── exp_config_dev4.ini # 样机4实验配置
│   ├── exp_config_dev6.ini # 样机6实验配置
│   ├── system_config_dev1.ini # 样机1系统配置
│   ├── system_config_dev2.ini # 样机2系统配置
│   ├── system_config_dev3.ini # 样机3系统配置
│   ├── system_config_dev4.ini # 样机4系统配置
│   ├── system_config_dev6.ini # 样机6系统配置
│   └── rpi_rsa*           # SSH密钥
│
├── 功能面板模块/
│   ├── cw_panel.py        # CW谱数据采集面板
│   ├── iir_panel.py       # IIR模式面板
│   ├── iir_dc_panel.py    # IIR+DC混合模式面板
│   ├── daq_panel.py       # DAQ示波器面板
│   ├── dc_panel.py        # DC示波器面板
│   ├── dc_cw_panel.py     # 直流CW谱面板
│   ├── ultra_cw_panel.py  # 全光谱采集面板
│   ├── pid_panel.py       # PID控制面板
│   ├── laser_phase_optimization_panel.py  # 相位优化面板
│   └── power_panel.py     # 电源控制面板
│
├── 工具模块/
│   ├── data_process_tools.py  # 数据处理工具
│   ├── realtime_display_tool.py  # 实时显示工具
│   └── utils/             # 工具函数
│       └── signal_process.py  # 信号处理
│
├── tests/                 # 测试套件
│   ├── unit/              # 单元测试
│   ├── integration/       # 集成测试
│   └── legacy/            # 遗留测试
│
├── docs/                  # 项目文档
│   ├── custom_workflow_module/  # 工作流模块文档
│   │   ├── README.md
│   │   ├── 开发设计文档_自定义实验节点工作流扩展模块.md
│   │   └── 接口文档.md
│   └── original_document/       # 原始文档
│       ├── 重构完成报告.md
│       └── 打包说明.md
│
├── log/                   # 运行日志目录
├── examples/              # 示例文件
├── .gitignore             # Git忽略配置
└── README.md              # 本文档
```

### 核心模块说明

#### 1. 主界面 (Exp_UI.py)

`ExperimentApp` 类是程序主窗口，主要职责：
- 初始化设备连接（温度计、超声电机、锁相放大器）
- 创建各功能面板并加入标签页
- 配置日志系统（文件 + UI 双输出）
- 加载实验配置与系统配置
- 管理设备状态机
- 处理设备状态变更信号

**关键参数**:
- `device_name`: 设备名称（如"样机1"）
- `exp_config_path`: 实验配置文件路径
- `sys_config_path`: 系统配置文件路径
- `lockin_port`: 锁相放大器端口（IP:端口或COM口）
- `ultramotor_port`: 超声电机串口
- `log_path`: 日志文件路径

#### 2. 状态机 (manager.py)

设备状态枚举：
```python
INIT → OFFLINE → IDLE ⇄ CONFIGURING
                  ↓
    EXP_RUNNING / DAQ_RUNNING / IIR_RUNNING / DC_RUNNING / PID_RUNNING
                  ↓
              STOPPING → IDLE
              ERROR → IDLE
```

**状态说明**:
- `INIT`: 程序初次启动
- `OFFLINE`: USB设备未连接
- `IDLE`: 设备已连接，处于空闲状态
- `MONITOR`: 监视模式（低优先级）
- `EXP_RUNNING`: 正在执行封装好的实验
- `DAQ_RUNNING`: 正在进行DAQ模式采集
- `IIR_RUNNING`: 正在进行IIR模式采集
- `PID_RUNNING`: 正在进行PID模式采集
- `DC_RUNNING`: 正在进行DC模式采集
- `CONFIGURING`: 正在下发设备配置
- `ERROR`: 实验出现故障
- `STOPPING`: 正在终止所有实验

#### 3. 工作流执行引擎 (workflow_extension/engine.py)

执行流程：
1. 构建有向无环图（DAG）
2. 拓扑排序确定执行顺序
3. 按序调用各节点的 `executor` 函数
4. 通过端口传递数据
5. 提供节点状态信号反馈

**信号机制**:
- `node_started(str)`: 节点开始执行
- `node_finished(str, object)`: 节点执行完成
- `node_failed(str, str)`: 节点执行失败
- `run_finished`: 工作流执行完成

#### 4. 数据传输层次结构

```
┌─────────────────────────────────────────────────────────────┐
│  1. UI显示层 (workflow_tab.py + pyqtgraph)                   │
│     - 负责数据可视化渲染                                      │
│     - 提供用户交互界面                                        │
│     - 接收工作流执行结果并显示                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 工作流层 (workflow_extension)                            │
│     - WorkflowExecutor: 节点执行引擎，拓扑排序                │
│     - 节点执行器: 调用设备接口获取数据                        │
│     - 端口连接: 节点间数据传递                                │
│     - 数据模型: WorkflowNodeModel, WorkflowEdgeModel          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  3. Python封装层 (manager.py + interface/)                   │
│     - manager.py: 设备管理器，统一设备接口                    │
│     - interface/: 各种设备的Python驱动封装                    │
│     - ctypes/FFI: Python与C库互操作                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  4. C/C++驱动层 (DLL/SO动态链接库)                            │
│     - USBAPI_x64.dll: USB通信驱动                            │
│     - libusb-1.0.dll: USB协议栈                              │
│     - 厂商SDK: 硬件厂商提供的C/C++开发包                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  5. 硬件设备层                                                │
│     - 锁相放大器 (LIA_Mini_DoubleMW)                          │
│     - 微波源                                                 │
│     - 超声电机 (USM20)                                       │
│     - 激光器                                                 │
└─────────────────────────────────────────────────────────────┘
```

#### 5. 工作流画布系统 (workflow_extension/canvas/)

画布系统已从单一文件重构为模块化目录结构：

**模块职责**:
- `scene.py`: 管理工作流场景中的所有节点和连接
- `view.py`: 提供画布视图的缩放和平移功能
- `items/node_item.py`: 节点的可视化表示和交互
- `items/edge_item.py`: 连接线的可视化表示
- `widgets/high_precision_spinbox.py`: 高精度数值输入控件
- `widgets/title_edit_filter.py`: 标题编辑事件过滤器
- `widgets/wheel_combo_box.py`: 滚轮优化的下拉框

**重构优势**:
1. 模块化：职责清晰，便于维护
2. 可扩展性：新增功能只需添加对应文件
3. 代码复用：自定义控件可在其他地方复用
4. 可读性：每个文件专注于特定功能
5. 测试友好：模块化设计便于单元测试

---

## 快速开始

### 环境要求

- Python 3.8+
- Windows / Linux
- USB 驱动支持

### 安装步骤

#### 1. 克隆或下载项目

```bash
# 如果使用Git
git clone <repository-url>
cd NVMagUI_v20260507
```

#### 2. 创建虚拟环境（推荐）

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

**注意事项**:
- Windows用户：ctypes为内置库，无需额外安装
- Linux用户：需要安装libusb-1.0系统库
  ```bash
  sudo apt-get install libusb-1.0-0-dev
  ```

#### 4. 配置设备

编辑 `config/exp_config.ini` 和 `config/system_config.ini` 文件，设置设备参数和连接信息。

### 启动程序

根据您的设备样机编号，选择对应的启动入口：

```bash
# 样机 1
python Exp_UI_dev1.py

# 样机 2
python Exp_UI_dev2.py

# 样机 3
python Exp_UI_dev3.py

# 样机 4
python Exp_UI_dev4.py

# 样机 6
python Exp_UI_dev6.py
```

或者直接运行默认版本：

```bash
python Exp_UI.py
```

### 首次使用

1. **连接设备** — 确保 USB 设备已连接
2. **检查配置** — 确认配置文件中的设备参数正确
3. **启动程序** — 运行对应的启动脚本
4. **下发配置** — 点击"下发所有配置"按钮初始化设备
5. **选择模式** — 切换到对应标签页开始实验
6. **数据保存** — 数据会自动保存到配置的本地数据目录

### 验证安装

运行以下命令验证依赖是否正确安装：

```bash
python -c "import PySide6; import pyqtgraph; import numpy; print('依赖安装成功')"
```

---

## 设备接口

### 锁相放大器 (LIA)

支持多种连接方式：

| 连接方式 | 驱动文件 | 特点 |
|----------|----------|------|
| **USB** | `interface/Lockin/LIA_Mini_DoubleMW.py` | 基于libusb，直接USB连接 |
| **RS485** | `interface/Lockin/LIA_Mini_DoubleMW_RS485.py` | 串口通信，支持长距离 |
| **RS485优化版** | `interface/Lockin/LIA_Mini_DoubleMW_RS485_IIR_optimized_20250629.py` | IIR模式性能优化 |
| **以太网** | `interface/Lockin/LIA_Mini_DoubleMW_Ethernet_20250717.py` | 网络连接，支持远程控制 |
| **5通道版本** | `interface/Lockin/LIA_Tensor_5CH.py` | 支持5通道输入 |

**配置示例** (system_config.ini):
```ini
# USB版本
lockin_port = USB

# RS485版本
lockin_port = COM3

# 以太网版本
lockin_port = 192.168.3.100:5005
```

### 电源设备

#### UDP3305S 可编程电源

- **驱动文件**: `interface/UDP3305S.py` (USB) / `interface/UDP3305S_RS232.py` (RS232)
- **功能**: 激光器电流控制
- **配置**: `config/power_config.ini`

#### Rigol DP832 电源

- **驱动文件**: `interface/DP832.py` (USB) / `interface/DP832_RS232.py` (RS232)
- **功能**: 三通道可编程电源，可用于多种设备供电

### 辅助设备

#### 4通道温度计

- **驱动文件**: `interface/Thermometer_4ch.py`
- **功能**: 实时温度监控，支持4通道同时测量
- **接口**: USB

#### 超声电机 USM20

- **驱动文件**: `interface/usm20.py` / `interface/Ultramotor_USM20.py`
- **功能**: 样品旋转控制，支持精确角度控制
- **接口**: 串口 (COM)
- **配置参数**:
  - `target_angle`: 目标角度
  - `motor_direction`: 转动方向（正转/反转/自动）

#### 磁通门磁力计

- **驱动文件**: `interface/1ksps_fluxgate_magnetometer.py`
- **功能**: 磁场参考测量
- **采样率**: 1ksps
- **接口**: 串口

#### RTC时钟

- **驱动文件**: `interface/ds1307_rtc_clk.py`
- **功能**: 实时时钟，用于时间戳记录
- **接口**: I2C

---

## 工作流系统

### 快速上手

1. **进入工作流页面** — 点击"自定义实验-节点工作流"标签页
2. **添加节点** — 从左侧节点库双击或拖拽节点到画布
3. **连接节点** — 拖拽节点的输出端口到另一个节点的输入端口
4. **配置参数** — 选中节点，在参数面板中配置参数
5. **运行工作流** — 点击"运行"按钮执行工作流
6. **停止工作流** — 点击"停止"按钮中断执行
7. **保存工作流** — 点击"保存"按钮将工作流保存为JSON文件
8. **加载工作流** — 点击"加载"按钮加载已保存的工作流

### 内置节点类型

| 分类 | 节点类型 | 功能描述 | 实现文件 |
|------|----------|----------|----------|
| **设备控制** | `device.select` | 选择设备配置并自动更新相关参数 | `device_select_nodes.py` |
| | `device.connect` | 初始化设备参数并下发所有配置 | `device_init_node.py` |
| **CW谱采集** | `cw.spectrum_acquire` | CW谱数据采集 | `cw_nodes.py` |
| **IIR谱采集** | `iir.acquire` | IIR模式数据采集 | `iir_nodes.py` |
| **全光谱采集** | `all_optical.acquire` | 全光谱数据采集 | `all_optical_nodes.py` |
| **超声电机** | `ultramotor.status` | 控制超声电机并读取状态 | `ultramotor_nodes.py` |
| **数据可视化** | `data.display` | 将采集数据显示在双图显示面板 | `data_visualization_nodes.py` |

### 节点详细说明

#### 设备选择节点 (`device.select`)

**功能**: 选择设备配置并自动更新相关参数

**输入端口**: 无

**输出端口**: `device_config` (dict) - 设备配置信息

**参数**:
- `device_name`: 设备名称（下拉选择）
- `exp_config_path`: 实验配置文件路径（支持文件选择按钮）
- `sys_config_path`: 系统配置文件路径（支持文件选择按钮）
- `lockin_port`: 锁相放大器端口（支持文件选择按钮）
- `ultramotor_port`: 超声电机端口
- `log_path`: 日志文件路径（支持文件选择按钮）

**特性**:
- 设备名称改变时自动更新其他参数
- 支持相对路径和绝对路径自动判断
- 文件路径参数右侧提供文件选择图标按钮

#### 设备初始化节点 (`device.connect`)

**功能**: 初始化设备参数并下发所有配置

**输入端口**: `device_config` (dict) - 设备配置

**输出端口**: `device_out` (device) - 设备对象

**参数**: 包含锁相、激光、微波、存储等所有设备参数（支持三级分类）

**特性**:
- 自动连接设备（如果未连接）
- 下发所有设备参数配置
- 支持参数联动和实时更新

#### CW谱采集节点 (`cw.spectrum_acquire`)

**功能**: CW谱数据采集

**输入端口**: `device_in` (device) - 设备对象

**输出端口**: `data` (dict) - 采集的数据

**参数**:
- `mw_channel`: 微波通道
- `start_freq`: 起始频率
- `stop_freq`: 结束频率
- `step_freq`: 频率步进
- `single_point_count`: 单点采集数

**数据格式**:
```python
{
    "data_type": "cw",
    "mw_channel": "...",
    "mw_freq": [...],
    "ch1_x": [...],
    "ch1_y": [...],
    "ch2_x": [...],
    "ch2_y": [...],
    "point_count": ...
}
```

#### IIR谱采集节点 (`iir.acquire`)

**功能**: IIR模式数据采集

**输入端口**: `device_in` (device) - 设备对象

**输出端口**: `data` (dict) - 采集的数据

**参数**:
- `acq_mode`: 采集模式（定时长/无限）
- `acq_time`: 采集时长

**数据格式**:
```python
{
    "data_type": "iir",
    "time": [...],
    "ch1": [...],
    "ch2": [...],
    "sample_rate": ...,
    "point_count": ...
}
```

#### 全光谱采集节点 (`all_optical.acquire`)

**功能**: 全光谱数据采集

**输入端口**: `device_in` (device) - 设备对象

**输出端口**: `data` (dict) - 采集的数据

**参数**:
- `start_motor_angle`: 起始角度
- `stop_motor_angle`: 结束角度
- `step_motor_angle`: 步进角度

**数据格式**:
```python
{
    "data_type": "all_optical",
    "motor_angle": [...],
    "fluo_dc": [...],
    "laser_dc": [...],
    "point_count": ...
}
```

### 示例工作流

#### 简单的 CW 谱采集流程

```
设备选择 → 设备初始化 → CW谱采集 → 数据可视化
```

### 节点连接规则

- 端口类型必须兼容（如`device`只能连接到`device`输入）
- 一个输出端口可以连接多个输入端口
- 不能创建环路（系统会检测并阻止）
- 连接完成后可以右键点击连线删除

### 工作流文件格式

工作流文件使用纯JSON格式（.json），便于调试和与其他系统集成。

**JSON结构示例**:
```json
{
  "version": "1.0",
  "name": "CW谱采集工作流",
  "nodes": [
    {
      "node_id": "node_001",
      "node_type": "device.select",
      "title": "设备选择",
      "position": [100, 100],
      "params": {...}
    }
  ],
  "edges": [
    {
      "from_node": "node_001",
      "to_node": "node_002",
      "from_port": "device_config",
      "to_port": "device_in"
    }
  ]
}
```

### 节点开发

创建自定义节点需在 `workflow_extension/node/` 目录下实现并注册。

**开发步骤**:
1. 在 `workflow_extension/node/` 目录下创建新的节点文件
2. 实现节点的 `executor` 函数
3. 在 `workflow_extension/builtins.py` 中注册节点
4. 定义节点的输入输出端口和参数

详细文档见 [工作流模块开发文档](docs/custom_workflow_module/开发设计文档_自定义实验节点工作流扩展模块.md)。

---

## 配置说明

### 配置文件结构

项目使用 INI 格式的配置文件，分为实验配置和系统配置两类。

### 实验参数配置 (config/exp_config.ini)

实验配置文件包含所有实验相关的参数设置，每个参数支持以下字段：

```ini
[parameter_name]
label = 参数显示标签
type = 参数类型 (float/int/bool/string)
desc = 参数描述
value = 默认值
min = 最小值
max = 最大值
unit = 单位
category = 一级分类
subcategory = 二级分类
editable = 是否可编辑 (True/False)
```

**主要配置分类**:

| 分类 | 参数示例 | 说明 |
|------|----------|------|
| **Laser** | laser_power | 激光器电流 (0-2A) |
| **LIA** | lockin_tc, lockin_sample_rate | 锁相放大器时间常数、采样率 |
| **Microwave** | mw_ch1_freq, mw_ch2_freq | 微波频率 (2.6-3.1 GHz) |
| **Virtual** | lockin_iir_gain, lockin_daq_gain | IIR/DAQ转换系数 |
| **Storage** | save_path, file_prefix | 数据保存路径和文件前缀 |

**配置示例**:
```ini
[laser_power]
label = 激光器电流
type = float
desc = 电流源向激光器供电的电流，单位为A。
min = 0.0
max = 2.0
value = 0.8
unit = A
category = Laser
editable = True

[lockin_tc]
label = LIA时间常数
type = float
desc = 锁相放大器滤波时间常数，单位为s。
min = 0.0
max = 10.0
value = 0.1
unit = s
category = LIA
editable = True

[mw_ch1_freq]
label = CH1微波频率
type = int
desc = 微波源通道1的输出频率。
min = 2600000000
max = 3100000000
value = 2895500000
unit = Hz
category = Microwave
editable = True
```

### 系统配置 (config/system_config.ini)

系统配置文件包含连接信息、路径配置等系统级设置。

**配置示例**:
```ini
[Connection]
localname = 169.254.51.231
hostname = 169.254.51.251
username = pi
password = esr

[Path]
local_code_path = D:/Software Learning/NVMagUI
remote_code_path = /home/pi/Program/NVMagUI
local_data_path = D:/Software Learning/NVMagUI_Data
remote_data_path = /home/pi/Program/NVMagUI_Data
libusb_path = interface/Lockin/usblib/module_64/libusb-1.0.so

[Sync]
direction = up

[Exemptions]
exempt1 = NVMagUI_py311env
exempt2 = .idea
exempt3 = config/sync_config.ini
exempt4 = pc_connection_log.txt
exempt5 = deprecated
exempt6 = experiment_log.txt
exempt7 = interface/Lockin/usblib
exempt8 = config/system_config.ini
exempt9 = log
```

**配置说明**:
- `[Connection]`: 远程连接配置（用于代码同步）
- `[Path]`: 本地和远程路径配置
- `[Sync]`: 同步方向配置
- `[Exemptions]`: 同步时排除的文件/目录

### 多设备配置

项目支持多台设备样机独立配置，每台设备有独立的配置文件：

| 设备 | 实验配置 | 系统配置 |
|------|----------|----------|
| 样机1 | `config/exp_config_dev1.ini` | `config/system_config_dev1.ini` |
| 样机2 | `config/exp_config_dev2.ini` | `config/system_config_dev2.ini` |
| 样机3 | `config/exp_config_dev3.ini` | `config/system_config_dev3.ini` |
| 样机4 | `config/exp_config_dev4.ini` | `config/system_config_dev4.ini` |
| 样机6 | `config/exp_config_dev6.ini` | `config/system_config_dev6.ini` |

**添加新设备配置**:
1. 复制现有配置文件（如 `exp_config_dev1.ini`）
2. 重命名为 `exp_config_devX.ini`（X为新设备编号）
3. 修改配置文件中的参数
4. 创建对应的 `Exp_UI_devX.py` 启动脚本
5. 在启动脚本中指定新的配置文件路径

---

## 开发指南

### 项目依赖

主要 Python 库：

| 库 | 版本要求 | 用途 |
|----|----------|------|
| PySide6 | >=6.8.0 | GUI 框架 |
| pyqtgraph | >=0.13.0 | 实时数据可视化 |
| numpy | >=1.21.0 | 数值计算 |
| pyserial | >=3.5 | 串口通信 |
| configparser | >=5.3.0 | INI 配置解析 |
| psutil | >=5.9.0 | 系统资源监控 |
| Pillow | >=10.0.0 | 图像处理 |
| matplotlib | >=3.7.0 | 静态绘图 |
| pyinstaller | >=6.0.0 | 打包工具 |

### 代码规范

- 遵循 PEP 8 代码风格
- 使用类型提示（Type Hints）
- 模块文档字符串使用 Google 风格
- 函数和类添加详细的文档字符串
- 提交前运行测试

**代码风格示例**:
```python
def calculate_cw_spectrum(device: Virtual_Device, start_freq: int, 
                          stop_freq: int, step_freq: int) -> dict:
    """
    计算CW谱数据
    
    Args:
        device: 虚拟设备对象
        start_freq: 起始频率 (Hz)
        stop_freq: 结束频率 (Hz)
        step_freq: 频率步进 (Hz)
    
    Returns:
        dict: 包含频率和振幅数据的字典
        
    Raises:
        ValueError: 当频率参数无效时
    """
    # 实现代码
    pass
```

### 项目结构说明

```
NVMagUI_v20260507/
├── Exp_UI.py              # 主程序入口
├── General.py             # 通用工具函数
├── manager.py             # 状态机管理
├── workflow_extension/    # 工作流扩展模块
├── interface/             # 硬件设备接口
├── config/                # 配置文件
├── tests/                 # 测试文件
└── docs/                  # 文档
```

### 添加新功能

#### 添加新的数据采集面板

1. 在项目根目录创建新的面板文件（如 `new_panel.py`）
2. 继承基础面板类或实现面板接口
3. 在 `Exp_UI.py` 中导入并添加到标签页
4. 在配置文件中添加相关参数

#### 添加新的设备接口

1. 在 `interface/` 目录下创建新的设备驱动文件
2. 实现设备连接、配置、数据采集等功能
3. 在 `General.py` 中注册设备类
4. 在配置文件中添加设备参数

#### 添加新的工作流节点

1. 在 `workflow_extension/node/` 目录下创建节点文件
2. 实现节点的 `executor` 函数
3. 在 `workflow_extension/builtins.py` 中注册节点
4. 定义节点的输入输出端口和参数规范

### 调试技巧

#### 1. 启用调试日志

在代码中添加调试日志：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug("调试信息")
```

#### 2. 使用虚拟设备

在没有实际硬件时，可以使用 `General.py` 中的 `Virtual_Device` 类进行测试。

#### 3. 查看日志

运行日志保存在 `log/` 目录下，可以查看详细的运行信息。

### 打包可执行文件

使用 PyInstaller 打包：

```bash
python build_exe.py
```

**打包说明**:
- 打包脚本位于 `build_exe.py`
- 生成的可执行文件位于 `dist/` 目录
- 详细说明见 [打包说明文档](docs/original_document/打包说明.md)

**打包注意事项**:
- 确保所有依赖都已正确安装
- Windows下需要包含USB驱动DLL
- Linux下需要确保libusb-1.0可用
- 测试打包后的可执行文件

---

## 测试

### 运行测试

```bash
# 运行所有测试
cd tests
python run_tests.py

# 或使用 pytest
pytest -v

# 运行特定测试文件
pytest tests/unit/test_node_registry.py -v

# 运行特定测试类
pytest tests/unit/test_node_registry.py::TestNodeRegistry -v

# 运行特定测试方法
pytest tests/unit/test_node_registry.py::TestNodeRegistry::test_register -v

# 查看测试覆盖率
pytest --cov=workflow_extension --cov-report=html
```

### 测试分类

- **单元测试** (`tests/unit/`) — 节点注册、序列化、执行器
- **集成测试** (`tests/integration/`) — UI 交互、工作流集成、性能
- **遗留测试** (`tests/legacy/`) — 历史测试用例

### 测试结构

```
tests/
├── unit/              # 单元测试
│   ├── test_node_registry.py
│   ├── test_serializer.py
│   └── test_engine.py
├── integration/       # 集成测试
│   ├── test_workflow_integration.py
│   ├── test_ui_integration.py
│   └── test_performance.py
└── legacy/            # 遗留测试
    └── test_legacy.py
```

### 编写测试

#### 单元测试示例

```python
import unittest
from workflow_extension.node_registry import NodeRegistry

class TestNodeRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = NodeRegistry()
    
    def test_register_node(self):
        """测试节点注册功能"""
        # 测试代码
        pass
    
    def test_get_node(self):
        """测试节点获取功能"""
        # 测试代码
        pass

if __name__ == '__main__':
    unittest.main()
```

### 测试最佳实践

1. **隔离性**: 每个测试应该独立运行，不依赖其他测试
2. **可读性**: 测试名称应该清晰描述测试内容
3. **完整性**: 测试应该覆盖正常情况和异常情况
4. **速度**: 单元测试应该快速执行
5. **维护性**: 测试代码应该易于理解和维护

### 日志分析

#### 查看运行日志

日志文件位置：`log/experiment_log.txt`

**关键日志信息**:
- 设备连接状态
- 配置下发结果
- 数据采集状态
- 错误信息和堆栈跟踪

#### 启用调试日志

在代码中设置日志级别：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 附录

### 术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| NV色心 | NV Center | 金刚石中的氮-空位缺陷中心 |
| LIA | Lock-in Amplifier | 锁相放大器 |
| CW | Continuous Wave | 连续波 |
| IIR | Infinite Impulse Response | 无限脉冲响应滤波器 |
| DAQ | Data Acquisition | 数据采集 |
| PID | Proportional-Integral-Derivative | 比例-积分-微分控制 |
| USM | Ultrasonic Motor | 超声电机 |

### 参考资料

1. NV色心磁探测原理相关论文
2. 设备厂商提供的技术手册
3. Python官方文档
4. PySide6官方文档
5. pyqtgraph官方文档

### 快捷键

在工作流编辑器中可用的快捷键：

| 快捷键 | 功能 |
|--------|------|
| Ctrl+Z | 撤销 |
| Ctrl+Y | 重做 |
| Delete | 删除选中节点/连线 |
| Ctrl+S | 保存工作流 |
| 鼠标滚轮 | 缩放画布 |
| 鼠标左键拖拽 | 平移画布 |
