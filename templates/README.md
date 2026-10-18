# templates/ — 雛形

| ファイル | 使いどころ |
|---|---|
| `PREREG_TEMPLATE.md` | **事前登録**。判定帯・対照・やらないことを**数値を見る前に凍結**する（結果を見てから基準を動かす事故を止める）。実験フォルダに `PREREG.md` としてコピーし、凍結時の sha256 を `run.sh` 側で記録する |
| `SESSION_NOTES_TEMPLATE.md` | 複数エージェント運用向けの `SESSION_NOTES.md`（担当・チケット・起動の実体・4 要素・台帳反映チェック付き）。1 エージェントなら `/exp-new` が作るもので足りる |
| `daily_report_TEMPLATE.md` | 複数エージェント運用向けの日報（★範囲・測定の有無・担当別ファイル名） |
| `knowledge_ledgers_TEMPLATE.md` | `knowledge/ledgers/` の台帳 4 枚 + ★索引の必須項目と、なぜその項目が要るか |

背景・ルールは `AGENTS.md`（ルール 9〜12・§実験管理の正本と更新手順）。
