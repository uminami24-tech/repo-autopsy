"""tests/test_plan.py — plan.py のユニットテスト（T-16）。

ネットワークを使わず unittest.mock で LLM クライアントをモックする。
FR-08〜10 の受け入れ基準をテストする。
"""

from __future__ import annotations

import json
from unittest.mock import patch, call

import pytest

from repo_autopsy.llm import LLMError
from repo_autopsy.models import InstallStep, Plan
from repo_autopsy.plan import (
    _parse_combined,
    _parse_steps,
    _prompt_combined,
    _prompt_steps,
    _prompt_summary,
    build_plan,
)

_SAMPLE_README = """# FastAPI

FastAPI framework, high performance, easy to learn, fast to code, ready for production.

## Installation

```bash
pip install fastapi
pip install "uvicorn[standard]"
```

## Usage

```python
from fastapi import FastAPI
app = FastAPI()
```
"""


# ---------------------------------------------------------------------------
# T-16-1: プロンプト生成（FR-08, FR-09）
# ---------------------------------------------------------------------------


class TestPromptSummary:
    def test_summary_prompt_contains_readme(self):
        prompt = _prompt_summary("# Hello\nThis is a test.")
        assert "# Hello" in prompt
        assert "200 字以内" in prompt

    def test_summary_prompt_truncates_long_readme(self):
        long_readme = "x" * 15000
        prompt = _prompt_summary(long_readme)
        # 12000 字に制限されること
        assert len(prompt) < 15000 + 500  # プロンプト文字列のオーバーヘッドを考慮


class TestPromptSteps:
    def test_steps_prompt_contains_readme(self):
        prompt = _prompt_steps("## Install\n```bash\npip install foo\n```")
        assert "pip install foo" in prompt

    def test_steps_prompt_contains_json_format(self):
        prompt = _prompt_steps("readme")
        assert '"step"' in prompt
        assert '"cmd"' in prompt
        assert '"description"' in prompt


class TestPromptCombined:
    """統合プロンプトのテスト（FR-08/09 統合呼び出し）。"""

    def test_combined_prompt_contains_readme(self):
        prompt = _prompt_combined("# Hello\nThis is a test.")
        assert "# Hello" in prompt

    def test_combined_prompt_contains_both_keys(self):
        prompt = _prompt_combined("readme")
        assert '"summary"' in prompt
        assert '"steps"' in prompt

    def test_combined_prompt_truncates_long_readme(self):
        """README は先頭 12,000 文字に切り詰めること。"""
        long_readme = "x" * 15000
        prompt = _prompt_combined(long_readme)
        # 15000字が丸ごと入っていないこと
        assert "x" * 15000 not in prompt


# ---------------------------------------------------------------------------
# T-16-2: JSON パース（FR-09）
# ---------------------------------------------------------------------------


class TestParseSteps:
    def test_parse_valid_json(self):
        raw = json.dumps([
            {"step": 1, "cmd": "pip install fastapi", "description": "Install FastAPI"},
            {"step": 2, "cmd": "uvicorn main:app", "description": "Run server"},
        ])
        steps = _parse_steps(raw)
        assert len(steps) == 2
        assert isinstance(steps[0], InstallStep)
        assert steps[0].cmd == "pip install fastapi"
        assert steps[1].step == 2

    def test_parse_json_in_code_block(self):
        """```json ... ``` で囲まれた JSON もパースできること。"""
        raw = '```json\n[{"step": 1, "cmd": "npm install", "description": "Install deps"}]\n```'
        steps = _parse_steps(raw)
        assert len(steps) == 1
        assert steps[0].cmd == "npm install"

    def test_parse_empty_array(self):
        steps = _parse_steps("[]")
        assert steps == []

    def test_parse_invalid_json_returns_empty(self):
        """JSON パース失敗時は空リストを返す（FR-09）。"""
        steps = _parse_steps("this is not json")
        assert steps == []

    def test_parse_non_array_returns_empty(self):
        """配列以外の JSON が返ってきた場合も空リスト。"""
        steps = _parse_steps('{"key": "value"}')
        assert steps == []

    def test_parse_partial_items(self):
        """不正なアイテムは無視して残りをパース。"""
        raw = json.dumps([
            {"step": 1, "cmd": "pip install foo", "description": "Install"},
            "not_a_dict",
            {"step": 3, "cmd": "foo run", "description": "Run"},
        ])
        steps = _parse_steps(raw)
        assert len(steps) == 2


# ---------------------------------------------------------------------------
# _parse_combined テスト（統合プロンプト応答パーサー）
# ---------------------------------------------------------------------------


class TestParseCombined:
    def test_parse_valid_combined_json(self):
        raw = json.dumps({
            "summary": "FastAPI は高速な Web フレームワークです。",
            "steps": [
                {"step": 1, "cmd": "pip install fastapi", "description": "インストール"},
                {"step": 2, "cmd": "uvicorn main:app", "description": "起動"},
            ],
        })
        summary, steps = _parse_combined(raw)
        assert summary == "FastAPI は高速な Web フレームワークです。"
        assert len(steps) == 2
        assert steps[0].cmd == "pip install fastapi"

    def test_parse_combined_empty_steps(self):
        raw = json.dumps({"summary": "要約テキスト", "steps": []})
        summary, steps = _parse_combined(raw)
        assert summary == "要約テキスト"
        assert steps == []

    def test_parse_combined_in_code_block(self):
        """```json ... ``` で囲まれた JSON もパースできること。"""
        inner = json.dumps({"summary": "要約です", "steps": []})
        raw = f"```json\n{inner}\n```"
        summary, steps = _parse_combined(raw)
        assert summary == "要約です"

    def test_parse_combined_invalid_json_returns_empty(self):
        summary, steps = _parse_combined("これは JSON ではない")
        assert steps == []

    def test_parse_combined_summary_truncated_to_200(self):
        long_summary = "あ" * 300
        raw = json.dumps({"summary": long_summary, "steps": []})
        summary, _ = _parse_combined(raw)
        assert len(summary) <= 200


# ---------------------------------------------------------------------------
# T-16-3: build_plan 正常系（FR-08, FR-09）
# ---------------------------------------------------------------------------


class TestBuildPlan:
    def test_build_plan_success(self):
        """統合プロンプト 1 回の呼び出しで summary と steps を返すこと。"""
        combined_response = json.dumps({
            "summary": "FastAPI は Python の高速 Web フレームワークです。OpenAPI を自動生成します。",
            "steps": [
                {"step": 1, "cmd": "pip install fastapi", "description": "FastAPI をインストール"},
                {"step": 2, "cmd": "uvicorn main:app", "description": "サーバーを起動"},
            ],
        })

        with patch("repo_autopsy.plan.chat") as mock_chat:
            mock_chat.return_value = combined_response
            plan = build_plan(_SAMPLE_README)

        assert isinstance(plan, Plan)
        assert len(plan.summary_ja) > 0
        assert len(plan.steps) == 2
        assert plan.llm_error is None
        assert plan.steps[0].cmd == "pip install fastapi"
        # 統合1回呼び出しであること
        assert mock_chat.call_count == 1

    def test_build_plan_summary_truncated_to_200(self):
        """200 字超の要約は切り詰められること。"""
        combined_response = json.dumps({
            "summary": "あ" * 300,
            "steps": [],
        })

        with patch("repo_autopsy.plan.chat") as mock_chat:
            mock_chat.return_value = combined_response
            plan = build_plan(_SAMPLE_README)

        assert len(plan.summary_ja) <= 200


# ---------------------------------------------------------------------------
# T-16-4: LLM 失敗フォールバック（FR-10）
# ---------------------------------------------------------------------------


class TestBuildPlanFallback:
    def test_llm_failure_sets_error(self):
        """LLM が常に失敗する場合、llm_error が設定されること（FR-10）。"""
        with patch("repo_autopsy.plan.chat") as mock_chat:
            mock_chat.side_effect = LLMError("API エラー")
            plan = build_plan(_SAMPLE_README)

        assert plan.llm_error is not None
        assert "LLM 応答取得失敗" in plan.llm_error

    def test_llm_failure_steps_are_empty(self):
        """LLM 失敗時の手順は空リストになること（FR-10）。"""
        with patch("repo_autopsy.plan.chat") as mock_chat:
            mock_chat.side_effect = LLMError("接続タイムアウト")
            plan = build_plan(_SAMPLE_README)

        assert plan.steps == []

    def test_llm_retries_before_giving_up(self):
        """最大 1 回リトライする（つまり合計 2 回試行）こと（FR-10 改定）。"""
        with patch("repo_autopsy.plan.chat") as mock_chat:
            mock_chat.side_effect = LLMError("サーバーエラー")
            build_plan(_SAMPLE_README)

        # 統合1プロンプト × 最大2回（初回 + リトライ1回）= 合計 2 回
        assert mock_chat.call_count == 2

    def test_llm_succeeds_on_retry(self):
        """リトライで成功した場合は正常に Plan を返すこと。"""
        combined_ok = json.dumps({
            "summary": "2 回目で成功した要約です。",
            "steps": [{"step": 1, "cmd": "brew install foo", "description": "Install"}],
        })

        call_count = 0

        def side_effect(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMError("1 回目は失敗")
            return combined_ok

        with patch("repo_autopsy.plan.chat", side_effect=side_effect):
            plan = build_plan(_SAMPLE_README)

        assert plan.summary_ja == "2 回目で成功した要約です。"
        assert len(plan.steps) == 1
        assert plan.llm_error is None

    def test_json_parse_failure_returns_empty_steps(self):
        """JSON パース失敗時は steps が空で summary はテキストになること。"""
        with patch("repo_autopsy.plan.chat") as mock_chat:
            mock_chat.return_value = "これは有効な JSON ではありません"
            plan = build_plan(_SAMPLE_README)

        assert plan.steps == []
        assert plan.llm_error is None  # JSON パース失敗は LLM エラーではない
