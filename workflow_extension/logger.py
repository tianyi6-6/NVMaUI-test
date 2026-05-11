"""
工作流统一日志模块

提供工作流系统的标准化日志输出，包括：
- get_logger: 获取带统一前缀的模块级 logger
- 节点执行日志快捷方法：node_start / node_finish / node_fail / node_data_pass
- 日志级别规范：
    DEBUG   — 画布交互细节（拖拽、端口命中、缩放等）
    INFO    — 用户操作反馈、节点执行状态、工作流生命周期
    WARNING — 非致命异常（上游数据无效、未知数据类型等）
    ERROR   — 节点执行失败、设备通信异常等

使用方式：
    from workflow_extension.logger import get_logger
    log = get_logger("Engine")
    log.info("工作流开始执行")
    log.node_start("CW谱采集", "cw.spectrum_acquire")
"""

import logging

_WORKFLOW_PREFIX = "Workflow"


def get_logger(module_name: str) -> logging.Logger:
    """获取工作流模块专用 logger

    返回一个名为 ``Workflow.ModuleName`` 的 logging.Logger 实例，
    便于在全局日志中按模块过滤工作流相关输出。

    Args:
        module_name: 模块简称，如 "Engine"、"Scene"、"CW"

    Returns:
        logging.Logger: 带统一命名空间的 logger 实例
    """
    return logging.getLogger(f"{_WORKFLOW_PREFIX}.{module_name}")


def _fmt_node(title: str, node_type: str) -> str:
    return f"[{title}({node_type})]"


def node_start(log: logging.Logger, title: str, node_type: str, **kwargs):
    """记录节点开始执行

    Args:
        log: logger 实例
        title: 节点标题
        node_type: 节点类型
        **kwargs: 附加信息键值对
    """
    extra = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    suffix = f", {extra}" if extra else ""
    log.info("▶ 开始执行 %s%s", _fmt_node(title, node_type), suffix)


def node_finish(log: logging.Logger, title: str, node_type: str, *, result_summary: str = "", **kwargs):
    """记录节点执行完成

    Args:
        log: logger 实例
        title: 节点标题
        node_type: 节点类型
        result_summary: 输出结果摘要（自动截断）
        **kwargs: 附加信息键值对
    """
    extra = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    parts = []
    if result_summary:
        if len(result_summary) > 80:
            result_summary = result_summary[:80] + "..."
        parts.append(f"输出={result_summary}")
    if extra:
        parts.append(extra)
    suffix = f" ({', '.join(parts)})" if parts else ""
    log.info("✔ 执行完成 %s%s", _fmt_node(title, node_type), suffix)


def node_fail(log: logging.Logger, title: str, node_type: str, error: str, **kwargs):
    """记录节点执行失败

    Args:
        log: logger 实例
        title: 节点标题
        node_type: 节点类型
        error: 错误信息
        **kwargs: 附加信息键值对
    """
    extra = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    suffix = f", {extra}" if extra else ""
    log.error("✘ 执行失败 %s: %s%s", _fmt_node(title, node_type), error, suffix)


def node_data_pass(log: logging.Logger, from_title: str, to_title: str, to_port: str, data_summary: str):
    """记录节点间数据传递

    Args:
        log: logger 实例
        from_title: 源节点标题
        to_title: 目标节点标题
        to_port: 目标端口名称
        data_summary: 数据摘要（自动截断）
    """
    if len(data_summary) > 50:
        data_summary = data_summary[:50] + "..."
    log.debug("↗ 数据传递: %s → %s.%s (数据: %s)", from_title, to_title, to_port, data_summary)
