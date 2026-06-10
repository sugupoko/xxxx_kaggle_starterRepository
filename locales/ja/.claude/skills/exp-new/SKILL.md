---
name: exp-new
description: 新しい実験フォルダを reference/ から雛形コピーして作成する。SESSION_NOTES.md と run.sh も自動生成。Claude用は expA00, A01, ...、人間用は exp200, 201, ... の連番で命名する。
argument-hint: "<実験名> [--human で人間用 exp200_xxx 形式]"
---

# 新規実験フォルダ作成 Skill

## 手順

1. **引数解析**:
   - `$ARGUMENTS` から実験名を取得（必須）
   - `--human` フラグ有無を判定

2. **フォルダ名決定**:
   - Claude 用: `workspace/expA00_<name>` から始め、既存を見て A01, A02, ..., B00, B01, ... と進める
   - 人間用: `workspace/exp200_<name>` から始め、既存を見て 201, 202, ... と進める
   - `ls workspace/` で既存フォルダを確認してから次の番号を決定

3. **雛形コピー**:
   ```bash
   cp -r reference/ workspace/<新フォルダ名>/
   ```

4. **SESSION_NOTES.md を生成**（既にあれば追記しない、上書きしない）:

```markdown
# SESSION_NOTES — <実験フォルダ名>

## セッション情報
- 日付: YYYY-MM-DD
- 作業フォルダ: workspace/<実験フォルダ名>
- 目標: <実験名から推定 or ユーザーに確認>

## ベース
- ベース: reference/ (PyTorch Lightning + timm + smp)
- 親 exp（あれば）: ...

## 試したアプローチと結果
<!-- 実験を回したら追記 -->

## ファイル構成
- train.py
- src/
- config.yaml
- run.sh

## 重要な知見
<!-- 学習中に得られた知見 -->

## 次のステップ
- [ ] ...

## 性能変化の記録
| 試行 | 変更点 | CV | LB | 備考 |
|------|--------|-----|-----|------|

## コマンド履歴
<!-- 実行した主要コマンド -->
```

5. **run.sh を生成**（実行権限付与）:

```bash
#!/bin/bash
# 学習・推論を一発で回すスクリプト
# 重要: cd "$(dirname "$0")" で実験フォルダに移動してから python を呼ぶ。
#       これがないと results/ がリポジトリルートや別の場所に生成されてしまう。
# 使い方: bash run.sh data.fold=0 trainer.max_epochs=30
#         引数は OmegaConf dotlist 形式で config.yaml を上書きする（--config フラグは存在しない）
set -e

cd "$(dirname "$0")"

# 学習（train.py は実験フォルダ直下。引数はそのまま渡す）
python train.py "$@"

# 推論（必要に応じて）
# python predict.py ckpt_path=results/<実験名>/fold0/last.ckpt
```

6. **config.yaml の experiment.name を新フォルダ名に書き換え**

7. **results/ の出力先を実験フォルダ基準にする**:
   - `train.py` の出力先が cwd 依存になっていないか確認
   - 必要なら `output_dir = Path(__file__).resolve().parent / 'results' / experiment_name / f'fold{fold}'` のように**実験フォルダ基準の絶対パス**に書き換える（train.py は実験フォルダ直下にあるため parent 1段）
   - 学習を試走して `workspace/<新フォルダ名>/results/...` に出力されることを確認してからユーザーに報告

8. **報告**:
   - 作成したフォルダのパス
   - SESSION_NOTES.md と run.sh のパス
   - 次にすべきアクション（config.yaml を編集 → `bash workspace/<新フォルダ名>/run.sh`）

## 注意

- **同名フォルダがあれば作成しない**。ユーザーに連番をどうするか確認する
- reference/ がない場合は警告して停止
- データセット・モデルファイルは雛形に含めない（`.gitignore` 対象）
