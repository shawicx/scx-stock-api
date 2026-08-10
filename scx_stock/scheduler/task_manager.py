"""
@description 后台任务管理器：管理长耗时运维任务（如全量同步）的执行状态。

任务提交后立即返回 task_id，后台异步执行，前端通过 task_id 轮询状态。
状态存在内存（单进程足够，运维任务频率低）。
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TaskInfo(BaseModel):
    """任务状态信息。

    :param task_id: 任务唯一标识。
    :param name: 任务名称。
    :param status: 当前状态。
    :param progress: 进度描述（人类可读）。
    :param result: 任务结果（status=done 时）。
    :param error: 失败原因（status=failed 时）。
    :param created_at: 创建时间戳。
    :param elapsed: 已耗时秒数。
    """

    task_id: str
    name: str
    status: TaskStatus
    progress: str = ""
    result: dict[str, Any] | None = None
    error: str = ""
    created_at: float
    elapsed: float = 0


class TaskManager:
    """后台任务管理器，管理任务的生命周期与状态查询。

    任务通过 asyncio.create_task 在后台执行，状态存内存字典。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._coros: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._counter = 0

    async def _next_id(self) -> str:
        """生成下一个任务 ID。

        :returns: 形如 task_1 的 ID。
        """
        async with self._lock:
            self._counter += 1
            return f"task_{self._counter}"

    def submit(
        self,
        name: str,
        coro_factory: Callable[["TaskHandle"], Awaitable[Any]],
    ) -> str:
        """提交后台任务，立即返回 task_id。

        :param name: 任务名称。
        :param coro_factory: 接受 TaskHandle 的工厂函数，返回待执行协程。
        :returns: task_id。
        """
        task_id = f"task_{int(time.time() * 1000)}"
        handle = TaskHandle(task_id, name, self)
        info = TaskInfo(
            task_id=task_id,
            name=name,
            status=TaskStatus.PENDING,
            created_at=time.time(),
        )
        self._tasks[task_id] = info

        async def _runner():
            self._tasks[task_id].status = TaskStatus.RUNNING
            self._tasks[task_id].progress = "任务已启动"
            try:
                result = await coro_factory(handle)
                self._tasks[task_id].result = result if isinstance(result, dict) else {"result": result}
                self._tasks[task_id].status = TaskStatus.DONE
                self._tasks[task_id].progress = "完成"
                logger.info("后台任务 %s(%s) 完成: %s", task_id, name, self._tasks[task_id].result)
            except Exception as e:  # noqa: BLE001
                self._tasks[task_id].status = TaskStatus.FAILED
                self._tasks[task_id].error = f"{type(e).__name__}: {e}"
                logger.exception("后台任务 %s(%s) 失败", task_id, name)
            finally:
                self._tasks[task_id].elapsed = round(time.time() - info.created_at, 1)

        self._coros[task_id] = asyncio.create_task(_runner())
        logger.info("提交后台任务 %s(%s)", task_id, name)
        return task_id

    def update_progress(self, task_id: str, progress: str) -> None:
        """更新任务进度描述。

        :param task_id: 任务 ID。
        :param progress: 进度文本。
        """
        if task_id in self._tasks:
            self._tasks[task_id].progress = progress

    def get(self, task_id: str) -> TaskInfo | None:
        """查询任务状态。

        :param task_id: 任务 ID。
        :returns: TaskInfo 或 None（不存在）。
        """
        info = self._tasks.get(task_id)
        if info is None:
            return None
        # 实时更新 elapsed
        if info.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
            info.elapsed = round(time.time() - info.created_at, 1)
        return info

    def list_tasks(self) -> list[TaskInfo]:
        """列出所有任务（最近的在前）。

        :returns: TaskInfo 列表。
        """
        return sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )


class TaskHandle:
    """任务句柄，供后台协程内部更新进度。

    :param task_id: 任务 ID。
    :param name: 任务名称。
    :param manager: 所属 TaskManager。
    """

    def __init__(self, task_id: str, name: str, manager: TaskManager) -> None:
        self.task_id = task_id
        self.name = name
        self._manager = manager

    def update_progress(self, progress: str) -> None:
        """更新进度描述。

        :param progress: 进度文本。
        """
        self._manager.update_progress(self.task_id, progress)


_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    """获取全局任务管理器单例。

    :returns: TaskManager 实例。
    """
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager
