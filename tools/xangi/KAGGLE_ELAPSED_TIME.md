# Kaggle 提出時間監視の再開手順（xangi で Discord に流す場合）

この文書は、xangi・bot セッションまたはマシンの再起動後に、コア側の
**`tools/kaggle_elapsed_time.py`**（提出の経過時間監視）を常駐させ直すための正本。

> **オプション**: xangi を使わないなら §1 だけでよい。Discord に流したいときだけ §2 のラッパを使う。

## 0. 先に結論 — 今の `tools/kaggle_elapsed_time.py` は Discord に送らない

前のコンペで使っていた版は、スクリプト自身が `xangi-cmd discord_send` を叩き、通知済み状態を JSON に持っていた。
テンプレートに入っている版は**その後のリファクタ版で、Discord 依存が無い**（xangi はオプションのため）。違いは次のとおり。

| | 旧版（前のコンペ） | **現行版 `tools/kaggle_elapsed_time.py`** |
|---|---|---|
| コンペ指定 | env `KAGGLE_COMPETITION` | ファイル冒頭の定数 **`COMPETITION`**（env は読まない） |
| Discord 通知 | env `KAGGLE_DISCORD_CHANNEL` があれば `xangi-cmd discord_send` | **無い**。stdout に出すだけ |
| 「提出を検知」通知 | あり（📤） | **無い** |
| 完了 / エラー | 通知 | stdout に `✅ 完了: LB=…, run-time=…min desc=…` / `❌ エラー: desc=…, elapsed=…min` |
| 進行中 | — | 1 分ごとに `⏳ RUNNING: …` を stdout |
| 重複通知の防止 | `submission_complete_logs/.<comp>_notified.json` | 状態ファイルは無い。**起動時点で進行中だった提出だけ**を追う |
| 完了の記録 | — | `submission_complete_logs/<時刻>_<分>min_complete_<file>[_LB<score>].txt` |
| 多重起動防止 | `.locks/kaggle_elapsed_time.lock` | **無い**（§2 のラッパは flock で防ぐ） |
| API 失敗 | — | 指数バックオフ（最大 5 回）。上限を超えても常駐ループは落ちない |

🔴 現行版の性質から来る注意:

- **監視が止まっていた間に完了した提出は、どこにも出ない**（次に起動した時点で進行中のものしか追わないため）。
  止まっていた期間があったら `kaggle competitions submissions <comp>` を手で見る
- `submission_complete_logs/` は**カレントディレクトリ**に作られる。必ずリポジトリ直下で起動する
- `print` はバッファされるので、パイプやログに流すときは **`python3 -u`**

## 1. xangi を使わない場合（ログに書くだけ）

```bash
cd <REPO>                                     # リポジトリ直下
# COMPETITION 定数を自分のコンペの slug に書き換えておく（ファイル冒頭の「=== 設定 ===」）
pgrep -af '[k]aggle_elapsed_time'             # 何も出なければ起動してよい（二重起動防止はこのスクリプトに無い）
setsid nohup python3 -u tools/kaggle_elapsed_time.py >> kaggle_elapsed_time.log 2>&1 < /dev/null &
```

## 2. xangi で Discord に流す場合（`tools/xangi/kaggle_elapsed_notify.sh`）

現行版の stdout を読み、**`✅ 完了` と `❌ エラー` の行だけ**を `xangi-cmd discord_send` で流すラッパ。
コアのスクリプトは書き換えない（`COMPETITION` 定数も、import してから差し替えるので編集不要）。

通知の契約はコア側 `tools/notify.sh` と同じ: **`XANGI_CMD`（または `XANGI_ROOT`）と `NOTIFY_CHANNEL` の両方**が
あるときだけ送る。無ければ `tools/xangi/kaggle_elapsed_time.log` に書くだけで、監視自体は動く。

### 2.1 起動

```bash
cd <REPO>
pgrep -af '[k]aggle_elapsed'                  # 何も出なければ起動してよい（ラッパは flock でも二重起動を拒否する）
NOTIFY_CHANNEL=<CHANNEL_ID> \
setsid nohup tools/xangi/kaggle_elapsed_notify.sh <competition-slug> > /dev/null 2>&1 < /dev/null &
```

- `XANGI_ROOT` / `XANGI_CMD` / `NOTIFY_CHANNEL` は `tools/xangi/xangi.env` に書いておけば前置しなくてよい
- Kaggle の認証・パッケージが実行ユーザーの HOME の外にある環境だけ、`KAGGLE_CONFIG_DIR` / `KAGGLE_SITE_PACKAGES` も渡す
  （切り離して走らせると user-site が外れて `ModuleNotFoundError: kaggle` になることがある）

### 2.2 起動確認（報告の前に両方見る）

```bash
pgrep -af '[k]aggle_elapsed'                       # ラッパ（bash）と python の 2 本
ps -o pid,ppid,pgid,sid,cmd -p "$(cat tools/xangi/.kaggle_elapsed_notify.pid)"   # PPID=1 / PGID=PID を確認（AGENTS.md ルール 15）
tail -20 tools/xangi/kaggle_elapsed_time.log
```

ログに `no active submissions`（進行中なし・5 分ごと）か `checking...`（進行中あり・1 分ごと）が出ていれば正常。

### 2.3 通知内容

- 完了: `✅ **Kaggle 提出完了**（<slug>）` + 元の行（LB・経過分・説明）
- エラー: `❌ **Kaggle 提出エラー**（<slug>）` + 元の行
- 送信は `--mention false`（人への通知・bot の起動はしない）。`discord_send` の失敗はログに `[notify] discord_send failed`

LLM に要約させたい（＝相手 bot のターンを起こしたい）なら、ラッパの `notify()` を
`"$XCMD" trigger --channel "$NOTIFY_CHANNEL" --source kaggle-elapsed --message "$1"` に変える。
ただし trigger は 1 回ごとに LLM ターンが走る（使用率を食う）ので、定型の通知は `discord_send` のままが推奨
（`XANGI_CRON_SPEC.md` §5.4）。

### 2.4 停止・再起動

```bash
cat tools/xangi/.kaggle_elapsed_notify.pid
kill -TERM -"$(cat tools/xangi/.kaggle_elapsed_notify.pid)"   # 先頭の - = プロセスグループごと（python も止まる）
pgrep -af '[k]aggle_elapsed'                                    # 残っていないことを確認してから次へ
```

- PID だけに TERM を送ると、bash はフォアグラウンドのパイプライン（python）が終わるまで止まらない。だからグループで止める
- `pkill -f` や曖昧なパターンで他の Python プロセスを巻き込まないこと（AGENTS.md ルール 8）
- 停止後は §2.1 → §2.2

## 3. 注意

- `nohup` 常駐であり、マシン再起動時の自動起動ではない。再起動後は本手順で起動する
  （xangi の `startup` 型スケジュールに §2.1 を書いておけば、xangi 起動時に自動で起こせる → `XANGI_CRON_SPEC.md` §2）
- 2 体の bot がリポジトリを共有している場合、**このラッパを動かすのは 1 体だけ**（提出レーン側。AGENTS.md ルール 13）。
  PID / lock ファイルはリポジトリ内にあるので相手からも見えるが、PID は起動したコンテナの中でしか意味を持たない
- Kaggle API 認証の失敗は `tools/xangi/kaggle_elapsed_time.log` に出る
