---
name: strategy
description: コンペ戦略の横断synthesis を実行する。competition-strategist agent を起動し、daily_reports/* と全 SESSION_NOTES.md / claudeSummary.md / submit/SUBMISSIONS.md / KAGGLE_DIRECTION.md を一括ロードして「次の一手」を出力する。週1回や局面の変わり目で使う。
argument-hint: "[追加の指示 or 空欄でデフォルト synthesis]"
---

# 戦略 Synthesis Skill

## 手順

1. **対象ファイルの存在確認**:
   - `KAGGLE_DIRECTION.md` / `claudeSummary.md` / `daily_reports/` / `submit/SUBMISSIONS.md` / `workspace/` の存在をチェック
   - 不足があれば「該当ファイルなし」と明示して agent に渡す

2. **competition-strategist agent を起動**:
   - subagent_type: `competition-strategist`
   - プロンプトに以下を明示:
     - コンペ名と締切（KAGGLE_DIRECTION.md から）
     - **必ず先頭でフェーズ判定**（時間ベース + マイルストーンベース、乖離があれば警告）を出すこと
     - **以降の提案はそのフェーズの "やる" に限定**（KAGGLE_DIRECTION.md「フェーズ別の指針」参照）
     - `$ARGUMENTS` があれば追加の観点として渡す（例: 「ensemble 戦略に絞って」「LB shake リスクを重点的に」）
     - 出力先: 今日の日報 `daily_reports/YYYYMMDD.md` の「戦略・ロードマップ」セクションへ追記

3. **agent の出力を今日の日報へ追記**:
   - 今日の日報 `daily_reports/YYYYMMDD.md` の「戦略・ロードマップ」セクションに追記する（**別ファイル `strategy_*.md` は作らない**。記録は日報に一本化）
   - 今日の日報がまだ無ければ `/daily-report` の手順で作成してから追記する
   - 主要な提案（**フェーズ判定**、堅実+爆発、未踏領域、リスク）を要約してユーザーに報告
   - **乖離警告があれば最優先で伝える**（「中盤入っているのに baseline 未完成」など）

4. **次のアクションを提案**:
   - 提案された「次の一手」のうち、明日着手できるものを 1-2 個に絞ってリコメンド
   - 必要に応じて `/exp-new` での実験フォルダ作成、`/survey-papers` での追加調査を提案

## 使いどころ

- **週1回**: 定点観測として
- **CV が頭打ちになったとき**: 局所解から脱出するため
- **LB shake が起きたとき**: 何が原因か俯瞰するため
- **新しいデータが追加されたとき**: 戦略を再評価
- **締切1週間前**: 残りリソースの配分を最適化

## 注意

- agent はファクトベースで出力する。**推測には「推測:」が付く**
- 「ベスト〇〇」は数値の引用元（実験フォルダ・日報日付）を必ず添える
- agent の提案を盲目的に実行せず、ユーザーが判断する材料として扱う
