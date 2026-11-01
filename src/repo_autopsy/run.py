"""run.py — 手順の安全チェック・dry-run・一時ディレクトリでの実行・ログ記録。

FR-20〜28 を実装する。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Final

import typer

from .models import InstallStep, RunResult, SafetyIssue, StepResult

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

#: 子プロセスに渡す環境変数のホワイトリスト（FR-24）
ENV_ALLOWLIST: Final[frozenset[str]] = frozenset({"PATH", "HOME", "LANG", "TMPDIR", "TERM"})

#: 危険パターン（FR-21）。パターンは (正規表現, 日本語の理由) のタプルリスト。
_DANGER_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"\bsudo\b"), "sudo検出（管理者権限の要求）"),
    (re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f|rm\s+-[a-zA-Z]*f[a-zA-Z]*r"), "rm -rf検出（再帰削除）"),
    (re.compile(r"curl\b.*\|\s*(ba)?sh\b", re.DOTALL), "curl|bash検出（パイプ経由の任意コード実行）"),
    (re.compile(r"wget\b.*\|\s*(ba)?sh\b", re.DOTALL), "wget|sh検出（パイプ経由の任意コード実行）"),
    (re.compile(r"chmod\s+\+s"), "chmod +s検出（SUID設定）"),
    (re.compile(r"chown\s+root"), "chown root検出（root所有権変更）"),
    # 環境変数への API キー直書き（例: export KEY=sk-... / export ZRO_...=...）
    (re.compile(r"export\s+\w+\s*=\s*(sk-|ZRO_)\S+"), "APIキー直書き検出（秘密情報の露出）"),
    # chmod 777 も危険
    (re.compile(r"chmod\s+[0-9]*7[0-9]*7[0-9]*"), "chmod 777検出（過剰なパーミッション付与）"),
]

# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------


class DangerousCommandError(Exception):
    """FR-21: 危険なコマンドが検出された（実行はされない）。"""


class UserAbortError(Exception):
    """FR-22: ユーザーが確認プロンプトで実行を中断した。"""


# ---------------------------------------------------------------------------
# 純粋関数: 安全チェック（FR-21）
# ---------------------------------------------------------------------------


def check_safety(steps: list[InstallStep]) -> list[SafetyIssue]:
    """手順リストを検査し、危険なコマンドのリストを返す。

    純粋関数: IO なし、副作用なし。
    どんなコマンド文字列が来ても例外を投げない（ただし型エラーは除く）。

    Args:
        steps: インストール手順のリスト。

    Returns:
        検出された SafetyIssue のリスト（問題なければ空リスト）。
    """
    issues: list[SafetyIssue] = []
    for step in steps:
        for pattern, reason in _DANGER_PATTERNS:
            if pattern.search(step.cmd):
                issues.append(SafetyIssue(step=step.step, cmd=step.cmd, reason=reason))
                break  # 1コマンドにつき最初の検出理由だけ記録
    return issues


# ---------------------------------------------------------------------------
# 環境変数ユーティリティ（FR-24）
# ---------------------------------------------------------------------------


def _safe_env() -> dict[str, str]:
    """ENV_ALLOWLIST に含まれるキーのみを現在の環境変数から抽出して返す。

    OPENAI_API_KEY, ZRO_API_KEY, GITHUB_TOKEN などの秘密情報は除外される。
    """
    return {k: v for k, v in os.environ.items() if k in ENV_ALLOWLIST}


# ---------------------------------------------------------------------------
# 実行（FR-20〜28）
# ---------------------------------------------------------------------------


def execute_plan(
    steps: list[InstallStep],
    *,
    dry_run: bool = True,
    yes: bool = False,
    timeout: int = 600,
) -> RunResult:
    """インストール手順を実行する。

    Args:
        steps:    インストール手順のリスト。
        dry_run:  True のとき（既定）はコマンドを表示するだけで実行しない（FR-20）。
        yes:      True のとき確認プロンプトを省略する（FR-28、CI 用）。
                  ただし危険コマンドの検出は回避できない（FR-21）。
        timeout:  各コマンドのタイムアウト秒数（既定 600 秒、FR-25）。

    Returns:
        RunResult（dry_run / 実行結果 / 安全問題を含む）。

    Raises:
        UserAbortError: `yes=False` の状態でユーザーが確認プロンプトを拒否した場合。
    """
    # --- 安全チェック（FR-21）: dry_run / yes に関わらず必ず実行 ---
    safety_issues = check_safety(steps)

    # 危険なステップを除外した安全なステップだけ実行対象にする
    dangerous_step_nums = {issue.step for issue in safety_issues}
    safe_steps = [s for s in steps if s.step not in dangerous_step_nums]

    # 安全問題を表示
    if safety_issues:
        typer.echo("⚠️  危険なコマンドを検出しました。該当ステップは実行しません。")
        for issue in safety_issues:
            typer.echo(f"   ステップ {issue.step}: {issue.cmd!r} → {issue.reason}", err=True)

    # --- dry-run（FR-20）---
    if dry_run:
        typer.echo("\n[dry-run] 以下のコマンドを実行する予定です（実行はしません）:")
        for step in steps:
            marker = "🚫" if step.step in dangerous_step_nums else "  "
            typer.echo(f"  {marker} [{step.step}] {step.cmd}")
        if not steps:
            typer.echo("  （実行する手順がありません）")
        return RunResult(dry_run=True, safety_issues=safety_issues)

    # --- 確認プロンプト（FR-22）: --run 指定時かつ --yes なし ---
    if not yes:
        typer.echo("\n以下のコマンドを一時ディレクトリで実行します:")
        for step in safe_steps:
            typer.echo(f"  [{step.step}] {step.cmd}")
        if not safe_steps:
            typer.echo("  （実行可能な手順がありません）")
            return RunResult(dry_run=False, safety_issues=safety_issues)

        answer = typer.prompt("続行しますか？ [y/N]", default="N")
        if answer.strip().lower() != "y":
            raise UserAbortError("ユーザーが実行を中止しました。")

    if not safe_steps:
        typer.echo("実行可能な手順がありません（すべて危険なコマンドのためスキップ）。")
        return RunResult(dry_run=False, safety_issues=safety_issues)

    # --- 一時ディレクトリの作成（FR-23）---
    work_dir = tempfile.mkdtemp(prefix="repo_autopsy_")
    step_results: list[StepResult] = []
    env = _safe_env()

    try:
        for step in safe_steps:
            typer.echo(f"[run] ステップ {step.step}: {step.cmd}")
            start = time.monotonic()
            timed_out = False
            exit_code: int | None = None
            stdout_str = ""
            stderr_str = ""

            try:
                proc = subprocess.run(
                    step.cmd,
                    shell=True,  # noqa: S602 — shell=True は意図的（インストール手順を実行するため）
                    capture_output=True,
                    text=True,
                    cwd=work_dir,
                    env=env,
                    timeout=timeout,
                )
                exit_code = proc.returncode
                stdout_str = proc.stdout
                stderr_str = proc.stderr
            except subprocess.TimeoutExpired as e:
                timed_out = True
                stdout_str = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr_str = (e.stderr or b"").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
                typer.echo(f"[run] ⏰ タイムアウト ({timeout}秒) — ステップ {step.step}", err=True)

            elapsed = time.monotonic() - start

            result = StepResult(
                step=step.step,
                cmd=step.cmd,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                elapsed_sec=elapsed,
                timed_out=timed_out,
            )
            step_results.append(result)

            status = "⏰タイムアウト" if timed_out else ("✅成功" if exit_code == 0 else f"❌失敗(exit={exit_code})")
            typer.echo(f"[run]   → {status}  ({elapsed:.1f}秒)")

    finally:
        # 一時ディレクトリを削除（FR-23）
        shutil.rmtree(work_dir, ignore_errors=True)

    # --- サマリー作成（FR-27）---
    total = len(step_results)
    succeeded = sum(1 for r in step_results if r.exit_code == 0 and not r.timed_out)
    summary = f"{succeeded}/{total} ステップ成功"

    return RunResult(
        dry_run=False,
        safety_issues=safety_issues,
        steps=step_results,
        summary=summary,
        work_dir=None,  # 削除済みなので None
    )
