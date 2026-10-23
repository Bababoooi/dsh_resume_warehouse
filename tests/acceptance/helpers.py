"""AC harness 的小工具：pdf 事实、档案快照、直查库。"""

from __future__ import annotations

import json
from pathlib import Path


def artifact(flow: dict, key: str = "zh-original") -> dict:
    payload = flow["artifacts"].get(key) or {}
    items = payload.get("artifacts") or []
    assert items, f"{key} 没有产物：{json.dumps(payload, ensure_ascii=False)[:400]}"
    return items[0]


def artifact_path(flow: dict, key: str = "zh-original") -> Path:
    item = artifact(flow, key)
    return flow["data_dir"] / "exports" / item["filename"]


def pdf_text(flow: dict, key: str = "zh-original") -> str:
    cache = flow.setdefault("_pdf_text", {})
    if key not in cache:
        import pdfplumber

        with pdfplumber.open(str(artifact_path(flow, key))) as pdf:
            cache[key] = "\n".join((page.extract_text() or "") for page in pdf.pages)
    return cache[key]


def pdf_pages(flow: dict, key: str = "zh-original") -> int:
    import pdfplumber

    with pdfplumber.open(str(artifact_path(flow, key))) as pdf:
        return len(pdf.pages)


def pdf_metrics(flow: dict, key: str = "zh-original") -> dict:
    cache = flow.setdefault("_pdf_metrics", {})
    if key in cache:
        return cache[key]
    import pdfplumber

    sizes: list[float] = []
    images: list[dict] = []
    overflow = 0
    with pdfplumber.open(str(artifact_path(flow, key))) as pdf:
        for page in pdf.pages:
            left = float(page.mediabox[0])
            right = float(page.mediabox[2])
            for char in page.chars:
                if str(char.get("text") or "").strip():
                    sizes.append(round(float(char["size"]), 2))
                if float(char["x1"]) > right + 0.5 or float(char["x0"]) < left - 0.5:
                    overflow += 1
            for image in page.images:
                images.append(
                    {
                        "x0": round(float(image["x0"]), 2),
                        "right_gap": round(float(page.mediabox[2]) - float(image["x1"]), 2),
                        "top": round(float(image["top"]) + max(0.0, -float(page.mediabox[1])), 2),
                        "w": round(float(image["x1"]) - float(image["x0"]), 2),
                        "h": round(float(image["bottom"]) - float(image["top"]), 2),
                    }
                )
    counts: dict[float, int] = {}
    for size in sizes:
        counts[size] = counts.get(size, 0) + 1
    cache[key] = {
        "sizes": sorted(set(sizes)),
        # 字号不能只看「出现过」：粗体标题比正文大 0.5pt，`max(set(sizes), key=count)`
        # 在去重列表上取众数会随机挑到 11.5，把版式判据测成假红。这里给逐字号字符数。
        "size_counts": counts,
        "body_size": max(counts, key=counts.get) if counts else 0.0,
        "min": min(sizes) if sizes else 0.0,
        "images": images,
        "overflow": overflow,
    }
    return cache[key]


def db(flow: dict):
    from app import db as db_mod

    return db_mod.get_conn()


def db_one(flow: dict, sql: str, params: tuple = ()):
    row = db(flow).execute(sql, params).fetchone()
    return row


def db_int(flow: dict, sql: str, params: tuple = ()) -> int:
    row = db_one(flow, sql, params)
    return int(row[0]) if row else 0


def snapshot_profile(client) -> dict:
    return client.get("/api/v1/profile").get_json()["data"]


def restore_profile(client, snapshot: dict) -> None:
    fields = {
        key: snapshot.get(key)
        for key in (
            "name_zh",
            "name_en",
            "school_zh",
            "school_en",
            "degree",
            "major",
            "grad_year",
            "phone",
            "email",
            "city",
            "available_date",
            "available_note",
            "skills",
        )
    }
    client.put("/api/v1/profile", json=fields)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_repo(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def wait_job(client, job_id, *, timeout_s: float = 120.0) -> dict:
    import time

    deadline = time.time() + timeout_s
    body: dict = {}
    while time.time() < deadline:
        body = (client.get(f"/api/v1/jobs/{job_id}").get_json() or {}).get("data") or {}
        if body.get("status") in ("succeeded", "failed", "interrupted"):
            return body
        time.sleep(0.05)
    return body
