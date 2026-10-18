# 台帳 4 枚 + ★索引（`knowledge/ledgers/`・必須項目と書き方）

> seed は `knowledge/ledgers/` に置いてある。ここは各台帳の**必須項目と、なぜその項目が要るか**の説明。
> 役割分担: 日報＝時系列 / 詳細 Markdown＝チケット単位の作業ノート / ここ＝複数チケットから再利用する確定知見。

## 1. `knowledge/ledgers/experiments_index.md` — workspace の地図

必須: フォルダ / 目的 / 状態 / キー結果 / `SESSION_NOTES.md` へのリンク
**`exp*` が増えたら 1 行追記する**（忘れると地図が腐る）。

```markdown
# 🗂 実験インデックス（workspace/ の地図）
> 最終更新: YYYY-MM-DD。命名: Agent A=expA00_name / Agent B=expB00_name / 人間=exp200_name（AGENTS.md）
| フォルダ | 目的 | 状態 | キー結果 |
|---|---|---|---|
```

## 2. `knowledge/ledgers/training_runs.md` — 学習 run 1 本ずつの台帳

必須: run ID / **base（何からの差分か）** / 変更レバー / 教師 / fold・seed / CV / 状態 / 採否 / 成果物パス

- 🔴 **数値は実物（`metrics.csv` / `training_log.json`）から取る。日報や記憶からの転記にしない**
- 🔴 **「走行中」と書いてある行は信用せず、必ず実プロセスと状態ファイルを見る**
- 🔴 **教師が違う run を縦に並べない。** 指標は「その教師に対する順位」でしかない

## 3. `knowledge/ledgers/data_versions.md` — データ版の台帳

必須: 生成元 / 件数 / 内容ハッシュ / 使用 run / 上書き禁止

> なぜ作ったか: キャッシュ CSV の中身を変えたのに**名前を据え置いて上書き**した結果、
> 同じファイル名で違う中身を使った run が混在し、`cache/` は gitignore なので
> **git 履歴にも残らず、どちらを使ったか永久に分からなくなった**。
> → **データを変えたら名前を変える。版を消さない**（fold の `vNNN` と同じ思想）。

## 4. `submit/SUBMISSIONS.md` — 提出台帳

必須: 提出 ID / モデル元パス / 教師 / fold / CV / LB / Notebook・Dataset / 一次ログ

- 提出したら**必ず**書く。LB 待ちは「提出中」
- 一次ログ（`kaggle kernels push` の出力・完走ログ）を**消さない**。版番号はそこにしか出ない

## 5. `knowledge/ledgers/daily_reports_map.md` — ★番号の索引

`★NNN — YYYYMMDD[_B].md §セクション名 / TNNN` を 1 行ずつ。
**日報を作ったら★の有無に関わらず 1 行足す**（`star.sh check` は★ベースなので索引漏れを拾えない）。
