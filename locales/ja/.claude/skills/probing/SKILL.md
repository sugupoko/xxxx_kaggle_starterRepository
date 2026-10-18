---
name: probing
description: Leaderboard probing（LB probing）を実行する。まず問題設定からどの probing が可能かを診断し、定数提出で public test の分布（pos_ratio / mean / class比率）を逆算する「値 probing」と、グループ単位の構造（group_id / patient_id 等の per-group サンプル数・membership）を逆算する「構造 probing」を使い分ける。**デフォルトは Kaggle Code Competition**（提出はノートブック実行）。提出枠とルールを確認してから使う。
argument-hint: "[指標 logloss|rmse|mae|accuracy で開始 / 空欄で KAGGLE_DIRECTION.md から推定]"
---

# Leaderboard Probing Skill

public LB スコアは「test set の集約統計量」なので、精巧な提出を出すと返ってきたスコアから非公開の test 情報を逆算できる。本 skill は **(1) 問題設定からどの probing が可能かを診断** し、**(2) 適切なモードで安全に実行** する。

詳細な原理・指標別の式・過去事例・判定表は `survey/papers/lb_probing.md` を参照（無ければ `/survey-papers leaderboard probing` か kaggle-researcher で先に作る）。

> **前提: デフォルトは Kaggle Code Competition。**
> Code Competition では **CSV を直接アップロードできず、提出はノートブック実行**。
> probing のロジック（定数 / 条件付き予測）は **推論ノートブックの中に書く**。ローカルで CSV を作って upload するのは CSV Competition のときだけ。
> 提出フロー（Dataset upload → Notebook push → Save & Run All → Submit）は `tools/kaggle_code_competition_submission.md` を参照。

## probing の4モード

| モード | 取れる情報 | 成立条件 |
|--------|-----------|---------|
| **A. 値 probing** | test 全体の統計量（pos_ratio / mean / Var / class比率） | public LB がある。指標が定数提出に反応する（AUC は不可） |
| **B. 構造 probing** | グループ単位の per-group サンプル数・membership（例: group_id ごとの件数、test に居る/居ない） | **コードコンペ**で test 側のグループキーが推論時に見える + 指標が**per-sample 平均**（1/N 刻みで動く） |
| **C. 混同行列 probing** | 正例数 P / pos_ratio（混同行列 TP/FP/FN から） | 指標が **F1 / F2 / Fβ / precision / recall**（global confusion matrix から計算される系） |
| **D. ID/構造 probing** | public/private の分離、グループ構造（提出不要） | test の **ID に生成規則**（ハッシュ・連番・剰余）がある。EDA の延長で倫理リスク低 |

Code Competition は test メタデータが推論時に読めるので、**A〜D を組み合わせられる**のが強み（特に B はコードコンペでしか成立しない）。出典は `survey/papers/lb_probing.md` §12（C=bilzard 方式 / D=Ringa_hyj 方式）。

## 手順

### Step 1. 可能性診断（前提確認・スキップ禁止）

実装に入る前に「そもそも何ができるか」を必ず判定する。**特に断りがなければ Code Competition として扱う。**

1. **提出形式**: `survey/competition/overview.md` から確認（デフォルト Code Competition）
   - **Code Competition（既定）** → 値 probing **＋ 構造 probing** が可能。提出はノートブック実行
   - CSV Competition → 値 probing が実用的（ローカルで定数 CSV を作って直接 upload）
   - Docker / public LB 無し → フィードバックが遅く probing **非推奨**
2. **指標**: 評価指標を確認
   - LogLoss / RMSE / MAE / Accuracy → 値 probing（モードA）で逆算可能
   - F1 / F2 / Fβ / precision / recall → 混同行列 probing（モードC）で正例数 P を逆算
   - per-sample 平均系（Dice / mAP / IoU / accuracy など）→ 構造 probing（モードB）が刺さる
   - **AUC → 定数提出に反応しないので probing ほぼ不可**
3. **グループキーの可視性**: 推論ノートブックで test 側の group_id / patient_id 等のキーを読んで分岐できるか（モードB）
   - test の **ID 体系**（ハッシュ・連番）も確認 → モードD（ID/構造 probing）が提出なしで使える
4. **提出枠**: 1日の枠を確認。probing は枠を消費するのでモデル提出とのトレードオフを明示
5. **ルール**: probing がコンペ規約で禁止されていないか。定数提出による分布把握は通常許容。**行単位 probing による全ラベル取得は実質違反**になりうる。グレーなら**ユーザーに判断を仰ぐ**

診断はヘルパーに任せられる（`--format` は省略すると code）:
```bash
python .claude/skills/probing/scripts/probe.py diagnose --metric dice --group-key-visible yes --quota 5
# → 可能なモード（value / structural）とコスト・注意を出力
```

### Step 2. モード選択

診断結果に応じて A / B を選ぶ。両方やれる場合は目的で選ぶ（全体分布が欲しい→A、test 構成が欲しい→B）。

---

### モード A: 値 probing（test 全体の統計量）

**2A-1. 指標と必要提出数**:

| 指標 | 提出する定数 | 逆算できる情報 | 必要提出数 |
|------|------------|--------------|-----------|
| LogLoss(2値) | p=0.1 など（**p≠0.5**） | pos_ratio | 1回 |
| LogLoss(多値) | 各クラスを全行に | クラス別割合 | クラス数 |
| RMSE | c=0.0, 1.0 の2点 | mean(y), Var(y) | 2回 |
| MAE | 定数を変えて最小点探索 | median(y) | 二分探索 O(log n) |
| Accuracy | 全行をクラスk に | クラスk の比率 | クラス数 |
| AUC | — | 直接逆算困難 | 非推奨 |

**2A-2. 提出を作る**:

- **Code Competition（既定）** — 推論ノートブック内で、入力を無視して全行に定数を出力する:
  ```python
  # inference_notebook.py の予測部分を probing 用に差し替える
  sub = pd.read_csv(SAMPLE_SUB)
  sub[TARGET] = 0.1            # 定数（LogLoss なら p != 0.5）
  sub.to_csv("submission.csv", index=False)
  assert len(sub) == EXPECTED_ROWS
  ```
  これを `tools/kaggle_code_competition_submission.md` のフローで push → Save & Run All → Submit。

- CSV Competition のとき — ローカルで定数 CSV を生成して直接 upload:
  ```bash
  python .claude/skills/probing/scripts/probe.py gen \
    --sample <sample_submission.csv> --col <target列> \
    --values 0.1 0.9 --outdir probing/subs
  ```
  生成物は `probing/subs/`（`.gitignore` 対象・提出物そのものなので commit しない）。ファイル名 `const_*` でモデル提出と区別される。

**2A-3. 逆算**:
```bash
python .claude/skills/probing/scripts/probe.py invert --metric logloss --pairs 0.1=<スコア>
# rmse なら: --metric rmse --pairs 0.0=<score> 1.0=<score>
```

---

### モード B: 構造 probing（グループ単位の件数・membership）

**原理**: 指標が `score = (1/N) Σ m_i`（per-sample 平均）のとき、一部のサンプルだけ予測を変えるとスコアがサンプル数に比例して動く。N=110 なら1サンプル ≈ 0.9% の量子ステップになり、**整数個数が読める**。Code Competition で test 側メタデータが見えることが前提。

**2B-1. グループキーで条件分岐した予測を推論ノートブックに書く**:
```python
# inference_notebook.py — group_id ごとの件数を測る
sub = pd.read_csv(SAMPLE_SUB)
mask = (meta["group_key"] == TARGET_GROUP)   # 推論時に見えるメタデータで分岐
sub.loc[mask,  TARGET] = FLIPPED              # この subset だけ変える
sub.loc[~mask, TARGET] = BASELINE
sub.to_csv("submission.csv", index=False)
```
- まず **全行 BASELINE**（base スコア）と **全行 FLIPPED**（full スコア = キャリブレーション）の2本を提出
- 次に **TARGET_GROUP だけ FLIPPED** にしたノートブックを group ごとに提出

**2B-2. 個数・membership を逆算**:
```bash
python .claude/skills/probing/scripts/probe.py invert --metric subset_count \
  --n 110 --base <baseスコア> --full <全行flipスコア> --probe <subsetだけflipスコア>
# → subset count = k 件（fraction %）、swing≈0 なら「test に存在しない」
```
- `k = N × (probe - base) / (full - base)`。`full - base` が per-sample デルタ d
- subset の swing が ≈0 → そのグループは **test に居ない（0件）**
- 全グループの件数を足して N に閉じるか検算する（例: N=110 でグループ A 78 件 + B 32 件 = 110 なら閉じている）

---

### モード C: 混同行列 probing（F1 / F2 / Fβ / precision / recall）

**原理**（出典: bilzard §12-A）: F値系は global な混同行列（TP/FP/FN）から計算されるので、定数提出1本では逆算できないが、**全行を陽性で提出**すると `TP=P, FP=N-P, FN=0` に固定され、F値が正例数 P だけの関数になる:
```
F_beta(全行=1) = (1+β²)·P / ((1+β²)·P + (N-P))   →   P = F·N / (a - F·(a-1)),  a = 1+β²
precision(全行=1) = P/N = pos_ratio              （precision なら一発）
```

**C-1. 全行=1（陽性）の提出を作る**（Code Comp なら推論ノートブック内で `sub[TARGET]=1`）

**C-2. 正例数 P を逆算**:
```bash
python .claude/skills/probing/scripts/probe.py invert --metric f1 --n <総行数> --pairs allpos=<F1スコア>
# f2 なら --metric f2、Fβ 一般なら --metric fbeta --beta <β>
```
- 全行=0（陰性）の提出と組み合わせると、サブグループ別の precision/recall を分離して混同行列を完全復元できる（操作を複数独立に設計するのが鍵）

---

### モード D: ID/構造 probing（提出不要・EDA レベル）

**原理**（出典: Ringa_hyj §12-B/C, Instant Gratification）: test の **ID 生成規則**（MD5 ハッシュ・連番・剰余）を逆算すると、提出を1回もせずに public/private の分離やグループ構造を特定できる。倫理リスクは低い（通常の EDA の延長）。

**D-1. test の ID/メタデータを観察**: ID が連番か、ハッシュか、特定変数で剰余分割されていないか（例: `wheezy-copper-turtle-magic` の 0〜511 で 512 グループ）

**D-2. 生成規則の仮説を検証**: 例えば「ID = md5(str(i)+'test')」を疑うなら、その規則で再現できるか確認:
```python
import hashlib
cand = [hashlib.md5(f"{i}test".encode()).hexdigest() for i in range(EXPECTED)]
# test の ID 集合と突き合わせて一致するか
```

**D-3. 活用**: public/private 境界が分かれば public LB 過学習を回避でき、グループ構造が分かればグループ内モデリングに切り替えられる。**提出枠を消費しない**のが最大の利点。

---

### Step 3. 提出はユーザーが手動（全モード共通）

- Code Competition の提出（Save & Run All → "Submit to Competition"）も、CSV の upload も、**Claude は実行しない**。「このノートブック / CSV を提出して、返ってきた public LB を教えてください」と依頼する
- どの定数 / どのグループがどのスコアだったか取り違えないよう、**対応表**を提示する
- Code Competition では1提出に Notebook 実行時間がかかる。probing は提出回数だけでなく**実行時間制限**にも注意

### Step 4. 記録と活用（全モード共通）

- 結果を `survey/competition/probing_log.md` に追記（無ければ作る）。テンプレ:
  ```markdown
  ## probing YYYY-MM-DD — <モード> / <指標>
  - A値: const=<値> → LB=<スコア> → pos_ratio/mean=<値>
  - B構造: group=<キー> → 件数=<k> / membership=<在/不在> / 総N=<>
  - C混同行列: 全行=1 → F=<スコア> → 正例数 P=<値> / pos_ratio=<値>
  - D-ID: 規則=<ハッシュ/連番/剰余> → public/private 分離 or グループ構造=<...>
  - 解釈: train 分布との差、CV 設計への反映、public LB のノイズ評価
  ```
- **活用方針を提案**（堅実 + 爆発）:
  - 堅実: 判明した分布/構成を post-calibration の基準にする / **CV を test 構成に合わせて重み付け** / public LB のノイズ（小グループ）を見極めて一喜一憂を避ける / CV-LB 乖離の説明
  - 爆発: ルール確認の上で、判明したラベルを pseudo label として学習に追加（通常より高精度）

## 注意

- **行単位 probing（1行ずつ flip して全ラベル取得）は実質的なルール違反になりうる**。実行前に必ずユーザーへ確認し、グレーなら止める
- p=0.5 の LogLoss 提出は情報量ゼロ（どの pos_ratio でも同じスコア）。**p≠0.5** を使う
- 構造 probing は **指標が per-sample 平均** かつ **グループキーが推論時に見える** ことが前提。AUC や rank 系では成立しない
- Code Competition では提出が Notebook 実行になるため、定数 / 条件付き予測は**ノートブック内に書く**（ローカル CSV を upload しない）。実行時間制限・`enable_internet: false` にも注意
- 提出枠は有限。probing に何枠使うかを事前に宣言し、モデル検証を圧迫しないこと
- 逆算した分布/構成が train と大きく違う場合、fold 設計 / validation 戦略の見直しを daily report に記録する
