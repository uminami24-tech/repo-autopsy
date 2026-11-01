"""mcp_server.py — Repo Autopsy の MCP サーバー。

公式 mcp パッケージ（mcp 2.x / MCPServer）を使い、
Kiro チャットから `analyze_repo` ツールを呼べるようにする。

ツール:
    analyze_repo(url: str) -> str
        GitHub リポジトリの URL を受け取り、fetch → judge → report を
        dry-run で実行して日本語レポート Markdown を返す。

起動方法:
    uv run autopsy-mcp          # stdio モード（Kiro MCP 接続用）
    uv run python -m repo_autopsy.mcp_server  # 直接起動
"""

from __future__ import annotations

import asyncio

from mcp.server.mcpserver import MCPServer

from .fetch import FetchError, InvalidURLError, fetch_repo
from .judge import decide, run_rules
from .models import Plan, RunResult
from .report import render

# MCPServer インスタンスを作成
mcp = MCPServer(
    name="autopsy",
    description="公開 GitHub リポジトリを解析し、日本語の検証レポートを返す",
    version="0.1.0",
)


@mcp.tool()
def analyze_repo(url: str) -> str:
    """GitHub リポジトリの URL を解析し、日本語レポート Markdown を返す。

    Args:
        url: https://github.com/<owner>/<repo> 形式の GitHub URL

    Returns:
        日本語 Markdown 形式のレポート文字列。
        エラー時はエラーメッセージを含む文字列を返す。
    """
    # 1. fetch（ネットワーク必要。テスト時は monkeypatch する）
    try:
        meta = fetch_repo(url)
    except InvalidURLError as e:
        return f"エラー: URL の形式が不正です。\n{e}"
    except FetchError as e:
        return f"エラー: GitHub API の取得に失敗しました。\n{e}"
    except Exception as e:  # noqa: BLE001
        return f"エラー: fetch ステージで予期せぬエラーが発生しました。\n{e}"

    # 2. plan は省略（MCP ツールでは LLM 二重呼び出しを避ける）
    plan = Plan(
        summary_ja="（MCP モードでは LLM 要約を省略しています。autopsy CLI では要約を取得できます）",
        steps=[],
        llm_error=None,
    )

    # 3. dry-run（コマンドは実行しない）
    run_result = RunResult(dry_run=True, safety_issues=[], steps=[], summary="MCP dry-run")

    # 4. judge
    signals = run_rules(meta, run_result)
    verdict = decide(signals)

    # 5. report（ファイル保存はしない。文字列だけ返す）
    try:
        content = render(meta, plan, run_result, verdict)
    except Exception as e:  # noqa: BLE001
        return f"エラー: レポート生成に失敗しました。\n{e}"

    return content


def main() -> None:
    """エントリポイント: stdio モードで MCP サーバーを起動する。"""
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
