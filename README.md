# Repo Autopsy（リポ検死）

公開 GitHub リポジトリの URL を 1 つ入力するだけで、**日本語の Mac（Apple Silicon）向け検証レポート**を自動生成する CLI ツールです。

「使う前に罠を見抜く」という一次判定を、日本語で、数分で提供します。

---

## 概要

海外の AI ツールを試したいとき、英語の README を読み解き、arm64 対応を確認し、ライセンスを調べ……という作業は時間がかかります。Repo Autopsy は以下を自動で行います：

1. GitHub API でメタデータ・README・ライセンスを取得
2. LLM（OpenAI 互換 API）で日本語要約とインストール手順を抽出
3. ルールベース（罠シグナル 13 個 + 条件付きシグナル 3 個）で「使える / 条件付き / 罠」を判定
4. 日本語 Markdown レポート（8 章立て）を `reports/<owner>__<repo>.md` に保存

**ローカル実行が本体**です。クラウドへの送信はありません（LLM への README テキスト送信を除く）。

---

## インストール

Python 3.12 以上と [uv](https://github.com/astral-sh/uv) が必要です。

```bash
git clone https://github.com/your-org/repo-autopsy.git
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

---

## 判定ラベル

| ラベル | 意味 |
|--------|------|
| **使える** | arm64 Mac で主要機能が動作し、無料枠で試せる。ライセンスは商用可。 |
| **条件付き** | 動作するが制限あり（Rosetta 必要、有料 API 必須、GPL ライセンスなど）。条件を明示。 |
| **罠** | CUDA/NVIDIA 必須、`curl \| bash`、`sudo` 要求、ライセンス不明、1 年超放置、実行ログに致命的エラーなど。 |

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

---

## ライセンス

MIT License © 2026 Repo Autopsy contributors
