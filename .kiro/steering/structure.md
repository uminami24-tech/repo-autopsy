---
inclusion: always
---

# Directory Structure

```
repo-autopsy/
├── src/repo_autopsy/
│   ├── cli.py        # Typer エントリポイント。引数解析と各段の呼び出しのみ
│   ├── fetch.py      # GitHub REST API でメタデータ・README・LICENSE を取得
│   ├── plan.py       # LLM で README 日本語要約とインストール手順 JSON を抽出
│   ├── run.py        # 手順の安全チェック、dry-run、一時ディレクトリでの実行
│   ├── judge.py      # ルールベース判定（罠シグナル 10 個以上）と根拠列挙
│   ├── report.py     # Jinja2 テンプレートで日本語 Markdown レポートを生成
│   ├── llm.py        # LLM クライアント（OpenAI 互換。環境変数で差し替え可）
│   └── models.py     # dataclass / TypedDict（RepoMeta, Plan, RunResult, Verdict）
├── tests/
│   ├── test_fetch.py
│   ├── test_plan.py
│   ├── test_run.py
│   ├── test_judge.py   # PBT（Hypothesis）もここ
│   └── test_report.py
├── templates/
│   └── report.md.j2   # レポートの Jinja2 テンプレート
├── examples/           # サンプル入出力（CI でのスナップショットテスト用）
├── reports/            # 生成されたレポートの出力先（.gitignore に入れない）
├── docs/               # GitHub Pages 用の静的サイト
├── .env.example        # 環境変数のサンプル（実値なし）
├── pyproject.toml      # uv / ruff / pytest の設定
└── README.md
```

## モジュール境界ルール

- `cli.py` はビジネスロジックを持たない。I/O と順序制御のみ。
- `fetch.py` は外部 HTTP のみ。ファイル書き込み・LLM 呼び出しは行わない。
- `llm.py` は LLM API 呼び出しのみ。判定ロジックは `judge.py` に置く。
- `judge.py` はネットワーク・ファイル IO を持たない（純粋関数ベース）。
- モジュール間の受け渡しは `models.py` の型を使う。
