# Repo Autopsy（リポ検死）

公開 GitHub リポジトリの URL を 1 つ入力するだけで、**日本語の Mac（Apple Silicon）向け検証レポート**を自動生成する CLI ツールです。

「使う前に罠を見抜く」という一次判定を、日本語で、数分で提供します。

---

## 概要

海外の AI ツールを試したいとき、英語の README を読み解き、arm64 対応を確認し、ライセンスを調べ……という作業は時間がかかります。Repo Autopsy は以下を自動で行います：

1. GitHub API でメタデータ・README・ライセンスを取得
2. LLM（OpenAI 互換 API）で日本語要約とインストール手順を抽出
3. ルールベース（罠シグナル 13 個 + 条件付きシグナル 6 個）で「使える / 条件付き / 罠」を判定
4. 日本語 Markdown レポート（8 章立て）を `reports/<owner>__<repo>.md` に保存

**ローカル実行が本体**です。クラウドへの送信はありません（LLM への README テキスト送信を除く）。

---

## インストール

Python 3.12 以上と [uv](https://github.com/astral-sh/uv) が必要です。

```bash
git clone https://github.com/uminami24-tech/repo-autopsy.git
cd repo-autopsy
uv sync
```

---

## 使い方

```bash
# dry-run（既定）: コマンドは実行せず内容を確認するだけ
uv run autopsy https://github.com/owner/repo

# --run: 実際にインストール手順を一時ディレクトリで実行（確認プロンプトあり）
uv run autopsy https://github.com/owner/repo --run

# -y フラグで確認プロンプトを省略（CI 用）
uv run autopsy https://github.com/owner/repo --run -y

# 出力先を指定
uv run autopsy https://github.com/owner/repo --output my-report.md
```

生成されたレポートは `reports/<owner>__<repo>.md` に保存されます。

---

## 環境変数

`.env.example` をコピーして `.env` を作成し、以下の変数を設定してください：

| 変数名 | 既定値 | 説明 |
|--------|--------|------|
| `OPENAI_API_KEY` | —（必須） | LLM API キー（`ZRO_API_KEY` でも可） |
| `ZRO_API_KEY` | —（`OPENAI_API_KEY` の代替） | Zro API キー |
| `OPENAI_BASE_URL` | `https://zro.moonmath.ai/v1` | LLM エンドポイント |
| `AUTOPSY_MODEL` | `deepseek-v4.1-flash` | 使用モデル |
| `GITHUB_TOKEN` | —（任意） | GitHub PAT（未設定時は 60 req/h 制限） |

```bash
cp .env.example .env
# .env を編集して API キーを設定
```

> **注意**: Zro など OpenAI 互換の別エンドポイントを使うときは、シェルに既存の `OPENAI_API_KEY` / `OPENAI_BASE_URL` が設定されていると、それが優先されて 401 になります。`unset OPENAI_API_KEY OPENAI_BASE_URL` してから `ZRO_API_KEY` を設定して実行してください。

---

## 判定ラベル

| ラベル | 意味 |
|--------|------|
| **使える** | arm64 Mac で主要機能が動作し、無料枠で試せる。ライセンスは商用可。 |
| **条件付き** | 動作するが制限あり（Rosetta 必要、有料 API 必須、GPL ライセンスなど）。条件を明示。NOASSERTION（独自/判別不能ライセンス）も条件付きとして扱い、LICENSE 本文の確認を促す。arm64 の明記がない場合（C-05）や有料 API のみ言及の場合（C-06）も条件付きとして扱う。 |
| **罠** | CUDA/NVIDIA 必須、`curl \| bash`、`sudo` 要求、LICENSE ファイルが存在しない、1 年超放置、実行ログに致命的エラー、x86_64 専用の明示（Intel only 等）など。NOASSERTION は罠扱いしない。 |

判定はあくまで**一次判定**であり、動作を保証するものではありません。

---

## dry-run 既定と安全設計

- **既定は dry-run**。`--run` フラグを明示したときのみコマンドを実行します。
- `--run` 実行前に全コマンドを表示し、`y/N` の確認プロンプトを出します（`-y` で省略可）。
- 以下のコマンドは**自動的に「罠」判定**され、実行されません：
  - `sudo`、`rm -rf`、`curl ... | bash`、`wget ... | sh`、`chmod +s`
- 実行は必ず**一時ディレクトリ**内で行い、終了後に削除します。
- 子プロセスには `PATH`, `HOME`, `LANG` のみを渡します（API キーは渡しません）。

---

## MCP から使う

Kiro チャットから直接 `analyze_repo` ツールを呼ぶことができます。

### 設定

`.kiro/settings/mcp.json` にサーバーが登録済みです。Kiro を開くと自動的に `autopsy` MCP サーバーが起動します。

```jsonc
// .kiro/settings/mcp.json（登録済み）
{
  "mcpServers": {
    "autopsy": {
      "command": "uv",
      "args": ["run", "autopsy-mcp"]
    }
  }
}
```

### 使い方

Kiro のチャットで次のように呼べます：

```
analyze_repo("https://github.com/owner/repo")
```

`autopsy-mcp` コマンドは stdio 経由で MCP サーバーとして動作し、`analyze_repo` ツール 1 つを提供します。内部では fetch → judge → report を dry-run で実行し、日本語レポート Markdown を返します（LLM 要約は省略）。

---

## テストの実行

```bash
uv run pytest
```

Hypothesis による Property-Based Testing（PBT）を含む全テストが実行されます。

---

## 開発について

本ツールは [Kiro](https://kiro.dev) を使い、**spec 駆動開発**で作成されました。

- `.kiro/specs/` に要件・設計・タスクが仕様書として記録されています
- `.kiro/steering/` にコーディング規約・安全ルール・レポートスタイルが定義されています
- 実装は仕様書を参照しながら段階的に進めました
- `.kiro/hooks/` に 3 本の Agent フックを設定しています（v1 スキーマ、`PostFileSave` トリガー）：
  - `pytest-on-save.json`: `src/` または `tests/` の Python ファイル保存時に自動でテストを実行
  - `secret-scan-on-save.json`: ソース・ドキュメント・レポートの保存時に API キーらしい値が含まれていないかスキャン
  - `report-style-check.json`: `reports/` または `examples/` の Markdown 保存時に日本語スタイルの統一性を確認

---

## ライセンス

MIT License © 2026 Repo Autopsy contributors
