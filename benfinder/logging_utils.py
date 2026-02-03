"""
统一的日志工具，便于在不同模块中创建写入文件的 logger。
"""

import logging
import os
from pathlib import Path
from typing import Optional


class SourceFormatter(logging.Formatter):
    """统一补齐 source 字段，便于按来源过滤日志。"""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "source"):
            source_override = os.getenv("BENFINDER_LOG_SOURCE")
            record.source = source_override or record.filename
        return super().format(record)


def _resolve_log_path(log_path: Optional[Path]) -> Optional[Path]:
    try:
        import config as project_config

        pipeline_path = getattr(project_config, "PIPELINE_LOG_PATH", None)
        if pipeline_path:
            return Path(pipeline_path)
    except Exception:
        pass
    if log_path is None:
        return None
    return Path(log_path)


def setup_file_logger(
    name: str, log_path: Optional[Path], level: int = logging.DEBUG
) -> logging.Logger:
    """
    创建（或复用）一个写入指定文件的 logger。

    - name: logger 名称，通常对应具体任务。
    - log_path: 日志文件的完整路径。
    - level: 日志级别，默认 DEBUG。

    若同名 logger 已存在相同文件的 handler，则直接返回，避免重复添加。
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    resolved_path = _resolve_log_path(log_path)
    if resolved_path is None:
        return logger

    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    # 检查是否已经存在同一路径的 FileHandler，避免重复写入。
    target_path = str(resolved_path)
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == target_path:
            return logger

    formatter = SourceFormatter("%(asctime)s | %(levelname)s | %(source)s | %(message)s")
    fh = logging.FileHandler(target_path, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger
