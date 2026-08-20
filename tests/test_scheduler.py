"""
@description 调度器测试：任务时区固定为 Asia/Shanghai，不受系统时区影响。
"""

from scx_stock.scheduler.runner import SchedulerRunner


class TestSchedulerTimezone:
    """所有 cron 任务的 trigger 必须显式使用 Asia/Shanghai。

    CronTrigger.from_crontab 不传 timezone 时回退系统本地时区，
    生产容器为 UTC，曾导致 21:00（CST）的分析任务实际在次日 05:00 触发。
    """

    def test_all_jobs_use_shanghai_timezone(self):
        """注册的所有任务 trigger 时区应为 Asia/Shanghai，而非系统本地时区。"""
        runner = SchedulerRunner()
        runner.setup()

        jobs = runner._scheduler.get_jobs()
        assert jobs, "应注册至少一个定时任务"
        for job in jobs:
            assert str(job.trigger.timezone) == "Asia/Shanghai", job.id
