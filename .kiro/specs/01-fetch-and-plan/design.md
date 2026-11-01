# Design — 01 Fetch and Plan

## モジュール構成

```
src/repo_autopsy/
├── fetch.py     # GitHub API アクセス（FR-01〜07）
├── plan.py      # LLM 呼び出し（FR-08〜10）
├── llm.py       # LLM クライアント（共通）
└── models.py    # RepoMeta, Plan 型定義
```

## データフロー

```
CLI (cli.py)
  └─→ fetch.fetch_repo(url) → RepoMeta
        └─→ plan.build_plan(readme_text) → Plan
              └─→ （後続: run, judge, report）
```

## 主要な型（models.py）

```python
@dataclass
class RepoMeta:
    owner: str
    repo: str
    url: str
    license_spdx: str | None      # FR-04
    last_commit_at: str           # ISO 8601 (FR-02)
    stars: int                    # FR-02
    language: str | None          # FR-02
    topics: list[str]             # FR-02
    readme_text: str              # FR-03
    root_files: list[str]         # FR-05

@dataclass
class Plan:
    summary_ja: str               # FR-08（200字以内）
    steps: list[InstallStep]      # FR-09
    llm_error: str | None         # FR-10

@dataclass
class InstallStep:
    step: int
    cmd: str
    description: str
```

## fetch.py の設計

- `fetch_repo(url: str) -> RepoMeta` を公開 API とする。
- `httpx.Client` を使い、`with` ブロックで接続を管理する。
- `GITHUB_TOKEN` があれば `Authorization` ヘッダーに設定（FR-06）。
- 4xx/5xx は `FetchError` を raise。403/429 は専用メッセージ（FR-07）。
- 内部で `_validate_url`, `_fetch_meta`, `_fetch_readme`, `_fetch_license`, `_fetch_root_files` に分割する。

## plan.py の設計

- `build_plan(readme_text: str) -> Plan` を公開 API とする。
- LLM プロンプトは**統合プロンプト** `_prompt_combined()` 1 本で要約・手順を同時取得する（FR-08/09 効率化）。
  - README は先頭 12,000 文字に切り詰める（FR-08 改定）。
  - 応答は `{"summary": "...", "steps": [...]}` 形式の JSON 1 個。
- 後方互換のため `_prompt_summary()` / `_prompt_steps()` も残す（テスト用）。
- 手順抽出はレスポンスを `json.loads()` でパースし、失敗したら空配列（FR-09）。
- リトライは初回 + 最大 1 回（合計 2 回）のシンプルなループ（FR-10 改定）。

## llm.py の設計

- `chat(messages: list[dict]) -> str` を公開 API とする。
- 環境変数 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `ZRO_API_KEY` / `AUTOPSY_MODEL` を読む。
- `AUTOPSY_LLM_TIMEOUT`（既定 300 秒）で read タイムアウトを設定可能にする（FR-10b）。
- `_extract_content(data)` でレスポンスの `content` フィールドのみを取得し、`reasoning_content` は無視する（FR-10c）。
- `httpx.Client` を使用（`base_url` を差し替え可能）。

## エラー設計

| 例外クラス | 発生箇所 | 意味 |
|-----------|---------|------|
| `InvalidURLError` | fetch.py | URL 形式が不正（FR-01） |
| `FetchError` | fetch.py | HTTP エラー全般（FR-07） |
| `RateLimitError(FetchError)` | fetch.py | 403/429（FR-07） |
| `LLMError` | llm.py | LLM API 失敗（FR-10） |

## テスト方針

- `fetch.py`: `httpx` の `respx` または `unittest.mock` でモックし、実際の API を呼ばない。
- `plan.py`: LLM クライアントをモック。JSON パース失敗ケースも必ずテストする。
- `llm.py`: 環境変数のオーバーライドで `ZRO_API_KEY` フォールバックをテストする。
