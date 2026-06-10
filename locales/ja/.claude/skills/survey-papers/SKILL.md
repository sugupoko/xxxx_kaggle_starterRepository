---
name: survey-papers
description: コンペに関連する論文や類似コンペの解法を検索し、survey/papers/にまとめる。リサーチフェーズや新しいアプローチを探すときに使う。
argument-hint: "[検索キーワード or 空欄でコンペ名から自動検索]"
context: fork
agent: Explore
---

# 論文・解法調査スキル

## 手順

1. **検索クエリの決定**:
   - `$ARGUMENTS` があればそれを使う
   - なければ `KAGGLE_DIRECTION.md` のコンペ名から関連キーワードを抽出

2. **WebSearchで調査** (以下を並行して検索):
   - arXiv で関連論文を検索
   - 過去の類似コンペ上位解法（Kaggle / grand-challenge.org / MICCAI Challenges / CodaBench など、プラットフォームを限定しない）
   - Papers With Code で関連手法
   - GitHub で関連実装

3. **各論文/解法について以下をまとめる**:
   - タイトル・著者・URL
   - 手法の要約（3-5行）
   - 使用モデル/アーキテクチャ
   - データセット・評価指標
   - 主要な結果
   - このコンペへの転用可能性

4. **調査結果の全文を返す**:
   - この skill は `context: fork`（読み取り専用の Explore agent）で実行されるため、**fork 内ではファイルを保存しない**
   - カテゴリ別に整理（データセット論文、手法論文、ベンチマーク論文、ツール/ライブラリ）した**調査結果の全文**を最終応答としてそのまま返す
   - 受け取ったメイン会話側が `survey/papers/maybe_related_research.md` に追記保存する

5. **転用アイデアの提案**:
   - このコンペに使えそうな手法をリストアップ
   - 実装の難易度と期待される効果を評価
