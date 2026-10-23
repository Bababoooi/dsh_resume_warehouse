"""长任务执行器：把 >2s 的活丢进线程池，立即返回 ``job_id``（契约 §13）。

设计取舍：
- 单进程 Flask（threaded=8）下不引入 Celery/Redis；``ThreadPoolExecutor`` + SQLite ``job`` 表足够。
- 任务体自己拿线程局部连接（``db.get_conn()``），不跨线程复用父请求的连接。
- 进程重启时 ``server.py`` 把 ``queued/running`` 标成 ``interrupted``（JOB_INTERRUPTED 409）。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ..errors import ApiError
from ..repos import JobRepo

logger = logging.getLogger(__name__)

#: 同时跑 2 个后台任务：变体生成是等上游 LLM，占线程不占 CPU。
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rw-job")

#: 在跑/待跑的 future（测试用 ``wait_idle`` 收口，避免临时数据库被拆掉后任务还在写）
_FUTURES: set[Any] = set()

ProgressFn = Callable[..., None]


def _run(job_id: str, work: Callable[[ProgressFn], Any], message: str | None) -> None:
    jobs = JobRepo()
    try:
        jobs.update(job_id, status="running", progress=5, message=message or "执行中")

        def report(progress: int, text: str | None = None) -> None:
            jobs.update(job_id, progress=progress, message=text)

        result = work(report)
        jobs.update(job_id, status="succeeded", progress=100, result=result, message="完成")
    except ApiError as exc:
        payload = exc.to_dict().get("error", {})
        jobs.update(job_id, status="failed", progress=100, error=payload, message=str(exc.message))
    except Exception as exc:  # noqa: BLE001 - 后台线程绝不能让异常逃逸
        logger.exception("job %s crashed", job_id)
        jobs.update(
            job_id,
            status="failed",
            progress=100,
            error={"code": "INTERNAL", "message": "任务执行失败", "details": {"type": type(exc).__name__}},
            message="任务执行失败",
        )
    finally:
        # E) 后台线程结束前关掉本线程的 SQLite 连接（``db.close_conn`` 只影响当前线程）：
        # 线程池会复用线程，不关就会一直握着 WAL 读事务与文件句柄。
        db_mod.close_conn()


def submit(kind: str, work: Callable[[ProgressFn], Any], *, message: str | None = None) -> str:
    """建 job 行并异步执行；返回 ``job_id``（调用方回 202）。"""
    job_id = JobRepo().create(kind, message=message)
    future = _EXECUTOR.submit(_run, job_id, work, message)
    _FUTURES.add(future)
    future.add_done_callback(_FUTURES.discard)
    return job_id


def wait_idle(timeout: float = 10.0) -> None:
    """等当前所有后台任务收尾（测试 tearDown 与优雅退出用，不关闭线程池）。"""
    for future in list(_FUTURES):
        try:
            future.result(timeout=timeout)
        except Exception:  # noqa: BLE001 - 任务失败由 job 行记录，这里只负责等它结束
            continue


def shutdown(wait: bool = False) -> None:
    """测试与优雅退出的收口（生产进程生命周期内不需要调用）。"""
    _EXECUTOR.shutdown(wait=wait, cancel_futures=True)
