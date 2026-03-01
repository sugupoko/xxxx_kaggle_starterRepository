---
name: survey-discussion
description: Kaggleのディスカッションを定点観測する。スクレイピングでディスカッション一覧を取得し、前回との差分を分析する。
---

# ディスカッション定点観測スキル

KAGGLE_DIRECTION.md のディスカッション収集ワークフローに従う。

## 手順

1. **コンペ名の確認**: `KAGGLE_DIRECTION.md` からコンペURLを取得

2. **環境確認**:
   - Playwright がインストールされているか確認
   - なければ案内: `pip install playwright beautifulsoup4 lxml && playwright install chromium`

3. **スクレイピングスクリプトの確認/作成**:
   - `survey/discussion/` にスクレイピングスクリプトがあるか確認
   - なければ KAGGLE_DIRECTION.md に従って `scrape_with_playwright.py` と `scrape_discussion_details.py` を作成

4. **データ取得**:
   ```bash
   cd survey/discussion
   python scrape_with_playwright.py
   python scrape_discussion_details.py
   ```

5. **差分分析** (過去のスナップショットが存在する場合):
   - 新規トピックの特定
   - コメント数の増加
   - 注目度の高いディスカッション（コメント増加率）
   - 公式アナウンスメントの確認

6. **結果の整理**:
   - `survey/discussion/discussion_snapshot_YYYYMMDD.json` にスナップショット保存
   - `survey/discussion/discussion_activity_summary.md` に活動分析レポートを更新
   - 重要な発見があれば `claudeSummary.md` の知見セクションにも追記

7. **レポート**: 新規・注目ディスカッションのサマリーを報告
