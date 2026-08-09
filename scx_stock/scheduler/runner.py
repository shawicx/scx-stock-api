"""
@description APScheduler 调度器：注册每日同步任务，随应用生命周期启停。
"""

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scx_stock.config.settings import get_settings
from scx_stock.scheduler.sync_jobs import (
    rebuild_search_index,
    sync_all,
    sync_etf_list,
    sync_stock_industries,
)
from scx_stock.scheduler.analysis_job import daily_analysis_job

logger = logging.getLogger(__name__)

# 默认调度计划（可被 Settings 覆盖）：
#   - 每日 09:00 同步股票列表（sync_all 内部串行：股票+ETF+行业+索引）
#   - 每日 09:10 同步 ETF 列表
#   - 每日 09:15 同步行业映射
#   - 每日 09:20 重建搜索索引
#   - 每日 21:00 执行支撑位分析并发邮件（cron 来自 SCX_ANALYSIS_CRON）
DEFAULT_SCHEDULE = {
    "sync_stock_list": {"cron": "0 9 * * 1-5", "func_name": "sync_stock_list"},
    "sync_etf_list": {"cron": "10 9 * * 1-5", "func_name": "sync_etf_list"},
    "sync_stock_industries": {"cron": "15 9 * * 1-5", "func_name": "sync_stock_industries"},
    "rebuild_search_index": {
        "cron": "20 9 * * 1-5",
        "func_name": "rebuild_search_index",
    },
    "daily_analysis": {"cron": None, "func_name": "daily_analysis"},  # cron 动态取自 Settings
}

# 任务名 → 异步函数
_JOB_REGISTRY: dict[str, Any] = {
    "sync_stock_list": sync_all,  # sync_all 内部串行：股票+ETF+行业+索引
    "sync_etf_list": sync_etf_list,
    "sync_stock_industries": sync_stock_industries,
    "rebuild_search_index": rebuild_search_index,
    "daily_analysis": daily_analysis_job,
}


class SchedulerRunner:
    """APScheduler 封装，负责注册与启停。

    使用 AsyncIOScheduler 在 FastAPI 同一事件循环中运行。
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    def setup(self) -> None:
        """注册默认任务（不立即启动）。"""
        s = get_settings()
        for job_id, cfg in DEFAULT_SCHEDULE.items():
            func = _JOB_REGISTRY.get(cfg["func_name"])
            if func is None:
                logger.warning("unknown job func: %s, skip", cfg["func_name"])
                continue
            # daily_analysis 的 cron 动态取自 SCX_ANALYSIS_CRON
            cron = cfg["cron"] or s.analysis_cron
            trigger = CronTrigger.from_crontab(cron)
            self._scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                name=job_id,
                replace_existing=True,
                misfire_grace_time=600,
            )
            logger.info("registered job %s (%s)", job_id, cron)

    def start(self) -> None:
        """启动调度器。"""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("scheduler started")

    def shutdown(self) -> None:
        """停止调度器。"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler stopped")


_runner: SchedulerRunner | None = None


def get_scheduler() -> SchedulerRunner:
    """获取全局调度器单例。

    :returns: SchedulerRunner 实例。
    """
    global _runner
    if _runner is None:
        _runner = SchedulerRunner()
        _runner.setup()
    return _runner
