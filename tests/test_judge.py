"""tests/test_judge.py — judge.py のテスト。

カバレッジ:
- T-52: 各ルール（R-01〜R-13, C-01〜C-03）の正・負ケースを単体テスト
- T-53: PBT — 任意の入力で decide() が必ず Label 3値のいずれかを返し例外を出さない
- T-54: PBT — 同一入力で判定が変わらない（決定性）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from repo_autopsy.judge import CONDITIONAL_RULES, TRAP_RULES, decide, run_rules
from repo_autopsy.models import (
    InstallStep,
    Label,
    Plan,
    RepoMeta,
    RunResult,
    SafetyIssue,
    Signal,
    SignalKind,
    StepResult,
    Verdict,
)

# ---------------------------------------------------------------------------
# ヘルパー: デフォルトの最小限 RepoMeta / RunResult を生成
# ---------------------------------------------------------------------------


def _meta(
    *,
    readme: str = "arm64 Apple Silicon install guide",
    license_spdx: str | None = "MIT",
    last_commit_at: str | None = None,
    stars: int = 100,
    language: str | None = "Python",
    topics: list[str] | None = None,
) -> RepoMeta:
    """テスト用 RepoMeta を生成する（デフォルトは「使える」状態）。"""
    if last_commit_at is None:
        # 直近 30 日以内
        dt = datetime.now(tz=timezone.utc) - timedelta(days=30)
        last_commit_at = dt.isoformat()
    return RepoMeta(
        owner="testowner",
        repo="testrepo",
        url="https://github.com/testowner/testrepo",
        license_spdx=license_spdx,
        last_commit_at=last_commit_at,
        stars=stars,
        language=language,
        topics=topics or [],
        readme_text=readme,
        root_files=["README.md", "pyproject.toml"],
    )


def _run(
    *,
    dry_run: bool = True,
    cmds: list[str] | None = None,
    stdouts: list[str] | None = None,
    stderrs: list[str] | None = None,
) -> RunResult:
    """テスト用 RunResult を生成する。"""
    cmds = cmds or []
    stdouts = stdouts or [""] * len(cmds)
    stderrs = stderrs or [""] * len(cmds)
    steps = [
        StepResult(
            step=i + 1,
            cmd=cmd,
            stdout=stdouts[i],
            stderr=stderrs[i],
            exit_code=0,
            elapsed_sec=0.1,
            timed_out=False,
        )
        for i, cmd in enumerate(cmds)
    ]
    return RunResult(dry_run=dry_run, safety_issues=[], steps=steps, summary="")


# ---------------------------------------------------------------------------
# T-52: 各ルールの正・負ケース
# ---------------------------------------------------------------------------


class TestR01Cuda:
    """R-01: CUDA/GPU 必須の言及を検出。"""

    def test_positive_readme(self) -> None:
        meta = _meta(readme="requires cuda and nvidia-smi to run")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-01" in rule_ids

    def test_positive_cmd(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon supported")
        run = _run(cmds=["pip install torch.cuda"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-01" in rule_ids

    def test_negative(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon supported. No GPU required.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-01" not in rule_ids


class TestR02NoArm64:
    """R-02: arm64 向けバイナリ・wheel の明示がない。"""

    def test_positive(self) -> None:
        meta = _meta(readme="Install on Linux x86. No arm support.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-02" in rule_ids

    def test_negative_arm64(self) -> None:
        meta = _meta(readme="Supports arm64 and Apple Silicon.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-02" not in rule_ids

    def test_negative_aarch64(self) -> None:
        meta = _meta(readme="aarch64 wheels available on PyPI")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-02" not in rule_ids


class TestR03BadLicense:
    """R-03: 非商用ライセンスまたはライセンス不明。"""

    def test_positive_none(self) -> None:
        meta = _meta(readme="arm64 supported", license_spdx=None)
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-03" in rule_ids

    def test_positive_noassertion(self) -> None:
        meta = _meta(readme="arm64 supported", license_spdx="NOASSERTION")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-03" in rule_ids

    def test_positive_agpl(self) -> None:
        meta = _meta(readme="arm64 supported", license_spdx="AGPL-3.0-only")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-03" in rule_ids

    def test_positive_ccbync(self) -> None:
        meta = _meta(readme="arm64 supported", license_spdx="CC-BY-NC-4.0")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-03" in rule_ids

    def test_negative_mit(self) -> None:
        meta = _meta(readme="arm64 supported", license_spdx="MIT")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-03" not in rule_ids

    def test_negative_apache(self) -> None:
        meta = _meta(readme="arm64 supported", license_spdx="Apache-2.0")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-03" not in rule_ids


class TestR04StaleRepo:
    """R-04: 最終コミットが 365 日以上前。"""

    def test_positive(self) -> None:
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=400)).isoformat()
        meta = _meta(readme="arm64 supported", last_commit_at=old_date)
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-04" in rule_ids

    def test_negative(self) -> None:
        recent_date = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()
        meta = _meta(readme="arm64 supported", last_commit_at=recent_date)
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-04" not in rule_ids

    def test_boundary_exactly_365(self) -> None:
        boundary_date = (datetime.now(tz=timezone.utc) - timedelta(days=365)).isoformat()
        meta = _meta(readme="arm64 supported", last_commit_at=boundary_date)
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-04" in rule_ids


class TestR05Immature:
    """R-05: スターが 10 未満の未成熟なリポジトリ。"""

    def test_positive_zero_stars(self) -> None:
        meta = _meta(readme="arm64 supported", stars=0)
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-05" in rule_ids

    def test_positive_9_stars(self) -> None:
        meta = _meta(readme="arm64 supported", stars=9)
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-05" in rule_ids

    def test_negative_10_stars(self) -> None:
        meta = _meta(readme="arm64 supported", stars=10)
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-05" not in rule_ids

    def test_negative_many_stars(self) -> None:
        meta = _meta(readme="arm64 supported", stars=5000)
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-05" not in rule_ids


class TestR06Sudo:
    """R-06: sudo を含む抽出済み手順コマンドが存在する。

    仕様変更（問題4修正）:
      - README 本文は対象外。LLM で抽出したステップの cmd のみを検査する。
      - 理由: LLM 失敗時は手順が空になるため、README に sudo の説明文が
        あるだけで R-06 が誤発火していた。
    """

    def test_positive_cmd(self) -> None:
        """抽出済み手順コマンドに sudo があれば R-06 が発火する。"""
        meta = _meta()
        run = _run(cmds=["sudo apt-get install python3"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-06" in rule_ids

    def test_negative_readme_only(self) -> None:
        """README に sudo があっても手順コマンドになければ R-06 は発火しない（誤検知修正）。"""
        meta = _meta(readme="arm64 Apple Silicon. Run: sudo pip install ...")
        result = run_rules(meta, _run())  # 手順コマンドなし
        rule_ids = [s.rule_id for s in result]
        assert "R-06" not in rule_ids

    def test_negative(self) -> None:
        meta = _meta(readme="arm64 supported. pip install mypackage")
        run = _run(cmds=["pip install mypackage"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-06" not in rule_ids

    def test_negative_pseudosudo(self) -> None:
        """'pseudosudo' などの誤検知をしないことを確認。"""
        meta = _meta(readme="arm64 supported. Use pseudosudo for testing")
        run = _run(cmds=["pseudosudo run"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-06" not in rule_ids


class TestR07CurlBash:
    """R-07: curl|bash または wget|sh を含む手順が存在する。"""

    def test_positive_curl_bash(self) -> None:
        meta = _meta()
        run = _run(cmds=["curl https://install.sh | bash"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-07" in rule_ids

    def test_positive_wget_sh(self) -> None:
        meta = _meta()
        run = _run(cmds=["wget https://install.sh | sh"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-07" in rule_ids

    def test_positive_readme(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon. curl https://example.com/install.sh | bash")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-07" in rule_ids

    def test_negative(self) -> None:
        meta = _meta()
        run = _run(cmds=["curl https://example.com/data.json -o data.json"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-07" not in rule_ids


class TestR08HardcodedKey:
    """R-08: README に API キーの固定値（sk-...）が含まれる。"""

    def test_positive(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon. OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz1234")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-08" in rule_ids

    def test_negative_short_sk(self) -> None:
        """短い sk- は誤検知しないことを確認。"""
        meta = _meta(readme="arm64 Apple Silicon. skipping step 1")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-08" not in rule_ids

    def test_negative(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon. Set OPENAI_API_KEY to your key.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-08" not in rule_ids


class TestR09ModuleNotFound:
    """R-09: 実行ログに ModuleNotFoundError が含まれる。"""

    def test_positive_stderr(self) -> None:
        meta = _meta()
        run = _run(cmds=["python app.py"], stderrs=["ModuleNotFoundError: No module named 'torch'"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-09" in rule_ids

    def test_positive_stdout(self) -> None:
        meta = _meta()
        run = _run(cmds=["python app.py"], stdouts=["Error: ModuleNotFoundError occurred"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-09" in rule_ids

    def test_negative(self) -> None:
        meta = _meta()
        run = _run(cmds=["python app.py"], stdouts=["All modules loaded successfully"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-09" not in rule_ids


class TestR10NoDistribution:
    """R-10: 実行ログに 'No matching distribution found' が含まれる。"""

    def test_positive(self) -> None:
        meta = _meta()
        run = _run(
            cmds=["pip install mypackage"],
            stderrs=["ERROR: No matching distribution found for mypackage"],
        )
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-10" in rule_ids

    def test_negative(self) -> None:
        meta = _meta()
        run = _run(
            cmds=["pip install mypackage"],
            stdouts=["Successfully installed mypackage-1.0.0"],
        )
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-10" not in rule_ids


class TestR11Killed:
    """R-11: 実行ログに 'Killed' が含まれる（OOM）。"""

    def test_positive(self) -> None:
        meta = _meta()
        run = _run(cmds=["python train.py"], stderrs=["Killed"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-11" in rule_ids

    def test_negative(self) -> None:
        meta = _meta()
        run = _run(cmds=["python train.py"], stdouts=["Training complete"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-11" not in rule_ids


class TestR12CommandNotFound:
    """R-12: 実行ログに 'command not found' が含まれる。"""

    def test_positive(self) -> None:
        meta = _meta()
        run = _run(cmds=["mytool --version"], stderrs=["bash: mytool: command not found"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-12" in rule_ids

    def test_negative(self) -> None:
        meta = _meta()
        run = _run(cmds=["python --version"], stdouts=["Python 3.12.0"])
        result = run_rules(meta, run)
        rule_ids = [s.rule_id for s in result]
        assert "R-12" not in rule_ids


class TestR13PaidApiOnly:
    """R-13: 有料 API のみ言及、無料枠なし。"""

    def test_positive(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon. Requires OPENAI_API_KEY to run.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-13" in rule_ids

    def test_negative_free_tier_mentioned(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon. Requires OPENAI_API_KEY. Free tier available.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-13" not in rule_ids

    def test_negative_no_api(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon. Fully local, no API needed.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "R-13" not in rule_ids


class TestC01Rosetta:
    """C-01: Rosetta または x86_64 が README に含まれる。"""

    def test_positive_rosetta(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon supported. Rosetta required for some features.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-01" in rule_ids

    def test_positive_x86_64(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon supported. x86_64 wheel available.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-01" in rule_ids

    def test_negative(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon supported. Native ARM binary.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-01" not in rule_ids


class TestC02PaidApiWithFree:
    """C-02: 有料 API の言及があるが無料枠の説明もある。"""

    def test_positive(self) -> None:
        meta = _meta(
            readme="arm64 Apple Silicon. Requires OPENAI_API_KEY. Free tier available with 100 calls/day."
        )
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-02" in rule_ids

    def test_negative_no_api(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon. No API needed.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-02" not in rule_ids

    def test_negative_api_but_no_free(self) -> None:
        """有料 API の言及があるが無料枠の説明がない → C-02 は検出しない（R-13 が検出する）。"""
        meta = _meta(readme="arm64 Apple Silicon. Requires OPENAI_API_KEY.")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-02" not in rule_ids


class TestC03GplLicense:
    """C-03: GPL または LGPL ライセンス。"""

    def test_positive_gpl(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon supported", license_spdx="GPL-3.0-only")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-03" in rule_ids

    def test_positive_lgpl(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon supported", license_spdx="LGPL-2.1-only")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-03" in rule_ids

    def test_negative_mit(self) -> None:
        meta = _meta(readme="arm64 Apple Silicon supported", license_spdx="MIT")
        result = run_rules(meta, _run())
        rule_ids = [s.rule_id for s in result]
        assert "C-03" not in rule_ids


# ---------------------------------------------------------------------------
# decide() の単体テスト
# ---------------------------------------------------------------------------


class TestDecide:
    def test_trap_signals_give_trap(self) -> None:
        signals = [Signal(kind=SignalKind.TRAP, rule_id="R-01", description="CUDA必須")]
        verdict = decide(signals)
        assert verdict.label == Label.TRAP

    def test_conditional_only_gives_conditional(self) -> None:
        signals = [Signal(kind=SignalKind.CONDITIONAL, rule_id="C-01", description="Rosetta")]
        verdict = decide(signals)
        assert verdict.label == Label.CONDITIONAL

    def test_empty_signals_give_usable(self) -> None:
        verdict = decide([])
        assert verdict.label == Label.USABLE
        assert "罠シグナルなし" in verdict.summary_ja

    def test_trap_takes_priority_over_conditional(self) -> None:
        signals = [
            Signal(kind=SignalKind.TRAP, rule_id="R-01", description="CUDA"),
            Signal(kind=SignalKind.CONDITIONAL, rule_id="C-01", description="Rosetta"),
        ]
        verdict = decide(signals)
        assert verdict.label == Label.TRAP

    def test_signals_preserved_in_verdict(self) -> None:
        signals = [Signal(kind=SignalKind.TRAP, rule_id="R-03", description="ライセンス不明")]
        verdict = decide(signals)
        assert len(verdict.signals) == 1
        assert verdict.signals[0].rule_id == "R-03"


# ---------------------------------------------------------------------------
# T-53: PBT — decide() が必ず Label 3 値のいずれかを返し例外を出さない
# ---------------------------------------------------------------------------

_signal_strategy = st.builds(
    Signal,
    kind=st.sampled_from(SignalKind),
    rule_id=st.text(min_size=1, max_size=10),
    description=st.text(max_size=200),
)


@given(signals=st.lists(_signal_strategy, max_size=20))
@settings(max_examples=200)
def test_pbt_decide_always_returns_valid_label(signals: list[Signal]) -> None:
    """T-53: 任意のシグナルリストで decide() が Label 3 値のいずれかを返す（FR-30）。"""
    verdict = decide(signals)
    assert verdict.label in (Label.USABLE, Label.CONDITIONAL, Label.TRAP)


# ---------------------------------------------------------------------------
# T-54: PBT — 決定性（同一入力で同一出力）
# ---------------------------------------------------------------------------


@given(signals=st.lists(_signal_strategy, max_size=20))
@settings(max_examples=200)
def test_pbt_decide_is_deterministic(signals: list[Signal]) -> None:
    """T-54: 同一入力で decide() は常に同じ判定を返す（FR-35）。"""
    verdict1 = decide(signals)
    verdict2 = decide(signals)
    assert verdict1.label == verdict2.label


# ---------------------------------------------------------------------------
# PBT — run_rules() も例外を出さない
# ---------------------------------------------------------------------------

_readme_strategy = st.text(max_size=2000)
_iso_date_strategy = st.one_of(
    st.just("2023-01-01T00:00:00+00:00"),
    st.just("2020-06-15T12:00:00Z"),
    st.just(""),
    st.just("not-a-date"),
    st.text(max_size=30),
)
_license_strategy = st.one_of(
    st.none(),
    st.sampled_from(["MIT", "Apache-2.0", "GPL-3.0-only", "AGPL-3.0-only", "CC-BY-NC-4.0", "NOASSERTION"]),
    st.text(max_size=30),
)


@given(
    readme=_readme_strategy,
    license_spdx=_license_strategy,
    stars=st.integers(min_value=0, max_value=100000),
    last_commit_at=_iso_date_strategy,
    log_text=_readme_strategy,
)
@settings(max_examples=100)
def test_pbt_run_rules_never_raises(
    readme: str,
    license_spdx: str | None,
    stars: int,
    last_commit_at: str,
    log_text: str,
) -> None:
    """任意の入力で run_rules() が例外を出さないことを確認（FR-35）。"""
    meta = RepoMeta(
        owner="owner",
        repo="repo",
        url="https://github.com/owner/repo",
        license_spdx=license_spdx,
        last_commit_at=last_commit_at,
        stars=stars,
        language=None,
        topics=[],
        readme_text=readme,
        root_files=[],
    )
    run_result = _run(cmds=["echo test"], stdouts=[log_text], stderrs=[log_text])
    # 例外が出ないことを確認
    signals = run_rules(meta, run_result)
    verdict = decide(signals)
    assert verdict.label in (Label.USABLE, Label.CONDITIONAL, Label.TRAP)
