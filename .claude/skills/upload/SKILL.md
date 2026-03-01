---
name: upload
description: 実験フォルダをKaggle Datasetにアップロードしてバージョン管理する。tools/kaggle_upload.shのラッパー。
argument-hint: "[フォルダパス]"
disable-model-invocation: true
---

# Kaggle Dataset アップロードスキル

## 手順

1. **引数の確認**: `$ARGUMENTS` からアップロード対象フォルダを取得

2. **フォルダの確認**:
   - 指定フォルダが存在するか確認
   - フォルダ内のファイル一覧とサイズを表示
   - .gitignore に含まれる大きなファイル（.pth, .ckpt等）も含まれることを確認

3. **アップロード実行**:
   ```bash
   bash tools/kaggle_upload.sh {フォルダパス}
   ```

4. **結果の報告**:
   - 新規作成 or バージョン更新
   - Dataset のURL
   - アップロードサイズ
