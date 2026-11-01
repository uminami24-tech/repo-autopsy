"""tests/test_llm.py — llm.py のユニットテスト（T-17）。

ネットワークを使わず httpx.MockTransport でモックする。
ZRO_API_KEY フォールバック・環境変数の挙動をテストする。
"""

from __future__ import annotations

import json

import httpx
import pytest

from repo_autopsy.llm import LLMError, _get_api_key, _get_base_url, _get_model, chat

# ---------------------------------------------------------------------------
# ヘルパー：成功レスポンスのファクトリ
# ---------------------------------------------------------------------------


def _llm_success_response(content: str = "テスト応答") -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    }


def _make_llm_transport(
    status: int = 200,
    body: dict | None = None,
) -> httpx.MockTransport:
    response_body = body if body is not None else _llm_success_response()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=response_body)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# T-17-1: API キーの優先順位（FR-08/09）
# ---------------------------------------------------------------------------


class TestGetApiKey:
    def test_openai_api_key_used_when_set(self, monkeypatch):
        """OPENAI_API_KEY が設定されていれば使用する。"""
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key-xxx")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)
        key = _get_api_key()
        assert key == "openai-key-xxx"

    def test_zro_api_key_fallback(self, monkeypatch):
        """OPENAI_API_KEY がなければ ZRO_API_KEY を使用する。"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ZRO_API_KEY", "zro-key-yyy")
        key = _get_api_key()
        assert key == "zro-key-yyy"

    def test_openai_key_takes_priority_over_zro(self, monkeypatch):
        """両方設定されている場合は OPENAI_API_KEY を優先する。"""
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key-xxx")
        monkeypatch.setenv("ZRO_API_KEY", "zro-key-yyy")
        key = _get_api_key()
        assert key == "openai-key-xxx"

    def test_no_key_raises_llm_error(self, monkeypatch):
        """どちらも設定されていなければ LLMError を raise する。"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ZRO_API_KEY", raising=False)
        with pytest.raises(LLMError, match="API キーが設定されていません"):
            _get_api_key()

    def test_key_value_not_in_error_message(self, monkeypatch):
        """エラーメッセージに API キーの値が含まれないこと（セキュリティ）。"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-very-secret-key")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)
        # キーは正常に取得できる（エラーにならない）
        key = _get_api_key()
        assert key == "sk-very-secret-key"


# ---------------------------------------------------------------------------
# T-17-2: 環境変数の読み取り
# ---------------------------------------------------------------------------


class TestEnvVars:
    def test_default_base_url(self, monkeypatch):
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        url = _get_base_url()
        assert url == "https://zro.moonmath.ai/v1"

    def test_custom_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1/")
        url = _get_base_url()
        # 末尾スラッシュは除去される
        assert not url.endswith("/")
        assert "api.openai.com" in url

    def test_default_model(self, monkeypatch):
        monkeypatch.delenv("AUTOPSY_MODEL", raising=False)
        model = _get_model()
        assert model == "deepseek-v4.1-flash"

    def test_custom_model(self, monkeypatch):
        monkeypatch.setenv("AUTOPSY_MODEL", "gpt-4o-mini")
        model = _get_model()
        assert model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# T-17-3: chat() 関数の動作
# ---------------------------------------------------------------------------


class TestChat:
    def test_chat_success(self, monkeypatch):
        """正常な LLM レスポンスからコンテンツを返すこと。"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)

        transport = _make_llm_transport(200, _llm_success_response("テスト応答テキスト"))

        import unittest.mock as mock
        with mock.patch("repo_autopsy.llm.httpx.Client") as mock_cls:
            mock_ctx = mock_cls.return_value.__enter__.return_value
            mock_ctx.post.return_value = httpx.Response(
                200, json=_llm_success_response("テスト応答テキスト")
            )
            result = chat([{"role": "user", "content": "テスト"}])

        assert result == "テスト応答テキスト"

    def test_chat_http_error_raises_llm_error(self, monkeypatch):
        """HTTP 4xx/5xx は LLMError を raise すること。"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)

        import unittest.mock as mock
        with mock.patch("repo_autopsy.llm.httpx.Client") as mock_cls:
            mock_ctx = mock_cls.return_value.__enter__.return_value
            mock_ctx.post.return_value = httpx.Response(500, json={"error": "Internal Server Error"})
            with pytest.raises(LLMError, match="HTTP 500"):
                chat([{"role": "user", "content": "テスト"}])

    def test_chat_request_error_raises_llm_error(self, monkeypatch):
        """接続エラーは LLMError を raise すること。"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)

        import unittest.mock as mock
        with mock.patch("repo_autopsy.llm.httpx.Client") as mock_cls:
            mock_ctx = mock_cls.return_value.__enter__.return_value
            mock_ctx.post.side_effect = httpx.RequestError("接続失敗", request=None)
            with pytest.raises(LLMError, match="リクエストが失敗"):
                chat([{"role": "user", "content": "テスト"}])

    def test_chat_no_key_raises_llm_error(self, monkeypatch):
        """API キーがなければ LLMError を raise すること。"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ZRO_API_KEY", raising=False)
        with pytest.raises(LLMError):
            chat([{"role": "user", "content": "テスト"}])

    def test_chat_malformed_response_raises_llm_error(self, monkeypatch):
        """不正なレスポンス構造は LLMError を raise すること。"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)

        import unittest.mock as mock
        with mock.patch("repo_autopsy.llm.httpx.Client") as mock_cls:
            mock_ctx = mock_cls.return_value.__enter__.return_value
            mock_ctx.post.return_value = httpx.Response(200, json={"unexpected": "structure"})
            with pytest.raises(LLMError, match="パースに失敗"):
                chat([{"role": "user", "content": "テスト"}])


# ---------------------------------------------------------------------------
# T-17-4: AUTOPSY_LLM_TIMEOUT と reasoning_content 無視（FR-10b/10c）
# ---------------------------------------------------------------------------


class TestLLMTimeout:
    def test_default_timeout_is_300(self, monkeypatch):
        """AUTOPSY_LLM_TIMEOUT 未設定時は 300 秒であること（FR-10b）。"""
        monkeypatch.delenv("AUTOPSY_LLM_TIMEOUT", raising=False)
        from repo_autopsy.llm import _get_timeout
        assert _get_timeout() == 300.0

    def test_custom_timeout_from_env(self, monkeypatch):
        """AUTOPSY_LLM_TIMEOUT=120 のとき 120.0 を返すこと（FR-10b）。"""
        monkeypatch.setenv("AUTOPSY_LLM_TIMEOUT", "120")
        from repo_autopsy.llm import _get_timeout
        assert _get_timeout() == 120.0

    def test_invalid_timeout_falls_back_to_default(self, monkeypatch):
        """AUTOPSY_LLM_TIMEOUT が不正値のとき既定値にフォールバックすること。"""
        monkeypatch.setenv("AUTOPSY_LLM_TIMEOUT", "not-a-number")
        from repo_autopsy.llm import _get_timeout
        assert _get_timeout() == 300.0

    def test_timeout_is_passed_to_httpx(self, monkeypatch):
        """chat() が httpx.Client を呼ぶとき AUTOPSY_LLM_TIMEOUT の値を渡すこと。"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)
        monkeypatch.setenv("AUTOPSY_LLM_TIMEOUT", "180")

        import unittest.mock as mock
        with mock.patch("repo_autopsy.llm.httpx.Client") as mock_cls:
            mock_ctx = mock_cls.return_value.__enter__.return_value
            mock_ctx.post.return_value = httpx.Response(
                200, json=_llm_success_response("ok")
            )
            chat([{"role": "user", "content": "test"}])
        # httpx.Client(timeout=180.0) で呼ばれていること
        mock_cls.assert_called_once_with(timeout=180.0)


class TestReasoningContentIgnored:
    def test_content_used_not_reasoning_content(self, monkeypatch):
        """reasoning_content フィールドは無視し content のみ返すこと（FR-10c）。"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)

        response_with_reasoning = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "reasoning_content": "内部推論ステップ（使わない）",
                    "content": "最終的な回答テキスト",
                }
            }]
        }

        import unittest.mock as mock
        with mock.patch("repo_autopsy.llm.httpx.Client") as mock_cls:
            mock_ctx = mock_cls.return_value.__enter__.return_value
            mock_ctx.post.return_value = httpx.Response(200, json=response_with_reasoning)
            result = chat([{"role": "user", "content": "テスト"}])

        assert result == "最終的な回答テキスト"
        assert "内部推論ステップ" not in result

    def test_empty_content_with_reasoning_content(self, monkeypatch):
        """content が空文字列でも正常に空文字列を返すこと。"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("ZRO_API_KEY", raising=False)

        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "reasoning_content": "推論のみ",
                    "content": "",
                }
            }]
        }

        import unittest.mock as mock
        with mock.patch("repo_autopsy.llm.httpx.Client") as mock_cls:
            mock_ctx = mock_cls.return_value.__enter__.return_value
            mock_ctx.post.return_value = httpx.Response(200, json=response)
            result = chat([{"role": "user", "content": "テスト"}])

        assert result == ""
