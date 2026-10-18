# Local Taskboard

外部サービスへ接続せず、リポジトリ内だけで動くチケット管理（標準ライブラリのみ）。
1 チケットを `tickets/TNNN.json` として保存し、`board.html` / `dashboard.html` はいつでも再生成できる生成物として扱う（gitignore 済み）。
複数エージェントで回すときのタスク状態の正本（→ `AGENTS.md` §実験管理の正本と更新手順）。1 エージェントでも使える。

## Commands

```bash
python3 taskboard/task.py list
python3 taskboard/task.py show T001
python3 taskboard/task.py new --title "実験名" --type experiment --priority high --owner agent-b
python3 taskboard/task.py update T001 --status running --run-id expB12
python3 taskboard/task.py step add T001 "fold1学習" "fold2学習"   # チェックリスト項目を足す
python3 taskboard/task.py step rm  T001 --index 2                  # 項目を消す
python3 taskboard/task.py update T001 --first-step "python3 xxx.py" --link "knowledge/yyy.md" --label cv --depends-on T007
python3 taskboard/task.py check T001 1                             # 既存項目の on/off
python3 taskboard/task.py close T001 --result "CV 0.90 / LB 0.91" --decision adopted
python3 taskboard/task.py build                                    # board.html を作り直す
python3 taskboard/build_dashboard.py                               # dashboard.html を作り直す
```

- `board.html` はブラウザで直接開ける。検索、owner/type/priority フィルタ、カンバン表示を含み、外部通信しない
- `dashboard.html` は「いま何が動いていて、何が詰まっていて、どのレバーが効いたか」の状況ビュー。
  `workspace/**/training_log.json` を走査するので、**キー名（主指標・教師・fold・val 件数）は
  `build_dashboard.py` 冒頭の定数を学習コードに合わせる**。`SEED_BAND` に seed 違いの実測幅を入れると「差なし」判定が出る

## Rules

- チャットは相談と速報。実行が必要になった時点でチケットを作る
- 1 チケットは 1 つの検証目的。fold ごとの進捗は `checklist` に入れる
- `running` にする前に owner、run ID、完了条件を記録する
- **`ready` にする前に `first_step` と `checklist` を埋める。** これが無いチケットは
  「何をすればいいか分からない」ので着手できない（実例: ある日 15 件がそうなっていた）。
  `first_step` は**そのまま貼って動く 1 コマンド**か**開く 1 ファイル**にする。抽象的な方針を書かない
- `links` に根拠（日報の★・台帳・実ファイルパス）を入れる。後から「なぜこれをやるのか」を辿れるように
- 学習終了だけでは close しない。評価、成果物、台帳反映まで完了条件に含める
- `blocked` は理由と解除条件を書く。採否は `adopted/rejected/hold` で残す
- JSON を編集したら `python3 taskboard/task.py build` を実行する
- **チケットは `new` で作る。JSON を手で置かない。** ID は `new` が `O_EXCL` でファイルごと確保するので、
  同時実行しても衝突しない。手作りすると同じ ID を 2 人が使い、**片方が黙って消える**
  （実例: 3 本同時実行で 2 本消えた。`AGENTS.md` ルール 3-b の★番号衝突と同じ構造）
- 日報の `## 次にやること` は「その日の記録」、チケットは「継続タスクの状態」。役割が違う（`AGENTS.md` 参照）

## 詳細ファイル（`details/TNNN.md`）

`new` が自動生成する。検討過程・実測値・根拠・判断・次の一手はここに書く。
**状態・目的・完了条件は書き写さない**（JSON が正。両方に書くと片方が必ず腐る）。
`## 次の一手` を変えたら `task.py update TNNN --first-step "..."` も揃える（board のカードに出るのは `first_step`）。

## Status

`backlog / ready / running / blocked / review / done`

チェック番号は `show` で表示される `checklist` の 1 始まりの番号。取り消しは `check T001 1 --undo`。

## Ticket schema

必須: `id`, `title`, `status`, `type`, `priority`, `owner`, `created_at`, `updated_at`, `objective`,
`done_when`。任意: `first_step`, `run_ids`, `depends_on`, `labels`, `checklist`, `result`, `decision`, `links`, `notes`。

`first_step` は board.html にコマンドとして表示される。`checklist` も各カードに一覧表示される。
