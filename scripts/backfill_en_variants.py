#!/usr/bin/env python3
"""批量补齐英文变体（改语言渲染，不改事实）。

背景：英文 PDF 目前有 20 行正文里 11 行是中文回退（`LANG_FALLBACK`）。原理由是
「en 变体不足」，现在补齐素材——**只做措辞翻译，不加事实、不改数字**。

为什么走 HTTP 而不是直接调服务层：变体生成是**花钱的上云动作**，契约要求先经
consent preview 让用户看到将发送的字段清单。脚本绕开 preview 就等于绕开那道门，
所以这里严格走 `/llm/preview → /packages/{id}/variants/generate → /jobs → POST /variants`。

用法：
    python3 scripts/backfill_en_variants.py                 # dry-run：只列缺口
    python3 scripts/backfill_en_variants.py --apply          # 真跑（会产生 LLM 调用）
    python3 scripts/backfill_en_variants.py --apply --limit 2 --tone impact
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import httpx


def _base_url(explicit: str | None) -> str:
    if explicit:
        return explicit.rstrip("/")
    port = 8765
    try:
        with open(os.path.join("data", "runtime", "app_port"), encoding="utf-8") as fh:
            port = json.load(fh)["port"]
    except Exception:
        pass
    return f"http://127.0.0.1:{port}"


def _get(client: httpx.Client, path: str, **params: Any) -> Any:
    resp = client.get(path, params=params or None)
    resp.raise_for_status()
    return resp.json().get("data")


def _post(client: httpx.Client, path: str, body: dict[str, Any]) -> Any:
    resp = client.post(path, json=body)
    if resp.status_code >= 400:
        raise RuntimeError(f"{path} → {resp.status_code} {resp.text[:300]}")
    return resp.json().get("data")


def _wait_job(client: httpx.Client, job_id: str, timeout: float) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = _get(client, f"/api/v1/jobs/{job_id}")
        status = str(job.get("status") or "")
        if status in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(1.5)
    raise TimeoutError(f"作业 {job_id} 超时（{timeout}s）")


def _gaps(package: dict[str, Any]) -> list[str]:
    """有中文变体但缺英文变体的 bullet_key（保持原顺序）。"""
    by_lang: dict[str, set[str]] = {"zh": set(), "en": set()}
    for variant in package.get("variants") or []:
        by_lang.setdefault(str(variant.get("lang") or "zh"), set()).add(str(variant.get("bullet_key") or ""))
    return sorted(by_lang["zh"] - by_lang["en"] - {""})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量补齐英文变体（默认 dry-run）")
    parser.add_argument("--apply", action="store_true", help="真的调用模型并入库")
    parser.add_argument("--base-url", default=None, help="服务地址（默认读 data/runtime/app_port）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理几个包（0 = 全部）")
    parser.add_argument("--tone", default="impact", help="目标语气（默认 impact）")
    parser.add_argument("--timeout", type=float, default=240.0, help="单个作业超时秒数")
    args = parser.parse_args(argv)

    base = _base_url(args.base_url)
    print(f"服务：{base}　模式：{'apply' if args.apply else 'dry-run'}　语气：{args.tone}")

    with httpx.Client(base_url=base, timeout=60.0) as client:
        health = _get(client, "/api/v1/health")
        data = (health or {}).get("data") or health or {}
        if not (data.get("llm_ready") or (health or {}).get("llm_ready")):
            print("AI 未就绪（key 未配置或 provider=off），先处理再跑。", file=sys.stderr)
            return 2

        listing = _get(client, "/api/v1/packages", status="ready", include_variants=1, limit=200) or {}
        packages = listing.get("items") or []
        if args.limit:
            packages = packages[: args.limit]
        print(f"ready 包 {len(packages)} 个")

        plan: list[tuple[dict[str, Any], list[str]]] = []
        for package in packages:
            try:
                # 单包详情要 `?include=variants`（列表才是 include_variants=1）。
                # 传错参数不会报错，只会安静地返回不带 variants 的包——那会让缺口
                # 恒为 0，看起来「已经全齐」，实际什么都没查。下面有断言兜这个。
                detail = _get(client, f"/api/v1/packages/{package['id']}", include="variants") or {}
            except Exception:
                detail = package
            missing = _gaps(detail)
            if missing:
                plan.append((detail, missing))

        # 反向护栏：如果所有包都「没有变体」，说明是查询姿势错了，不是真的没缺口。
        looked_at = [d for d, _ in plan] or []
        if packages and not plan and all(not (p.get("variants") or []) for p in packages):
            print(
                "查到的所有包都不带 variants——这几乎一定是查询参数写错了，而不是真的没有缺口。",
                file=sys.stderr,
            )
            return 3

        total_keys = sum(len(keys) for _, keys in plan)
        print(f"缺英文变体的包 {len(plan)} 个，共 {total_keys} 条要点")
        for detail, keys in plan:
            print(f"  · {str(detail.get('title') or '')[:28]:30s} 缺 {len(keys)} 条：{keys[:3]}{'…' if len(keys) > 3 else ''}")
        if not args.apply:
            print("\n（dry-run 结束；加 --apply 才会调用模型）")
            return 0
        if not plan:
            print("没有缺口，无需生成。")
            return 0

        created = 0
        failed: list[str] = []
        for detail, keys in plan:
            title = str(detail.get("title") or detail["id"])
            print(f"\n→ 生成 {title[:26]}（{len(keys)} 条 / {args.tone} / en）")
            try:
                preview = _post(
                    client,
                    "/api/v1/llm/preview",
                    {
                        "purpose": "bullets_generate",
                        "selections": {"bullet_keys": keys, "tones": [args.tone], "lang": "en"},
                    },
                )
                preview_id = (preview or {}).get("preview_id") or (preview or {}).get("id")
                sha = (preview or {}).get("payload_sha256")
                if not preview_id:
                    raise RuntimeError(f"preview 响应缺少 preview_id：{str(preview)[:200]}")
                submitted = _post(
                    client,
                    f"/api/v1/packages/{detail['id']}/variants/generate",
                    {
                        "preview_id": preview_id,
                        "bullet_keys": keys,
                        "tones": [args.tone],
                        "lang": "en",
                        "expected_payload_sha256": sha,
                    },
                )
                job = _wait_job(client, submitted["job_id"], args.timeout)
                if job.get("status") != "succeeded":
                    raise RuntimeError(f"作业失败：{job.get('error') or job.get('status')}")
                result = job.get("result_json") or job.get("result") or {}
                if isinstance(result, str):
                    result = json.loads(result)
                variants = result.get("variants") or []
                print(f"   模型返回 {len(variants)} 条变体")
                for index, variant in enumerate(variants):
                    text = str(variant.get("text") or "").strip()
                    if not text:
                        continue
                    key = variant.get("bullet_key") or keys[min(index, len(keys) - 1)]
                    try:
                        _post(
                            client,
                            f"/api/v1/packages/{detail['id']}/variants",
                            {
                                "bullet_key": key,
                                "text": text[:400],
                                "tone": variant.get("tone") or args.tone,
                                "lang": "en",
                                "keywords": variant.get("keywords") or [],
                                "verified": False,
                            },
                        )
                        created += 1
                    except Exception as exc:  # 单条失败不该中断整批
                        failed.append(f"{title}/{key}: {exc}")
                        print(f"   ! 入库失败 {key}: {exc}")
            except Exception as exc:
                failed.append(f"{title}: {exc}")
                print(f"   ! 该包失败：{exc}")

        print(f"\n完成：新增英文变体 {created} 条，失败 {len(failed)} 项")
        for item in failed[:5]:
            print("  ·", item)
        return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
