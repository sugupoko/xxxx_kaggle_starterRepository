# Kaggle 定点観測ウォッチャー 仕様書 ＆ 他コンペ移植手順

xangi（Discord bot）から cron で叩いて、Kaggle コンペの **Discussion（ホスト告知）** と
**公開ノートブック（パブリックコード）** の差分だけを Discord に流す仕組みの仕様。
コンペ非依存に書いてあるので、`KAGGLE_WATCH_SLUG` を差し替えれば他コンペにそのまま使える。

- 実体（**コア側**）: `tools/kaggle_disc_watch.py` / `tools/kaggle_code_watch.py`
  - ウォッチャー自体は xangi に依存しない（差分を stdout に出すだけ）。手で叩いても、別の cron で回してもよい
  - この文書（`tools/xangi/` 側）は「**xangi の cron で回して Discord に流す**」運用の仕様
- 2 つのコンペで運用（2026-06〜10）。Kaggle CLI 2.2.4 で動作確認済み

> **環境差分（重要）**
> xangi の実行ユーザーの HOME と、Kaggle の認証・CLI の置き場がズレる環境があった
> （HOME は別ユーザーなのに `kaggle.json` と `kaggle` が別の HOME 側にある）。その場合だけ
> `KAGGLE_CONFIG_DIR` / `KAGGLE_BIN` / `KAGGLE_SITE_PACKAGES` を指定する（素の環境なら不要）。
> ほかに `KAGGLE_WATCH_SLUG`（必須）/ `DISC_PAGES` / `VOTE_DELTA_REPORT` で挙動を変えられる。

---

## 1. 全体設計

```
xangi cron (30分毎ポーリング)
    └─> python3 tools/kaggle_XXX_watch.py
            ├─ Kaggle CLI (CSV出力 -v) で最新一覧を取得
            ├─ state JSON と比較して「前回実行からの差分」だけ stdout に出す
            └─ state を今回の観測値で上書き
    └─> 出力あり: LLM が日本語要約して Discord 投稿
        出力なし: 空文字を返す = 無投稿（xangi が空応答を握り潰す仕様を利用）
```

設計上のキモは3つ:

1. **差分ベース（state ファイル）** なので、何回叩いても重複投稿しない
   → だから「1日1回の正確な発火」に頼らず、**多数回ポーリングして1回でも当たればいい**設計にできる
2. **空出力＝無投稿**。新着ゼロの日はチャンネルが汚れない
3. **要約は LLM 側**。スクリプトは生の差分テキストを吐くだけで、重要度判定（ホスト告知/ルール変更/締切）はプロンプトの仕事

---

## 2. Discussion ウォッチャー（`kaggle_disc_watch.py`）

### 2.1 目的
コンペ主催（ホスト）の告知・ルール変更・締切・バグ修正・仕様回答を取りこぼさない。

### 2.2 動作仕様

| 項目 | 内容 |
| --- | --- |
| 取得API | `kaggle competitions topics list <SLUG> --sort-by new -p N -v -q` |
| 取得範囲 | `PAGES`（env `DISC_PAGES`。20件/ページ × N。当初 2 = **最新40トピック**、コア側の既定は 3） |
| 詳細取得 | `kaggle competitions topic-messages <SLUG> <topic_id> --sort-by old\|new -n N -v -q` |
| state | `tools/.kaggle_disc_watch.json` … `{topic_id: commentCount}` |
| 差分1 | state に無い topic_id → **🆕 新トピック**（最初の投稿＝スレ主/ホスト告知の冒頭 240 字） |
| 差分2 | commentCount が増加 → **💬 新着返信×N**（増分 N 件を新しい順に取得、各 200 字） |
| state更新 | 毎回、今回観測した窓（PAGES×20 件）で丸ごと上書き（一覧から消えた topic は state から落ちる） |
| 初回/`--seed` | state を記録するだけで **出力なし**（過去ログの大量投稿を防ぐ） |
| HTML処理 | `strip_html()` でタグ除去。`<a href=X>Y</a>` → `Y(X)` に畳んでリンクを保つ |

### 2.3 出力フォーマット（stdout）

```
🆕 **新トピック** [Second Round Information]
  https://www.kaggle.com/competitions/<SLUG>/discussion/732331
  (2026-08-02 11:00:01) As the Simulation Category enters its final stage, …

💬 **新着返信×2** [Game Engine Source Code]
  https://www.kaggle.com/competitions/<SLUG>/discussion/717141
  ・(2026-08-01 22:46:30) could you please confirm whether the official engine supports…
```

差分が無ければ **標準出力は完全に空**（`--seed`/初回のみ stderr に `[seed] N topics` を出す）。

### 2.4 使い方

```bash
KAGGLE_WATCH_SLUG=<SLUG> python3 tools/kaggle_disc_watch.py          # 差分を出力（無ければ無出力）
KAGGLE_WATCH_SLUG=<SLUG> python3 tools/kaggle_disc_watch.py --seed   # state を作り直すだけ（以後の差分から拾う）
```

---

## 3. パブリックコード ウォッチャー（`kaggle_code_watch.py`）

Discussion 版と同型。公開ノートブックの **新規公開** と **票の急増（注目度）** を検知する。

| 項目 | 内容 |
| --- | --- |
| 取得API | `kaggle kernels list --competition <SLUG>` を2系統で取得して dedup |
| 系統1 | 直近更新順（`dateRun`）… `RECENT_PAGES = 3`（最新60件）→ 新規公開の検知 |
| 系統2 | 票数順（`voteCount`）… `TOP_PAGES = 2`（上位40件）→ 票の伸びの検知 |
| state | `tools/.kaggle_code_watch.json` … `{ref: totalVotes}` |
| 差分1 | state に無い ref → **🆕 新規ノートブック** |
| 差分2 | 票が `VOTE_DELTA_REPORT = 10` 以上伸びた → **📈 注目度急上昇** |

閾値 `VOTE_DELTA_REPORT` はコンペの規模で調整する（参加者が多いコンペなら 20〜30 に上げないと鳴りっぱなしになる）。

---

## 4. cron 仕様（xangi スケジューラ）

### 4.1 登録内容（運用していた形）

```
[Discussion]
  ID     : s_xxxxxxxx_xxxx     (schedule_add が払い出す。作り直すたびに変わる)
  cron式 : 0,30 7-12 * * *     (JST基準 / 朝7:00〜12:30に30分毎 = 12回)
  報告先 : #ディスカッション (<CHANNEL_ID>)

[パブリックコード]
  ID     : s_xxxxxxxx_xxxx
  cron式 : 15,45 7-12 * * *    (Discussion とズラして同時発火を避ける)
  報告先 : #ディスカッション (<CHANNEL_ID>)
```

> 🔴 **cron 式は `tools/xangi/kaggle_watch_health.py` の `LANES` と文字列で一致させる。**
> 生存監視（`xangi_health_daemon.sh`）は schedules.json をこの式で照合している。式を変えたら両方直す。

> **時刻は JST 解釈**。コンテナの `date` は UTC なので、state ファイルの mtime を見るときは +9h して読むこと
> （例: mtime `2026-08-02 23:30 UTC` = `8/3 8:30 JST` に実行された）。

### 4.2 プロンプト（Discussion 版・そのまま流用可）

`<SLUG>` と観測対象の説明だけ差し替えれば他コンペで使える。

```text
[定点観測:Kaggle日次] cd <REPO_DIR> && KAGGLE_WATCH_SLUG=<SLUG> python3 tools/kaggle_disc_watch.py を実行。
出力(過去24h分の新トピック/公式スレ新着返信=コンペホストの告知やルール解説を含む)があれば
日本語で要点を簡潔にまとめ、ホストの告知・ルール変更・締切・バグ修正など我々の作業に効く情報は
特に強調して報告。各項目にKaggleリンクも付ける。
【重要】出力が空(=新着なし)の場合は何も書かず空文字だけを返すこと(挨拶も絵文字も一切書かない=無投稿にする)。
このcronは取りこぼし対策で日中複数回発火する設計なので、新着がある初回だけ投稿されればよい。
<bot の人格・書式の指定（例: 一人称わたし/さん付け/絵文字）>で。
```

### 4.3 プロンプト（パブリックコード版）

```text
[定点観測:パブリックコード] cd <REPO_DIR> && KAGGLE_WATCH_SLUG=<SLUG> python3 tools/kaggle_code_watch.py を実行。
出力(新規公開ノートブック=🆕 / 既存NBの票急増=📈)があれば日本語で要点を簡潔にまとめる。
特に <このコンペで効く技術キーワード> など、わたしたちの作業に効くものを強調。各項目にKaggleリンクを付ける。
【重要】出力が空(=新規なし)の場合は何も書かず空文字だけを返すこと(挨拶も絵文字も一切書かない=無投稿)。
このcronは取りこぼし対策で日中複数回発火する設計なので、新規がある初回だけ投稿されればよい。
<bot の人格・書式の指定>で。
```

### 4.4 運用コマンド

```bash
xangi-cmd schedule_list                              # 一覧・ID確認
xangi-cmd schedule_add --input "<上のプロンプト>" --channel <チャンネルID>
xangi-cmd schedule_toggle --id <ID>                  # 一時停止/再開
xangi-cmd schedule_remove --id <ID>                  # 削除
```

`schedule_add` の `--input` 先頭に `cron 0,30 7-12 * * * ` を付けると cron 式で登録できる。

---

## 5. 他コンペへの移植手順

1. **スクリプトはコア側 `tools/` にある**（テンプレートに同梱。コピー不要）
2. **slug を決める**（URL の `/competitions/<ここ>`）。cron のプロンプトで `KAGGLE_WATCH_SLUG=<SLUG>` を前置する
   - `kaggle` が PATH に無い環境では `KAGGLE_BIN` も前置する（素の環境なら不要）
   - state ファイル名は `Path(__file__).parent` 基準（`tools/.kaggle_*_watch.json`）。
     **同じ tools/ で複数コンペを回すなら**、§5.1 のように state ファイル名を slug 付きにすること
3. **コンペ規模に合わせて閾値調整**
   - 討論が活発なコンペ → `PAGES` を 3〜5 に（40件窓から公式スレが溢れるのを防ぐ、§6-2 参照）
   - 参加者が多いコンペ → `VOTE_DELTA_REPORT` を 20〜30 に
4. **seed する**（これを忘れると初回に過去全件が流れる）
   ```bash
   KAGGLE_WATCH_SLUG=<SLUG> python3 tools/kaggle_disc_watch.py --seed
   KAGGLE_WATCH_SLUG=<SLUG> python3 tools/kaggle_code_watch.py --seed
   ```
5. **cron 登録**（§4.2 / §4.3 のプロンプト、`<REPO_DIR>` と強調キーワードを差し替え）
6. **動作確認**: 手動で1回実行して無出力になること、翌朝 state の mtime が更新されていることを見る

### 5.1 オプション: 1ファイルで複数コンペを回す

slug は既に環境変数（`KAGGLE_WATCH_SLUG`）で切り替えられる。複数コンペを同時に回すなら state も分ける最小パッチ
（**state ファイル名が変わるので導入時は再 seed が必要**。生存監視の `LANES` のファイル名も合わせる）:

```python
STATE = Path(__file__).resolve().parent / f".kaggle_disc_watch_{SLUG}.json"
```

---

## 6. 既知の制約・ハマりどころ

1. **著者名が取れない**
   - Kaggle API は `authorName` を**全て空**で返す → 「ホストの発言だけ」フィルタは実装不可能
   - 対策: 新トピック＋全スレの新着返信を拾い、**重要度の選別は LLM 側の要約プロンプトに任せる**
2. **監視窓は「最新 N トピック」だけ**
   - `PAGES=2` → 40件。フォーラムが伸びて古い公式スレ（Welcome / Rules / Important Info 等）が窓から溢れると、
     そのスレへのホスト返信を**取りこぼす**
   - さらに、溢れた後にそのスレが再浮上すると state に無いので **「🆕 新トピック」と誤検知**する
   - 対策: 活発なコンペでは `PAGES` を増やす／公式スレ ID を常時監視するホワイトリストを足す
3. **プロンプトの「過去24h分」は厳密には不正確**
   - 実際は「**前回実行からの差分**」。数日止まっていれば数日分まとめて出る（実害は薄いが仕様として認識しておく）
4. **node-cron が発火をまるごと落とす**（この箱の根本問題・2026-06-30 判明）
   - シム/学習で CPU が飽和し、イベントループが1秒以上ブロックされると **cron の発火がスキップされ、後追い実行もされない**
   - 同時刻に別 cron が走ってエージェントが埋まっている場合も同様に沈黙する（`runningJobs` ガード）
   - **1発勝負の `0 9 * * *` にしてはいけない**理由がこれ。だから 30 分毎ポーリング＋差分 dedup という形になっている
   - その後、WSL2 の壁時計ジャンプで node-cron が発火を捨てていた真犯人も見つかった（`XANGI_CRON_SPEC.md` §10.2.2）
5. **それでも落ちる時は落ちる**
   - 実測: 2026-08-03 8:30 JST を最後に 8/4・8/5 は Discussion 版が1回も走らなかった
   - **恒久策**: OS 常駐の bash デーモンを置くのが確実。実際に入れたのが `tools/xangi/xangi_health_daemon.sh`
     （state が古いレーンを検知して通報し、発火窓の中なら `xangi-cmd trigger` で直接起こす＝バックストップ。
     `XANGI_CRON_SPEC.md` §10.2.3 / §10.4）
6. **API レート制限**
   - `topic-messages` は差分があるトピックの数だけ叩く。大量の新着があると呼び出しが増えるので、
     429 が出るようなら `PAGES` を絞るか実行間隔を空ける

---

## 7. 生存確認（デバッグ手順）

```bash
# 1) cron が登録されているか
xangi-cmd schedule_list

# 2) 最後に走ったのはいつか（state の mtime。UTC 表示なので +9h で JST）
ls -la --time-style=full-iso tools/.kaggle_*watch*.json

# 3) スクリプト自体は生きているか（手動実行）
KAGGLE_WATCH_SLUG=<SLUG> python3 tools/kaggle_disc_watch.py ; echo "exit=$?"

# 4) Kaggle CLI の認証が生きているか（KAGGLE_BIN を使っているならそのパスで）
kaggle competitions topics list <SLUG> -v -q | head -3

# 5) 生存監視の判定をその場で見る（無出力＝正常）
XANGI_ROOT=<xangi のディレクトリ> python3 tools/xangi/kaggle_watch_health.py --auto
```

`3)` が無出力・`exit=0` なら **正常（新着なし）**。エラーが出るなら CLI のバージョン差（CSV ヘッダ位置）か認証切れを疑う。
