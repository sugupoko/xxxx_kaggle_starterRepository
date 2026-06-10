---
name: submit-check
description: 提出物の事前検証を実行する。Kaggle CSV / Kaggle Code Competition / 予測ファイル zip / Docker コンテナの4形式に対応。submission-validator agent を呼び出して機械的にチェックする。提出直前に必ず使う。
argument-hint: "<submit/v00X_<元exp>_xxx のパス> [--platform kaggle|gc|codabench]"
---

# 提出物 事前検証 Skill

## 手順

1. **引数解析**:
   - `$ARGUMENTS` から提出フォルダパスを取得（必須、例: `submit/v001_baseline`）
   - `--platform` フラグがあればそれを使う、なければ `KAGGLE_DIRECTION.md` から推定

2. **形式判定**:
   - フォルダ内のファイル構成から判定:
     - `notebook.py` あり → (A) Kaggle CSV型
     - `kernel-metadata.json` + `dataset-metadata.json` あり → (A') Kaggle Code Competition 型
     - `predict.py` + `run.sh` あり → (B) 予測ファイル zip 型
     - `Dockerfile` + `process.py` あり → (C) Docker コンテナ型

3. **submission-validator agent を呼び出し**:
   - 上で判定した形式と提出フォルダパスを渡して実行依頼
   - agent は自動で形式に応じた検証を行う
   - (A') の場合は submission-validator の「1'. Kaggle Code Competition 型のチェック」（kernel-metadata / dataset-metadata / self-contained notebook の検証）を実行させる

4. **検証結果を集約して報告**:
   - Pass / Fail / Warning を上から順に表示
   - Fail があれば**提出してはいけない**旨を強調
   - 修正案を最後に提示

5. **submit/SUBMISSIONS.md への記録準備**:
   - メタ情報（実験フォルダ・モデル元パス・fold 定義・学習データ・主要パラメータ・前処理・CV）を agent の出力から抽出
   - SUBMISSIONS.md にまだ記載がなければ、追記用の行を提案する（**自動コミットはしない**）

## 注意

- **絶対に外部にアップロードしない**。実アップロードはユーザーが手動で行う
- 検証中にモデルファイル / submission.csv / 予測 zip を `.gitignore` から外していないか確認
- Docker 検証では `bash test.sh` を実行する。長時間かかる場合は run_in_background で回す
