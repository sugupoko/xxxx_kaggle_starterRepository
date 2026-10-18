# <expXXX_name> — SESSION_NOTES

> 作成: YYYY-MM-DD。担当: <Agent A / Agent B / 人間>。チケット: T<NNN>
> 正本の分担 → 状態は `taskboard/tickets/TNNN.json`、検討過程は `taskboard/details/TNNN.md`、
> 時系列は日報、確定知見は `knowledge/`（wiki）、一覧台帳は `knowledge/ledgers/`。**ここは「このフォルダで何をしたか」**。

## 目的（1 行）

## 事前登録

- `PREREG.md`（凍結日時・sha256）:
- 判定帯:

## 走らせている条件

- データ / 教師 / fold / seed / epoch:
- 計算資源（GPU・クラウド・課金）:
- コマンド: `bash run.sh ...`

## 起動の実体（報告前に目視したもの）

```
PID / PPID=1 / PGID=SID / 状態ファイル / ログ初行
```

## 結果

| run | 主指標 | 判定（🔵採用 / 🔶不決着 / 🔴棄却） | 一次証拠のパス |
|---|---|---|---|

## 4 要素（AGENTS.md ルール 12）

| 観測条件 | |
|---|---|
| 推論状態 | 🔵確認済 / 🔶不決着 / 🔴未測定・反証 |
| 採否 gate | |
| 再開条件 / 未確定 | |

## 台帳へ反映したか

- [ ] `knowledge/ledgers/experiments_index.md` に 1 行
- [ ] `knowledge/ledgers/training_runs.md` に run 行
- [ ] `knowledge/ledgers/data_versions.md`（新しい教師・キャッシュを作った場合）
- [ ] 日報に追記（★番号は `tools/star.sh next` で払い出す）
