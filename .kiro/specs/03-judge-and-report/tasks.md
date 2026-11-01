# Tasks — 03 Judge and Report

## 実装タスク

### モデル拡張

- [x] **T-40** `models.py` に `SignalKind`, `Signal`, `Label`, `Verdict` を追加する

### judge.py — ルール実装

- [x] **T-41** `Rule` dataclass（`rule_id`, `pattern`, `source`, `description`）と `check()` メソッドを実装する
- [x] **T-42** 罠ルール R-01〜R-07（コマンド・README 由来）を実装する（→ FR-31: 1〜7）
  - R-01: CUDA/nvidia-smi
  - R-02: arm64 wheel 不記載
  - R-03: 非商用・ライセンス不明
  - R-04: 最終コミット 365 日超
  - R-05: リリース 0 件かつスター 10 未満
  - R-06: sudo を含む手順
  - R-07: curl|bash / wget|sh
- [x] **T-43** 罠ルール R-08〜R-13（ログ・README 由来）を実装する（→ FR-31: 8〜13）
  - R-08: README 内の固定 API キー
  - R-09: ModuleNotFoundError
  - R-10: No matching distribution
  - R-11: Killed（OOM）
  - R-12: command not found
  - R-13: 有料 API のみ言及・無料枠なし
- [x] **T-44** 条件付きルール C-01〜C-03 を実装する（→ FR-32）
  - C-01: Rosetta/x86_64 の言及
  - C-02: 有料 API だが無料枠の説明あり
  - C-03: GPL/LGPL ライセンス
- [x] **T-45** `run_rules(meta, run_result) -> list[Signal]` を実装する（→ FR-31/32）
- [x] **T-46** `decide(signals) -> Verdict` を実装する（→ FR-30/33/34）

### report.py

- [x] **T-47** `templates/report.md.j2` を 8 章・日本語見出しで作成する（→ FR-36/38）
- [x] **T-48** `render(meta, plan, run_result, verdict) -> str` を Jinja2 で実装する（→ FR-36）
- [x] **T-49** `save(content, meta) -> Path` を実装し `reports/` 自動作成を含める（→ FR-37）
- [x] **T-50** dry-run 時の「dry-run のため未実行」表記をテンプレートに含める（→ FR-36 第4章）

### CLI 統合

- [x] **T-51** `cli.py` に judge/report ステージを追加し、判定結果をターミナルに表示する

### テスト

- [x] **T-52** `tests/test_judge.py`: 各ルール（R-01〜R-13, C-01〜C-03）の正・負ケースを単体テストする（→ FR-31/32）
  - R-06 の修正後テスト: 手順コマンドなし・llm_error あり状態では R-06 が発火しないことを確認
- [x] **T-53** `tests/test_judge.py`（PBT）: 任意の入力で `decide()` が必ず `Label` 3値のいずれかを返し例外を出さないことを確認する（→ FR-30）
- [x] **T-54** `tests/test_judge.py`（PBT）: 同一入力で判定が変わらない（決定性）を確認する（→ FR-35）
- [x] **T-55** `tests/test_report.py`: 生成レポートに英語見出しが含まれないことをアサートする（→ FR-38）
- [x] **T-55b** `tests/test_report.py`: LLM 失敗時レポートに「暫定判定」が含まれることをテストする（→ FR-39）
- [x] **T-56** `tests/test_report.py`: `reports/` ディレクトリが存在しなくても保存できることをテストする（→ FR-37）
- [x] **T-57b** `tests/test_llm.py`: `AUTOPSY_LLM_TIMEOUT` が反映されることをテストする（→ FR-10b）
- [x] **T-57c** `tests/test_llm.py`: `reasoning_content` が無視され `content` のみ返されることをテストする（→ FR-10c）
- [x] **T-57d** `tests/test_plan.py`: 統合プロンプト 1 回呼び出しで summary + steps が取得できることをテストする（→ FR-08/09）
- [x] **T-57e** `tests/test_plan.py`: リトライが最大 1 回（合計 2 回試行）であることをテストする（→ FR-10 改定）

### E2E 確認

- [ ] **T-57** 3 本の実在公開リポジトリで `autopsy <url>` を実行し、`reports/*.md` が生成されレポートの章立てが揃っていることを確認する（→ 計画書 1-9 MVP 完了条件）

---

## 後続（MVP 後）

- MCP サーバー `analyze_repo(url)` ツールの実装（autopsy MCP）
- Hooks 2〜4: PBT スイート自動実行・秘密情報スキャン・レポート日本語スタイルチェック
- GitHub Pages 用静的サイト（`docs/`）へのレポート自動コピー
- ルール追加: `requirements.txt` の廃止パッケージ検出、ライセンス商用可否の自動判定
