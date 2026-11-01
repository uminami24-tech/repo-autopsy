# Design — 03 Judge and Report

## モジュール構成

```
src/repo_autopsy/
├── judge.py      # ルールベース判定（FR-30〜35）
├── report.py     # Jinja2 レポート生成・保存（FR-36〜38）
└── models.py     # Signal, Verdict 型追加
templates/
└── report.md.j2  # レポートテンプレート（全章・日本語見出し）
```

## データフロー

```
RepoMeta + RunResult（from 01/02）
  └─→ judge.run_rules(meta, run_result) → list[Signal]
  └─→ judge.decide(signals) → Verdict
  └─→ report.render(meta, plan, run_result, verdict) → str（Markdown）
  └─→ report.save(content, meta) → Path（reports/ に保存）
```

## 主要な型（models.py 追記）

```python
from enum import Enum

class SignalKind(str, Enum):
    TRAP = "罠"
    CONDITIONAL = "条件付き"

@dataclass
class Signal:
    kind: SignalKind
    rule_id: str       # "R-01" 等
    description: str   # 日本語の説明

class Label(str, Enum):
    USABLE = "使える"
    CONDITIONAL = "条件付き"
    TRAP = "罠"

@dataclass
class Verdict:
    label: Label
    signals: list[Signal]     # FR-34
    summary_ja: str           # LLM 補足（任意）
```

## judge.py の設計

### ルール定義

```python
TRAP_RULES: list[Rule] = [
    Rule("R-01", r"cuda|nvidia-smi|torch\.cuda", "source", "CUDA/GPU必須のため Apple Silicon 非対応の可能性"),
    Rule("R-02", ..., "meta.license_spdx", "非商用ライセンスまたはライセンス不明"),
    Rule("R-03", ..., "meta.last_commit_at", "最終コミットが1年以上前"),
    # ... 合計13個（FR-31）
]
CONDITIONAL_RULES: list[Rule] = [
    Rule("C-01", r"[Rr]osetta|x86_64", "source", "Rosetta使用の可能性"),
    # ... FR-32
]
```

- `source` は `"readme"`, `"cmd"`, `"log"`, `"meta"` の区別をもつ。
- `Rule` は `check(meta: RepoMeta, run: RunResult) -> Signal | None` メソッドを持つ。

### `run_rules(meta, run_result) -> list[Signal]`

- 全ルールを順に評価し、検出したシグナルを返す。
- 純粋関数。IO なし（→ FR-35 決定性）。

### `decide(signals) -> Verdict`

- 罠シグナルが 1 件以上 → `Label.TRAP`（→ FR-33）。
- 罠 0 件、条件付き 1 件以上 → `Label.CONDITIONAL`。
- 両方 0 件 → `Label.USABLE`。
- `signals` が空なら `summary_ja = "罠シグナルなし"`（→ FR-34）。

## report.py の設計

### `render(meta, plan, run_result, verdict) -> str`

- `jinja2.Environment(loader=FileSystemLoader("templates"))` でテンプレートを読む。
- テンプレートに渡す変数: `meta`, `plan`, `run_result`, `verdict`, `generated_at`（ISO 8601）。
- `verdict.label` / `signal.kind` は `str, Enum` なので `.value` で日本語文字列を取得する（→ 「Label.TRAP」表示を防ぐ）。
- `plan.llm_error` が設定されているときは暫定判定ブロックを表示する（→ FR-39）。

### `save(content: str, meta: RepoMeta) -> Path`

- `reports/` ディレクトリを `Path.mkdir(parents=True, exist_ok=True)` で作成（→ FR-37）。
- ファイル名: `{meta.owner}__{meta.repo}.md`。

## templates/report.md.j2 の章立て

```
# {{ meta.repo }} 検証レポート

## 判定: {{ verdict.label }}（一次判定）

（3行まとめ）

## 基本情報
## インストール手順
## 実行結果
## 判定の根拠
## Apple Silicon（Mac）での注意点
## 無料で試せる範囲
## 検証環境
```

全見出しは日本語（→ FR-38）。

## テスト方針

- `judge.py`: 各ルール（13個）の正・負ケースを単体テスト。
- PBT（Hypothesis）: 任意の `RepoMeta` / `RunResult` で `decide()` が必ず `Label` 3値のいずれかを返し例外を出さない（→ FR-30/35）。
- PBT: 同一入力で出力が変わらない（決定性、→ FR-35）。
- `report.py`: テンプレート生成後に英語見出しが含まれないことをアサート（→ FR-38）。
