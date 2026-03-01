---
name: submit
description: Kaggleにsubmissionファイルを提出し、tools/kaggle_elapsed_time.pyで状態監視を開始する。
argument-hint: "[submissionファイルパス] [メッセージ]"
disable-model-invocation: true
---

# Kaggle提出スキル

## 手順

1. **引数の解析**: `$ARGUMENTS` から提出ファイルのパスとメッセージを取得

2. **提出ファイルの確認**:
   - ファイルが存在するか確認
   - ファイル形式の確認 (csv, zip等)
   - 行数やカラム名を確認して妥当性チェック
   - sample_submission.csv があれば形式を比較

3. **コンペ名の確認**: `KAGGLE_DIRECTION.md` からコンペ名を取得

4. **提出コマンドの実行**:
   ```bash
   kaggle competitions submit -c {コンペ名} -f {ファイルパス} -m "{メッセージ}"
   ```

5. **提出監視の開始**:
   - `tools/kaggle_elapsed_time.py` の `COMPETITION` 変数を更新（必要な場合）
   - 監視スクリプトをバックグラウンドで起動:
   ```bash
   python tools/kaggle_elapsed_time.py &
   ```

6. **結果の報告**:
   - 提出ID
   - 提出日時
   - 提出ファイル名
   - メッセージ

7. **SESSION_NOTES.md への記録**: 現在の実験フォルダのSESSION_NOTES.mdに提出記録を追記
