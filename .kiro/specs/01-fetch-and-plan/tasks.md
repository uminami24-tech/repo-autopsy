# Tasks — 01 Fetch and Plan

## 実装タスク

### セットアップ

- [x] **T-01** `pyproject.toml` に `httpx`, `openai`, `typer`, `jinja2` を追加し `uv sync` を通す
- [x] **T-02** `src/repo_autopsy/models.py` に `RepoMeta`, `Plan`, `InstallStep` dataclass を実装する

### fetch.py

- [x] **T-03** `_validate_url(url: str) -> tuple[str, str]` を実装し、`owner/repo` を返す（→ FR-01）
- [x] **T-04** `_fetch_meta(owner, repo, client)` を実装し `RepoMeta` の基本フィールドを埋める（→ FR-02）
- [x] **T-05** `_fetch_readme(owner, repo, client)` を実装し Base64 デコードして返す（→ FR-03）
- [x] **T-06** `_fetch_license(owner, repo, client)` を実装し SPDX 識別子を返す（→ FR-04）
- [x] **T-07** `_fetch_root_files(owner, repo, client)` を実装しファイル名一覧を返す（→ FR-05）
- [x] **T-08** `GITHUB_TOKEN` 対応ヘッダー設定を `fetch_repo()` に追加する（→ FR-06）
- [x] **T-09** 403/429 を `RateLimitError` として raise する（→ FR-07）

### llm.py

- [x] **T-10** `llm.py` の `chat()` 関数を実装し、環境変数 3 種（`OPENAI_API_KEY`/`ZRO_API_KEY`/`AUTOPSY_MODEL`）を読む（→ FR-08/09）
- [x] **T-10b** `AUTOPSY_LLM_TIMEOUT`（既定 300 秒）対応を追加する（→ FR-10b）
- [x] **T-10c** `_extract_content()` を追加し `reasoning_content` を無視する（→ FR-10c）

### plan.py

- [x] **T-11** `_prompt_summary(readme_text: str) -> str` を実装し 200 字以内の日本語要約プロンプトを組み立てる（→ FR-08 後方互換用）
- [x] **T-12** `_prompt_steps(readme_text: str) -> str` を実装しインストール手順 JSON 抽出プロンプトを組み立てる（→ FR-09 後方互換用）
- [x] **T-12b** `_prompt_combined(readme_text: str) -> str` を実装し要約・手順を 1 回の呼び出しで取得する（→ FR-08/09）
- [x] **T-13** `build_plan()` にリトライ処理（最大 **1 回**）を実装する（→ FR-10 改定）
- [x] **T-14** JSON パース失敗時に空配列 `[]` を返すフォールバックを実装する（→ FR-09）

### テスト

- [x] **T-15** `tests/test_fetch.py`: URL バリデーション・メタ取得・README/LICENSE/ファイル一覧のモックテストを書く（→ FR-01〜07）
- [x] **T-16** `tests/test_plan.py`: 要約・手順 JSON・LLM 失敗フォールバックのモックテストを書く（→ FR-08〜10）
- [x] **T-17** `tests/test_llm.py`: `ZRO_API_KEY` フォールバックのテストを書く

### 結合確認

- [ ] **T-18** `autopsy https://github.com/tiangolo/fastapi` を dry-run で実行し、`RepoMeta` と `Plan` が正しく生成されることをログで確認する（→ FR-11）

---

## 後続（MVP 後）

- `GITHUB_TOKEN` なし時の 60 req/h 制限への自動バックオフ実装
- GitHub GraphQL API への移行検討（取得項目の拡充）
