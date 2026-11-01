"""LLM クライアントモジュール（OpenAI 互換 /chat/completions）。

公開 API:
    chat(messages: list[dict]) -> str

環境変数:
    OPENAI_BASE_URL     既定: https://zro.moonmath.ai/v1
    OPENAI_API_KEY      優先。なければ ZRO_API_KEY を使用（FR-08/09）
    AUTOPSY_MODEL       既定: deepseek-v4.1-flash
    AUTOPSY_LLM_TIMEOUT 既定: 300（秒）。Zro など推論モデルは応答に時間がかかるため

モジュール境界ルール:
    - LLM API 呼び出しのみ。判定ロジックは judge.py に置く。
    - API キーをログ・レポート・コードに含めない。
"""

from __future__ import annotations

import os

import httpx

# ---------------------------------------------------------------------------
# 定数・デフォルト値
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "https://zro.moonmath.ai/v1"
_DEFAULT_MODEL = "deepseek-v4.1-flash"
_DEFAULT_TIMEOUT = 300.0  # 秒。Zro の推論モデルは 70 秒超かかる場合がある


# ---------------------------------------------------------------------------
# 例外クラス
# ---------------------------------------------------------------------------


class LLMError(RuntimeError):
    """LLM API 呼び出しに失敗したとき（FR-10）。"""


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    """API キーを環境変数から取得する。OPENAI_API_KEY 優先、なければ ZRO_API_KEY（FR-08/09）。"""
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ZRO_API_KEY")
    if not key:
        raise LLMError(
            "API キーが設定されていません。"
            "OPENAI_API_KEY または ZRO_API_KEY 環境変数を設定してください。"
        )
    return key


def _get_base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _get_model() -> str:
    return os.environ.get("AUTOPSY_MODEL", _DEFAULT_MODEL)


def _get_timeout() -> float:
    """AUTOPSY_LLM_TIMEOUT 環境変数からタイムアウト秒数を取得する。既定 300 秒。"""
    val = os.environ.get("AUTOPSY_LLM_TIMEOUT")
    if val is None:
        return _DEFAULT_TIMEOUT
    try:
        t = float(val)
        if t <= 0:
            return _DEFAULT_TIMEOUT
        return t
    except (ValueError, TypeError):
        return _DEFAULT_TIMEOUT


def _extract_content(data: dict) -> str:
    """レスポンス JSON からアシスタントの content を取得する。

    reasoning_content フィールドは無視し、content のみを返す。
    Zro / DeepSeek 推論モデルは reasoning_content を別フィールドで返すが
    本ツールでは使用しない。
    """
    try:
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        return content
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"LLM API レスポンスのパースに失敗しました: {e}") from e


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def chat(messages: list[dict]) -> str:
    """OpenAI 互換 /chat/completions エンドポイントを呼び出す。

    Args:
        messages: OpenAI 形式のメッセージリスト（[{"role": "...", "content": "..."}, ...]）。

    Returns:
        str: アシスタントの返答テキスト（reasoning_content は含まない）。

    Raises:
        LLMError: API キーが未設定、または HTTP エラーが発生したとき。
    """
    api_key = _get_api_key()
    base_url = _get_base_url()
    model = _get_model()
    timeout = _get_timeout()

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
    except httpx.RequestError as e:
        raise LLMError(f"LLM API へのリクエストが失敗しました: {e}") from e

    if resp.status_code >= 400:
        raise LLMError(
            f"LLM API からエラーが返されました（HTTP {resp.status_code}）"
        )

    try:
        data = resp.json()
        return _extract_content(data)
    except LLMError:
        raise
    except (ValueError, KeyError) as e:
        raise LLMError(f"LLM API レスポンスのパースに失敗しました: {e}") from e
