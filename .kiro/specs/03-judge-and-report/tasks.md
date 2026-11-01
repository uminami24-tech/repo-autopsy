# Tasks — 03 Judge and Report

## 実装タスク

### モデル拡張

- [x] **T-40** `models.py` に `SignalKind`, `Signal`, `Label`, `Verdict` を追加する

### judge.py — ルール実装

- [x] **T-41** `Rule` dataclass（`rule_id`, `pattern`, `source`, `description`）と `check()` メソッドを実装する
- [x] **T-42** 罠ルール R-01〜R-07（コマンド・README 由来）を実装する（→ FR-31: 1〜7）
  - R-01: CUDA/nvidia-smi
  - R-02: x86_64 専用明示（Intel only 等）かつ arm64 記載なし（2026-11-01 修正: 旧「arm64 未記載」から変更）
  - R-03: 非商用・ライセンス不明
  - R-04: 最終コミット 365 日超
  - R-05: リリース 0 件かつスター 10 未満
  - R-06: sudo を含む手順
  - R-07: curl|bash / wget|sh
- [x] **T-43** 罠ルール R-08〜R-13（ログ・README 由来）を実装する（→ FR-31: 8〜12）
  - R-08: README 内の固定 API キー
  - R-09: ModuleNotFoundError
  - R-10: No matching distribution
  - R-11: Killed（OOM）
  - R-12: command not found
  - R-13: 廃止（C-06 に降格。2026-11-01 実リポ検証で ollama 等ローカルモデルの誤検知を確認）
- [x] **T-44** 条件付きルール C-01〜C-06 を実装する（→ FR-32）
  - C-01: Rosetta/x86_64 の言及
  - C-02: 有料 API だが無料枠の説明あり
  - C-03: GPL/LGPL ライセンス
  - C-04: NOASSERTION ライセンス（独自/判別不能）
  - C-05: arm64 の明記なし（純 Python 等でも発火するため罠→条件付きに降格。2026-11-01 修正）
  - C-06: 有料 API のみ言及・無料枠なし・ローカルモデルなし（R-13 から降格。2026-11-01 修正）
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

- ~~MCP サーバー `analyze_repo(url)` ツールの実装（autopsy MCP）~~ ✅ 完了（2026-11-01）
- ~~Hooks 2〜4: PBT スイート自動実行・秘密情報スキャン・レポート日本語スタイルチェック~~ ✅ 完了（2026-11-01）
- GitHub Pages 用静的サイト（`docs/`）へのレポート自動コピー
- ルール追加: `requirements.txt` の廃止パッケージ検出、ライセンス商用可否の自動判定

---

## 変更追記（2026-11-01）— NOASSERTION ライセンス対応

### fetch.py 改修

- [x] **T-60** `fetch.py` の `_fetch_license` を改修: NOASSERTION 時に `content`（base64）を読んで SPDX 簡易判定（→ FR-04b）
  - MIT / Apache-2.0 / BSD-3-Clause / BSD-2-Clause / ISC / MPL-2.0 / GPL-3.0 / AGPL-3.0 / LGPL-3.0 を判定
  - 判別できない場合は `"NOASSERTION"` を返す

### judge.py 改修

- [x] **T-61** `judge.py` の R-03 を改修: `license=None` のみ罠、`NOASSERTION` は C-04 へ（→ FR-31b）
- [x] **T-62** `judge.py` に C-04「独自ライセンスまたは判別不能（NOASSERTION）」を追加（→ FR-32b）

### report・cli 改修

- [x] **T-63** `templates/report.md.j2` の基本情報表でライセンス表示を NOASSERTION 対応に修正（→ FR-40）
- [x] **T-64** `cli.py` に `_format_license()` を追加し、NOASSERTION を区別して表示（→ FR-40）

### テスト追加

- [x] **T-65** `tests/test_judge.py`: R-03 が `license=None` のとき罠、`NOASSERTION` のとき発火しないことをテスト
- [x] **T-66** `tests/test_judge.py`: C-04 が `NOASSERTION` のとき条件付きになることをテスト
- [x] **T-67** `tests/test_fetch.py`: `_detect_spdx_from_text` が各ライセンステキストを正しく判定することをテスト
- [x] **T-68** `tests/test_fetch.py`: NOASSERTION + content で判定できるケースをテスト
- [x] **T-69** `tests/test_mcp_server.py`: `analyze_repo` ツールを fetch を monkeypatch して単体テスト

---

## 変更追記（2026-11-01）— 誤検知修正（実リポ検証）

simonw/llm・openai/whisper で `autopsy` を実行したところ、R-02（arm64 未記載）と R-13（有料 API のみ）が純 Python ツールやローカルモデル対応ツールに対して誤発火することを確認したため、以下の修正を行った。

- [x] **T-70** `judge.py` の R-02 を「x86_64 専用の明示かつ arm64 記載なし」の場合のみ発火するよう修正（→ FR-31 改定）
- [x] **T-71** `judge.py` に C-05「arm64 の明記なし」を追加（旧 R-02 の降格版、条件付き）（→ FR-32 改定）
- [x] **T-72** `judge.py` の R-13 を廃止（常に False）し、C-06「有料 API のみ言及・ローカルモデルなし・無料枠なし」を追加（→ FR-32 改定）
- [x] **T-73** `tests/test_judge.py`: R-02 の新仕様テスト（x86 専用のみ罠、arm64 未記載は C-05）を追加
- [x] **T-74** `tests/test_judge.py`: R-13 廃止・C-06 の新仕様テスト（ローカルモデル言及で非発火）を追加
