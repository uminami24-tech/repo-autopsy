"""データモデル定義（RepoMeta, Plan, InstallStep, Signal, Verdict）。

モジュール間の受け渡しはこのファイルの型を使う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# judge.py が使う型（FR-30〜35）
# ---------------------------------------------------------------------------


class SignalKind(str, Enum):
    """判定シグナルの種類。"""

    TRAP = "罠"
    CONDITIONAL = "条件付き"


@dataclass
class Signal:
    """判定シグナル 1 件。"""

    kind: SignalKind
    rule_id: str       # "R-01" 等
    description: str   # 日本語の説明


class Label(str, Enum):
    """判定ラベル（FR-30）。"""

    USABLE = "使える"
    CONDITIONAL = "条件付き"
    TRAP = "罠"


@dataclass
class Verdict:
    """judge.decide() の出力。"""

    label: Label
    signals: list[Signal] = field(default_factory=list)  # FR-34
    summary_ja: str = ""                                   # LLM 補足（任意）


@dataclass
class InstallStep:
    """インストール手順の 1 ステップ。"""

    step: int
    cmd: str
    description: str


@dataclass
class RepoMeta:
    """GitHub リポジトリのメタデータ。fetch.py が生成する。"""

    owner: str
    repo: str
    url: str
    license_spdx: str | None          # FR-04: SPDX 識別子。LICENSE がなければ None
    last_commit_at: str                # ISO 8601 (FR-02)
    stars: int                         # FR-02
    language: str | None               # FR-02
    topics: list[str]                  # FR-02
    readme_text: str                   # FR-03
    root_files: list[str]              # FR-05

    @property
    def full_name(self) -> str:
        """owner/repo 形式の文字列を返す。"""
        return f"{self.owner}/{self.repo}"


@dataclass
class Plan:
    """LLM が生成した計画（要約 + インストール手順）。plan.py が生成する。"""

    summary_ja: str                    # FR-08: 200 字以内の日本語要約
    steps: list[InstallStep] = field(default_factory=list)  # FR-09
    llm_error: str | None = None       # FR-10: LLM 失敗時のエラー文字列


# ---------------------------------------------------------------------------
# run.py が使う型（FR-21〜27）
# ---------------------------------------------------------------------------


@dataclass
class SafetyIssue:
    """危険なコマンドの検出結果。check_safety() が生成する。"""

    step: int
    cmd: str
    reason: str  # "sudo検出", "curl|bash検出" 等


@dataclass
class StepResult:
    """インストール手順の 1 ステップの実行結果。"""

    step: int
    cmd: str
    stdout: str
    stderr: str
    exit_code: int | None    # タイムアウト時は None
    elapsed_sec: float
    timed_out: bool


@dataclass
class RunResult:
    """execute_plan() の実行結果全体。"""

    dry_run: bool
    safety_issues: list[SafetyIssue] = field(default_factory=list)  # FR-21
    steps: list[StepResult] = field(default_factory=list)
    summary: str = ""                                                # FR-27
    work_dir: str | None = None                                      # 一時ディレクトリ
