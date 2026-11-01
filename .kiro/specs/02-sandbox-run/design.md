# Design — 02 Sandbox Run

## モジュール構成

```
src/repo_autopsy/
├── run.py       # 安全チェック・dry-run・実行・ログ記録（FR-20〜28）
└── models.py    # StepResult, RunResult 型追加
```

## データフロー

```
Plan（from 01-fetch-and-plan）
  └─→ run.check_safety(plan.steps) → list[SafetyIssue]
  └─→ run.execute_plan(plan.steps, dry_run, yes) → RunResult
        └─→ 後続: judge.py
```

## 主要な型（models.py 追記）

```python
@dataclass
class SafetyIssue:
    step: int
    cmd: str
    reason: str          # "sudo検出", "curl|bash検出", etc.

@dataclass
class StepResult:
    step: int
    cmd: str
    stdout: str
    stderr: str
    exit_code: int | None   # タイムアウト時は None
    elapsed_sec: float
    timed_out: bool

@dataclass
class RunResult:
    dry_run: bool
    safety_issues: list[SafetyIssue]   # FR-21
    steps: list[StepResult]
    summary: str                        # FR-27: "3/4 ステップ成功"
    work_dir: str | None               # 実行時の一時ディレクトリ（後で削除）
```

## run.py の設計

### `check_safety(steps: list[InstallStep]) -> list[SafetyIssue]`

- 正規表現パターンリストでコマンド文字列を検査する（FR-21）。
- パターン:
  - `r'\bsudo\b'`
  - `r'rm\s+-[rf]+\s'` または `r'rm\s+-rf'`
  - `r'curl\s+.*\|\s*(ba)?sh'`
  - `r'wget\s+.*\|\s*(ba)?sh'`
  - `r'chmod\s+\+s'`
  - `r'chown\s+root'`
- 純粋関数。IO なし。

### `execute_plan(steps, dry_run, yes, timeout) -> RunResult`

1. `check_safety()` を呼び、安全問題があれば表示する。
2. `dry_run=True` の場合は手順一覧を表示して `RunResult(dry_run=True, ...)` を返す（FR-20）。
3. `dry_run=False` かつ `yes=False` の場合は確認プロンプト（FR-22）。`y` 以外は exit。
4. 一時ディレクトリを作成し、安全なステップを順次 `subprocess.run()` で実行（FR-23/24）。
5. 環境変数ホワイトリストを `os.environ` からフィルタして子プロセスに渡す（FR-24）。
6. `timeout` を `subprocess.run(timeout=...)` に設定（FR-25）。
7. `StepResult` を収集し `RunResult` を返す（FR-26/27）。
8. `finally` ブロックで一時ディレクトリを `shutil.rmtree()` で削除（FR-23）。

## 環境変数ホワイトリスト

```python
ENV_ALLOWLIST = {"PATH", "HOME", "LANG", "TMPDIR", "TERM"}
```

## エラー設計

| 例外クラス | 発生箇所 | 意味 |
|-----------|---------|------|
| `DangerousCommandError` | run.py | FR-21 の危険コマンド検出（実行はしない） |
| `UserAbortError` | run.py | FR-22 で `y` 以外が入力された |

## テスト方針

- `check_safety()`: パターンごとに正・負のケースを単体テストする。
- `execute_plan()`: `subprocess.run` をモックし、dry-run / 実行 / タイムアウトを検証する。
- PBT（Hypothesis）: 任意のコマンド文字列で `check_safety()` が例外を投げないことを確認する。
- `sudo` を含む手順が `--yes` でも実行されないことを確認する（FR-28・安全保証テスト）。
