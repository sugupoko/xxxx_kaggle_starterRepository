# はじめに
これはデータ分析コンペティション用のレポジトリです（Kaggle だけでなく grand-challenge.org / CodaBench / 独自プラットフォームにも対応。ファイル名は歴史的経緯で KAGGLE_DIRECTION.md のまま）。
CLAUDE.md と合わせてルールを確認してください。

対象コンペはこれです。
コンペ名：
URL：
締切 / タイムライン：
評価指標：


# ディレクトリ構造

作業でよく触る場所だけ抜粋（最新の完全な構造は Readme.md の「リポジトリ構造」を参照）。

```
./                                # Primary working directory
├── myMemo.md                     # 自分のメモを残す。
├── claudeSummary.md              # 各実験のメモ、知見を集約する
├── datasets/                     # コンペデータの置き場（git 管理外）
├── tools/                        # Utility scripts
│   ├── kaggle_elapsed_time.py    # Submission status monitoring
│   └── kaggle_upload.sh          # Dataset upload/versioning script
├── survey/                       # 調査した内容を格納するフォルダ
│   ├── competition/              # コンペ概要（/onboard の出力 overview.md）
│   ├── discussion/               # kaggleのディスカッションを定点観測する
│   └── papers/                   # 論文の内容をまとめておく
└── workspace/                    # Main development workspace
    ├── fold/                     # fold割り当ての永続化（generate_folds.py + {version}/folds.csv）
    └── expXXX/                   # 実験フォルダ
```

# 実験方法
Claudeの実験フォルダと、人間の実験フォルダを分けています。
* claude用
  * exp(アルファベット)（数字２桁）_（実験名）でフォルダを作成しその中で実験をする
    workspace/expA00_baseline
  * ナンバリングは大きく実験を変える際に変更すること。多少の微調整やパラメータ探索は同じフォルダ内で実行すること。
* 人間用
  * exp(数字3桁)_実験名

## セッション記録のルール

**重要**: 各実験フォルダには必ず `SESSION_NOTES.md` を作成すること

### SESSION_NOTES.mdに含めるべき内容

1. **セッション情報**
   - 日付
   - 作業フォルダ
   - 目標

2. **試したアプローチと結果**
   - 各アプローチの詳細な説明
   - 使用したファイル名
   - 定量的な結果（メトリクス、スコアなど）
   - 問題点と改善点

3. **ファイル構成**
   - 作成したスクリプトのリスト
   - 可視化結果のリスト
   - データファイルのリスト

4. **重要な知見**
   - セッション中に得られた重要な発見
   - 避けるべきアプローチ
   - 有効だったテクニック

5. **次のステップ**
   - 次回実行すべきタスク
   - 検討すべきアイデア
   - 優先度付き

6. **性能変化の記録**
   - 実験名と性能変化の記録
   - 何をしてどのようになったかを俯瞰できるように

7. **コマンド履歴**
   - 実行した主要なコマンド
   - 再現性のための記録

### 例
```
workspace/exp000_all_test/SESSION_NOTES.md
workspace/exp200_xxxxxxxx/SESSION_NOTES.md
```

### 目的
- セッション中断時でもすぐに作業を再開できる
- 過去の試行を忘れずに記録
- 他の人（または未来の自分）が理解できるドキュメント 

# コンペの進行方法
- 必ずデータの分析を行いその前提で検討を進めること
- コンペのルールに基づき、コンペの指標に合った性能改善をしていくこと

# 学習のコードについて
1. 学習のログも残すようにしてほしい。学習曲線などです。こういう感じできれいにして。
```
./exp000_all_test
├── SESSION_NOTES.md
├── run.sh                        # cd "$(dirname "$0")" してから train.py を呼ぶ
├── train.py                      # 実験フォルダ直下に置く
├── config.yaml
├── src/                          # datamodule / model などのモジュール
└── results/
    └── {experiment_name}/
        └── foldN/                # ckpt・学習曲線・ログ・config コピーを集約
```
2. 学習は途中から再開できるようにしておいてほしい。PCが途中で止まることがあります。
3. AMPで学習するようにしておいてほしい。

# surveyフォルダ

## discussionフォルダ
定点観測できるようにスクレイピング結果はフォルダにまとめておくこと。差分でどんな情報が出たかを別でまとめておくこと

### ディスカッション収集ワークフロー

#### 1. 初回セットアップ
```bash
# Playwrightのインストール
pip install playwright beautifulsoup4 lxml
playwright install chromium

# ディレクトリ作成
mkdir -p survey/discussion
cd survey/discussion
```

#### 2. ディスカッションリスト取得

**スクリプト**: `scrape_with_playwright.py`

```python
# Playwrightを使ってディスカッションページをスクレイピング
# - headlessブラウザでJavaScript実行後のHTMLを取得
# - ディスカッションタイトルとURLを抽出
# - discussions_playwright.json に保存
```

**実行**:
```bash
python scrape_with_playwright.py
```

#### 3. 詳細情報（コメント数等）取得

**スクリプト**: `scrape_discussion_details.py`

```python
# 各ディスカッションページを巡回
# - コメント数を取得
# - ビュー数、投票数を取得（可能な場合）
# - discussion_snapshot_YYYYMMDD_detailed.json に保存
```

**実行**:
```bash
python scrape_discussion_details.py
```

#### 4. スナップショット管理

**ファイル構成**:
- `discussion_snapshot_YYYYMMDD.json` - 基本情報のスナップショット
- `discussion_snapshot_YYYYMMDD_detailed.json` - コメント数等の詳細情報
- `kaggle_discussions_organized.md` - 整理されたサマリー
- `discussion_activity_summary.md` - 活動度分析レポート
- `README.md` - スナップショット履歴とガイド

#### 5. 差分チェック（次回実行時）

```bash
# 新しいスナップショットを取得
python scrape_with_playwright.py
python scrape_discussion_details.py

# 差分を確認（手動またはスクリプト化）
# - 新規トピック
# - コメント数の増加
# - 最終更新日時の変化
```

#### 6. 定期実行推奨

**頻度**: 週1-2回
**タイミング**: コンペティション序盤は頻繁に、後半は週1回程度

**チェックポイント**:
- 公式アナウンスメントの確認
- データパッチ等の重要更新
- 評価指標に関する議論
- 有効なソリューションの共有

### 注意事項

1. **Kaggle APIの制限**
   - 公式Kaggle APIにはディスカッション取得機能なし
   - Playwrightによる動的スクレイピングが必要

2. **スクレイピングマナー**
   - 各リクエスト間に2-3秒の待機時間
   - headlessモードで実行
   - 過度なアクセスを避ける

### WebFetch / WebSearch の活用

Claude Code には **WebFetch / WebSearch が標準搭載**されている。静的に取得できるページ（公式の Overview / Rules / Data ページなど）はまずこれらで取得する。
JavaScript レンダリングが必要なページ（Kaggle のディスカッション一覧など）だけ、上記の Playwright スクレイピングにフォールバックする。

## papersフォルダ
論文の内容をまとめておく

### 調査ワークフロー

1. **関連論文の検索**
   - WebSearchで過去のコンペ、関連研究を検索
   - arXiv、Google Scholar等から論文を取得

2. **論文サマリー作成**
   - `survey/papers/` 配下にトピックごとの .md ファイルで要約をまとめる
   - 手法、データセット、評価指標、結果を記録

3. **カテゴリ別整理**
   - データセット論文
   - 手法論文
   - ベンチマーク論文
   - ツール・ライブラリ

## competitionフォルダ（`survey/competition/`）
コンペティションの基本情報を `survey/competition/` にまとめる（`/onboard` の出力先）

### 収集する情報

1. **overview.md** - コンペ概要
   - 背景・目的
   - データ形式
   - 評価指標
   - 主要な課題
   - 推奨アプローチ

2. **データソース**
   - 配布データ（train/test）の分析
   - ファイルフォーマット（CSV / Parquet / 画像 など）の構造理解
   - メタデータの確認

---

# 設計意図：なぜこのルールなのか

このセクションは具体的な手順ではなく、**判断の指針**を示す。
手順は Skills や Readme.md を参照すること。

## フェーズ別の指針（序盤・中盤・終盤）

**「いきなりアンサンブル」「いきなり TTA」を防ぐための時系列ガード。**
コンペには段階がある。**各フェーズの "やるべきこと" と "やってはいけないこと" を分けないと、終盤にやるべき最適化を序盤に持ち込んでリソースを溶かす**（典型的な早期最適化）。

判定は**時間ベース + マイルストーンベースのハイブリッド**で行う:
- 時間ベース: `KAGGLE_DIRECTION.md` の締切と `daily_reports/` の最初の日付から進捗 % を計算
- マイルストーンベース: 各フェーズの完了条件が満たされたかを `SESSION_NOTES.md` / `submit/SUBMISSIONS.md` / `claudeSummary.md` から判定
- **両者が乖離していたら警告**: 「終盤に入ったが single baseline がまだ動いていない」「中盤なのにアンサンブルを試している」など

### 序盤 (~30% / マイルストーン: baseline 完成 + CV/LB 相関確認 + submission 1回成功)

**やる**:
- データ理解（EDA: 分布・欠損・グループ構造・外れ値）
- fold 設計（grouping キー特定 → `workspace/fold/{version}/folds.csv` 永続化）
- 評価指標の正確な実装（コンペ仕様と sklearn デフォルトのギャップを潰す）
- **1つの strong single model** を作る（reference/ ベースで十分）
- 動く submission pipeline（CSV / 予測 zip / Docker のいずれか）
- 論文・類似コンペ・discussion の調査（`/survey-papers`）

**禁止**:
- アンサンブル（**single の絶対値がないと、伸び幅を測れない**）
- TTA（後で効果を測るために、ベース推論で良い）
- heavy augmentation（過学習対策は過学習が起きてから）
- 複雑な post-processing（閾値最適化・形態学処理など）
- 過度な hyperparam tuning（探索の前にアーキを試すべき）

**完了条件**:
- [ ] CV スコアが安定して出る（fold 間ばらつきが許容範囲）
- [ ] CV/LB 相関を1回は確認した
- [ ] submission pipeline が動く（提出 error にならない）
- [ ] 評価指標の実装が公式と一致している確認済み

### 中盤 (30-70% / マイルストーン: 独立した single model 3つ以上、エラーパターン把握)

**やる**:
- **モデル多様性を上げる**: encoder 変更、アーキテクチャ変更、入力モダリティ変更
- エラー分析（prediction vs ground truth を最低 20 件目視 → エラータイプ分類）
- データ追加・外部データ・pseudo-labeling の検討
- augmentation の効果を **CV で定量的に検証**
- 前処理の改善（normalization, sampling, クラス不均衡対策）
- 損失関数の調整（focal, dice, custom）

**禁止**:
- **アンサンブル本格化**（single CV を伸ばすのが先。混ぜると個別モデルの貢献が見えない）
- 過度な hyperparam search（lr / batch / optimizer の grid search で時間溶かす）
- 終盤向けの post-processing tuning（評価が不安定になる）

**完了条件**:
- [ ] 独立した方向性の single model が 3-5 個揃った（CV が独立して伸びている）
- [ ] エラーパターンが分類できている（前処理 / 後処理 / モデル容量 / データ不足のどれが効くか把握）
- [ ] CV/LB の安定した相関が継続している

### 終盤 (70%- / マイルストーン: ensemble CV > best single CV、final 2 submission 選定基準明確)

**やる**:
- **アンサンブル戦略**: 重み最適化（CV ベース）、stacking、blending
- TTA（flip / multi-scale / 確率平均方法の選定）
- post-processing 最適化（閾値、形態学処理、後処理 NMS など）
- 最終 submission の選定（best CV / best LB / 保守的安定型 のバランス）
- LB shake リスク評価（CV/LB 相関、fold 間ばらつき、提出履歴の分散）
- 提出物の完全検証（`/submit-check`）

**禁止**:
- **新アーキテクチャ着手**（学習時間が間に合わない / 検証が浅くなる）
- 大きな前処理変更（中盤で確立したパイプラインを壊さない）
- 大規模な hyperparam tuning（diminishing returns）
- 新規外部データの追加（検証時間不足）

**完了条件**:
- [ ] ensemble CV が best single CV を上回る
- [ ] final 2 submission の選定基準が明確（理由を SESSION_NOTES に書ける）
- [ ] LB shake シナリオを評価済み（楽観/悲観の両方）
- [ ] `/submit-check` を提出予定の全 submission に対して通過

### フェーズ間の乖離警告

時間とマイルストーンが乖離していたら、`competition-strategist` agent が警告する:

- **進捗遅延**: 「中盤入っているが、まだ baseline が動いていない」→ 序盤を優先せよ
- **早期最適化**: 「序盤なのにアンサンブルを試している」→ single を伸ばせ
- **終盤の新規着手**: 「残り3日で新アーキを試そうとしている」→ 既存資産の最適化に絞れ

## 「堅実＋爆発」の意図

Kaggleの上位解法を振り返ると、段階的改善（堅実）だけで勝てることは稀。多くの金メダル解法には「それは普通やらない」という飛躍がある。

- 堅実なアプローチだけでは局所解に陥る。encoder変更、ハイパラ調整、Augmentation追加…これらは必要だが、それだけでは順位は頭打ちになる
- 一方で爆発だけでは博打になる。堅実なベースラインがあってこそ、爆発の効果を正しく測れる
- **常に両方を並べることで「今やるべきこと」と「試す価値があること」を分離する**
- 爆発案は失敗前提でいい。10個のうち1個当たれば大きなジャンプになる
- 異分野（NLP→CV、音声→時系列など）からの転用、問題の再定義（セグメンテーション→検出に変換）、非自明な外部データ活用などが典型的な爆発案
- 「それは無理だろう」と思ったアイデアほど、他の参加者も試していない可能性が高い

## Fold設計の意図

Foldの切り方はCVの信頼性を左右する。**CVが信頼できなければ、全ての実験判断が狂う。**

- ランダムKFoldは「データが完全にi.i.d.」という前提がある。現実のKaggleデータでその前提が成り立つことは少ない
- グループリーク（同じ患者/画像/セッションがtrain/valに分かれる）は、CVを不当に高く見せる。LBで初めて気づくと手遅れになる
- 時系列リーク（未来の情報で過去を予測）はさらに深刻。Purged KFold等で明示的に防ぐ必要がある
- **最初のfold設計に時間をかけることが、後の全実験の価値を決める**
- fold間スコアのばらつきが大きい場合、データのグループ構造を見落としている可能性が高い
- CV/LB相関が弱い場合、fold設計が現実のテスト分布を反映できていない

## 前処理の意図

- trainデータの統計量で正規化するのは「testの情報を使わない」というリーク防止の原則。fold内でも同様に、val foldの情報をtrain側の正規化に使わない
- Augmentationを弱めから始めるのは、モデルの素の学習能力を先に確認するため。強いAugmentationは過学習への対症療法であり、根本原因（データ不足/モデル容量）を隠す
- **Augmentationの効果は必ずCV値で定量的に判断する。「効きそう」で入れない**

## 評価指標の意図

- コンペの評価指標を正確に再現するのは大前提。sklearn等のデフォルトパラメータがコンペと一致しないケースは多い（averageの指定、閾値、重み付けなど）
- Lossと評価指標が異なる場合（例：BCELossで学習してF1で評価）、最適解がずれる可能性がある。この差異を意識した上で、必要なら閾値最適化やカスタムLossを検討する
- **「CVが改善した」と言えるためには、評価指標の実装が正しいことが前提**

## 提出・アンサンブルの意図

- single modelのスコアを記録してからアンサンブルするのは、各モデルの寄与を把握するため。アンサンブルは「最良のモデルを組み合わせる」のであって「全部混ぜる」のではない
- 提出前チェックは当たり前に見えるが、行数不一致やカラム名ミスでsubmission errorになるのは時間の無駄。特にpost-processingを変更した後は必ずチェックする
