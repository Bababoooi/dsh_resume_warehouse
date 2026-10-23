"""t7 下行抓取：白名单、开关、私网、跳转上限、正文过短、超时、24h 缓存。

四条红线（docs/API-CONTRACT §7 + REVIEW-CHECKLIST ANL-05）：

1. 只 GET 公开页，**零用户字段**（无 cookie、无 Authorization）；
2. 白名单 + `allow_web_fetch` 开关 + 私网地址三重拦截，全部 403 `EGRESS_BLOCKED`；
3. 抓不到就降级为「只用粘贴的 JD」，绝不能把分析整体拖垮；
4. 缓存只落本机 `data/files/`，24h 内 `from_cache=true`，**永不二次上云**。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

PROJECT = SERVER.parent

from app import create_app  # noqa: E402
from app import db as db_mod  # noqa: E402
from app.adapters import fetch_client  # noqa: E402
from app.services import jobrun  # noqa: E402


def html_page(body_chars: int = 400, *, title: str = "数据分析实习生 - 招聘") -> bytes:
    paragraph = "岗位职责：负责增长数据分析，搭建指标体系，输出归因结论。" * 20
    return (
        f"<html><head><title>{title}</title>"
        "<script>var x = 1;</script><style>.a{}</style></head>"
        f"<body><h1>{title}</h1><p>{paragraph[:body_chars]}</p></body></html>"
    ).encode("utf-8")


def response_for(url: str, body: bytes, *, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=body,
        headers={"content-type": "text/html; charset=utf-8", **(headers or {})},
        request=httpx.Request("GET", url),
    )


class FetchBaseTest(unittest.TestCase):
    def setUp(self) -> None:
        base = PROJECT / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        jobrun.wait_idle()
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        db_mod.reset_paths_for_tests()

    def seed_settings(self, **values) -> None:
        from app.repos import SettingsRepo

        repo = SettingsRepo()
        for key, value in values.items():
            repo.set(key, value)

    def error(self, response) -> dict:
        payload = response.get_json()
        self.assertFalse(payload["ok"], payload)
        return payload["error"]


class FetchPolicyTest(FetchBaseTest):
    """三重拦截：域名不在白名单 / 全局开关关掉 / 解析到私网地址。"""

    def test_host_not_in_allowlist_is_403(self) -> None:
        response = self.client.post("/api/v1/fetch/public-page", json={"url": "https://example.com/jd/1"})
        self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
        error = self.error(response)
        self.assertEqual(error["code"], "EGRESS_BLOCKED")
        self.assertEqual(error["details"]["reason"], "host_not_allowed")
        self.assertEqual(error["details"]["host"], "example.com")
        self.assertIn("allowed_hosts", error["details"])

    def test_fetch_disabled_is_403(self) -> None:
        self.seed_settings(allow_web_fetch=False)
        response = self.client.post(
            "/api/v1/fetch/public-page", json={"url": "https://www.zhipin.com/job_detail/1.html"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.error(response)["details"]["reason"], "fetch_disabled")

    def test_private_address_is_403(self) -> None:
        self.seed_settings(fetch_allowed_hosts=["127.0.0.1", "localhost"])
        for url in ("http://127.0.0.1:8080/jd", "http://localhost:9000/jd"):
            with self.subTest(url=url):
                response = self.client.post("/api/v1/fetch/public-page", json={"url": url})
                self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
                self.assertEqual(self.error(response)["details"]["reason"], "private_address")

    def test_non_http_scheme_is_403(self) -> None:
        response = self.client.post("/api/v1/fetch/public-page", json={"url": "file:///etc/passwd"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.error(response)["details"]["reason"], "unsupported_scheme")

    def test_custom_allowlist_is_honored(self) -> None:
        self.seed_settings(fetch_allowed_hosts=["example.com"])
        # 设置里的域名是「追加」到内置白名单（docs §7：把公司域名加进白名单），不是替换
        hosts = fetch_client.allowed_hosts()
        self.assertIn("example.com", hosts)
        self.assertIn("www.zhipin.com", hosts)

        url = "https://example.com/jd"
        transport = httpx.MockTransport(lambda request: response_for(str(request.url), html_page()))
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            result = fetch_client.fetch_public_page(url, use_cache=False, client=client)
        self.assertEqual(result.host, "example.com")
        self.assertGreaterEqual(result.chars, 200)


class FetchBehaviourTest(FetchBaseTest):
    """抓取成功、跳转、过短正文、超时、超限与缓存。"""

    URL = "https://www.zhipin.com/job_detail/abc.html"

    def _fetch(self, handler) -> httpx.Client:
        transport = httpx.MockTransport(handler)
        return httpx.Client(transport=transport, follow_redirects=False)

    def test_fetch_ok_strips_scripts_and_returns_text(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return response_for(str(request.url), html_page())

        result = fetch_client.fetch_public_page(self.URL, use_cache=False, client=self._fetch(handler))
        self.assertEqual(result.host, "www.zhipin.com")
        self.assertEqual(result.title, "数据分析实习生 - 招聘")
        self.assertGreaterEqual(result.chars, 200)
        self.assertNotIn("var x = 1", result.text)
        self.assertFalse(result.from_cache)

    def test_short_body_is_422_empty_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return response_for(str(request.url), b"<html><body><p>too short</p></body></html>")

        with self.assertRaises(fetch_client.ApiError) as ctx:
            fetch_client.fetch_public_page(self.URL, use_cache=False, client=self._fetch(handler))
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")
        self.assertEqual(ctx.exception.http_status, 422)
        self.assertEqual(ctx.exception.details["reason"], "EMPTY_BODY")

    def test_timeout_is_504(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        with self.assertRaises(fetch_client.ApiError) as ctx:
            fetch_client.fetch_public_page(self.URL, use_cache=False, client=self._fetch(handler))
        self.assertEqual(ctx.exception.code, "TIMEOUT")
        self.assertEqual(ctx.exception.http_status, 504)

    def test_network_error_is_502_and_not_reported_as_llm(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        with self.assertRaises(fetch_client.ApiError) as ctx:
            fetch_client.fetch_public_page(self.URL, use_cache=False, client=self._fetch(handler))
        self.assertEqual(ctx.exception.code, "FETCH_UNREACHABLE")
        self.assertNotIn("LLM", ctx.exception.code)

    def test_too_many_redirects_is_403(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            request.url = request.url  # noqa: SLF001 - 只为让 URL 唯一
            return response_for(str(request.url), b"", status=302, headers={"location": str(request.url)})

        with self.assertRaises(fetch_client.ApiError) as ctx:
            fetch_client.fetch_public_page(self.URL, use_cache=False, client=self._fetch(handler))
        self.assertEqual(ctx.exception.details["reason"], "too_many_redirects")

    def test_cache_hit_second_time(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return response_for(str(request.url), html_page())

        client = self._fetch(handler)
        first = fetch_client.fetch_public_page(self.URL, client=client)
        second = fetch_client.fetch_public_page(self.URL, client=client)
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(first.text, second.text)

    def test_no_user_credentials_in_request(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update({key.lower(): value for key, value in request.headers.items()})
            return response_for(str(request.url), html_page())

        fetch_client.fetch_public_page(self.URL, use_cache=False, client=self._fetch(handler))
        self.assertEqual(seen.get("user-agent"), fetch_client.USER_AGENT)
        self.assertNotIn("authorization", seen)
        self.assertNotIn("cookie", seen)


class CompanyAnalyzeTest(FetchBaseTest):
    """ANL-05：抓取失败只降级、不失败；缓存 30 天内不重复分析。"""

    def test_fetch_failure_degrades_to_jd_only(self) -> None:
        jd_text = "岗位职责：门店数据运营。要求：本科及以上学历，不设院校门槛。熟悉 Excel、SQL。"
        body = {
            "company_name": "禾味食品集团",
            "jd_text": jd_text,
            "fetch_url": "https://example.com/careers",  # 不在白名单 → 抓取必失败
            "allow_fetch": True,
            "method": "heuristic",
        }
        response = self.client.post("/api/v1/company-profiles/analyze", json=body)
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        job_id = response.get_json()["data"]["job_id"]
        import time

        for _ in range(100):
            job = self.client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
            if job["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(job["status"], "succeeded", job)
        result = job["result_json"]
        codes = [item["code"] for item in result["warnings"]]
        self.assertIn("FETCH_FAILED", codes)
        profile = result["profile"]
        self.assertEqual(profile["company_name"], "禾味食品集团")
        self.assertFalse(profile["school_preference"]["hard_filter"])
        self.assertTrue(profile["hiring_preferences"], "四项必答不得为空")

    def test_cache_hit_skips_llm(self) -> None:
        body = {
            "company_name": "星链数科（杭州）有限公司",
            "jd_text": "要求：985/211 院校优先，硕士及以上。熟悉 SQL、Python。",
            "method": "heuristic",
        }
        first = self.client.post("/api/v1/company-profiles/analyze", json=body)
        self.assertEqual(first.status_code, 202)
        job_id = first.get_json()["data"]["job_id"]
        import time

        for _ in range(100):
            job = self.client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
            if job["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(job["status"], "succeeded", job)

        with mock.patch("httpx.Client.post", side_effect=AssertionError("缓存命中不许调模型")):
            cached = self.client.post("/api/v1/company-profiles/analyze", json=body)
        self.assertEqual(cached.status_code, 200, cached.get_data(as_text=True))
        data = cached.get_json()["data"]
        self.assertTrue(data["cache_hit"])
        self.assertEqual(data["profile"]["company_name"], body["company_name"])

        refreshed = self.client.post(
            "/api/v1/company-profiles/analyze", json={**body, "refresh": True}
        )
        self.assertEqual(refreshed.status_code, 202)

    def test_analyze_without_jd_or_url_is_422(self) -> None:
        response = self.client.post(
            "/api/v1/company-profiles/analyze", json={"company_name": "空白公司"}
        )
        self.assertEqual(response.status_code, 422)

    def test_fetch_disabled_warns_and_uses_jd(self) -> None:
        body = {
            "company_name": "静默食品",
            "jd_text": "要求：本科及以上。熟悉 Excel。",
            "fetch_url": "https://www.zhipin.com/job_detail/x.html",
            "allow_fetch": False,
            "method": "heuristic",
        }
        response = self.client.post("/api/v1/company-profiles/analyze", json=body)
        self.assertEqual(response.status_code, 202)
        job_id = response.get_json()["data"]["job_id"]
        import time

        for _ in range(100):
            job = self.client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
            if job["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(job["status"], "succeeded", job)
        codes = [item["code"] for item in job["result_json"]["warnings"]]
        self.assertIn("FETCH_DISABLED", codes)


class FetchHtmlTest(unittest.TestCase):
    def test_html_to_text_extracts_title_and_body(self) -> None:
        title, text = fetch_client.html_to_text(
            "<html><head><title>T</title><script>x</script></head>"
            "<body><h1>标题</h1><p>正文 &amp; 符号</p></body></html>"
        )
        self.assertEqual(title, "T")
        self.assertIn("标题", text)
        self.assertIn("&", text)
        self.assertNotIn("script", text)


if __name__ == "__main__":
    unittest.main()
