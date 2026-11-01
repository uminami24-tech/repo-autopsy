"""LLM で README の日本語要約とインストール手順 JSON を生成するモジュール。

公開 API:
    build_plan(readme_text: str) -> Plan

モジュール境界ルール:
    - llm.py 経由の LLM 呼び出しのみ。ファイル書き込み・HTTP は行わない。
    - 要約と手順抽出は 1 回の LLM 呼び出しで取得し、待ち時間を最小化する（FR-08/09）。
"""

from __future__ import annotations

import json
import logging

from .llm import LLMError, chat
from .models import InstallStep, Plan

logger = logging.getLogger(__name__)

# README の先頭何文字までを LLM に渡すか（トークン節約）
_README_MAX_CHARS = 12000

# リトライ最大回数（初回 + 最大 1 回 = 最大 2 回試行）
_MAX_RETRIES = 1


# ---------------------------------------------------------------------------
# プロンプト生成（T-11, T-12）
# ---------------------------------------------------------------------------


def _prompt_combined(readme_text: str) -> str:
    """要約と手順抽出を 1 回で行う統合プロンプトを組み立てる（FR-08/09）。

    - README は先頭 12,000 文字に切り詰める
    - 応答は JSON オブジェクト 1 個のみ（前置き・コードブロック記号不要）
    """
    truncated = readme_text[:_README_MAX_CHARS] if len(readme_text) > _README_MAX_CHARS else readme_text
    return (
        "以下の README を読み、次の JSON 形式のみを出力してください。\n"
        "前置き・説明・コードブロック記号（```）は一切不要です。JSON オブジェクト 1 個だけを返してください。\n\n"
        "形式:\n"
        '{"summary": "<200字以内の日本語要約>", "steps": [{"step": 1, "cmd": "...", "description": "..."}, ...]}\n\n'
        "コマンドが見つからない場合は steps を空配列 [] にしてください。\n\n"
        f"---README---\n{truncated}\n---END---"
    )


# ---------------------------------------------------------------------------
# レガシー互換（test_plan.py が直接インポートしているため残す）
# ---------------------------------------------------------------------------


def _prompt_summary(readme_text: str) -> str:
    """README の日本語要約プロンプト（後方互換用）。"""
    truncated = readme_text[:_README_MAX_CHARS] if len(readme_text) > _README_MAX_CHARS else readme_text
    return (
        "以下の README テキストを読み、200 字以内の日本語で要約してください。\n"
        "要約のみを出力し、前置き・説明・装飾は不要です。\n\n"
        f"---README---\n{truncated}\n---END---"
    )


def _prompt_steps(readme_text: str) -> str:
    """インストール手順 JSON 抽出プロンプト（後方互換用）。"""
    truncated = readme_text[:_README_MAX_CHARS] if len(readme_text) > _README_MAX_CHARS else readme_text
    return (
        "以下の README からインストール・実行に必要なコマンドを抽出し、"
        "次の JSON 形式のみを出力してください（前置き・説明・コードブロック記号は不要）。\n"
        "コマンドが見つからない場合は空配列 [] を返してください。\n\n"
        '形式: [{"step": 1, "cmd": "...", "description": "..."}, ...]\n\n'
        f"---README---\n{truncated}\n---END---"
    )


# ---------------------------------------------------------------------------
# JSON パース（T-14）
# ---------------------------------------------------------------------------


def _parse_steps(text: str) -> list[InstallStep]:
    """LLM の返答テキストから InstallStep リストをパースする。失敗時は空リスト（FR-09）。"""
    # コードブロック記号を除去（```json ... ``` 形式に対応）
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # 最初と最後の ``` 行を除く
        inner = [ln for ln in lines[1:] if not ln.strip().startswith("```")]
        cleaned = "\n".join(inner).strip()

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("インストール手順 JSON のパースに失敗しました。空配列を返します。")
        return []

    if not isinstance(data, list):
        return []

    steps: list[InstallStep] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            steps.append(
                InstallStep(
                    step=int(item.get("step", len(steps) + 1)),
                    cmd=str(item.get("cmd", "")),
                    description=str(item.get("description", "")),
                )
            )
        except (TypeError, ValueError):
            continue
    return steps


def _parse_combined(text: str) -> tuple[str, list[InstallStep]]:
    """統合プロンプトの返答から (summary_ja, steps) をパースする。

    パース失敗時は ("", []) を返す。
    """
    cleaned = text.strip()
    # コードブロック記号を除去
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner = [ln for ln in lines[1:] if not ln.strip().startswith("```")]
        cleaned = "\n".join(inner).strip()

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("統合 JSON のパースに失敗しました。raw テキストを要約として使います。")
        return (cleaned[:200].strip() if cleaned else "", [])

    if not isinstance(data, dict):
        return ("", [])

    summary = str(data.get("summary", "")).strip()[:200]
    raw_steps = data.get("steps", [])
    steps: list[InstallStep] = []
    if isinstance(raw_steps, list):
        for item in raw_steps:
            if not isinstance(item, dict):
                continue
            try:
                steps.append(
                    InstallStep(
                        step=int(item.get("step", len(steps) + 1)),
                        cmd=str(item.get("cmd", "")),
                        description=str(item.get("description", "")),
                    )
                )
            except (TypeError, ValueError):
                continue

    return (summary, steps)


# ---------------------------------------------------------------------------
# 公開 API（T-13）
# ---------------------------------------------------------------------------


def build_plan(readme_text: str) -> Plan:
    """README テキストから Plan（日本語要約 + インストール手順）を生成する（FR-08〜10）。

    要約と手順抽出を 1 回の LLM 呼び出しで取得する（待ち時間の最小化）。
    LLM 呼び出しは最大 _MAX_RETRIES 回リトライする（初回 + 1 回 = 最大 2 回）。
    最終的に失敗した場合は llm_error にエラー文字列を設定して後続処理を続行する（FR-10）。

    Args:
        readme_text: README の全文テキスト。

    Returns:
        Plan: 要約・手順・エラー情報を持つデータオブジェクト。
    """
    prompt = _prompt_combined(readme_text)
    messages = [{"role": "user", "content": prompt}]

    last_error: str | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            raw = chat(messages)
            summary_ja, steps = _parse_combined(raw)
            if not summary_ja:
                summary_ja = "（要約の取得に失敗しました）"
            return Plan(
                summary_ja=summary_ja,
                steps=steps,
                llm_error=None,
            )
        except LLMError as e:
            last_error = str(e)
            if attempt < _MAX_RETRIES:
                logger.warning("LLM リトライ %d/%d: %s", attempt + 1, _MAX_RETRIES, e)
            else:
                logger.error("LLM が %d 回失敗しました: %s", _MAX_RETRIES + 1, e)

    return Plan(
        summary_ja="（要約の取得に失敗しました）",
        steps=[],
        llm_error=f"LLM 応答取得失敗: {last_error}",
    )
