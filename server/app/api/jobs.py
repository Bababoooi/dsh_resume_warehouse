"""后台任务查询（>2s 的操作统一返回 202 + job_id）。

本进程是单进程 threaded 模式，任务由各业务模块在线程里跑并写 job 表；
进程重启时残留任务由启动钩子标为 interrupted。
"""

from __future__ import annotations

from flask import Blueprint, request

from ..repos import JobRepo
from . import common

bp = Blueprint("jobs", __name__)


def _view(job: dict) -> dict:
    return {
        "id": job["id"],
        "kind": job["kind"],
        "status": job["status"],
        "progress": job.get("progress") or 0,
        "message": job.get("message"),
        "result_json": job.get("result_json"),
        "error_json": job.get("error_json"),
        "created_at": job.get("created_at"),
        "finished_at": job.get("finished_at"),
    }


@bp.get("/jobs")
def list_jobs():
    repo = JobRepo()
    items = repo.list(status=request.args.get("status") or None, limit=common.limit(default=20, maximum=100))
    for item in items:
        item["result_json"] = item.get("result_json")
        item["error_json"] = item.get("error_json")
    payload = common.list_envelope(items, len(items), limit_value=len(items) or 1, offset_value=0)
    return common.ok(payload)


@bp.get("/jobs/<job_id>")
def get_job(job_id: str):
    return common.ok(_view(JobRepo().get(job_id)))
