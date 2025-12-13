# はじめに
これはKaggleのコンペティション用のレポジトリです。
/initをしたらここを読み込んでルールを確認してください。

対象コンペはこれです。
コンペ名：


# ディレクトリ構造

```
./                                # Primary working directory
├── datasets/
│   └── distributed/              # Competition data download scripts
├── tools/                        # Utility scripts
│   ├── kaggle_elapsed_time.py    # Submission status monitoring
    └── kaggle_upload.sh          # Dataset upload/versioning script
├── survey                        # 調査した内容を格納するフォルダ
    ├── disscussion               # kaggleのディスカッションを定点観測する 
    └── papers                    # 論文の内容をまとめておく
└── workspace/                    # Main development workspace
    └── expXXX                    # Dataset upload/versioning script
```

# 実験方法
Claudeの実験フォルダと、人間の実験フォルダを分けています。
* claude用
  * exp(アルファベット)（数字２桁）_（実験名）でフォルダを作成しその中で実験をする
    worspace/expA00_baseline
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

6. **コマンド履歴**
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

### MCPツールの活用（推奨）

**MCP (Model Context Protocol)** ツールが利用可能な環境では、以下の方法でより簡単に実行できます：

#### MCP利用可能性の確認
```bash
# MCPツールの確認
env | grep -i mcp
which mcp
```

#### MCPでのWeb取得
MCPツールには`mcp__web_fetch`や`mcp__web_search`などのツールが含まれている場合があり、WebFetchより制限が少ない可能性があります。

**利用可能なMCPツール例**:
- `mcp__web_fetch` - WebページのHTMLを取得
- `mcp__web_search` - Web検索
- `mcp__browser` - ブラウザ操作

**使用方法**:
```
Claude Codeに以下のように指示：
「MCPツールを使ってKaggleのディスカッションページを取得して」
```

#### MCP vs Playwright比較

| 方法 | メリット | デメリット |
|------|----------|------------|
| **MCP** | - セットアップ不要<br>- Claude Codeとの統合<br>- より簡潔 | - 環境依存<br>- ツールが限定的な場合あり |
| **Playwright** | - 確実に動作<br>- 詳細な制御可能<br>- 汎用性が高い | - セットアップ必要<br>- 環境構築が必要 |

**推奨アプローチ**:
1. まずMCPツールの有無を確認
2. MCPが利用できない場合はPlaywrightを使用
3. 両方試して、より効果的な方を選択

## papersフォルダ
論文の内容をまとめておく

### 調査ワークフロー

1. **関連論文の検索**
   - WebSearchで過去のコンペ、関連研究を検索
   - arXiv、Google Scholar等から論文を取得

2. **論文サマリー作成**
   - `mabe_related_research.md` に要約をまとめる
   - 手法、データセット、評価指標、結果を記録

3. **カテゴリ別整理**
   - データセット論文
   - 手法論文
   - ベンチマーク論文
   - ツール・ライブラリ

## competitionフォルダ
コンペティションの基本情報をまとめる

### 収集する情報

1. **overview.md** - コンペ概要
   - 背景・目的
   - データ形式
   - 評価指標
   - 主要な課題
   - 推奨アプローチ

2. **データソース**
   - train.csv, test.csv の分析
   - Parquetファイルの構造理解
   - メタデータの確認

## notebooksフォルダ
公開ノートブックの分析（今後追加予定）

### 収集対象
- ベースラインノートブック
- EDAノートブック
- 上位解法ノートブック