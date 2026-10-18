# bot 同士の会話プロトコル — 2026-08-06 修正まとめ

xangi（Agent A・Claude）と codex 系 bot（Agent B）を同じ Discord チャンネルに常駐させて会話させるための修正記録。
**2つの正反対の故障**を同時に直した。

| 故障 | 症状 | 一言でいうと |
|---|---|---|
| **A: 止まらない** | 「もう止めるね」と書いた返信でも会話が再点火する | 返信しただけで相手が起動していた |
| **B: 届かない** | #サーベイ で 17:54 から会話が完全停止。誰も気付けない | 本文の `<@BotID>` が実メンションになっていなかった |

結論として **「本文のメンションだけが会話の継続スイッチ」** に統一した。

---

## 1. 合意した規則

1. **継続スイッチは本文のメンション**。会話を続けたい返答には本文に `<@相手BotID>` を書く
2. **止めたいときはメンションを外す**。これが唯一の確実な停止方法
3. **返信（リプライ）形式は自由に使ってよい**。ただし返信通知だけでは相手を起動させない
4. **送信は「実メンション」で行う**。`allowed_mentions` を解決しない送信は届かないものとして扱う

---

## 2. 故障A: 会話が止まらない

### 原因

Discord の「返信」は、本文にメンションが無くても返信先ユーザーへのメンション（`replied_user`）を含む。
discord.js の `message.reply()` は既定が `repliedUser: true` なので、**返信するたびに相手を呼び出していた**。
相手が bot だとそれだけでターンが起動するため、「止める」と書いた返信ですら会話が終わらない。

### 直し方

**送信側**: 返信先が bot のときだけ `repliedUser: false` にする。人間への返信通知は従来どおり残す。

```ts
// src/discord/message-handler.ts
export function replyAllowedMentions(repliedTo: { author: { bot: boolean } }) {
  return { parse: ['users'], repliedUser: !repliedTo.author.bot };
}
```

**受信側**: bot 発言では `replied_user` を無視する（`ignoreRepliedUser: true`）。

| 返信先 | `repliedUser` | 効果 |
|---|---|---|
| bot | `false` | 返信しても相手のターンは起動しない |
| 人間 | `true` | 「ピコン」は今までどおり届く |

Client 既定は `{ parse: ['users'] }` のみ指定。`allowed_mentions` を明示すると `replied_user` は
Discord 側の既定 false が効くので、**安全側が既定・人間への通知だけ明示的に付け直す**向きに倒してある。
`@everyone` / `@here` / ロールは既定では解決しない。

---

## 3. 故障B: 会話が届かない（#サーベイ 停止の真因）

### 原因

**Discord は `allowed_mentions` で「本文の `<@ID>` を実際のメンションとして解決するか」を決める。**
解決せずに送ると、受信側には `message.mentions` が**空**のまま届く。

さらに厄介なのが次の2点:

- **画面上は青いメンション表示のまま**なので、送信側も人間も成功しているように見える
- discord.js の `MessageMentions#has(user, { ignoreRepliedUser: true })` は
  **「本文を解析した結果（`parsedUsers`）」と「Discord が解決した `mentions`」の両方**に載っていることを要求する
  → 未解決の本文メンションは無条件で落ちる

結果、Agent B 側の `discord_send` にメンション解決オプションが無かったため、
**Agent A は #サーベイ で一度も起動していなかった**。チャンネル設定の差ではなく送信経路の差。

### 直し方

**送信側**: メンション解決オプションを必ず有効化する。

```bash
xangi-cmd discord_send --channel <id> --message "<@BotID> 本文" --mention true
```

**受信側**: bot 発言に限り、Discord の解決結果に加えて**本文の文字列**も判定に使う（フォールバック）。
相手の送信経路が壊れていても会話が成立するようにするため。

```ts
export function hasTextMention(content: string, selfId: string): boolean {
  return new RegExp(`<@!?${selfId}>`).test(content ?? '');
}
```

---

## 4. 受信判定の最終形

```
自分自身の投稿                        → 反応しない（無限ループ防止）
bot発言 かつ RESPOND_TO_BOTS 対象外    → 反応しない
3層防御に引っかかる                    → 反応しない
本文が未確定（スピナー / 末尾カーソル） → 確定するまでポーリング（最大40秒）

isMentioned =
     mentions.has(self, { ignoreRepliedUser: 相手がbot })
  || (相手がbot && /<@!?selfId>/.test(確定後の本文))
```

- **文字列フォールバックは bot 発言のみ**。人間の経路は壊れていないので適用しない
- 判定は必ず **edit 確定後の最新 `content`** で行う。xangi 系 bot は
  `⠋ 考え中… 5s` を先に投稿してから edit で本文化するため、投稿時点の内容で判断すると永久に届かない
- ロールメンション `<@&id>` は自分宛て扱いしない

---

## 5. 変更したファイル（xangi 側）

| ファイル | 変更 |
|---|---|
| `src/index.ts` | Client 既定を `allowedMentions: { parse: ['users'] }` に。`@everyone`/ロールは解決しない |
| `src/discord/message-handler.ts` | `replyAllowedMentions()` / `hasTextMention()` / `isMentioningSelf()` を追加。初回返信・エラー返信の2箇所に適用 |
| `tests/discord-message-handler.test.ts` | 21件（メンション判定7件・返信メンション2件・本文確定判定10件・その他2件） |
| `docs/usage.md` / `docs/en/usage.md` | 「他 bot のメッセージへの応答」節に規則を追記 |

Agent B 側は、本文の文字列判定・ポーリング・`--mention` 相当は**元から実装済み**で、
今回 `repliedUser=false` を bot 宛てだけに限定する部分を揃えた（本人申告・テスト5件成功）。

---

## 6. 変えていない安全装置

会話の暴走を止める仕組みは今回いじっていない。メンション規則はあくまで「意図した会話」を制御するもので、
事故を止めるのはこちら。

| 層 | 設定 | 現在値 | 人間の発言でリセット |
|---|---|---|---|
| 第1層 | `RESPOND_TO_BOTS_MAX_CONSECUTIVE` | 6 | する |
| 第2層 | `RESPOND_TO_BOTS_COOLDOWN_MS` | 8000 (8秒) | **しない** |
| 第3層 | `RESPOND_TO_BOTS_WINDOW_MS` / `_MAX_PER_WINDOW` | 180000 (3分) / 8回 | **しない** |

第2層・第3層をリセットしないのが要点。人間が相槌を打つたびにカウンタが戻ると、
無限に燃料補給されて暴走が止まらなくなるため。

---

## 7. 落とし穴（次に触る人へ）

1. **青いメンション表示は「実メンション」の証拠にならない**。表示は本文の文字列だけで決まる。
   疑ったら受信側の `message.mentions` を見る
2. **`mentions.has(..., { ignoreRepliedUser: true })` は AND 条件**。
   「本文に書いてある」だけでは true にならない。これが故障B の直接原因
3. **文字列フォールバックの副作用**: bot が会話の中で相手の ID を `<@...>` 形式で引用すると、
   それだけで相手が起動する。ID を話題にするときはこの形式で書かない
4. **再起動しないと反映されない**。このコンテナには supervisor がいないので
   `xangi-cmd system_restart` は使わない（bot が死んだまま戻らない）。
   コンテナごと立て直すのが確実

   > 🔶 **追記（テンプレート化時・2026-10-18）: この項は古い。**
   > 2026-08-11 に supervisor（`tools/xangi/xangi_supervisor.sh`）を導入してからは、xangi が落ちても
   > 数秒で起こし直されるので `xangi-cmd system_restart` で再起動して反映してよい。
   > supervisor（または pm2 / systemd / Docker の restart policy）を**置いていない環境では、上の記述のとおり使わない**。
   > 経緯 → `../XANGI_CRON_SPEC.md` §10.2.3。上の本文は当時の記録として残している

---

## 8. 検証結果

| テスト | 内容 | 結果 |
|---|---|---|
| A | 本文に実メンションあり → 相手が起動するか | ✅ 起動した |
| B | 返信形式・本文メンション無し → 相手が沈黙するか | ✅ 150秒沈黙 |
| C | #サーベイ（故障Bの現場）での疎通 | ✅ 会話再開、議論継続中 |

---

## 関連

- 運用ルール → リポジトリ直下 `AGENTS.md` ルール 6 ／ xangi + Discord での具体的な作法 → `../README.md`
- 設定項目の一覧 → xangi の `docs/usage.md`「他 bot のメッセージへの応答（A/B 比較等）」
