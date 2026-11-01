# Tasks — 02 Sandbox Run

## 実装タスク

### モデル拡張

- [x] **T-20** `models.py` に `SafetyIssue`, `StepResult`, `RunResult` dataclass を追加する

### run.py — 安全チェック

- [x] **T-21** `check_safety(steps) -> list[SafetyIssue]` を実装する（→ FR-21）
  - パターン: `sudo`, `rm -rf`, `curl|bash`, `wget|sh`, `chmod +s`, `chown root`
- [x] **T-22** 危険コマンド検出時の日本語エラーメッセージを実装する（→ FR-21）

### run.py — dry-run

- [x] **T-23** `execute_plan()` の dry-run 分岐を実装し、手順一覧を日本語で表示する（→ FR-20）

### run.py — 確認プロンプト

- [x] **T-24** `--run` フラグ時の `y/N` 確認プロンプトを実装する（→ FR-22）
- [x] **T-25** `--yes` / `-y` フラグによる自動承認を実装する（→ FR-28）
  - ただし `check_safety()` は必ず通す（危険コマンドは `-y` でも実行しない）

### run.py — 実行・ログ

- [x] **T-26** 一時ディレクトリの作成・削除（`finally` ブロック）を実装する（→ FR-23）
- [x] **T-27** 環境変数ホワイトリスト (`PATH`, `HOME`, `LANG`, `TMPDIR`) でサブプロセスを起動する（→ FR-24）
- [x] **T-28** タイムアウト（既定 600 秒）を `subprocess.run(timeout=...)` で実装する（→ FR-25）
- [x] **T-29** `StepResult` を収集して `RunResult` に格納する（→ FR-26/27）

### CLI 統合

- [x] **T-30** `cli.py` に `--run` / `--yes` / `--timeout` オプションを追加する（→ FR-20/22/25/28）

### テスト

- [x] **T-31** `tests/test_run.py`: `check_safety()` の正・負テストを各パターンで書く（→ FR-21）
- [x] **T-32** `tests/test_run.py`: dry-run モードで何も実行されないことをテストする（→ FR-20）
- [x] **T-33** `tests/test_run.py`: `sudo` を含む手順が `--yes` でも実行されないことをテストする（→ FR-21/28）
- [x] **T-34** `tests/test_run.py`: タイムアウト時に `RunResult.timed_out=True` になることをテストする（→ FR-25）
- [x] **T-35** `tests/test_run.py`（PBT）: `hypothesis` で任意の文字列に対し `check_safety()` が例外を出さないことを確認する

### 結合確認

- [ ] **T-36** `autopsy <url> --run` を実際の低リスクリポジトリで試し、`RunResult` がログに正しく出ることを確認する

---

## 後続（MVP 後）

- `--network-off` フラグ（`unshare` / sandbox でネットワーク遮断）の検討
- Docker コンテナでの実行オプション
- MCP サーバー経由での `execute_plan()` 呼び出し
