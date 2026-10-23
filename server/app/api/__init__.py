"""蓝图注册入口（前缀 /api/v1，健康检查另有 /api/health 别名）。"""

from __future__ import annotations

from flask import Flask

from . import builds as builds_api
from . import companies as companies_api
from . import env as env_api
from . import files as files_api
from . import health as health_api
from . import imports as imports_api
from . import jds as jds_api
from . import jobs as jobs_api
from . import llm as llm_api
from . import naming as naming_api
from . import packages as packages_api
from . import profile as profile_api
from . import settings as settings_api
from . import templates as templates_api

API_PREFIX = "/api/v1"


def register_blueprints(app: Flask) -> None:
    for module in (
        health_api,
        env_api,
        profile_api,
        packages_api,
        files_api,
        jobs_api,
        settings_api,
        naming_api,
        llm_api,
        imports_api.imports_bp,
        imports_api.templates_bp,
        templates_api.templates_ops_bp,
        jds_api,
        companies_api,
        builds_api,
    ):
        app.register_blueprint(getattr(module, 'bp', module), url_prefix=API_PREFIX)
