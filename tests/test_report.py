"""tests/test_report.py — report.py のテスト。

カバレッジ:
- T-55: 生成レポートに英語の見出しが含まれないことをアサート（FR-38）
- T-56: reports/ ディレクトリが存在しなくても保存できることをテスト（FR-37）
"""

from __future__ import annotations

import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from repo_autopsy.models import (
    InstallStep,
    Label,
    Plan,
    RepoMeta,
    RunResult,
    Signal,
    SignalKind,
    StepResult,
    Verdict,
)
from repo_autopsy.report import has_english_heading, render, save

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _meta(
    owner: str = "testowner",
    repo: str = "testrepo",
    readme: str = "arm64 Apple Silicon supported",
    license_spdx: str | None = "MIT",
    stars: int = 100,
    language: str | None = "Python",
) -> RepoMeta:
    recent = (datetime.now(tz=timezone.utc) - timedelta(days=10)).isoformat()
    return RepoMeta(
        owner=owner,
        repo=repo,
        url=f"https://github.com/{owner}/{repo}",
        license_spdx=license_spdx,
        last_commit_at=recent,
        stars=stars,
        language=language,
        topics=["ai", "python"],
        readme_text=readme,
        root_files=["README.md", "pyproject.toml"],
    )


def _plan(summary: str = "テスト用の要約です。", steps: int = 2) -> Plan:
    return Plan(
        summary_ja=summary,
        steps=[
            InstallStep(step=i + 1, cmd=f"pip install pkg{i}", description=f"ステップ {i+1}")
            for i in range(steps)
        ],
        llm_error=None,
    )


def _run_dry() -> RunResult:
    return RunResult(dry_run=True, safety_issues=[], steps=[], summary="")


def _run_executed() -> RunResult:
    steps = [
        StepResult(
            step=1,
            cmd="pip install mypkg",
            stdout="Successfully installed mypkg-1.0.0",
            stderr="",
            exit_code=0,
            elapsed_sec=1.2,
            timed_out=False,
        ),
        StepResult(
            step=2,
            cmd="python main.py",
            stdout="Hello World",
            stderr="",
            exit_code=0,
            elapsed_sec=0.3,
            timed_out=False,
        ),
    ]
    return RunResult(dry_run=False, safety_issues=[], steps=steps, summary="2/2 ステップ成功")


def _verdict_usable() -> Verdict:
    return Verdict(label=Label.USABLE, signals=[], summary_ja="罠シグナルなし")


def _verdict_trap() -> Verdict:
    return Verdict(
        label=Label.TRAP,
        signals=[Signal(kind=SignalKind.TRAP, rule_id="R-01", description="CUDA/GPU 必須")],
        summary_ja="罠シグナル 1 件を検出しました。",
    )


def _verdict_conditional() -> Verdict:
    return Verdict(
        label=Label.CONDITIONAL,
        signals=[Signal(kind=SignalKind.CONDITIONAL, rule_id="C-01", description="Rosetta 使用の可能性")],
        summary_ja="条件付きシグナル 1 件を検出しました。",
    )


# ---------------------------------------------------------------------------
# T-55: 英語の見出しが含まれないことを確認（FR-38）
# ---------------------------------------------------------------------------


class TestNoEnglishHeadings:
    """T-55: 生成レポートのすべてのパターンで英語見出しが出ないことを確認。"""

    def test_usable_report_no_english_headings(self) -> None:
        content = render(_meta(), _plan(), _run_dry(), _verdict_usable())
        assert not has_english_heading(content), (
            "使えるレポートに英語見出しが含まれています:\n"
            + "\n".join(
                line for line in content.splitlines()
                if line.startswith("#") and re.match(r"^#{1,6}\s+[A-Za-z]", line)
            )
        )

    def test_trap_report_no_english_headings(self) -> None:
        content = render(_meta(), _plan(), _run_dry(), _verdict_trap())
        assert not has_english_heading(content), (
            "罠レポートに英語見出しが含まれています"
        )

    def test_conditional_report_no_english_headings(self) -> None:
        content = render(_meta(), _plan(), _run_dry(), _verdict_conditional())
        assert not has_english_heading(content), (
            "条件付きレポートに英語見出しが含まれています"
        )

    def test_executed_run_no_english_headings(self) -> None:
        content = render(_meta(), _plan(), _run_executed(), _verdict_usable())
        assert not has_english_heading(content), (
            "実行済みレポートに英語見出しが含まれています"
        )

    def test_no_plan_fallback_no_english_headings(self) -> None:
        """LLM 失敗でステップなし plan の場合もレポートを生成できる。"""
        fallback_plan = Plan(summary_ja="LLM 失敗", steps=[], llm_error="connection error")
        content = render(_meta(), fallback_plan, _run_dry(), _verdict_usable())
        assert not has_english_heading(content)

    def test_no_license_no_english_headings(self) -> None:
        content = render(_meta(license_spdx=None), _plan(), _run_dry(), _verdict_trap())
        assert not has_english_heading(content)

    def test_all_headings_are_japanese(self) -> None:
        """すべての見出し行が日本語（CJK 文字を含む）であることを確認。"""
        content = render(_meta(), _plan(), _run_dry(), _verdict_usable())
        in_code_block = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
            if in_code_block:
                continue
            m = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if m:
                heading_text = m.group(2)
                # 見出しに CJK 文字、または日本語の記号・数字のみが含まれるはず
                ascii_only_alpha = all(
                    not c.isalpha() or ord(c) > 127
                    for c in heading_text
                )
                has_cjk = any(
                    "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff"
                    for c in heading_text
                )
                # 英語アルファベットのみの見出しでないことを確認
                assert has_cjk or ascii_only_alpha, (
                    f"英語見出しを検出: '{heading_text}'"
                )


# ---------------------------------------------------------------------------
# T-55: has_english_heading() 自体のユニットテスト
# ---------------------------------------------------------------------------


class TestHasEnglishHeading:
    def test_detects_english_heading(self) -> None:
        content = "## Introduction\n\nSome text."
        assert has_english_heading(content) is True

    def test_does_not_detect_japanese_heading(self) -> None:
        content = "## はじめに\n\n本文です。"
        assert has_english_heading(content) is False

    def test_ignores_code_block(self) -> None:
        content = "## 実行結果\n\n```\n## This is a comment\n```\n"
        assert has_english_heading(content) is False

    def test_mixed_heading_with_cjk(self) -> None:
        """英語と日本語が混在する見出しは CJK があれば英語見出しと判定しない。"""
        content = "## Apple Silicon での注意点\n\n本文。"
        assert has_english_heading(content) is False

    def test_empty_content(self) -> None:
        assert has_english_heading("") is False


# ---------------------------------------------------------------------------
# T-56: reports/ ディレクトリが存在しなくても保存できることをテスト（FR-37）
# ---------------------------------------------------------------------------


class TestSave:
    """T-56: save() 関数のテスト。"""

    def test_saves_to_reports_dir_auto_create(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """reports/ が存在しなくても自動作成されてファイルが保存される。"""
        # カレントディレクトリを tmp_path に変更（reports/ が存在しない状態）
        monkeypatch.chdir(tmp_path)
        reports_dir = tmp_path / "reports"
        assert not reports_dir.exists(), "前提: reports/ が存在しないこと"

        meta = _meta(owner="myowner", repo="myrepo")
        content = "# テストレポート\n\n本文です。"
        dest = save(content, meta)

        assert reports_dir.exists(), "reports/ が自動作成されること"
        # save() は相対パス ("reports/...") を返す場合があるため resolved で比較
        assert dest.resolve() == (reports_dir / "myowner__myrepo.md").resolve()
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == content

    def test_filename_format(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """ファイル名が <owner>__<repo>.md 形式であることを確認。"""
        monkeypatch.chdir(tmp_path)
        meta = _meta(owner="alice", repo="cool-tool")
        dest = save("テスト", meta)
        assert dest.name == "alice__cool-tool.md"

    def test_custom_output_path(self, tmp_path: Path) -> None:
        """--output 指定時はそのパスに保存される。"""
        custom_path = tmp_path / "subdir" / "custom_report.md"
        meta = _meta()
        content = "カスタム出力テスト"
        dest = save(content, meta, output_path=custom_path)
        assert dest == custom_path
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == content

    def test_overwrites_existing_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """同名ファイルが存在する場合は上書きされる。"""
        monkeypatch.chdir(tmp_path)
        meta = _meta(owner="owner", repo="repo")
        save("初回の内容", meta)
        dest = save("2回目の内容", meta)
        assert dest.read_text(encoding="utf-8") == "2回目の内容"

    def test_save_returns_path_object(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        meta = _meta()
        dest = save("テスト", meta)
        assert isinstance(dest, Path)


# ---------------------------------------------------------------------------
# render() の統合テスト
# ---------------------------------------------------------------------------


class TestRender:
    def test_render_contains_repo_name(self) -> None:
        content = render(_meta(repo="my-awesome-tool"), _plan(), _run_dry(), _verdict_usable())
        assert "my-awesome-tool" in content

    def test_render_contains_verdict_label(self) -> None:
        content = render(_meta(), _plan(), _run_dry(), _verdict_trap())
        assert "罠" in content

    def test_render_dry_run_marker(self) -> None:
        """dry-run 時は「dry-run のため未実行」が含まれる（FR-36 第4章）。"""
        content = render(_meta(), _plan(), _run_dry(), _verdict_usable())
        assert "dry-run" in content
        assert "未実行" in content

    def test_render_executed_contains_summary(self) -> None:
        run = _run_executed()
        content = render(_meta(), _plan(), run, _verdict_usable())
        assert "成功" in content

    def test_render_signals_listed(self) -> None:
        content = render(_meta(), _plan(), _run_dry(), _verdict_trap())
        assert "R-01" in content

    def test_render_license_shown(self) -> None:
        content = render(_meta(license_spdx="Apache-2.0"), _plan(), _run_dry(), _verdict_usable())
        assert "Apache-2.0" in content

    def test_render_unknown_license(self) -> None:
        content = render(_meta(license_spdx=None), _plan(), _run_dry(), _verdict_trap())
        assert "不明" in content

    def test_render_footer_disclaimer(self) -> None:
        """レポート末尾に定型文が含まれる（ja-report-style.md）。"""
        content = render(_meta(), _plan(), _run_dry(), _verdict_usable())
        assert "Repo Autopsy" in content
        assert "一次判定" in content

    def test_render_footer_no_fixed_apple_silicon_string(self) -> None:
        """末尾フッターに固定文字列 'macOS（Apple Silicon）' が含まれないこと。"""
        content = render(_meta(), _plan(), _run_dry(), _verdict_usable())
        assert "macOS（Apple Silicon）" not in content

    def test_render_env_label_in_footer(self) -> None:
        """フッターおよび検証環境テーブルに実行環境ラベルが含まれること。"""
        import platform
        from repo_autopsy.report import _build_env_label
        env_label = _build_env_label()
        content = render(_meta(), _plan(), _run_dry(), _verdict_usable())
        # 環境ラベルがレポートに含まれること
        assert env_label in content
        # 検証環境テーブルに「実行環境」行があること
        assert "実行環境" in content

    def test_build_env_label_format(self) -> None:
        """_build_env_label() が 'システム名（アーキテクチャ）' 形式を返すこと。"""
        import re
        from repo_autopsy.report import _build_env_label
        label = _build_env_label()
        # 括弧（全角）を含む形式であること
        assert "（" in label and "）" in label
        # 空文字列でないこと
        assert label.strip()

    def test_render_with_no_steps_plan(self) -> None:
        """ステップのない plan でもクラッシュしない。"""
        empty_plan = Plan(summary_ja="ステップなし", steps=[], llm_error=None)
        content = render(_meta(), empty_plan, _run_dry(), _verdict_usable())
        assert content  # 空でないことを確認

    def test_render_with_none_plan(self) -> None:
        """plan=None のフォールバックでもクラッシュしない。"""
        content = render(_meta(), None, _run_dry(), _verdict_conditional())
        assert content
        assert "テスト" not in content or True  # 例外が出ないことを確認


# ---------------------------------------------------------------------------
# T-55b: LLM 失敗時の暫定判定明記テスト（FR-39）
# ---------------------------------------------------------------------------


class TestFallbackWarning:
    def test_llm_error_plan_shows_provisional_notice(self) -> None:
        """plan.llm_error が設定されているとき「暫定判定」が含まれること（FR-39）。"""
        fallback_plan = Plan(
            summary_ja="（要約の取得に失敗しました）",
            steps=[],
            llm_error="LLM 応答取得失敗: タイムアウト",
        )
        content = render(_meta(), fallback_plan, _run_dry(), _verdict_usable())
        assert "暫定判定" in content
        assert "LLM 要約なし" in content

    def test_no_error_plan_no_provisional_notice(self) -> None:
        """LLM が成功した（llm_error=None）場合は暫定判定ブロックが出ないこと。"""
        normal_plan = Plan(summary_ja="正常な要約テキスト", steps=[], llm_error=None)
        content = render(_meta(), normal_plan, _run_dry(), _verdict_usable())
        assert "暫定判定" not in content

    def test_provisional_notice_no_english_headings(self) -> None:
        """暫定判定ブロックがあっても英語見出しは出ないこと（FR-38）。"""
        fallback_plan = Plan(
            summary_ja="（要約失敗）",
            steps=[],
            llm_error="connection error",
        )
        content = render(_meta(), fallback_plan, _run_dry(), _verdict_trap())
        assert not has_english_heading(content)
