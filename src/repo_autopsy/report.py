"""report.py — Jinja2 テンプレートを使って日本語 Markdown レポートを生成・保存する。

公開 API:
    render(meta, plan, run_result, verdict) -> str
    save(content, meta, output_path=None) -> Path
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import Plan, RepoMeta, RunResult, Verdict

# テンプレートディレクトリの解決順:
#   1. プロジェクトルート直下の templates/
#   2. このファイルの親ディレクトリから 2 段上がった templates/（パッケージ内実行）
_TEMPLATE_DIRS: list[str] = [
    str(Path(__file__).parent.parent.parent / "templates"),  # repo root
    str(Path(__file__).parent / "templates"),                # src/repo_autopsy/templates（将来用）
]


def _build_env() -> Environment:
    """Jinja2 Environment を構築する。テンプレートは _TEMPLATE_DIRS から検索。"""
    existing_dirs = [d for d in _TEMPLATE_DIRS if Path(d).is_dir()]
    if not existing_dirs:
        # フォールバック: カレントディレクトリの templates/
        existing_dirs = ["templates"]
    return Environment(
        loader=FileSystemLoader(existing_dirs),
        autoescape=select_autoescape(disabled_extensions=["j2", "md", "md.j2"]),
        keep_trailing_newline=True,
    )


def render(
    meta: RepoMeta,
    plan: Plan | None,
    run_result: RunResult,
    verdict: Verdict,
) -> str:
    """Jinja2 テンプレートを使ってレポートの Markdown 文字列を生成する（FR-36）。

    LLM が失敗して plan が None または llm_error を持つ場合も、
    取得できた情報だけで「判定保留的な一次判定」レポートを生成する（フォールバック）。

    Args:
        meta:       GitHub リポジトリのメタデータ。
        plan:       LLM が生成した計画。LLM 失敗時は None または llm_error あり。
        run_result: 実行結果（dry-run の場合は steps が空）。
        verdict:    judge.decide() の出力。

    Returns:
        Markdown 形式のレポート文字列。
    """
    env = _build_env()
    template = env.get_template("report.md.j2")

    generated_at = datetime.now(tz=timezone.utc).isoformat()

    content = template.render(
        meta=meta,
        plan=plan,
        run_result=run_result,
        verdict=verdict,
        generated_at=generated_at,
    )
    return content


def save(
    content: str,
    meta: RepoMeta,
    output_path: str | Path | None = None,
) -> Path:
    """レポートを保存する（FR-37）。

    Args:
        content:     render() が返した Markdown 文字列。
        meta:        GitHub リポジトリのメタデータ（ファイル名に使用）。
        output_path: 保存先ファイルパス。None の場合は reports/<owner>__<repo>.md。

    Returns:
        保存したファイルの Path。
    """
    if output_path is not None:
        dest = Path(output_path)
    else:
        # FR-37: reports/<owner>__<repo>.md
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{meta.owner}__{meta.repo}.md"
        dest = reports_dir / filename

    # 親ディレクトリが存在しない場合は作成
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# 検証ヘルパー（テスト・CI 用）
# ---------------------------------------------------------------------------


def has_english_heading(content: str) -> bool:
    """レポートに英語の見出しが含まれているか検査する（FR-38 検証用）。

    コードブロック内の行は除外する。

    Args:
        content: レポートの Markdown 文字列。

    Returns:
        英語見出しが含まれていれば True。
    """
    in_code_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
        if in_code_block:
            continue
        # 見出し行 (#, ##, ###, ...) を検出
        m = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if m:
            heading_text = m.group(1)
            # 英語の見出し: ASCII 文字が 50% 超 かつ CJK が 0 文字
            ascii_count = sum(1 for c in heading_text if ord(c) < 128 and c.isalpha())
            cjk_count = sum(1 for c in heading_text if "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff")
            if ascii_count > 0 and cjk_count == 0 and len(heading_text) > 2:
                return True
    return False
