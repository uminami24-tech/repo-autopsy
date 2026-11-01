"""tests/test_fetch.py — fetch.py のユニットテスト（T-15）。

ネットワークを使わず httpx.MockTransport でモックする。
FR-01〜07 の受け入れ基準をテストする。
"""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import httpx
import pytest

from repo_autopsy.fetch import (
    FetchError,
    InvalidURLError,
    RateLimitError,
    _fetch_license,
    _fetch_meta,
    _fetch_readme,
    _fetch_root_files,
    _validate_url,
    fetch_repo,
)
from repo_autopsy.models import RepoMeta


# ---------------------------------------------------------------------------
# ヘルパー：モックレスポンスファクトリ
# ---------------------------------------------------------------------------


def _make_transport(routes: dict[str, tuple[int, object]]) -> httpx.MockTransport:
    """URL → (status_code, json_body) のマッピングから MockTransport を生成する。"""

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        for path, (status, body) in routes.items():
            if path in url_str:
                if isinstance(body, (dict, list)):
                    return httpx.Response(status, json=body)
                return httpx.Response(status, text=str(body))
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# T-15-1: URL バリデーション（FR-01）
# ---------------------------------------------------------------------------


class TestValidateUrl:
    def test_valid_url(self):
        owner, repo = _validate_url("https://github.com/tiangolo/fastapi")
        assert owner == "tiangolo"
        assert repo == "fastapi"

    def test_valid_url_with_trailing_slash(self):
        owner, repo = _validate_url("https://github.com/owner/repo/")
        assert owner == "owner"
        assert repo == "repo"

    def test_valid_url_with_git_suffix(self):
        owner, repo = _validate_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_invalid_url_no_repo(self):
        with pytest.raises(InvalidURLError):
            _validate_url("https://github.com/owner")

    def test_invalid_url_not_github(self):
        with pytest.raises(InvalidURLError):
            _validate_url("https://gitlab.com/owner/repo")

    def test_invalid_url_empty(self):
        with pytest.raises(InvalidURLError):
            _validate_url("")

    def test_invalid_url_plain_string(self):
        with pytest.raises(InvalidURLError):
            _validate_url("not-a-url")


# ---------------------------------------------------------------------------
# T-15-2: メタデータ取得（FR-02）
# ---------------------------------------------------------------------------


_SAMPLE_META = {
    "full_name": "tiangolo/fastapi",
    "pushed_at": "2024-01-15T10:00:00Z",
    "stargazers_count": 12345,
    "language": "Python",
    "topics": ["fastapi", "python", "api"],
    "license": {"spdx_id": "MIT"},
}


class TestFetchMeta:
    def test_fetch_meta_success(self):
        transport = _make_transport({"/repos/tiangolo/fastapi": (200, _SAMPLE_META)})
        with httpx.Client(transport=transport) as client:
            result = _fetch_meta("tiangolo", "fastapi", client)
        assert result["stargazers_count"] == 12345
        assert result["language"] == "Python"

    def test_fetch_meta_rate_limit_403(self):
        transport = _make_transport({"/repos/": (403, {"message": "Forbidden"})})
        with httpx.Client(transport=transport) as client:
            with pytest.raises(RateLimitError):
                _fetch_meta("owner", "repo", client)

    def test_fetch_meta_rate_limit_429(self):
        transport = _make_transport({"/repos/": (429, {"message": "Too Many Requests"})})
        with httpx.Client(transport=transport) as client:
            with pytest.raises(RateLimitError):
                _fetch_meta("owner", "repo", client)

    def test_fetch_meta_404(self):
        transport = _make_transport({"/repos/": (404, {"message": "Not Found"})})
        with httpx.Client(transport=transport) as client:
            with pytest.raises(FetchError):
                _fetch_meta("owner", "nonexistent", client)


# ---------------------------------------------------------------------------
# T-15-3: README 取得（FR-03）
# ---------------------------------------------------------------------------


class TestFetchReadme:
    def test_fetch_readme_success(self):
        content = base64.b64encode(b"# Hello World\nThis is a README.").decode()
        # GitHub API は改行で区切られた Base64 を返す
        chunked = "\n".join(content[i : i + 60] for i in range(0, len(content), 60))
        transport = _make_transport({"/readme": (200, {"content": chunked, "encoding": "base64"})})
        with httpx.Client(transport=transport) as client:
            result = _fetch_readme("owner", "repo", client)
        assert result == "# Hello World\nThis is a README."

    def test_fetch_readme_not_found(self):
        transport = _make_transport({"/readme": (404, {"message": "Not Found"})})
        with httpx.Client(transport=transport) as client:
            result = _fetch_readme("owner", "repo", client)
        assert result == ""


# ---------------------------------------------------------------------------
# T-15-4: LICENSE 取得（FR-04）
# ---------------------------------------------------------------------------


class TestFetchLicense:
    def test_fetch_license_success(self):
        body = {"license": {"spdx_id": "Apache-2.0"}}
        transport = _make_transport({"/license": (200, body)})
        with httpx.Client(transport=transport) as client:
            result = _fetch_license("owner", "repo", client)
        assert result == "Apache-2.0"

    def test_fetch_license_not_found(self):
        transport = _make_transport({"/license": (404, {"message": "Not Found"})})
        with httpx.Client(transport=transport) as client:
            result = _fetch_license("owner", "repo", client)
        assert result is None

    def test_fetch_license_noassertion(self):
        """SPDX が NOASSERTION の場合もそのまま返す。"""
        body = {"license": {"spdx_id": "NOASSERTION"}}
        transport = _make_transport({"/license": (200, body)})
        with httpx.Client(transport=transport) as client:
            result = _fetch_license("owner", "repo", client)
        assert result == "NOASSERTION"


# ---------------------------------------------------------------------------
# T-15-5: ファイル一覧取得（FR-05）
# ---------------------------------------------------------------------------


class TestFetchRootFiles:
    def test_fetch_root_files_success(self):
        body = [
            {"name": "README.md", "type": "file"},
            {"name": "pyproject.toml", "type": "file"},
            {"name": "src", "type": "dir"},
        ]
        transport = _make_transport({"/contents/": (200, body)})
        with httpx.Client(transport=transport) as client:
            result = _fetch_root_files("owner", "repo", client)
        assert result == ["README.md", "pyproject.toml", "src"]


# ---------------------------------------------------------------------------
# T-15-6: GITHUB_TOKEN ヘッダー（FR-06）
# ---------------------------------------------------------------------------


class TestGithubToken:
    def test_token_header_present(self, monkeypatch):
        """GITHUB_TOKEN があれば Authorization ヘッダーを付与する。"""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token-value")

        received_headers = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received_headers.update(dict(request.headers))
            url_str = str(request.url)
            if "/repos/" in url_str and "/readme" not in url_str and "/license" not in url_str and "/contents" not in url_str:
                return httpx.Response(200, json=_SAMPLE_META)
            if "/readme" in url_str:
                content = base64.b64encode(b"readme").decode()
                return httpx.Response(200, json={"content": content})
            if "/license" in url_str:
                return httpx.Response(200, json={"license": {"spdx_id": "MIT"}})
            if "/contents" in url_str:
                return httpx.Response(200, json=[{"name": "README.md"}])
            return httpx.Response(404, json={})

        with patch("repo_autopsy.fetch.httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = lambda url: handler(
                httpx.Request("GET", url, headers={"authorization": "Bearer test-token-value"})
            )
            # _build_headers を直接テスト
            from repo_autopsy.fetch import _build_headers
            headers = _build_headers()
        assert "Authorization" in headers
        assert "test-token-value" in headers["Authorization"]

    def test_no_token_no_auth_header(self, monkeypatch):
        """GITHUB_TOKEN がなければ Authorization ヘッダーを付与しない。"""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        from repo_autopsy.fetch import _build_headers
        headers = _build_headers()
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# T-15-7: fetch_repo 統合テスト
# ---------------------------------------------------------------------------


class TestFetchRepo:
    def _make_full_transport(self) -> httpx.MockTransport:
        readme_content = base64.b64encode(b"# FastAPI\nInstall: pip install fastapi").decode()

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.endswith("/repos/tiangolo/fastapi"):
                return httpx.Response(200, json=_SAMPLE_META)
            if "/readme" in url:
                return httpx.Response(200, json={"content": readme_content, "encoding": "base64"})
            if "/license" in url:
                return httpx.Response(200, json={"license": {"spdx_id": "MIT"}})
            if "/contents/" in url:
                return httpx.Response(200, json=[{"name": "README.md"}, {"name": "main.py"}])
            return httpx.Response(404, json={"message": "Not Found"})

        return httpx.MockTransport(handler)

    def test_fetch_repo_success(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        transport = self._make_full_transport()

        with patch("repo_autopsy.fetch.httpx.Client") as mock_cls:
            mock_ctx = mock_cls.return_value.__enter__.return_value

            def mock_get(url, **kwargs):
                req = httpx.Request("GET", url)
                return transport.handle_request(req)

            mock_ctx.get.side_effect = mock_get
            result = fetch_repo("https://github.com/tiangolo/fastapi")

        assert isinstance(result, RepoMeta)
        assert result.owner == "tiangolo"
        assert result.repo == "fastapi"
        assert result.stars == 12345
        assert result.language == "Python"
        assert result.license_spdx == "MIT"
        assert "README.md" in result.root_files

    def test_fetch_repo_invalid_url(self):
        with pytest.raises(InvalidURLError):
            fetch_repo("https://example.com/not-github")
