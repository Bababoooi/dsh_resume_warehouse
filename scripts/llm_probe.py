#!/usr/bin/env python3
"""LLM 连通性自检（只读 .env，绝不打印 key）。

用法：
    python scripts/llm_probe.py            # 连通性 + 上下文模型 json 模式
    python scripts/llm_probe.py --analysis # 额外探测分析模型（deepseek-reasoner，会消耗极少量 token）
    python scripts/llm_probe.py --json     # 机器可读输出（供 DSH Skill doctor 复用）

输出：可用 / 不可用、模型名、重试后的结果、是否支持 json_object 模式。
所有错误只给错误码与短消息，key 任何片段都不会出现在输出里。
"""

from __future__ import annotations

import argparse
import json as jsonlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app import config as config_mod  # noqa: E402
from app.adapters import llm_client  # noqa: E402
from app.errors import ApiError  # noqa: E402

OK = "\033[32m✓\033[0m"
BAD = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def probe_models(client: llm_client.LlmClient) -> dict:
    result = client.probe_models(timeout_s=5.0)
    return {
        "reachable": bool(result.get("reachable")),
        "http_status": result.get("http_status"),
        "latency_ms": result.get("latency_ms"),
        "models": result.get("models") or [],
        "error_code": result.get("error_code"),
    }


def probe_chat(client: llm_client.LlmClient, *, model: str, provider: str, json_mode: bool, max_tokens: int) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是连通性自检助手，请以 json 返回：{\"ok\": true, \"echo\": \"pong\"}"},
            {"role": "user", "content": "ping（请返回 json）"},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        result = client.chat(payload, purpose="jd_analyze", provider=provider, model=model, validator=None, json_mode=json_mode)
    except ApiError as exc:
        return {
            "ok": False,
            "error_code": exc.code,
            "message": exc.message,
            "details": {k: v for k, v in (exc.details or {}).items() if k not in ("upstream",)},
        }
    parsed = result.parsed if json_mode else None
    return {
        "ok": result.ok,
        "http_status": result.http_status,
        "latency_ms": result.latency_ms,
        "attempts": result.attempts,
        "finish_reason": result.finish_reason,
        "total_tokens": (result.usage or {}).get("total_tokens"),
        "reasoning_tokens": (result.usage or {}).get("reasoning_tokens"),
        "json_parsed": bool(parsed) if json_mode else None,
        "raw_preview": (result.raw_text or "")[:120],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 连通性自检（不打印密钥）")
    parser.add_argument("--analysis", action="store_true", help="额外探测分析模型（reasoner）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    cfg = config_mod.load_config()
    report: dict = {
        "provider": cfg.provider,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "model_analysis": cfg.model_analysis,
        "key_set": cfg.key_set,  # 只有布尔值，绝不含 key 片段
        "ready": cfg.ready,
        "not_ready_reason": cfg.not_ready_reason,
        "max_retries": cfg.max_retries,
        "checks": {},
    }

    if not args.json:
        print("resume-warehouse · LLM 连通性自检")
        print(f"  provider   {cfg.provider}（{cfg.preset.label}）")
        print(f"  base_url   {cfg.base_url}")
        print(f"  model      {cfg.model}")
        print(f"  analysis   {cfg.model_analysis}")
        print(f"  key_set    {cfg.key_set}")
        print()

    client = llm_client.LlmClient(cfg)

    checks = report["checks"]
    checks["models"] = probe_models(client)
    if not args.json:
        m = checks["models"]
        status = OK if m["reachable"] else BAD
        detail = f"{m['http_status']} · {m['latency_ms']}ms" if m["reachable"] else f"{m.get('error_code') or '不可达'}"
        print(f"  {status} GET /models        {detail}")
        if m["models"]:
            print(f"    可用模型：{', '.join(m['models'])}")

    if cfg.ready:
        checks["chat"] = probe_chat(client, model=cfg.model, provider=cfg.provider, json_mode=True, max_tokens=64)
        if not args.json:
            c = checks["chat"]
            status = OK if c.get("ok") and c.get("json_parsed") else BAD
            if c.get("ok"):
                print(
                    f"  {status} {cfg.model}  json 模式   {c.get('http_status')} · {c.get('latency_ms')}ms"
                    f" · 重试 {max(0, (c.get('attempts') or 1) - 1)} 次 · json 解析 {'成功' if c.get('json_parsed') else '失败'}"
                )
            else:
                print(f"  {status} {cfg.model}  json 模式   {c.get('error_code')}: {c.get('message')}")
        if args.analysis:
            checks["analysis"] = probe_chat(
                client, model=cfg.model_analysis, provider=cfg.provider, json_mode=True, max_tokens=1024
            )
            if not args.json:
                c = checks["analysis"]
                status = OK if c.get("ok") and c.get("json_parsed") else BAD
                if c.get("ok"):
                    print(
                        f"  {status} {cfg.model_analysis}  json 模式   {c.get('http_status')} · {c.get('latency_ms')}ms"
                        f" · reasoning_tokens {c.get('reasoning_tokens')} · json 解析 {'成功' if c.get('json_parsed') else '失败'}"
                    )
                else:
                    print(f"  {status} {cfg.model_analysis}  json 模式   {c.get('error_code')}: {c.get('message')}")
    else:
        if not args.json:
            print(f"  {WARN} 未发送请求：{cfg.not_ready_reason}")

    if args.json:
        print(jsonlib.dumps(report, ensure_ascii=False, indent=2))
    else:
        # 判据以「真实 chat 调用」为准：/models 只是辅助信息，网络偶发抖动时它会先失败。
        chat = checks.get("chat") or {}
        models_ok = bool((checks.get("models") or {}).get("reachable"))
        chat_ok = bool(chat.get("ok") and chat.get("json_parsed"))
        retried = (chat.get("attempts") or 1) > 1
        usable = chat_ok and (models_ok or retried or not cfg.ready)
        print()
        if usable and not models_ok:
            print(f"结论：LLM 可用（GET /models 本次失败，但对话链路已由重试覆盖；连接偶发抖动属已知现象）")
        elif usable:
            print("结论：LLM 可用")
        else:
            print("结论：LLM 不可用（原因见上）")
    chat_ok = bool((checks.get("chat") or {}).get("ok") and (checks.get("chat") or {}).get("json_parsed"))
    return 0 if (chat_ok or not cfg.ready) else 1


if __name__ == "__main__":
    raise SystemExit(main())
