"""CLI エントリポイント（Typer）。

引数解析と各段の呼び出しのみ。ビジネスロジックは持たない。

パイプライン:
    fetch → plan → run（既定 dry-run / --run 時のみ実行）→ judge → report
"""

from __future__ import annotations

from pathlib import Path

import typer

from .fetch import FetchError, InvalidURLError, RateLimitError, fetch_repo
from .judge import decide, run_rules
from .models import Plan, RunResult
from .plan import build_plan
from .report import render, save
from .run import UserAbortError, execute_plan

app = typer.Typer(
    name="autopsy",
    help="公開 GitHub リポジトリの URL から日本語の Mac 向け検証レポートを自動生成します。",
    no_args_is_help=True,
)


def _format_license(spdx: str | None) -> str:
    """ライセンス識別子を表示用文字列に変換する。"""
    if spdx is None:
        return "ライセンス不明（LICENSE ファイルなし）"
    if spdx == "NOASSERTION":
        return "独自/判別不能（NOASSERTION）。LICENSE 本文を確認してください"
    return spdx


@app.command()
def main(
    url: str = typer.Argument(..., help="検証する GitHub リポジトリの URL"),
    run: bool = typer.Option(False, "--run", help="コマンドを実際に実行する（既定は dry-run）"),
    yes: bool = typer.Option(False, "--yes", "-y", help="確認プロンプトを省略して自動承認（CI 用）"),
    timeout: int = typer.Option(600, "--timeout", help="各コマンドのタイムアウト秒数（既定 600 秒）"),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="レポートの出力先ファイルパス（既定: reports/<owner>__<repo>.md）",
    ),
) -> None:
    """GitHub リポジトリを解析し、日本語レポートを生成します。"""

    # ── 1. fetch ─────────────────────────────────────────────────────────────
    typer.echo(f"[fetch] {url} を解析中...")
    try:
        meta = fetch_repo(url)
    except InvalidURLError as e:
        typer.echo(f"エラー: {e}", err=True)
        raise typer.Exit(code=1)
    except RateLimitError as e:
        typer.echo(f"レート制限エラー: {e}", err=True)
        raise typer.Exit(code=1)
    except FetchError as e:
        typer.echo(f"取得エラー: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"[fetch] {meta.full_name} ★{meta.stars} ({meta.language}) 取得完了")
    typer.echo(f"[fetch] ライセンス: {_format_license(meta.license_spdx)}")
    typer.echo(f"[fetch] 最終コミット: {meta.last_commit_at}")

    # ── 2. plan（LLM）──────────────────────────────────────────────────────
    typer.echo("[plan] LLM で要約・手順を生成中...")
    plan: Plan | None = None
    try:
        plan = build_plan(meta.readme_text)
        if plan.llm_error:
            typer.echo(f"[plan] ⚠️  LLM エラー: {plan.llm_error}", err=True)
            typer.echo("[plan] フォールバック: 取得済みメタデータのみでレポートを生成します。")
        else:
            typer.echo(f"[plan] 要約: {plan.summary_ja}")
            typer.echo(f"[plan] インストール手順: {len(plan.steps)} ステップ")
    except Exception as e:  # noqa: BLE001
        typer.echo(f"[plan] ⚠️  plan ステージで予期せぬエラーが発生しました: {e}", err=True)
        typer.echo("[plan] フォールバック: 取得済みメタデータのみでレポートを生成します。")
        # フォールバック plan（空）を作成
        plan = Plan(
            summary_ja="（LLM による要約を取得できませんでした）",
            steps=[],
            llm_error=str(e),
        )

    # ── 3. run（既定 dry-run / --run 指定時のみ実行）────────────────────────
    steps = plan.steps if plan else []
    run_result: RunResult
    try:
        run_result = execute_plan(
            steps,
            dry_run=not run,
            yes=yes,
            timeout=timeout,
        )
    except UserAbortError as e:
        typer.echo(f"\n中止: {e}")
        raise typer.Exit(code=0)
    except Exception as e:  # noqa: BLE001
        typer.echo(f"[run] ⚠️  実行ステージでエラーが発生しました: {e}", err=True)
        run_result = RunResult(dry_run=not run, safety_issues=[], steps=[], summary="実行エラー")

    if not run_result.dry_run and run_result.summary:
        typer.echo(f"\n[run] 実行完了: {run_result.summary}")

    # ── 4. judge ─────────────────────────────────────────────────────────────
    typer.echo("[judge] ルールベース判定を実行中...")
    try:
        signals = run_rules(meta, run_result)
        verdict = decide(signals)
    except Exception as e:  # noqa: BLE001
        # judge は純粋関数なので例外が出るはずだが、念のためフォールバック
        typer.echo(f"[judge] ⚠️  判定エラー: {e}", err=True)
        from .models import Label, Verdict
        verdict = Verdict(
            label=Label.CONDITIONAL,
            signals=[],
            summary_ja=f"判定エラーのためフォールバック（条件付き）: {e}",
        )

    typer.echo(f"[judge] 判定: {verdict.label.value}（シグナル {len(verdict.signals)} 件）")
    for sig in verdict.signals:
        typer.echo(f"[judge]   {sig.rule_id} [{sig.kind.value}] {sig.description}")

    # ── 5. report ────────────────────────────────────────────────────────────
    typer.echo("[report] レポートを生成中...")
    try:
        content = render(meta, plan, run_result, verdict)
        output_path: Path | None = Path(output) if output else None
        dest = save(content, meta, output_path)
        typer.echo(f"[report] ✅ レポートを保存しました: {dest}")
    except Exception as e:  # noqa: BLE001
        typer.echo(f"[report] ❌ レポートの生成・保存に失敗しました: {e}", err=True)
        raise typer.Exit(code=1)

    # ── 最終サマリー ──────────────────────────────────────────────────────────
    typer.echo("")
    typer.echo("=" * 60)
    typer.echo(f"  リポジトリ : {meta.full_name}")
    typer.echo(f"  判定       : {verdict.label.value}（一次判定）")
    typer.echo(f"  レポート   : {dest}")
    typer.echo("=" * 60)
