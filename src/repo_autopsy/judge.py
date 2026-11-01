"""judge.py — ルールベース判定モジュール。

ネットワーク・ファイル IO を持たない純粋関数ベース（FR-35 決定性）。

公開 API:
    run_rules(meta, run_result) -> list[Signal]
    decide(signals) -> Verdict
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .models import Label, RepoMeta, RunResult, Signal, SignalKind, Verdict

# ---------------------------------------------------------------------------
# Rule dataclass（T-41）
# ---------------------------------------------------------------------------


@dataclass
class Rule:
    """判定ルール 1 件。

    Attributes:
        rule_id:     ルール識別子（例: "R-01"）
        kind:        シグナルの種類（TRAP or CONDITIONAL）
        description: 日本語の説明
        check_fn:    (meta, run_result) -> bool を返す純粋関数
    """

    rule_id: str
    kind: SignalKind
    description: str
    check_fn: Callable[[RepoMeta, RunResult], bool]

    def check(self, meta: RepoMeta, run_result: RunResult) -> Signal | None:
        """ルールを評価し、シグナルを返す（検出なしなら None）。例外は絶対に出さない。"""
        try:
            triggered = self.check_fn(meta, run_result)
        except Exception:  # noqa: BLE001
            triggered = False
        if triggered:
            return Signal(kind=self.kind, rule_id=self.rule_id, description=self.description)
        return None


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------


def _text_sources(meta: RepoMeta, run_result: RunResult) -> str:
    """README + コマンド + ログを結合した検索対象テキストを返す。"""
    parts: list[str] = [meta.readme_text or ""]
    for step in run_result.steps:
        parts.append(step.cmd)
        parts.append(step.stdout)
        parts.append(step.stderr)
    return "\n".join(parts)


def _all_cmds(run_result: RunResult) -> str:
    """全コマンド文字列を結合して返す。"""
    return "\n".join(s.cmd for s in run_result.steps)


def _all_logs(run_result: RunResult) -> str:
    """全 stdout + stderr を結合して返す。"""
    parts: list[str] = []
    for step in run_result.steps:
        parts.append(step.stdout)
        parts.append(step.stderr)
    return "\n".join(parts)


def _days_since_iso(iso_str: str) -> int:
    """ISO 8601 文字列から現在までの経過日数を返す。パースできなければ 0。"""
    if not iso_str:
        return 0
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(tz=timezone.utc)
        return (now - dt).days
    except (ValueError, OverflowError):
        return 0


# ---------------------------------------------------------------------------
# 罠ルール R-01〜R-13（T-42, T-43）
# ---------------------------------------------------------------------------

_RE_CUDA = re.compile(r"cuda|nvidia-smi|torch\.cuda", re.IGNORECASE)
_RE_ARM64 = re.compile(r"arm64|[Aa]pple [Ss]ilicon", re.IGNORECASE)
_RE_ARM64_WHEEL = re.compile(r"arm64|[Aa]pple [Ss]ilicon|aarch64", re.IGNORECASE)
_RE_NC_LICENSE = re.compile(r"CC-BY-NC|AGPL|SSPL", re.IGNORECASE)
_RE_SUDO = re.compile(r"\bsudo\b")
_RE_CURL_BASH = re.compile(r"curl\b.*\|\s*(ba)?sh\b", re.DOTALL)
_RE_WGET_SH = re.compile(r"wget\b.*\|\s*(ba)?sh\b", re.DOTALL)
_RE_HARDCODED_KEY = re.compile(r"sk-[A-Za-z0-9]{10,}|XXXXXX+|[A-Za-z0-9_-]{20,}=\S{20,}")
_RE_MODULE_NOT_FOUND = re.compile(r"ModuleNotFoundError", re.IGNORECASE)
_RE_NO_DIST = re.compile(r"No matching distribution found", re.IGNORECASE)
_RE_KILLED = re.compile(r"\bKilled\b")
_RE_CMD_NOT_FOUND = re.compile(r"command not found", re.IGNORECASE)
_RE_PAID_API = re.compile(r"openai\.api_key|OPENAI_API_KEY|ANTHROPIC_API_KEY|claude\b|gpt-4", re.IGNORECASE)
_RE_FREE_TIER = re.compile(r"無料|free tier|free plan|free quota|free credit", re.IGNORECASE)


def _r01_cuda(meta: RepoMeta, run_result: RunResult) -> bool:
    """R-01: CUDA/GPU 必須の言及を検出（README + コマンド）。"""
    src = meta.readme_text + "\n" + _all_cmds(run_result)
    return bool(_RE_CUDA.search(src))


def _r02_no_arm64(meta: RepoMeta, _run: RunResult) -> bool:
    """R-02: arm64/Apple Silicon 向けバイナリ・wheel の明示がない。"""
    return not bool(_RE_ARM64_WHEEL.search(meta.readme_text or ""))


def _r03_bad_license(meta: RepoMeta, _run: RunResult) -> bool:
    """R-03: 非商用ライセンス（CC-BY-NC/AGPL）またはライセンス不明。"""
    spdx = meta.license_spdx or ""
    if not spdx or spdx == "NOASSERTION":
        return True
    return bool(_RE_NC_LICENSE.search(spdx))


def _r04_stale_repo(meta: RepoMeta, _run: RunResult) -> bool:
    """R-04: 最終コミットが 365 日以上前（放置リポジトリ）。"""
    return _days_since_iso(meta.last_commit_at) >= 365


def _r05_immature(meta: RepoMeta, _run: RunResult) -> bool:
    """R-05: リリース 0 件かつスターが 10 未満（未検証・未成熟）。"""
    # RepoMeta に releases フィールドはないため stars のみで判定
    return meta.stars < 10


def _r06_sudo(meta: RepoMeta, run_result: RunResult) -> bool:
    """R-06: sudo を含む手順が存在する（抽出した手順コマンドのみ対象）。

    README 本文は対象外。LLM で抽出したステップの cmd のみを検査することで
    「README に sudo の説明文があるだけ」の誤検知を防ぐ。
    """
    cmds = _all_cmds(run_result)
    return bool(_RE_SUDO.search(cmds))


def _r07_curl_bash(meta: RepoMeta, run_result: RunResult) -> bool:
    """R-07: curl|bash または wget|sh を含む手順が存在する。"""
    cmds = _all_cmds(run_result)
    readme = meta.readme_text or ""
    return bool(
        _RE_CURL_BASH.search(cmds)
        or _RE_WGET_SH.search(cmds)
        or _RE_CURL_BASH.search(readme)
        or _RE_WGET_SH.search(readme)
    )


def _r08_hardcoded_key(meta: RepoMeta, _run: RunResult) -> bool:
    """R-08: README 内に API キー・シークレットの固定値が含まれる。"""
    readme = meta.readme_text or ""
    # sk- で始まる典型的な OpenAI キー形式のみ（誤検知を減らすため）
    return bool(re.search(r"sk-[A-Za-z0-9]{20,}", readme))


def _r09_module_not_found(_meta: RepoMeta, run_result: RunResult) -> bool:
    """R-09: 実行ログに ModuleNotFoundError が含まれる（依存インストール失敗）。"""
    return bool(_RE_MODULE_NOT_FOUND.search(_all_logs(run_result)))


def _r10_no_distribution(_meta: RepoMeta, run_result: RunResult) -> bool:
    """R-10: 実行ログに 'No matching distribution found' が含まれる（arm64 wheel 不存在）。"""
    return bool(_RE_NO_DIST.search(_all_logs(run_result)))


def _r11_killed(_meta: RepoMeta, run_result: RunResult) -> bool:
    """R-11: 実行ログに 'Killed' が含まれる（OOM によるプロセス強制終了）。"""
    return bool(_RE_KILLED.search(_all_logs(run_result)))


def _r12_cmd_not_found(_meta: RepoMeta, run_result: RunResult) -> bool:
    """R-12: 実行ログに 'command not found' が含まれる（コマンド不在）。"""
    return bool(_RE_CMD_NOT_FOUND.search(_all_logs(run_result)))


def _r13_paid_api_only(meta: RepoMeta, run_result: RunResult) -> bool:
    """R-13: 有料 API への言及があり、無料枠の記載がない。"""
    src = meta.readme_text + "\n" + _all_cmds(run_result)
    if not _RE_PAID_API.search(src):
        return False
    return not bool(_RE_FREE_TIER.search(src))


# ---------------------------------------------------------------------------
# 条件付きルール C-01〜C-03（T-44）
# ---------------------------------------------------------------------------

_RE_ROSETTA = re.compile(r"[Rr]osetta|x86_64")
_RE_GPL = re.compile(r"\bL?GPL\b")


def _c01_rosetta(meta: RepoMeta, _run: RunResult) -> bool:
    """C-01: Rosetta または x86_64 が README に含まれる（Rosetta 使用の可能性）。"""
    return bool(_RE_ROSETTA.search(meta.readme_text or ""))


def _c02_paid_api_with_free(meta: RepoMeta, run_result: RunResult) -> bool:
    """C-02: 有料 API への言及があるが無料枠の説明もある。"""
    src = meta.readme_text + "\n" + _all_cmds(run_result)
    return bool(_RE_PAID_API.search(src)) and bool(_RE_FREE_TIER.search(src))


def _c03_gpl_license(meta: RepoMeta, _run: RunResult) -> bool:
    """C-03: GPL または LGPL ライセンス（商用利用に条件あり）。"""
    spdx = meta.license_spdx or ""
    return bool(_RE_GPL.search(spdx))


# ---------------------------------------------------------------------------
# ルールリスト
# ---------------------------------------------------------------------------

TRAP_RULES: list[Rule] = [
    Rule("R-01", SignalKind.TRAP, "CUDA/GPU 必須のため Apple Silicon 非対応の可能性があります", _r01_cuda),
    Rule("R-02", SignalKind.TRAP, "arm64（Apple Silicon）向けバイナリ・wheel の記載が見つかりません", _r02_no_arm64),
    Rule("R-03", SignalKind.TRAP, "非商用ライセンス（CC-BY-NC/AGPL）またはライセンス不明です", _r03_bad_license),
    Rule("R-04", SignalKind.TRAP, "最終コミットが 1 年以上前（放置リポジトリの可能性があります）", _r04_stale_repo),
    Rule("R-05", SignalKind.TRAP, "スター数が 10 未満の未成熟なリポジトリです", _r05_immature),
    Rule("R-06", SignalKind.TRAP, "sudo（管理者権限）を要求するコマンドが含まれています", _r06_sudo),
    Rule("R-07", SignalKind.TRAP, "curl|bash または wget|sh によるパイプ経由の実行が含まれています", _r07_curl_bash),
    Rule("R-08", SignalKind.TRAP, "README に API キーの固定値（sk-...）が含まれています", _r08_hardcoded_key),
    Rule("R-09", SignalKind.TRAP, "実行ログに ModuleNotFoundError（依存パッケージのインストール失敗）が含まれています", _r09_module_not_found),
    Rule("R-10", SignalKind.TRAP, "実行ログに 'No matching distribution found'（arm64 非対応 wheel の可能性）が含まれています", _r10_no_distribution),
    Rule("R-11", SignalKind.TRAP, "実行ログに 'Killed'（OOM によるプロセス強制終了）が含まれています", _r11_killed),
    Rule("R-12", SignalKind.TRAP, "実行ログに 'command not found'（必須コマンドの不在）が含まれています", _r12_cmd_not_found),
    Rule("R-13", SignalKind.TRAP, "有料 API のみ言及されており、無料枠の説明が見当たりません", _r13_paid_api_only),
]

CONDITIONAL_RULES: list[Rule] = [
    Rule("C-01", SignalKind.CONDITIONAL, "README に Rosetta または x86_64 の言及があります（Rosetta が必要な可能性があります）", _c01_rosetta),
    Rule("C-02", SignalKind.CONDITIONAL, "有料 API の言及がありますが、無料枠の説明も確認できます", _c02_paid_api_with_free),
    Rule("C-03", SignalKind.CONDITIONAL, "GPL/LGPL ライセンスです（商用利用には条件があります）", _c03_gpl_license),
]


# ---------------------------------------------------------------------------
# run_rules（T-45）
# ---------------------------------------------------------------------------


def run_rules(meta: RepoMeta, run_result: RunResult) -> list[Signal]:
    """全ルールを評価し、検出したシグナルのリストを返す（純粋関数）。

    Args:
        meta:       GitHub リポジトリのメタデータ。
        run_result: 実行結果（dry-run の場合は steps が空）。

    Returns:
        検出されたシグナルのリスト。
    """
    signals: list[Signal] = []
    for rule in TRAP_RULES + CONDITIONAL_RULES:
        signal = rule.check(meta, run_result)
        if signal is not None:
            signals.append(signal)
    return signals


# ---------------------------------------------------------------------------
# decide（T-46）
# ---------------------------------------------------------------------------


def decide(signals: list[Signal]) -> Verdict:
    """シグナルリストから最終判定を返す（FR-30/33/34）。

    優先順位（FR-33）:
        罠シグナルが 1 件以上 → Label.TRAP
        罠 0 件 + 条件付き 1 件以上 → Label.CONDITIONAL
        両方 0 件 → Label.USABLE

    Args:
        signals: run_rules() の戻り値。

    Returns:
        Verdict（ラベル・シグナル一覧・日本語サマリー）。

    Raises:
        なし（どんな入力でも例外を出さない）
    """
    trap_signals = [s for s in signals if s.kind == SignalKind.TRAP]
    cond_signals = [s for s in signals if s.kind == SignalKind.CONDITIONAL]

    if trap_signals:
        label = Label.TRAP
        summary = f"罠シグナル {len(trap_signals)} 件を検出しました。実行は推奨しません。"
    elif cond_signals:
        label = Label.CONDITIONAL
        summary = f"条件付きシグナル {len(cond_signals)} 件を検出しました。使用前に条件を確認してください。"
    else:
        label = Label.USABLE
        summary = "罠シグナルなし"

    return Verdict(label=label, signals=signals, summary_ja=summary)
