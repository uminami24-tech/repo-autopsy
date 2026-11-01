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
2. README に `x86_64 only` / `Intel only` 等の x86 専用の明示があり arm64 の記載がない（x86 専用宣言）
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
13. （廃止）旧「有料 API のみ言及・無料枠なし」は C-06 に降格（2026-11-01 実リポ検証で誤検知を確認）

### FR-32 条件付きシグナルのルール

THE SYSTEM SHALL 以下を「条件付き」シグナルとして記録しなければならない：

1. `Rosetta` または `x86_64` が README に含まれる（Rosetta 必要の可能性）
2. 有料 API への言及があるが無料枠の説明もある
3. ライセンスが `GPL` または `LGPL`（商用利用に条件あり）
4. ライセンスが `NOASSERTION`（独自/判別不能）。LICENSE 本文を確認してください（C-04）
5. README に `arm64`/`Apple Silicon`/`aarch64` の明記がない（純 Python 等は動作する場合が多いため条件付き）（C-05）
6. 有料 API への言及があり、無料枠の記載もなく、ローカルモデル（ollama/localhost 等）の言及もない（C-06）

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

---

## 変更追記（2026-11-01）— NOASSERTION ライセンス対応

### FR-04b NOASSERTION 時のライセンス簡易判定（fetch）

WHEN GitHub API の `/repos/{owner}/{repo}/license` が `spdx_id = "NOASSERTION"` を返したとき、  
THE SYSTEM SHALL レスポンスの `content`（base64）をデコードし、先頭テキストから  
MIT / Apache-2.0 / BSD-3-Clause / BSD-2-Clause / ISC / MPL-2.0 / GPL-3.0 / AGPL-3.0 / LGPL-3.0  
のいずれかに簡易判定して `license_spdx` に設定しなければならない。  
IF 判別できない場合は、`license_spdx` に `"NOASSERTION"` を設定しなければならない。

### FR-31b R-03 ルール改定（license=None は罠、NOASSERTION は条件付き）

WHEN ライセンス識別子が `None`（LICENSE ファイルが存在しない）のとき、  
THE SYSTEM SHALL 従来どおり「罠（R-03）」シグナルを発生させなければならない。  
WHEN ライセンス識別子が `"NOASSERTION"`（独自ライセンス・判別不能）のとき、  
THE SYSTEM SHALL R-03 を発生させず、代わりに「条件付き（C-04）」シグナルを発生させなければならない。

### FR-32b C-04 シグナル追加（独自ライセンスの可能性）

THE SYSTEM SHALL `license_spdx == "NOASSERTION"` のとき、  
「C-04: 独自ライセンスまたは判別不能（NOASSERTION）。LICENSE 本文を確認してください」  
という条件付きシグナルを追加しなければならない。

### FR-40 NOASSERTION の CLI・レポート表示

WHEN `license_spdx` が `"NOASSERTION"` のとき、  
THE SYSTEM SHALL CLI とレポートに「独自/判別不能（NOASSERTION）。LICENSE 本文を確認してください」と表示しなければならない。  
「ライセンス不明」（license=None の場合）と区別して表示しなければならない。
