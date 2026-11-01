# Requirements — 01 Fetch and Plan

## 概要

GitHub の公開リポジトリ URL からメタデータ・README・LICENSE を取得し、LLM で日本語要約とインストール手順 JSON を生成する。

---

## 受け入れ基準（EARS 形式）

### FR-01 URL 検証

WHEN ユーザーが `autopsy <url>` を実行したとき、  
THE SYSTEM SHALL URL が `https://github.com/<owner>/<repo>` 形式であることを検証し、  
形式が不正な場合はエラーメッセージを表示して処理を停止しなければならない。

### FR-02 リポジトリメタデータ取得

WHEN URL が有効な公開リポジトリを指すとき、  
THE SYSTEM SHALL GitHub REST API（`/repos/{owner}/{repo}`）から  
ライセンス名・最終コミット日時・スター数・主要言語・トピックスを取得しなければならない。

### FR-03 README 取得

WHEN リポジトリにアクセス可能なとき、  
THE SYSTEM SHALL `/repos/{owner}/{repo}/readme` エンドポイントから  
README のテキスト本文（Base64 デコード済み）を取得しなければならない。

### FR-04 LICENSE 取得

WHEN リポジトリにアクセス可能なとき、  
THE SYSTEM SHALL `/repos/{owner}/{repo}/license` エンドポイントから  
SPDX ライセンス識別子と本文テキストを取得しなければならない。  
LICENSE ファイルが存在しない場合は「ライセンス不明」として記録しなければならない。

### FR-05 ファイル一覧取得

WHEN リポジトリにアクセス可能なとき、  
THE SYSTEM SHALL `/repos/{owner}/{repo}/contents/` からルートディレクトリのファイル一覧（名前・種別）を取得しなければならない。

### FR-06 未認証アクセスとトークン対応

WHEN `GITHUB_TOKEN` 環境変数が設定されていないとき、  
THE SYSTEM SHALL 認証なしで API リクエストを送信しなければならない。  
WHEN `GITHUB_TOKEN` が設定されているとき、  
THE SYSTEM SHALL `Authorization: Bearer <token>` ヘッダーを付与しなければならない。

### FR-07 API レート制限の検出

WHEN GitHub API が HTTP 403 または 429 を返したとき、  
THE SYSTEM SHALL レート制限に達した旨のエラーメッセージを日本語で表示し、  
処理を停止しなければならない。

### FR-08 README 日本語要約の生成

WHEN README の取得が成功したとき、  
THE SYSTEM SHALL LLM に README テキストを渡し、  
200 字以内の日本語要約を生成しなければならない。  
README は先頭 **12,000 文字**に切り詰めてから LLM に渡さなければならない。

### FR-09 インストール手順の JSON 抽出

WHEN README の取得が成功したとき、  
THE SYSTEM SHALL LLM に README テキストを渡し、  
インストール・実行に必要なコマンドを順序付きの JSON 配列  
`[{"step": 1, "cmd": "...", "description": "..."}, ...]` として抽出しなければならない。  
コマンドが検出できない場合は空配列 `[]` を返しなければならない。  
要約と手順抽出は **1 回の LLM 呼び出し**で取得し、待ち時間を最小化しなければならない。

### FR-10 LLM 失敗時のフォールバック

WHEN LLM API がエラーを返したとき、  
THE SYSTEM SHALL 最大 **1 回**リトライし（初回 + 1 回 = 最大 2 回試行）、  
それでも失敗した場合は「LLM 応答取得失敗」と記録して後続処理を続行しなければならない。

### FR-10b LLM タイムアウト設定

THE SYSTEM SHALL 環境変数 `AUTOPSY_LLM_TIMEOUT`（秒、既定 **300**）で LLM API の  
read タイムアウトを設定可能でなければならない。  
Zro / DeepSeek などの推論モデルは 1 リクエストに 70 秒以上かかる場合があるため。

### FR-10c reasoning_content の無視

WHEN LLM レスポンスに `reasoning_content` フィールドが含まれるとき、  
THE SYSTEM SHALL `reasoning_content` を無視し、`content` フィールドのみを使用しなければならない。

### FR-11 結果の構造化保存

WHEN fetch と plan が完了したとき、  
THE SYSTEM SHALL 取得した全データを `RepoMeta` および `Plan` 型（models.py 定義）に格納し、  
後続のパイプラインステージに渡さなければならない。
