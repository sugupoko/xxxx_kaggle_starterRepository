# tools/xangi/ — bot を xangi + Discord で回す人向けのオプション

> **これはオプションです。** 使うのは、Claude などの bot を **[xangi](https://github.com/karaage0703/xangi)**
> （Discord に常駐させる bot 本体）で動かし、bot 同士・人間と Discord で会話させながらコンペを回す人だけ。
> **テンプレート本体（`CLAUDE.md` / `AGENTS.md` / `tools/*.sh` / `tools/*.py` / skills / agents）はこのフォルダが無くても動く。**
> `tools/xangi/` の外に、ここへ依存するものはありません（外からはドキュメント・コメントのリンクだけ:
> `AGENTS.md` ルール 6、`tools/notify.sh`、`tools/kaggle_submit_*.sh`、`tools/kaggle_code_competition_submission.md`）。

## 何が入っているか（ひとことで）

人間 1 人 + bot 2 体（Agent A = git レーン / Agent B = Kaggle 提出レーン、`AGENTS.md` 参照）で
約 2 か月コンペを回したときに、**bot の運用で実際に壊れたところ**を塞いだ道具。

| 困りごと（実際に起きた） | 道具 |
|---|---|
| xangi が落ちても誰も起こさない。`system_restart` が片道切符 | `xangi_supervisor.sh` |
| 定点観測 cron が**黙って止まり**、2 日分の Kaggle 新着を落とした | `xangi_health_daemon.sh` + `kaggle_watch_health.py` |
| Claude の週次上限に気づいたら残り 5% | `claude_usage.py`（デーモンが通知） |
| GPU が 3〜5 時間遊んでいたのに誰も気づかない | `gpu_idle_watch.sh` |
| bot 同士の会話が「送れて見えるのに届いていない」/「止めたのに止まらない」 | 下の「bot 同士の会話（実メンション）」+ `reference/` |

## 誰が使うべきか

- ✅ bot を **xangi** で Discord に常駐させている／させる予定（Claude Code backend を想定）
- ✅ 長時間学習・Kaggle の監視・cron（定点観測）を bot に任せたい
- ❌ ローカルで Claude Code を対話的に使うだけ → **不要**。コアだけで完結する
- ❌ Slack / 別の bot フレームワーク → 考え方（`XANGI_CRON_SPEC.md` §4〜§6、監視は LLM を通さない）は使えるが、スクリプトは xangi-cmd 前提

## 有効化の手順

### 1. xangi を用意する（どちらか）

**(a) 実績のある版に固定する（推奨）** — v0.49.6 + ローカル差分 patch

```bash
git clone https://github.com/karaage0703/xangi.git && cd xangi
git checkout v0.49.6
git apply --check <REPO>/tools/xangi/reference/xangi_local_v0.49.6.patch && \
  git apply <REPO>/tools/xangi/reference/xangi_local_v0.49.6.patch
cp <REPO>/tools/xangi/reference/scheduler-clock-drift.test.ts tests/
npm ci && npm run build && npx vitest run
```

**(b) 上流の最新を使う** — 下の「xangi のバージョン」の留保を読んでから。
**bot 間の実メンションが 1 往復届くことを実機で確かめるまで、bot 同士の会話は成立しない前提で扱う。**

xangi 側の `.env` で bot 同士の会話を使うなら `RESPOND_TO_BOTS` 系（安全装置 3 層）、デーモンのバックストップを使うなら
`TRIGGER_ENABLED=true`（起動時にしか読まれない）が要る。詳細は xangi の `docs/usage.md` と `reference/`。

### 2. 設定ファイルを作る

```bash
cp tools/xangi/xangi.env.example tools/xangi/xangi.env    # .gitignore 済み。チャンネル ID を入れる
```

`tools/xangi/*.sh` は起動時に `tools/xangi/xangi.env` を読む（`XANGI_ENV_FILE` で別パスも可）。
書式は `: "${VAR:=値}"` で、**環境変数で渡した値が勝つ**。
🔴 2 体の bot が同じリポジトリを別コンテナから共有するなら、このファイルも共有される。**bot ごとに違う値（`XANGI_ROOT` など）は起動コマンド側で渡す。**

### 3. 環境変数

**既定値は持たない。** 必須のものが未設定・雛形のまま（`<CHANNEL_ID>` / `/path/to/...`）なら、理由を出して起動しない（fail-fast）。
以前は既定値に特定コンテナのパスやチャンネル ID を埋めていて、別の bot のコンテナで動かすと**別チャンネルへ黙って投稿する**状態だった。

| 変数 | 必須 | 使う道具 | 中身 |
|---|---|---|---|
| `XANGI_ROOT` | ✅ | 全部 | xangi を clone / 起動しているディレクトリ（`.env` / `dist/` / `bin/xangi-cmd` / `.xangi/schedules.json` がある場所）。**bot ごとに違う** |
| `XANGI_CMD` | — | 全部 | `xangi-cmd` の場所。省略時 `$XANGI_ROOT/bin/xangi-cmd` |
| `HEALTH_CHANNEL` | ✅※ | health daemon ① | 定点観測 cron の異常の投稿先（※`ENABLE_CRON_CHECK=1` のとき） |
| `USAGE_CHANNEL` | ✅※ | health daemon ② | Claude 使用率のしきい値通知・ゲージ（※`ENABLE_USAGE=1` のとき） |
| `ENABLE_CRON_CHECK` / `ENABLE_USAGE` | — | health daemon | `1`=有効（既定）/ `0`=無効。Kaggle の定点観測 cron を回していないなら `ENABLE_CRON_CHECK=0` |
| `GPU_IDLE_CHANNEL` | ✅※ | gpu_idle_watch | GPU アイドル通知の投稿先（※無ければ `DISCORD_CHANNEL`） |
| `DISCORD_CHANNEL` | — | gpu_idle_watch | 汎用の既定チャンネル |
| `NOTIFY_CHANNEL` | — | **コア** `tools/notify.sh`、`kaggle_elapsed_notify.sh` | 提出系の通知先。下の「コアからの通知の契約」 |
| `CLAUDE_CREDENTIALS` / `CLAUDE_CONFIG_DIR` | — | claude_usage | 認証情報が実行ユーザーの HOME の外にある環境だけ |
| `CLAUDE_USAGE_DIR` | — | claude_usage | 状態・キャッシュの置き場（既定 `tools/xangi/`）。2 体とも回すなら bot ごとに分ける |
| `KAGGLE_CONFIG_DIR` / `KAGGLE_BIN` / `KAGGLE_SITE_PACKAGES` | — | Kaggle 系 | Kaggle の認証・CLI・パッケージが HOME の外にある環境だけ。**素の環境なら不要**（既定のパスは持たない） |

細かい調整用（間隔・しきい値）は各スクリプト冒頭のコメントにある（`HEALTH_INTERVAL` / `HEALTH_REALERT_H` /
`USAGE_DAILY_HOUR` / `USAGE_GAUGE_MIN` / `USAGE_BOARD` / `LANE_MIN_INTERVAL` / `RESTART_DELAY` / `BOOT_DELAY` /
`INTERVAL` / `IDLE_CHECKS` / `GPU_IDLE_PROC_PATTERN` / `GPU_IDLE_LOG_GLOB` / `GPU_IDLE_LOG_PATTERN`）。

### 4. 常駐させる

すべて `setsid nohup … &` で切り離し、**報告の前に PPID=1 を目視する**（`AGENTS.md` ルール 15）。
停止は **PID / PGID 指定**（`pkill -f` は自分を殺す。`AGENTS.md` ルール 8）。

```bash
# (1) supervisor — xangi が落ちたら起こし直す（pm2 / systemd / Docker の restart policy があるなら不要）
setsid nohup tools/xangi/xangi_supervisor.sh >/dev/null 2>&1 </dev/null &
tools/xangi/xangi_supervisor.sh --stop            # supervisor だけ止める（xangi は残す）
#   ロック・PID・ログは $XANGI_ROOT/logs/（bot ごと）。旧 xangi の掃除は cwd=$XANGI_ROOT のプロセスだけ

# (2) 監視デーモン — cron の生存監視 + バックストップ + Claude 使用率（LLM 不使用・15 分周期）
tools/xangi/xangi_health_daemon.sh --once         # まず 1 周だけ回して確認（ログ: /tmp/xangi_health_daemon.log）
setsid nohup tools/xangi/xangi_health_daemon.sh >/tmp/xangi_health_daemon.boot.log 2>&1 </dev/null &
kill -TERM "$(cat /tmp/xangi_health_daemon.pid)"  # 停止

# (3) GPU アイドル通知（任意）
setsid nohup tools/xangi/gpu_idle_watch.sh >/dev/null 2>&1 </dev/null &
kill -TERM "$(cat tools/xangi/.gpu_idle_watch.pid)"
```

監視デーモンは nohup 常駐なので **xangi / コンテナの再起動で死ぬ**。xangi の `startup` 型スケジュールと、
定点観測 cron の冒頭（watchdog 行）から毎回起動し直す運用とセットで使う（多重起動は flock で拒否されるので毎回叩いてよい）。
→ `XANGI_CRON_SPEC.md` §4.5 / §10.4

```bash
xangi-cmd schedule_add --channel <CHANNEL_ID> \
  --input "起動時 cd <REPO> && setsid nohup tools/xangi/xangi_health_daemon.sh >/tmp/xangi_health_daemon.boot.log 2>&1 </dev/null & を実行して生存を保証する（多重起動防止内蔵。already running なら正常で報告不要）"
```

Kaggle の定点観測（Discussion / 公開コード）を cron で回す手順 → `KAGGLE_WATCH_SPEC.md`。
提出の経過時間監視を Discord に流す手順 → `KAGGLE_ELAPSED_TIME.md`。

### 5. コアからの通知の契約（`tools/kaggle_submit_now.sh` / `tools/kaggle_submit_watch.sh`）

コアの提出スクリプトは `tools/notify.sh` の `notify_send` で通知する。xangi はオプションなので:

- **`XANGI_CMD` と `NOTIFY_CHANNEL` の両方が設定されているときだけ** `xangi-cmd trigger --channel "$NOTIFY_CHANNEL" --source <id> --message …` で送る
  （trigger = 受け取った bot が 1 ターン動いて報告する）
- どちらかが無ければ、通知内容を stdout とログに出すだけ。**提出の処理自体は変わらない**
- 通知の失敗は握りつぶさずログに残す（提出の成否とは独立）。`--source` は 64 文字で切り詰める
  （超えると**提出は成功しているのに通知だけ黙って落ちる**）

```bash
XANGI_CMD="$XANGI_ROOT/bin/xangi-cmd" NOTIFY_CHANNEL=<CHANNEL_ID> \
  bash tools/kaggle_submit_now.sh <user/kernel-slug> <competition-slug> "<message>" <version>
```

切り離して走らせるときは、`XANGI_CMD` / `NOTIFY_CHANNEL` も（Kaggle の `KAGGLE_CONFIG_DIR` などと同じく）**明示して渡す**こと。
xangi の子プロセスの env がそのまま残るとは限らない。

## bot 同士の会話（実メンション）— xangi + Discord の作法

`AGENTS.md` ルール 6（「届いたことを確認する」）の、xangi + Discord での具体形。

**本文に `<@BotID>` と書くだけでは相手 bot は起動しない。** Discord API の `message.mentions` に
相手 bot が含まれる「実メンション」でなければ、受信側は自分が呼ばれたと判定できない。
見た目は青いメンション表示になるので、**画面上は成功しているように見えて実際は届いていない**。

- **送信時はメンション解決オプションを必ず有効化する**
  ```bash
  xangi-cmd discord_send --channel <CHANNEL_ID> --message "<@BotID> 本文" --mention true
  ```
  - `--mention` を付けないと `allowed_mentions.parse` が空のまま送られ、本文の `<@ID>` は
    ただの文字列として相手に届く（`message.mentions` は空）
  - 値なしの `--mention` は**次の `--message` を値として食う**。必ず `--mention true` と書く
  - 解決するのは user メンションだけ。`@everyone` / ロールは `--mention true` でも解決しない
- **会話の継続スイッチは本文の実メンション**。Discord の「返信」形式にしただけでは相手は起動しない
  （patch 適用版は、bot 宛ての返信では `repliedUser: false` にして返信ピンで再点火しないようにしてある）
- **会話を終わらせたいときはメンションを外す**。これが唯一の確実な停止方法
- 実メンション化できない送信経路しか無いときは、**その制約をチャットで人間に報告する**（投げっぱなしにしない）
- **相手から応答が返ってくるまで「伝えた」と扱わない**
- bot が会話の中で相手の ID を `<@...>` 形式で**引用しただけで相手が起動する**（受信側の文字列フォールバックの副作用）。
  ID を話題にするときはこの形式で書かない

**背景（2026-08-06）**: あるチャンネルで夕方から会話が完全に止まった。Agent B 側の送信がメンション未解決だったため、
Agent A が一度も起動していなかった。同時刻の別チャンネルでは `--mention true` を使っていたので成立しており、
**チャンネル差ではなく送信経路の差**が原因だった。逆向きの故障（「止めるね」と書いた返信で会話が再点火して止まらない）も
同じ日に直している → `reference/bot-to-bot-mention-protocol.md`。

暴走を止めるのはメンション規則ではなく xangi の安全装置 3 層（`RESPOND_TO_BOTS_MAX_CONSECUTIVE` /
`_COOLDOWN_MS` / `_WINDOW_MS` + `_MAX_PER_WINDOW`）。第 2・3 層は**人間の発言でリセットしない**のが要点。

### Discord の 1 通は 1,900 字までに収める

Discord API の上限は 1 通 2,000 字で、xangi はそれより手前（約 1,900 字）で分割して送る。
**分割されると片方が届かないのに、送信は成功して見える**ことがあった。

- 1 通 1,900 字以内に収める。収まらないなら要約せず、**日報・チケットへのポインタ**を渡す
- Markdown の表は Discord で崩れる。表はコードブロック（等幅）か画像で
- 監視の常設表示は「毎回投稿」ではなく **1 通を編集し続ける**（`claude_usage.py --board`）

## xangi のバージョン（2026-10-18 実測）

| 何 | 版 | 備考 |
|---|---|---|
| **xangi（bot 本体）** | **v0.49.6**（tag が HEAD `f666ff8` を指す・2026-08-05） | 🔴 `package.json` の `version` は `0.1.0` のままなので**版は git tag で見る** |
| **実際に運用していたもの** | **v0.49.6 + ローカル未コミット差分 14 ファイル / +766 −48** | 🔴 **素の v0.49.6 ではない**。全文 → `reference/xangi_local_v0.49.6.patch`（upstream に PR は出していない。これが唯一のバックアップ） |
| 上流の最新 | **v0.59.4**（10 マイナー先） | 触ったファイルが上流で `message-handler` 17 / `config` 16 / `index` 13 / `scheduler` 7 commits 動いている |
| Node / npm | v22.22.3 / 10.9.8 | |
| Claude Code CLI | 2.1.300 | |
| Agent B（codex 系 bot） | 別コンテナ | 版は未確認 |

ローカル差分の中身:

| 系統 | ファイル | 何のため |
|---|---|---|
| **bot 間メンション** | `src/index.ts` / `src/discord/message-handler.ts` / `src/config.ts` / `src/cli/discord-api.ts` / `src/cli/xangi-cmd-help.ts` / tests 2 本 | 実メンション解決（`--mention`）と、返信による再点火の停止 |
| **cron の再 arm** | `src/scheduler.ts` + `scheduler-clock-drift.test.ts` | 定点観測が黙って止まる問題（WSL2 の壁時計ジャンプ。`XANGI_CRON_SPEC.md` §10.2.2） |
| **モデル宣言** | `src/backend-models.ts` | モデル ID をハードコードせず `CLAUDE_CODE_MODELS` で宣言 |
| その他 | `src/stream-session.ts` / `src/slack.ts` / `src/safe-env.ts` / `docs/usage.md`(+en) | 小粒 |

### 🔴 上流 v0.59.4 に上げる前に（留保）

- **観測条件**: 2026-10-18、上流 v0.59.4 の raw ファイルを **grep しただけ**。実行・テストはしていない
- 上流 v0.59.4 に `replyAllowedMentions` / `hasTextMention` / `isMentioningSelf` / `ignoreRepliedUser` /
  `rearmCronJobs` / `CRON_REARM_INTERVAL_MS` / `CLAUDE_CODE_MODELS` は**無い**
- 🔴 **むしろ逆向き**: 上流の送信は `allowedMentions: { parse: [] }`（**メンションを一切解決しない**）で統一されている。
  これは「届かない（故障 B）」状態そのもので、**上流のまま上げると bot 間の会話継続スイッチが成立しない見込み**
- 🔵 `repliedUser: false` は上流にも 1 箇所あるので、「返信で再点火（故障 A）」は上流でも抑えられているように見える
- 🔶 同等の対策が別名で入っている可能性は否定できない。`message-handler.ts` は上流 1,274 行 / こちら 1,347 行で
  **両方がベースから離れている → patch はそのままは当たらない前提**
- **上げる条件**: ① v0.59.4 で **bot→bot の実メンションが 1 往復届くか**を実機で試す
  ② 届かなければ patch の意図（`parse: ['users']` + 本文メンションのフォールバック + edit 確定待ちポーリング、
  cron の再 arm）を再実装する

## ファイル一覧

| ファイル | 一行 |
|---|---|
| `README.md` | この文書（入口） |
| `xangi.env.example` | 設定ファイルの雛形（`xangi.env` にコピーして使う。`xangi.env` は .gitignore 済み） |
| `.gitignore` | 状態・キャッシュ・PID・ログ・`xangi.env` を除外 |
| `_lib.sh` | シェルの共通処理（env ファイル読み込み・必須変数チェック・xangi-cmd の解決・JST 計算） |
| `xangi_supervisor.sh` | xangi 本体を抱えて、落ちたら数秒で起こし直す常駐 |
| `xangi_health_daemon.sh` | LLM 不使用の監視デーモン（cron 生存監視 + バックストップ trigger + Claude 使用率の通知） |
| `kaggle_watch_health.py` | Kaggle 定点観測 cron（コアのウォッチャー state）の沈黙を判定する（デーモンが呼ぶ） |
| `claude_usage.py` | Claude Code サブスクの使用率（5 時間枠 / 週次）を取得・しきい値判定・ゲージ／ボード生成 |
| `gpu_idle_watch.sh` | 学習プロセスが消えて GPU が一定時間アイドルになったら 1 回だけ通知する |
| `kaggle_elapsed_notify.sh` | コアの `tools/kaggle_elapsed_time.py` を常駐させ、完了 / エラー行だけ Discord に流すラッパ |
| `XANGI_CRON_SPEC.md` | xangi の cron（schedule）の仕様・プロンプト設計の定石・実運用の事故記録 |
| `KAGGLE_WATCH_SPEC.md` | Kaggle Discussion / 公開コードの定点観測を xangi cron で回す仕様と移植手順 |
| `CLAUDE_USAGE_SPEC.md` | Claude 使用率監視の仕様（取得元・落とし穴・しきい値・常設ボード） |
| `KAGGLE_ELAPSED_TIME.md` | 提出の経過時間監視の再開手順（現行コア版との差分と、Discord に流す方法） |
| `reference/README.md` | xangi 本体側の資産の案内と patch の当て方 |
| `reference/bot-to-bot-mention-protocol.md` | bot 同士の会話プロトコル（なぜ・何を決めたか。故障 A / B） |
| `reference/bot-to-bot-code-changes.md` | 上のプロトコルのために xangi のどのファイルをどう変えたか |
| `reference/xangi_local_v0.49.6.patch` | 運用していた xangi のローカル差分の全文（v0.49.6 比） |
| `reference/scheduler-clock-drift.test.ts` | cron 再 arm（壁時計ジャンプ対策）の回帰テスト |

## 環境の落とし穴（実際に踏んだもの）

- **`TZ=Asia/Tokyo` が効かないコンテナがある**（zoneinfo 無し。黙って UTC のまま＝9 時間ズレる）。
  このフォルダのスクリプトは JST を `date -u -d '+9 hours'` / `timezone(timedelta(hours=9))` で出している。自分で足すときも同じにする
- **xangi の実行ユーザーの HOME と、Kaggle / Claude の認証の置き場がズレる**ことがある → `KAGGLE_CONFIG_DIR` / `CLAUDE_CREDENTIALS` など
- **2 体の bot は別コンテナ**。ファイルは共有でもプロセスは互いに見えない（`AGENTS.md` ルール 14）。
  bot ごとのもの（supervisor のロック、デーモンのログ）は `$XANGI_ROOT/logs/` や `/tmp` に、
  リポジトリで共有したい状態（使用率の通知履歴など）は `tools/xangi/` に置いてある
- **デーモンのスクリプトを書き換えたら必ず再起動する**。bash は実行中のファイルを逐次読むので、走ったまま編集すると壊れた内容を読む
