# Requirements — 03 Judge and Report

## 概要

`RunResult` と `RepoMeta` から罠シグナルを検出して判定ラベルを決定し、
日本語 Markdown レポートを生成して `reports/` ディレクトリに保存する。

---

## 受け入れ基準（EARS 形式）

### FR-30 判定ラベルの決定

WHEN judge ステージが呼び出されたとき、  
THE SYSTEM SHALL `使える` / `条件付き` / `罠` のいずれか 1 つのラベルを返さなければならない。  
例外を出してはならない。

### FR-31 罠シグナルのルール（10 個以上）

THE SYSTEM SHALL 以下のシグナルを検出したとき「罠」シグナルとして記録しなければならない：

1. `cuda`, `nvidia-smi`, `torch.cuda` がコマンドまたは README に含まれる（CUDA 必須）
2. README に `arm64` または `Apple Silicon` 向けのバイナリ・wheel が明示されていない（arm64 未サポート）
3. ライセンスが `CC-BY-NC` / `AGPL` / ライセンス不明（商用制限またはライセンス無し）
4. 最終コミット日時が 365 日以上前（放置リポジトリ）
5. リリースが 0 件かつスターが 10 未満（未検証・未成熟）
6. `sudo` を含む**抽出済み手順コマンド**が存在する（README 本文は対象外。LLM 未取得時の誤検知を防ぐ）
7. `curl ... | bash` または `wget ... | sh` を含む手順または README が存在する
8. README に API キー・シークレットの固定値が含まれる（例: `sk-`、`XXXXXX`）
9. 実行ログに `ModuleNotFoundError` が含まれる（依存インストール失敗）
10. 実行ログに `No matching distribution found` が含まれる（arm64 wheel 不存在）
11. 実行ログに `Killed` が含まれる（OOM によるプロセス強制終了）
12. 実行ログに `command not found` が含まれる（コマンド不在）
13. 有料 API への言及（`openai.api_key`, `ANTHROPIC_API_KEY` 等）があり、無料枠の記載がない

### FR-32 条件付きシグナルのルール

THE SYSTEM SHALL 以下を「条件付き」シグナルとして記録しなければならない：

1. `Rosetta` または `x86_64` が README に含まれる（Rosetta 必要の可能性）
2. 有料 API への言及があるが無料枠の説明もある
3. ライセンスが `GPL` または `LGPL`（商用利用に条件あり）

### FR-33 判定の優先順位

WHEN 罠シグナルが 1 つ以上存在するとき、  
THE SYSTEM SHALL 判定を「罠」としなければならない。  
WHEN 罠シグナルが 0 かつ条件付きシグナルが 1 つ以上存在するとき、  
THE SYSTEM SHALL 判定を「条件付き」としなければならない。  
WHEN 罠・条件付きシグナルともに 0 のとき、  
THE SYSTEM SHALL 判定を「使える」としなければならない。

### FR-34 根拠の列挙

WHEN 判定が確定したとき、  
THE SYSTEM SHALL 検出したシグナルを 1 つ以上列挙しなければならない。  
シグナルが 0 件で「使える」のときは「罠シグナルなし」と記録しなければならない。

### FR-35 判定の決定性

THE SYSTEM SHALL 同じ `RepoMeta` と `RunResult` を入力すると、常に同じ判定を返さなければならない。

### FR-36 日本語 Markdown レポートの生成

WHEN 判定が確定したとき、  
THE SYSTEM SHALL Jinja2 テンプレートを使用して以下の章立てで日本語 Markdown レポートを生成しなければならない：

1. 3 行まとめと判定ラベル
2. 基本情報（ライセンス・最終更新・スター数・対応 OS）
3. 日本語インストール手順
4. 実行結果（dry-run 時は「dry-run のため未実行」と明記）
5. 判定の根拠（罠シグナルの一覧）
6. Mac（Apple Silicon）での注意点
7. 無料で試せる範囲
8. 検証日と環境

### FR-37 レポートのファイル保存

WHEN レポートの生成が完了したとき、  
THE SYSTEM SHALL `reports/<owner>__<repo>.md` にレポートを保存しなければならない。  
`reports/` ディレクトリが存在しない場合は自動作成しなければならない。

### FR-38 英語見出しの禁止

THE SYSTEM SHALL 生成されたレポートに英語の見出し（`#` 行）を残してはならない。  
コードブロック内のコマンドは除く。

### FR-39 LLM 失敗時の暫定判定明記

WHEN LLM の呼び出しが失敗して `plan.llm_error` が設定されているとき、  
THE SYSTEM SHALL 生成されたレポートに「**暫定判定**: LLM 要約なし・手順未取得のため、ルールベース（メタデータのみ）による判定です」と明記しなければならない。
