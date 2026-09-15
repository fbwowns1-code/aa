"""
logs/automation_YYYYMMDD.log에 실행 로그를 남기는 공용 모듈.

DB의 errors 테이블(core/database.py::log_error)이 "조회용" 기록이라면,
이 모듈은 사람이 tail -f로 실시간으로 볼 수 있는 평문 로그다.
형식: 시각 \t 계정 \t post_id \t 단계 \t 레벨 \t 메시지
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

LOG_DIR = Path("logs")

_loggers = {}


def _get_logger():
    today = datetime.now().strftime("%Y%m%d")
    logger = _loggers.get(today)
    if logger:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"automation.{today}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.FileHandler(LOG_DIR / f"automation_{today}.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    _loggers[today] = logger
    return logger


def log_event(
    account_id: Optional[str],
    post_id: Optional[str],
    step: Optional[str],
    level: str,
    message: str,
) -> None:
    """level: INFO / WARNING / ERROR 등 logging 모듈 레벨명."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts}\t{account_id or '-'}\t{post_id or '-'}\t{step or '-'}\t{level.upper()}\t{message}"
    logger = _get_logger()
    logger.log(getattr(logging, level.upper(), logging.INFO), line)
