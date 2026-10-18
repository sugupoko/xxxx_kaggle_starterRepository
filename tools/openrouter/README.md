# OpenRouter 残高監視（使う場合のみ）

LLM API を [OpenRouter](https://openrouter.ai/) 経由で使う（データ生成・ラベル付け・LLM-as-judge など）場合だけ必要なツール。
使わないならこのフォルダは無視してよい。

## このフォルダの中身

| ファイル | 役割 |
|---|---|
| `or_credit_watch.sh` | 残高・キー枠残・本日の使用額・前回比を数行で出す定点観測。cron / 定期実行から呼ぶ |
| `.gitignore` | 実行時 state（`.or_credit_watch.json`）を除外 |

## セットアップ

```bash
# リポジトリ直下に鍵ファイルを作る（*.env はルート .gitignore で除外済み）
printf 'OPENROUTER_API_KEY=%s\n' '<ここに貼る>' > .openrouter.env
chmod 600 .openrouter.env
git check-ignore .openrouter.env      # 出力があれば除外されている

bash tools/openrouter/or_credit_watch.sh
# 例: 🟢 OpenRouter 10/18 09:00 JST ｜ 残高 **$42.10** ｜ キー枠残 $18.00/$50 ｜ 本日 $1.20 ｜ 前回比 -0.35$(30分)
```

- 鍵は環境変数 `OPENROUTER_API_KEY` が優先。無ければ `.openrouter.env` を読む
- ⚠️ **鍵の値をチャット/ログ/コミットに出さない**。スクリプトは出力に鍵を混ぜず、curl の argv にも出さない
- 閾値は `OR_WARN_USD`（🟡 既定 20）/ `OR_CRIT_USD`（🔴 既定 5）で変更

## 読み方

- **実際に使える額 = 残高 と キー枠残 の小さい方**。キーに上限を付けている場合、残高より先にキー枠で止まる
- 残高がゼロ以下になると新規リクエストは **402** で弾かれる。バッチ処理が途中で黙って止まる典型原因
- 前回比がマイナスのときは消費ペース（$/h）を出し、24 時間以内に尽きる見込みなら警告する
- 出力は「正本」として通知にそのまま流す想定（LLM に再計算させない）。通知が要るなら呼び出し側で
  `tools/notify.sh` の `notify_send` に渡す（xangi を使う場合のみ。無ければ標準出力だけ）
- 時刻は `date -u -d '+9 hours'` で JST を明示計算している（`TZ=Asia/Tokyo` は zoneinfo の無いコンテナで効かないため）

関連: 外部 GPU 側の同種ツールは `tools/runpod/rp_credit_watch.sh`（`tools/runpod/README.md` §8）。
