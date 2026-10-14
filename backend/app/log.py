"""统一日志配置：控制台 + 滚动文件，结构化（时间/级别/模块/消息）。

生产建议把 stdout 交给容器日志系统收集；文件日志兜底本地排查。
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import BASE_DIR

LOG_DIR = BASE_DIR / "logs"
_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """幂等：只在首次调用时装配 handler。"""
    root = logging.getLogger()
    if getattr(root, "_surrealkb_ready", False):
        return

    root.setLevel(level.upper())
    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # 文件（10MB × 5，轮转）
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except Exception:  # noqa: BLE001 — 日志落盘失败不应阻断服务
        pass

    # 降低第三方噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    root._surrealkb_ready = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
