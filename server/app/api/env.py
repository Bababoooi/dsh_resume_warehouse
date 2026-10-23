"""GET /env —— 环境自检（供设置页与 preflight 复用）。"""

from __future__ import annotations

from flask import Blueprint, current_app

from .. import config as config_mod
from ..services import envcheck
from . import common

bp = Blueprint("env", __name__)


@bp.get("/env")
def env():
    cfg: config_mod.Config = current_app.extensions.get("cfg") or config_mod.get_config()
    snapshot = envcheck.env_snapshot(cfg)
    return common.ok(snapshot)
