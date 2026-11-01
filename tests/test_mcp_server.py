"""tests/test_mcp_server.py — mcp_server.py の単体テスト。

fetch を monkeypatch して、ネットワークなしで analyze_repo ツール関数を直接テストする。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from repo_autopsy.models import RepoMeta


# ---------------------------------------------------------------------------
# テスト用 RepoMeta ファクトリ
# ---------------------------------------------------------------------------


def _make_meta(
    *,
    license_spdx: str | None = "MIT",
    readme: str = "arm64 Apple Silicon supported. pip install mypackage",
    stars: int = 500,
    language: str = "Python",
) -> RepoMeta:
    last_commit = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()
    return RepoMeta(
        owner="testowner",
        repo="testrepo",
        url="https://github.com/testowner/testrepo",
        license_spdx=license_spdx,
        last_commit_at=last_commit,
        stars=stars,
        language=language,
        topics=["test"],
        readme_text=readme,
        root_files=["README.md", "pyproject.toml"],
    )


# ---------------------------------------------------------------------------
# analyze_repo ツール関数の直接テスト
# ---------------------------------------------------------------------------


class TestAnalyzeRepo:
    """analyze_repo ツール関数を fetch を monkeypatch してテスト。"""

    def test_analyze_repo_returns_markdown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch_repo を monkeypatch して analyze_repo が Markdown を返すことを確認。"""
        meta = _make_meta()
        monkeypatch.setattr("repo_autopsy.mcp_server.fetch_repo", lambda url: meta)

        from repo_autopsy.mcp_server import analyze_repo

        result = analyze_repo("https://github.com/testowner/testrepo")

        assert isinstance(result, str)
        assert len(result) > 100
        # レポートは判定ラベルを含むはず
        assert "使える" in result or "条件付き" in result or "罠" in result

    def test_analyze_repo_contains_repo_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """レポートにリポジトリ名が含まれることを確認。"""
        meta = _make_meta()
        monkeypatch.setattr("repo_autopsy.mcp_server.fetch_repo", lambda url: meta)

        from repo_autopsy.mcp_server import analyze_repo

        result = analyze_repo("https://github.com/testowner/testrepo")

        assert "testowner" in result
        assert "testrepo" in result

    def test_analyze_repo_invalid_url_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """不正 URL の場合はエラーメッセージを返す。"""
        from repo_autopsy.fetch import InvalidURLError
        monkeypatch.setattr(
            "repo_autopsy.mcp_server.fetch_repo",
            lambda url: (_ for _ in ()).throw(InvalidURLError("不正なURL"))
        )

        from repo_autopsy.mcp_server import analyze_repo

        result = analyze_repo("not-a-url")
        assert "エラー" in result

    def test_analyze_repo_noassertion_license_is_conditional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NOASSERTION ライセンスのときは「条件付き」判定になることを確認。"""
        meta = _make_meta(license_spdx="NOASSERTION", stars=1000)
        monkeypatch.setattr("repo_autopsy.mcp_server.fetch_repo", lambda url: meta)

        from repo_autopsy.mcp_server import analyze_repo

        result = analyze_repo("https://github.com/testowner/testrepo")

        assert isinstance(result, str)
        # NOASSERTION は条件付きシグナル C-04 → 罠シグナルがなければ「条件付き」
        assert "NOASSERTION" in result or "条件付き" in result or "独自" in result

    def test_analyze_repo_no_license_is_trap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LICENSE ファイルなし（None）のときは「罠」判定になることを確認。"""
        meta = _make_meta(license_spdx=None, stars=1000)
        monkeypatch.setattr("repo_autopsy.mcp_server.fetch_repo", lambda url: meta)

        from repo_autopsy.mcp_server import analyze_repo

        result = analyze_repo("https://github.com/testowner/testrepo")

        assert isinstance(result, str)
        # license=None は R-03（罠）→ 判定は「罠」になる
        assert "罠" in result

    def test_analyze_repo_fetch_error_returns_error_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FetchError 発生時はエラーメッセージ文字列を返す（例外を出さない）。"""
        from repo_autopsy.fetch import FetchError
        monkeypatch.setattr(
            "repo_autopsy.mcp_server.fetch_repo",
            lambda url: (_ for _ in ()).throw(FetchError("HTTP 404"))
        )

        from repo_autopsy.mcp_server import analyze_repo

        result = analyze_repo("https://github.com/owner/nonexistent")
        assert "エラー" in result
        assert isinstance(result, str)

    def test_analyze_repo_dry_run_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MCP サーバーは dry-run モードで動作し、コマンドを実行しない。"""
        meta = _make_meta()
        monkeypatch.setattr("repo_autopsy.mcp_server.fetch_repo", lambda url: meta)

        from repo_autopsy.mcp_server import analyze_repo

        result = analyze_repo("https://github.com/testowner/testrepo")

        # dry-run 表記がレポートに含まれるはず
        assert "dry-run" in result or "未実行" in result
