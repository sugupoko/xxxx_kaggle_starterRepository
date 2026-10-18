# bot 会話まわり — ソースコード変更まとめ（2026-08-06 / xangi 側）

`bot-to-bot-mention-protocol.md` が「なぜ・何を決めたか」、この文書が **「どのファイルをどう書き換えたか」**。
（どちらも当時は xangi リポジトリの `docs/` に置いていた。差分の全文は `xangi_local_v0.49.6.patch`。
この文書の時点は 11 ファイルで、その後 cron の再 arm などが足されて patch は 14 ファイルになっている）

対象は現在の作業ツリー差分（**未コミット**）:

```
 docs/en/usage.md                        |   6 +
 docs/usage.md                           |   6 +
 src/cli/discord-api.ts                  |  12 +-
 src/cli/xangi-cmd-help.ts               |   7 +-
 src/config.ts                           |  18 +++
 src/discord/message-handler.ts          | 261 ++++++++++++++++++++++++++---
 src/index.ts                            |  10 ++
 src/safe-env.ts                         |   3 +   ← 今回の件とは無関係
 src/slack.ts                            |   8 +-
 src/stream-session.ts                   |  10 ++
 tests/discord-message-handler.test.ts   | 188 +++++++++++++++++++-
 11 files changed, 500 insertions(+), 29 deletions(-)
```

---

## 1. `src/index.ts` — 送信メンションの既定値

Discord Client に `allowedMentions` を追加した（10行）。

```ts
const client = new Client({
  intents: [...],
  partials: [Partials.Message, Partials.Channel],
  // 送信時のメンション既定値。
  // - parse: ['users'] → 本文中の実メンションは通す（bot 同士の会話継続スイッチとして必要）。
  //   @everyone / @here / role は誤爆の影響が大きいので既定では解決しない。
  // - repliedUser は指定しない = Discord 側の既定 (false) が効き、「返信しただけ」では
  //   相手を通知しない。人間への返信だけは通知を残したいので、返信元を見て明示的に付け直す。
  allowedMentions: { parse: ['users'] },
});
```

**ポイント**: `repliedUser` を**あえて書かない**。`allowed_mentions` を明示すると Discord 側の既定
（`replied_user: false`）が効くので、**安全側が既定**になる。新しい返信箇所をうっかり足しても
bot にピンが飛ばない向きへ倒れる。

---

## 2. `src/discord/message-handler.ts` — 本体（+261行）

### 2-1. 返信メンションの制御（故障A: 会話が止まらない）

**追加した関数**:

```ts
export function replyAllowedMentions(repliedTo: { author: { bot: boolean } }): {
  parse: ['users'];
  repliedUser: boolean;
} {
  return { parse: ['users'], repliedUser: !repliedTo.author.bot };
}
```

**適用箇所は2つだけ**（どちらも人間が起点になりうる返信）:

```ts
// ① 初回返信（resolveDiscordMessageTarget 内）
sendInitial: (options: MessageReplyOptions) =>
  newThread
    ? newThread.send(options)                                   // スレッドは返信ではないので対象外
    : message.reply({ ...options, allowedMentions: replyAllowedMentions(message) }),

// ② エラー返信
await message
  .reply({ content: errorMessage, allowedMentions: replyAllowedMentions(message) })
  .catch(() => {});
```

返信候補ボタン（`processReplySuggestion`）と Web 経由のミラー投稿は**自分自身への返信**なので対象外。

型も1つ変更: `sendInitial` の引数を `Parameters<Message['reply']>[0]`（`string | MessagePayload |
MessageReplyOptions` の union）から `MessageReplyOptions` に狭めた。オプションを spread して
`allowedMentions` を差し込むため。

### 2-2. 呼ばれ判定（故障B: 会話が届かない）

**変更前**:

```ts
const isMentioned = message.mentions.has(client.user!);
```

**変更後**:

```ts
const effectiveMessage = settledBotMessage ?? message;   // edit 確定後の Message
const isMentioned = isMentioningSelf(effectiveMessage.mentions, client.user!, {
  fromBot: message.author.bot,
  content: effectiveMessage.content,
  selfId: client.user!.id,
});
```

**追加した関数**:

```ts
/** 本文の文字列として `<@id>` / `<@!id>` が書かれているか（Discord の解決状況は見ない） */
export function hasTextMention(content: string, selfId: string): boolean {
  return new RegExp(`<@!?${selfId}>`).test(content ?? '');
}

export function isMentioningSelf<TUser>(
  mentions: { has: (user: TUser, options?: { ignoreRepliedUser?: boolean }) => boolean },
  selfUser: TUser,
  options: { fromBot: boolean; content?: string; selfId?: string }
): boolean {
  if (mentions.has(selfUser, { ignoreRepliedUser: options.fromBot })) return true;
  if (!options.fromBot || !options.selfId) return false;
  return hasTextMention(options.content ?? '', options.selfId);
}
```

3行に要点が全部入っている:

| 行 | 意味 |
|---|---|
| `ignoreRepliedUser: options.fromBot` | bot 発言では返信ピンを無視（故障A の受信側） |
| `if (!options.fromBot ...) return false` | 文字列フォールバックは **bot 限定**。人間の経路は壊れていない |
| `hasTextMention(...)` | 送信側がメンションを解決していなくても届く（故障B の受信側） |

### 2-3. 本文の確定待ち（相手のストリーミング投稿対策）

xangi 系 bot は `⠋ 考え中… 5s` を先に投稿し、あとから edit で本文化する。
MessageCreate 時点の内容で判定すると、スピナー文字列をプロンプトとして受け取ってしまう。

```ts
const BOT_SETTLE_POLL_INTERVAL_MS = 2_000;
const BOT_SETTLE_MAX_WAIT_MS = 40_000;

export function isEphemeralStatusMessage(rawContent: string): boolean  // まだ書きかけか
function isNeverSettling(rawContent: string): boolean                  // 🔧 / ✅ は本文化されない
async function waitForBotMessageSettled(message: Message): Promise<Message | null>
```

判定対象は「メンションのみ・空」「スピナー始まり」「末尾が `▌`」「🔧 / ✅ 始まり」。
`current.fetch()` で 2秒おきに最大40秒ポーリングする（discord.js はキャッシュ済みインスタンスを
`_patch` して返すので `content` も `mentions` も最新化される）。

配置は**メンション判定より前**。後ろに置くと自動応答 ON のチャンネルで途中経過に反応してしまう。

### 2-4. 暴走防止の3層防御

判定順を整理し、**カウンタの記録位置を「実際に応答すると決まった後」へ移した**。
前段で記録すると、自分宛てでない bot 発言でクールダウンや時間窓を食い潰してしまうため。

```ts
// 前段: 上限に達していたら return（記録はしない）
// ...メンション / DM / 自動応答チャンネルの判定...
if (!isMentioned && !isDM && !isAutoReplyChannel) return;

// ここまで来た = 実際に応答する。3層のカウンタはこの時点で記録する
if (isFromAllowedBot) {
  consecutiveBotResponses.set(...);   // 第1層
  lastBotResponseAt.set(...);         // 第2層
  botResponseTimes.set(...);          // 第3層
}
```

---

## 3. `src/config.ts` — 3層防御の設定（+18行）

```ts
respondToBotsCooldownMs?: number;    // 【第2層】default 8000
respondToBotsWindowMs?: number;      // 【第3層】default 60000
respondToBotsMaxPerWindow?: number;  // 【第3層】default 6
```

`.env` の現在値は `COOLDOWN_MS=8000` / `WINDOW_MS=180000` / `MAX_PER_WINDOW=8` /
`MAX_CONSECUTIVE=6`。第2層・第3層は**人間の発言でリセットしない**のが要点。

---

## 4. `src/cli/discord-api.ts` — `discord_send --mention`

```ts
const enableMention = flags['mention'] !== undefined && flags['mention'] !== 'false';
const allowedMentions = enableMention ? { parse: ['users'] } : { parse: [] };
// ...
body: JSON.stringify({ content: chunk, allowed_mentions: allowedMentions }),
```

既定は `parse: []`（本文の `<@id>` は文字列として表示されるだけ）。
bot を呼ぶときだけ `--mention true` で user メンションを解決する。
`@everyone` / role は `--mention true` でも解禁しない。

## 5. `src/cli/xangi-cmd-help.ts` — help に注意書き3点

`--mention true` の必要性、**値なしの `--mention` は次の `--message` を値として食う**という
フラグ解析の落とし穴、user メンション限定であること。

## 6. `src/stream-session.ts` / `src/slack.ts` — カーソル記号の共有

```ts
export const STREAMING_CURSOR = '▌';
export const STREAMING_CURSOR_SUFFIX = ` ${STREAMING_CURSOR}`;
```

描画側（Discord / Slack のストリーミング表示）と判定側（`isEphemeralStatusMessage`）で
同じ定数を使う。片方だけ変えると「書きかけを確定と誤認する」バグに直結するため、
`' ▌'` のハードコードを全部この定数に置き換えた。

## 7. `tests/discord-message-handler.test.ts` — 21件

| describe | 件数 | 内容 |
|---|---|---|
| `shouldProcessDiscordMessage` | 2 | 既存 |
| `isEphemeralStatusMessage` | 10 | スピナー / カーソル / 🔧 / 引用文の誤検知回避 |
| `isMentioningSelf` | 7 | 返信のみ→無視、本文メンション→起動、未解決メンション→起動、人間は従来どおり |
| `replyAllowedMentions` | 2 | bot 宛て `false` / 人間宛て `true` |

`isMentioningSelf` のテストでは discord.js の `MessageMentions#has` と同じ意味論を持つ
スタブを使っている（`users` = 本文メンション + 返信先、`parsedUsers` = 本文のみ）。

## 8. `docs/usage.md` / `docs/en/usage.md`

「他 bot のメッセージへの応答（A/B 比較等）」の節に、継続スイッチ・停止方法・
文字列フォールバックとその副作用を追記。

## 9. ⚠️ `src/safe-env.ts` — 今回の件とは無関係

`CLAUDE_CONFIG_DIR` を `ALLOWED_ENV_KEYS` に追加。落とすと子プロセスが `$HOME/.claude` を見に行き
"Not logged in" になる、という別件の修正が同じ作業ツリーに乗っている。
**コミットを分けるならここは別コミットにする。**

---

## 設計判断（なぜこうしたか）

1. **既定を安全側に倒し、例外だけ明示する**
   `repliedUser` は既定で飛ばさず、人間への返信でだけ `true` を付け直す。
   逆向き（既定 true・bot だけ false）にすると、返信箇所を1つ足すたびに事故る余地が残る

2. **文字列フォールバックは bot 限定**
   人間の送信経路は壊れていないので緩める理由がない。適用範囲を狭くするほど
   「ID を引用しただけで起動する」副作用の被害面積が小さくなる

3. **メンション規則と暴走防止は別レイヤーとして扱う**
   メンション規則は「意図した会話」の制御、3層防御は「事故」の制御。
   混ぜると、規則を緩めたときに安全装置まで緩んでしまう

---

## 状態と次のアクション

- ビルド済み・稼働中（2026-08-07 06:36 起動のプロセスに反映済み）
- `tsc --noEmit` / eslint / 21件のテスト / build すべてクリーン
- **全部まだ未コミット**。コミットするなら「bot 会話まわり」と「`safe-env.ts` の別件」で
  2つに分けるのが素直
