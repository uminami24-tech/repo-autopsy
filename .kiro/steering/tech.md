---
inclusion: always
---

# Tech Stack

## 言語・ランタイム

- **Python 3.12+**（型ヒント必須、`match` 文歓迎）
- パッケージ管理: **uv**（`uv sync` 1コマンドで再現）

## 主要ライブラリ

| 用途 | ライブラリ |
|------|-----------|
| CLI | **Typer**（`autopsy <url> [--run]`） |
| テンプレート | **Jinja2**（レポート生成） |
| HTTP | **httpx**（GitHub API / LLM API。非同期不要ならSync） |
| テスト | **pytest** + **Hypothesis**（PBT） |

## LLM

- **OpenAI 互換 API** を使用。実装は `src/repo_autopsy/llm.py` に集約し、差し替えを容易にする。
- 環境変数:

| 変数名 | 既定値 | 説明 |
|--------|--------|------|
| `OPENAI_BASE_URL` | `https://zro.moonmath.ai/v1` | エンドポイント |
| `OPENAI_API_KEY` | —（必須） | API キー。`ZRO_API_KEY` も同等に読む |
| `AUTOPSY_MODEL` | `deepseek-v4.1-flash` | 使用モデル名 |

- キーの読み取り優先順: `OPENAI_API_KEY` → `ZRO_API_KEY`（どちらもあれば前者優先）。
- キーをログ・レポート・コミットに含めない（safety.md 参照）。

## GitHub API

- 未認証: 60 req/h。`GITHUB_TOKEN` 環境変数があれば使用（任意）。
- 公開リポジトリのみ対象。

## コード規約

- フォーマッタ: `ruff format`、リンタ: `ruff check`
- テストは `tests/` に置き、`pytest` で実行する。
- `.env.example` のみリポジトリに含め、`.env` は `.gitignore` に入れる。
