# tools/xangi/reference/ — bot 本体（別リポジトリ `xangi`）側の資産

このフォルダだけは**実験管理リポジトリの外**（`https://github.com/karaage0703/xangi`）の話。
2 体の bot を Discord で会話させるために必要だった分だけ持ってきてある。
動かしていた版と上流との差は `../README.md` の「xangi のバージョン」節。

| ファイル | 中身 |
|---|---|
| `bot-to-bot-mention-protocol.md` | **なぜ・何を決めたか**。「本文のメンションだけが会話の継続スイッチ」。故障A（止まらない）/ 故障B（届かない）の 2 つを同時に直した記録 |
| `bot-to-bot-code-changes.md` | **どのファイルをどう書き換えたか**（当時の差分の解説） |
| `xangi_local_v0.49.6.patch` | **実際に運用していたローカル差分の全文**（v0.49.6 比・14 ファイル / +766 −48）。🔴 upstream には出していないので、これが唯一のバックアップ |
| `scheduler-clock-drift.test.ts` | cron 再 arm のテスト（本体リポジトリでも未追跡だった）。patch を当てた xangi の `tests/` に置いて使う |

## 読むときの注意

- 🔴 `bot-to-bot-mention-protocol.md` §7-4 の「supervisor がいないので `system_restart` は使わない」は
  **2026-08-11 の supervisor 導入で古い**（再起動しても戻るようになった）。本文に追記で注記してある
- 🔴 patch は **v0.49.6 への差分**。上流は v0.59.4 まで進んでおり、同じファイルが 7〜17 commits 動いている。
  **そのままは当たらない前提**で、意図（`parse: ['users']` / 本文メンションのフォールバック /
  edit 確定待ちポーリング / cron 再 arm）を読んで再実装する
- 🔶 上流 v0.59.4 は送信を `allowedMentions: { parse: [] }` で統一しているので、
  **上げるだけでは bot 間メンションは届かない見込み**（grep のみの推定・実機未検証）
- テンプレート化にあたり、patch はコメント行 3 か所の bot 名を `Agent A / Agent B` に、
  テストコード内の文字列リテラルの bot 名・Discord ID をダミー（`Agent A` / `999999999999999999`）に置き換えた
  （テストはメッセージ形式だけを見るので挙動・行数は不変）

## patch の当て方（v0.49.6 に固定する場合）

```bash
git clone https://github.com/karaage0703/xangi.git && cd xangi
git checkout v0.49.6                       # package.json の version は 0.1.0 のまま。版は git tag で見る
git apply --check <REPO>/tools/xangi/reference/xangi_local_v0.49.6.patch && \
  git apply <REPO>/tools/xangi/reference/xangi_local_v0.49.6.patch
cp <REPO>/tools/xangi/reference/scheduler-clock-drift.test.ts tests/
npm ci && npm run build && npx vitest run   # テストが通ってから起動する
```
