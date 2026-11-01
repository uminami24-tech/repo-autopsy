"""GitHub REST API からリポジトリ情報を取得するモジュール。

公開 API:
    fetch_repo(url: str) -> RepoMeta

モジュール境界ルール:
    - 外部 HTTP のみ。ファイル書き込み・LLM 呼び出しは行わない。
    - API キーはログ・例外メッセージに含めない。
"""

from __future__ import annotations

import base64
import os
import re
from typing import Any

import httpx

from .models import RepoMeta

# GitHub API のベース URL
_GITHUB_API_BASE = "https://api.github.com"

# URL パターン: https://github.com/<owner>/<repo>（末尾スラッシュ・.git は許容）
_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?/?$"
)


# ---------------------------------------------------------------------------
# 例外クラス
# ---------------------------------------------------------------------------


class InvalidURLError(ValueError):
    """GitHub URL の形式が不正なときに raise する（FR-01）。"""


class FetchError(RuntimeError):
    """GitHub API アクセス時の HTTP エラー全般（FR-07）。"""


class RateLimitError(FetchError):
    """GitHub API の 403/429 レート制限エラー（FR-07）。"""


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _validate_url(url: str) -> tuple[str, str]:
    """URL を検証し (owner, repo) を返す。不正なら InvalidURLError を raise する（FR-01）。"""
    m = _GITHUB_URL_RE.match(url.strip())
    if not m:
        raise InvalidURLError(
            f"URL の形式が不正です。https://github.com/<owner>/<repo> の形式で指定してください。\n"
            f"入力値: {url}"
        )
    return m.group(1), m.group(2)


def _build_headers() -> dict[str, str]:
    """共通リクエストヘッダーを構築する。GITHUB_TOKEN があれば Authorization を付与（FR-06）。"""
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _check_response(resp: httpx.Response) -> None:
    """レスポンスのステータスコードを検査する。403/429 は RateLimitError（FR-07）。"""
    if resp.status_code in (403, 429):
        raise RateLimitError(
            f"GitHub API のレート制限に達しました（HTTP {resp.status_code}）。"
            "しばらく待ってから再実行するか、GITHUB_TOKEN を設定してください。"
        )
    if resp.status_code >= 400:
        raise FetchError(
            f"GitHub API からエラーが返されました（HTTP {resp.status_code}）: {resp.url}"
        )


def _fetch_meta(owner: str, repo: str, client: httpx.Client) -> dict[str, Any]:
    """リポジトリメタデータを取得して辞書を返す（FR-02）。"""
    resp = client.get(f"{_GITHUB_API_BASE}/repos/{owner}/{repo}")
    _check_response(resp)
    return resp.json()


def _fetch_readme(owner: str, repo: str, client: httpx.Client) -> str:
    """README テキスト（Base64 デコード済み）を返す（FR-03）。取得失敗時は空文字。"""
    resp = client.get(f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/readme")
    if resp.status_code == 404:
        return ""
    _check_response(resp)
    data = resp.json()
    encoded = data.get("content", "")
    # GitHub API は改行込みの Base64 を返す
    decoded = base64.b64decode(encoded.replace("\n", "")).decode("utf-8", errors="replace")
    return decoded


def _fetch_license(owner: str, repo: str, client: httpx.Client) -> str | None:
    """SPDX ライセンス識別子を返す（FR-04）。LICENSE がなければ None。"""
    resp = client.get(f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/license")
    if resp.status_code == 404:
        return None
    _check_response(resp)
    data = resp.json()
    license_info = data.get("license") or {}
    return license_info.get("spdx_id") or None


def _fetch_root_files(owner: str, repo: str, client: httpx.Client) -> list[str]:
    """ルートディレクトリのファイル名一覧を返す（FR-05）。"""
    resp = client.get(f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/contents/")
    _check_response(resp)
    items: list[dict[str, Any]] = resp.json()
    return [item["name"] for item in items if "name" in item]


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def fetch_repo(url: str) -> RepoMeta:
    """GitHub 公開リポジトリの URL から RepoMeta を生成して返す（FR-01〜07）。

    Args:
        url: https://github.com/<owner>/<repo> 形式の URL。

    Returns:
        RepoMeta: 取得したメタデータ。

    Raises:
        InvalidURLError: URL 形式が不正なとき。
        RateLimitError: API レート制限（403/429）のとき。
        FetchError: その他の HTTP エラーのとき。
    """
    owner, repo = _validate_url(url)

    headers = _build_headers()
    with httpx.Client(headers=headers, timeout=30.0) as client:
        meta = _fetch_meta(owner, repo, client)
        readme_text = _fetch_readme(owner, repo, client)
        license_spdx = _fetch_license(owner, repo, client)
        root_files = _fetch_root_files(owner, repo, client)

    # last_commit_at は pushed_at（最終プッシュ日時）を使用
    last_commit_at = meta.get("pushed_at") or meta.get("updated_at") or ""
    stars = meta.get("stargazers_count", 0)
    language = meta.get("language")
    topics = meta.get("topics") or []

    return RepoMeta(
        owner=owner,
        repo=repo,
        url=url,
        license_spdx=license_spdx,
        last_commit_at=last_commit_at,
        stars=stars,
        language=language,
        topics=topics,
        readme_text=readme_text,
        root_files=root_files,
    )
