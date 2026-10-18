# Claude レート制限（使用率）監視 仕様書

*作成: 2026-08-08 / 実体: `tools/xangi/claude_usage.py` + `tools/xangi/xangi_health_daemon.sh`*
*関連: `tools/xangi/XANGI_CRON_SPEC.md` §10.4（同じデーモンが cron 生存監視も兼ねる）*
*オプション機能（xangi + Discord で bot を回す人向け）。導入は `tools/xangi/README.md`*

## 0. これは何か

**Claude Code サブスクリプションの消費率（5時間枠 / 週次）を取得して、危なくなったら Discord に投げる**仕組み。
週次上限に当たると数日単位で作業が止まるので、「気づいたら残り 5%」を避けるのが目的。

## 1. どこから取るか

Claude Code の `/usage` が叩いているのと同じ OAuth エンドポイントを自前で叩く。

```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <accessToken>
anthropic-beta: oauth-2025-04-20
```

- **CLI に `claude usage` 相当のサブコマンドは無い**（`claude --help` の Commands に無い。
  あるのは agents / auth / auto-mode / doctor / gateway / import / install / mcp / plugin /
  project / setup-token / ultrareview / update）。なので自前で叩くしかない。
- エンドポイントは `claude` バイナリの文字列から特定した
  （`strings claude.exe | grep -oE '"/api/[a-z0-9_/-]+"'` に `"/api/oauth/usage"` がある）。
- **公開APIではないので、Claude Code の更新で壊れる可能性がある。**
  取得に失敗し続けたらまずここを疑う（`--json` で生レスポンスを見る）。

### 認証情報

`~/.claude/.credentials.json` の `claudeAiOauth.accessToken`。
**xangi の実行ユーザーの HOME と、Claude の認証の置き場がズレる環境がある**（実際にあった。
Kaggle 認証と同じ構図・`KAGGLE_WATCH_SPEC.md` 参照）。スクリプトは次の順に見る:

1. `CLAUDE_CREDENTIALS`（ファイルを直接指定）
2. `$CLAUDE_CONFIG_DIR/.credentials.json`
3. `~/.claude/.credentials.json`

- トークンは xangi が `claude` を動かすたびに自動更新される（有効期限は約4時間）。
- **CLAUDE.md の鍵の規約どおり、値は標準出力にも例外メッセージにも出さない。**
  失敗時に出すのは HTTP ステータスと例外の型名だけ。

## 2. レスポンスの読み方（2026-08-08 実測）

```json
{
  "five_hour":  {"utilization": 21.0, "resets_at": "2026-08-08T12:09:59.420056+00:00", ...},
  "seven_day":  {"utilization": 68.0, "resets_at": "2026-08-12T14:59:59.420076+00:00", ...},
  "seven_day_opus": null, "seven_day_sonnet": null,
  "limits": [
    {"kind": "session",       "percent": 21, "severity": "normal", "is_active": false},
    {"kind": "weekly_all",    "percent": 68, "severity": "normal", "is_active": true},
    {"kind": "weekly_scoped", "percent": 0,  "scope": {"model": {"display_name": "Fable"}}}
  ],
  "extra_usage": {"is_enabled": false, ...},
  "spend": {"enabled": false, ...}
}
```

- **見るのは `five_hour` と `seven_day` の `utilization`（%）だけでよい。**
  `limits[]` は同じ数字の別表現。`*_dollars` はこのプラン（`max` / `default_claude_max_20x`）では全部 `null`
- `seven_day_opus` / `seven_day_sonnet` などモデル別の枠は現状 `null`。将来値が入る可能性はある
- `weekly_scoped`（Fable 枠）は 0% のうちは表示しない設計にした（常時 0 だと邪魔なので）
- `extra_usage.is_enabled: false` ＝ **追加クレジットが無いので、上限に当たったらそこで止まる**

## 3. 【重要】実測で踏んだ落とし穴 2つ

### 3.1 `resets_at` はリクエストごとに揺れ、しかも分の境界をまたぐ

同じ枠なのに `...14:59:59.420076` → `...14:59:59.521764` と変わる。
**文字列のまま前回値と比較すると、毎回「枠がリセットされた」と誤判定して通知が暴れる。**

さらに厄介なのは、**値が分の境界に張り付いている**こと。丸めても揺れが境界をまたぐ:

```
17:09:59.420076  → 分丸め 17:09
17:10:00.790901  → 分丸め 17:10   ← 同じ枠なのに別枠に見える
```

分丸めで実装した結果、**2026-08-08 に「週次がリセットされました」の誤報を 2 回出した**
（週次のリセットは 8/12 なので、実際には何も起きていない）。

→ `reset_epoch()` で epoch 秒にし、`same_window()` で **±5分の許容差**をつけて比較する。
枠の間隔は 5 時間・7 日なので、この程度の許容差で取り違えることはない。

> **教訓**: 丸めは「境界に張り付いた値」には効かない。**同一性の判定は許容差で書く。**

### 3.2 このエンドポイント自体がレート制限される

短時間に数回叩いたら **HTTP 429** を返した（実測）。監視で毎分ポーリングするような設計にはできない。

→ 対処:
- **ローカルキャッシュ**（`tools/xangi/.claude_usage_cache.json`、既定 300 秒）を挟む。
  この期間内の再実行は API を叩かずキャッシュを返す
- 429 / 通信断は `UsageTransient` として扱い、**キャッシュがあればそれで凌ぐ / 無ければ黙って諦める**。
  監視は無投稿のまま次の周回に任せる（一時障害で通知を汚さない）
- 認証切れのような**人が動かないと直らない失敗だけ** `UsageError` として通報する

### 3.3 トークンの期限切れは「故障」ではない。鳴らすと毎晩スパムになる

アクセストークンの寿命は約 4 時間で、**`claude` が動くたびに更新される**。
つまり期限切れ＝**誰も bot を使っていない**という意味であって、壊れてはいない。
誰かが話しかけた瞬間に自動で直る。

これを「認証切れ＝人が動く必要のある失敗」に分類していたため、
**2026-08-09 の未明〜朝（3:00〜10:19、bot が誰にも使われていない時間帯）に、
同じエラーを 15 分おきに 6 連投した。** しかも毎晩再発する構造だった。

→ `UsageIdle` として分離し、**通報しない**（ボードは直近値のまま維持）。

あわせて、**取得エラー全般に重複抑制が無かった**のも直した。
本物のエラー（401・API 変更等）は `ERROR_REALERT_H`（既定 12 時間）に 1 回だけ通報し、
復旧したら「✅ 復旧しました」を 1 回出す。

| 分類 | 例 | 通報するか |
|---|---|---|
| `UsageIdle` | トークン期限切れ | **しない**（bot が使われれば直る） |
| `UsageTransient` | 429 / 通信断 | **しない**（キャッシュで凌ぐ） |
| `UsageError` | 401 / 認証情報が無い / API 変更 | **する**（12時間に1回まで） |

> **教訓**: 「異常を検知したら鳴らす」の前に、**「鳴らして人が何かできるか」**を問う。
> できないなら鳴らすだけ通知を汚す。「無投稿設計は沈黙と正常を区別できない」（`XANGI_CRON_SPEC.md` §5.3）
> の逆（**鳴らしすぎて誰も読まなくなる**）も同じくらい監視を殺す。

## 4. コマンド

```bash
cd <REPO>   # このリポジトリの直下

python3 tools/xangi/claude_usage.py            # 人が読む要約（バー付き）
python3 tools/xangi/claude_usage.py --brief    # 1行
python3 tools/xangi/claude_usage.py --json     # 生JSON（API変更を疑う時)
python3 tools/xangi/claude_usage.py --check    # しきい値を跨いだ時だけ出力（常駐監視用・正常時は無出力）
python3 tools/xangi/claude_usage.py --force    # キャッシュを無視して取りに行く（429に注意）
```

出力例:

```
5時間枠      █████░░░░░░░░░░░░░░░  23.0%  リセット 08/08 21:09 あと42分
週次(7日)    ██████████████░░░░░░  69.0%  リセット 08/12 23:59 あと99時間32分
追加クレジット: 無効（上限に当たったら止まる）
```

## 5. しきい値と重複抑制

| レーン | 鳴らす段 | 考え方 |
|---|---|---|
| `seven_day`（週次） | **50 / 70 / 80 / 90 / 95%** | 枯れると数日止まる。早めから刻む |
| `five_hour`（5時間枠） | **50 / 70 / 80 / 90 / 95%** | 当初は 80 からにしたが、人間の「5時間のほうも見たい」で週次と同じ刻みに（2026-08-08）。消費の**速さ**が見える |

- 状態は `tools/xangi/.claude_usage_state.json` に「枠のリセット時刻（epoch）＋最後に鳴らした段」を持つ。
  **同じ段は二度鳴らさない**。段が上がった時だけ鳴る
- **状態とキャッシュは `/tmp` ではなく `tools/xangi/` 配下**（`tools/xangi/.gitignore` 済。`CLAUDE_USAGE_DIR` で変更可。
  2 体の bot が同じリポジトリを共有して両方でこれを回すなら、bot ごとに分ける）。
  `/tmp` はコンテナ再起動で消え、そのたびに同じ段を鳴らし直してしまう（2026-08-08 に実際に発生）
- 枠がリセットされたら状態を捨て、直前に鳴っていた場合だけ「✅ リセットされました」を1回出す
- アイコンは段で変える: 90%以上 🚨 / 70%以上 ⚠️ / それ未満 📊

## 6. どこで動いているか

`tools/xangi/xangi_health_daemon.sh`（**LLM 不使用の常駐デーモン・15分周期**）が兼務する。
cron 側に載せていないのは、cron が詰まると気づけないから（`XANGI_CRON_SPEC.md` §5.2 / §10.4）。

```
15分ごと:
  ① kaggle_watch_health.py --auto   → 異常なら <HEALTH_CHANNEL>（定点観測）へ
  ② claude_usage.py --check         → しきい値を跨いだ時だけ <USAGE_CHANNEL>（rate-limit）へ
  ②' claude_usage.py --gauge        → 30 分ごとにゲージ 2 行を <USAGE_CHANNEL> へ（USAGE_GAUGE_MIN・0 で無効）
  ③ USAGE_DAILY_HOUR 時台の初回のみ → 使用量スナップショットを <USAGE_CHANNEL> へ（メンション無し・既定は無効）
  ④ claude_usage.py --board         → 常設ボードを**編集で**更新（<USAGE_CHANNEL>・USAGE_BOARD=1 のときだけ）
```

### 6.1 常設ボード（`--board`）

「今どれくらい使っているか」を常に見られるようにするための **1 通**。
15 分ごとに投稿すると 1 日 96 通でチャンネルが流れてしまうので、**同じメッセージを編集し続ける**。

- 本文の先頭に `📟 **Claude 使用量ボード**` という目印を入れてある。**これは変えない**
  （`discord_send` は message id を返さないので、投稿後に `discord_history` からこの目印で引き当てている）
- message id は `tools/xangi/.claude_usage_board.json` に保存。編集が失敗したら（＝人が消した等）
  自動で投稿し直して id を取り直す
- **取得に失敗した回はボードを書き換えない**（前の表示を残す）。
  期限切れキャッシュで凌いだ時だけ「⚠️ 取得に失敗したため直近値を表示中」を出す
- ボードには **5時間枠の「進み具合」** も出す:
  `時間 32% 消化 / 枠 7% 消費 → 余裕あり`。
  時間の経過より枠の消費が速ければ「時間より速く消費中」＝このペースだと枠を使い切る、という読み方

> `--board` の出所表示は 3 値（`live` / `cache` / `stale`）で区別している。
> 300 秒キャッシュの再利用（`cache`）は**正常**なので警告を出さない。当初これを
> 「取得できず」と表示してしまい、正常時にも警告が出ていた（2026-08-08 に修正）。

環境変数で変えられる: `USAGE_CHANNEL`（投稿先・必須）/ `USAGE_DAILY_HOUR`（日次の JST 時刻、既定 `-1` ＝無効）/
`USAGE_GAUGE_MIN` / `USAGE_BOARD` / `ENABLE_USAGE`（`0` でこの監視ごと無効）。

> コンテナのシステム時計は **UTC**。デーモンは `date -u -d '+9 hours'` で JST を出している。
> 🔴 `TZ=Asia/Tokyo` は使わない。zoneinfo の無いコンテナでは**黙って UTC のまま**になり、9 時間ズレる（実際に踏んだ）。

## 7. 運用メモ

- **週次が 80% を超えたら、重い実験の同時走行を控える**判断材料にする。
  リセット時刻は `resets_at` に出るので、「あと何時間耐えれば戻るか」で判断できる
- 使用率が上がる主因は cron レーンの発火回数と長時間セッション。
  定型の垂れ流しをデーモンへ寄せるほど消費は減る（`XANGI_CRON_SPEC.md` §5.4 と同じ話）
- 取得が壊れたら: ①`--json` で生レスポンスを見る ②`claude --help` の Commands を再確認
  （公式サブコマンドが生えていたらそちらへ乗り換える）③バイナリの文字列からエンドポイントを再特定する
