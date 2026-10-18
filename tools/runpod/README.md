# RunPod 接続・運用ノウハウ（汎用・移植用）

外部GPU（RunPod）で学習を回すための**接続・操作・鍵運用・コスト管理**を1か所に集約。
このフォルダ（`tools/runpod/`）ごと別リポジトリにコピーすれば移植完了。実機（runpodctl 2.3.0）で検証済の内容。
**価格・在庫は変動するので使用直前に `runpodctl gpu list` / 公式pricingで確認。**

## 前提（このガイドが想定していること）
本書は **「接続〜運用」から** 始まる。以下は**済んでいる前提**で扱う（手順は本書の対象外。最新は公式を参照）:
- **RunPodアカウント作成済み**（runpod.io でサインアップ）
- **支払い方法の登録 / クレジット投入済み**（RunPodはプリペイド。**残高ゼロだと pod を起動できない**。自動チャージ推奨）

上記が未了の人はまず公式でアカウント登録とクレジット投入を済ませてから §1 へ。

## このフォルダの中身
| ファイル | 役割 |
|---|---|
| `README.md` | 本書（接続ノウハウ全部） |
| `runpod_ops.py` | ローカルから pod 操作（Python SDK版。up/list/stop/down、Network Volume対応） |
| `smoke_test.sh` | 疎通テスト（最安GPUで起動→RUNNING待ち→接続情報→teardown） |
| `startup.sh` | pod内で実行する起動スクリプト（鍵注入・private clone・自動停止）。鍵の値は持たない |
| `pod_run.sh` | pod内の**1ジョブ学習エントリ**（汎用テンプレ）。Kaggle dataset 取得→自動展開検出→学習→`/workspace/out_<TAG>` 集約。多pod並列で各 pod に `setsid` で1回だけ投げる（§11） |
| `rp_ssh.sh` | **一時SSH鍵**の生成→RunPod登録→ssh/scp/stdin投入→破棄（§12）。鍵の値は出さず fingerprint のみ表示 |
| `rp_key_guard.sh` | `rp_ssh.sh` の setup/clean を **flock で直列化**し、稼働中 pod があれば拒否する唯一の入口（§12）。owner token 付き mark・失敗時 rollback |
| `rp_credit_watch.sh` | 残高・稼働レート・前回比・**停止したまま残っている pod** を数行で出す定点観測（§8）。cron / 定期実行用 |
| `.gitignore` | 上記ツールの実行時 state（`.rp_credit_watch.json` / `.rp_key.lock` / `.rp_inflight/`）を除外 |
| `.runpod.env.example` | ローカルの鍵ファイル雛形。コピーして `.runpod.env` を作り値を入れる（**gitignore必須**） |

---

## 0. 全体像（3行）
1. ローカルに `runpodctl` + Python SDK を入れ、`RUNPOD_API_KEY` だけ `.runpod.env` に置く
2. pod に渡す鍵（GitHub PAT / HF / Kaggle）は **RunPod Secrets** に登録し、pod env では **参照 `{{ RUNPOD_SECRET_x }}`** で注入（生値を出さない）
3. `runpodctl pod create --template-id ... --stop-after ...` で起動 → ブラウザ Web Terminal で作業 → `pod stop/delete`

---

## ★推奨ワークフロー（Kaggle×RunPod。次コンペで検証予定）

**原則: Kaggle = 唯一の真実（DC非依存・durable）／ Network Volume = 使い捨て高速scratch（DCに縛られる）／ container disk = 揮発。**
Volumeが消えても・DCが変わっても、Kaggleから再構築できる状態を常に保つ。

```
[前処理] 生データ小 → ローカルで前処理 / 生データ大 → pod上で前処理（上り帯域がボトルネックになるため）
   ↓ Kaggle private dataset に up（= 真実・版管理。fold一貫性のため version を記録）
[学習] pod上で kaggle datasets download → 学習 → ckpt は Volume(高速scratch)
   ↓ 重要ckpt / 良モデルは その都度 Kaggle(/HF) にも push（DC非依存の保険）
[提出] 良モデルを dataset 化 → 推論notebookにattach（Kaggle Code Competition）
```

### ストレージ3層の役割
| 層 | 役割 | 揮発性 |
|---|---|---|
| **Kaggle dataset** | cold durable（入力データ / 出力モデルの真実の置き場） | 永続・無料 |
| **Network Volume** | warm scratch（学習中ckpt・中間生成物） | 永続だが残高ゼロで消える→真実はKaggle側 |
| container disk | ephemeral（pod削除で消える） | 揮発 |

### Volume 要否・サイズ・個数の判断
- **小〜中容量 / 起動少**: Volume不要 or ckptのみの最小Volume。データはKaggleから毎回DL
- **巨大データ × 頻繁起動**: ⚠️ DL中もGPU課金が走る → データも一度Volumeに置いて再DLを省く（Volumeは大きくなる）。判断式 `毎回DL時間×GPU単価×起動回数` vs `データ分のVolume月額`
- **個数**: 数でなく「**実際に使うDCごとに1個**」（Volumeはpodと同一DC固定）。1個の中をフォルダ分けで複数実験を回せる
- **On-Demand単発のみ**なら Volume すら省ける（ckpt→container disk→良いものだけ最後にKaggle up）。Volumeが効くのは spot / 頻繁stop-resume / 多pod並列read

### ★運用で刺さる落とし穴（と対策）
1. **ローカル→Kaggleの上り帯域**が最大のボトルネック → 巨大データは pod上で前処理。ローカル前処理は数GB級まで
2. **GPU在庫の偏在でVolumeのDCにGPUが無い事故** → Volumeは使い捨て前提（真実はKaggle）。DCにこだわらない
3. **ckptがVolumeだけだと別DCで再開不可** → 重要ckptは定期的に Kaggle/HF にも push（DC非依存の保険）
4. **残高ゼロでVolume消失＝復元不可** → 自動チャージON ＋ 上記3で被害ゼロ
5. **「良かったらup」を後回しにすると消える＋提出に必須** → 学習完了→即 `kaggle datasets version` で push→それからpod削除、を1手順に固定

> **追加すべき要点は実質1つ**: 「ckptと良モデルは Volume だけでなく Kaggle(/HF) にも逃がす」。これで在庫偏在・DCロック・Volume消失の全部に耐える。

---

## 1. ローカル環境構築（1回）

```bash
# runpodctl（sudo不要・ユーザー領域へ）
mkdir -p ~/.local/bin
TAG=$(curl -s https://api.github.com/repos/runpod/runpodctl/releases/latest | grep -oP '"tag_name":\s*"\K[^"]+')
curl -sL -o ~/.local/bin/runpodctl "https://github.com/runpod/runpodctl/releases/download/${TAG}/runpodctl-linux-amd64"
chmod +x ~/.local/bin/runpodctl
runpodctl version          # 2.3.0+ を確認

# Python SDK（runpod_ops.py 用。CLIだけなら不要）
pip install --user runpod
```

---

## 2. 認証（鍵はローカル `.runpod.env` のみ）

```bash
cp tools/runpod/.runpod.env.example .runpod.env   # リポジトリ直下に置く
# .runpod.env を編集して RUNPOD_API_KEY を貼る（runpod.io/console/user/settings → API Keys → Create, Read/Write）
source .runpod.env
runpodctl me               # 残高・spend が出れば認証OK（課金なし）
```

- **`.runpod.env` は必ず gitignore**（`*.env` / `.runpod.env`）。`git check-ignore .runpod.env` で確認
- `RUNPOD_API_KEY` だけはローカル必須（runpodctlを動かす鍵＝Secret化できない）。`~/.runpod/config.toml`(=`runpodctl doctor`) でも可だが、`.runpod.env` に一元化すると runpod_ops.py / smoke_test.sh と共有できて楽
- ⚠️ **鍵の値をチャット/ログ/コミットに出さない**。存在確認は真偽＋長さ＋先頭数文字のみ（`[ -n "$RUNPOD_API_KEY" ] && echo "set (${#RUNPOD_API_KEY}文字)"`）。`echo $VAR` / `${VAR:-...}` / 鍵ファイルの `cat` は使わない

---

## 3. runpodctl 2.3.0 コマンド体系（新）

> ⚠️ ネット上の古い記事の `runpodctl create pods` / `get pod` / `stop pod` は **deprecated**。下記の新体系を使う。

```
runpodctl pod         create|list|get|start|stop|restart|delete|update
runpodctl gpu list    利用可能GPU種別と空き（要API key）
runpodctl network-volume create|list|get|delete|update   (alias: nv)
runpodctl datacenter list                                (alias: dc)  ← Volumeとpodは同一DC必須
runpodctl me          残高・spend  (alias: user/account)
runpodctl ssh         add-key|info|list-keys|remove-key
runpodctl send <file> / receive <code>   croc経由のファイル転送（SSH鍵不要）
runpodctl billing     課金履歴
```

### `pod create` 主要フラグ（実機確認）
| フラグ | 用途 |
|---|---|
| `--gpu-id` | GPU種別ID（下表）。`runpodctl gpu list` の `gpuId` 列 |
| `--cloud-type` | `SECURE`(既定) / `COMMUNITY` |
| `--network-volume-id` | 永続Volumeアタッチ |
| `--volume-mount-path` | マウント先（既定 `/workspace`） |
| `--image` | Dockerイメージ（templateなしなら必須） |
| `--template-id` | テンプレ起動。`runpodctl template search <kw>` で探す |
| `--env` | 環境変数（**JSON文字列**）。Secret参照を渡せる（§5） |
| `--ports` | 公開ポート `'8888/http,22/tcp'` |
| `--container-disk-in-gb` | コンテナディスク（既定20） |
| `--stop-after` | **自動停止 datetime（課金漏れ最終防衛）** 例 `2026-06-01T09:00:00Z` |
| `--terminate-after` | 自動削除 datetime |
| `--compliance` | ホストを規約で絞る `HIPAA,SOC_2_TYPE_2`（医療/機密データ時） |
| `--data-center-ids` | DC指定（Volumeと一致必須） |

### GPU ID（`--gpu-id` にそのまま渡す verbatim）
| GPU | gpuId |
|---|---|
| A100 80GB PCIe | `NVIDIA A100 80GB PCIe` |
| A100 80GB SXM | `NVIDIA A100-SXM4-80GB` |
| RTX 4090 | `NVIDIA GeForce RTX 4090` |
| L40S | `NVIDIA L40S` |
| RTX A6000 | `NVIDIA RTX A6000` |
| RTX A5000 | `NVIDIA RTX A5000` |
| H100 80GB | `NVIDIA H100 80GB HBM3` |

※ `gpu list` に**価格は出ない**（公式pricing or コンソールで確認）。`stockStatus`(High/Low)と`available`は出る。

### `network-volume create`
| フラグ | 必須 | 備考 |
|---|---|---|
| `--name` | ✅ | |
| `--size` | ✅ | GB（1–4000） |
| `--data-center-id` | ✅ | `runpodctl datacenter list` で確認。**podと同一DC必須** |

---

## 4. pod ライフサイクル & 接続

```bash
source .runpod.env
runpodctl me                                  # 残高（課金前確認）
runpodctl datacenter list                     # Volume置くDC決定
runpodctl gpu list                            # 目的GPUの空き・ID確認
# ★--template-id 必須（bare --image だと即EXITED）／--stop-after は切り忘れ保険
#   ※継続行 `\` の後ろにコメントを書くと行継続が壊れて --stop-after 等が落ちるので書かない
runpodctl pod create --name train \
  --gpu-id "NVIDIA A100 80GB PCIe" --cloud-type SECURE \
  --network-volume-id <VOL_ID> --volume-mount-path /workspace \
  --template-id runpod-torch-v280 \
  --container-disk-in-gb 40 \
  --stop-after $(date -u -d '+8 hours' +%Y-%m-%dT%H:%M:%SZ)
runpodctl pod list                            # ID・状態（RUNNINGになるまで数十秒）
runpodctl ssh info <POD_ID>                   # ssh接続情報
# ... 作業 ...
runpodctl pod stop <POD_ID>                   # 課金停止（Volume/disk保持）
runpodctl pod delete <POD_ID>                 # 完全削除（Network Volumeは残る）
runpodctl me                                  # spend確認
```

### pod 内での作業（接続方法）— SSH必須ではない
| 方法 | 鍵 | 備考 |
|---|---|---|
| **Web Terminal**（RunPodコンソール） | 不要 | ブラウザで即シェル。最も手軽 |
| **JupyterLab**（`--ports '8888/http'`） | 不要 | ブラウザ。ノート作業向き |
| **SSH** | 要（`runpodctl ssh add-key` で公開鍵登録） | `ssh root@<ip> -p <port>`。CI/rsync向き |

### ファイル転送（SSH鍵不要）
`runpodctl send <file>` → コードフレーズ表示 → 受信側 `runpodctl receive <code>`（croc, P2P）。
小〜中サイズの受け渡しに。大容量データは pod 上で直接DL（HF/Kaggle/S3）して Network Volume へ。

---

## 5. 鍵運用（2層モデル）— 生値を露出させない

pod に鍵を渡す方法は2通り。**機密度の高い鍵は RunPod Secrets を使う**のがベスト。

| | A: RunPod Secrets 参照 | B: `.runpod.env` 生値 → `--env` |
|---|---|---|
| ローカルディスク | ✅ 残さなくていい | 🟡 平文で残る（gitignore済の自PC） |
| pod設定/ダッシュボード/API/履歴 | ✅ 参照のみ（生値出ない） | 🔴 生値が出うる |
| RunPod側保管 | ✅ 暗号化・**再表示不可** | 🟡 pod envとして保持 |
| 稼働中pod内 `echo $X` | 🔴 読める | 🔴 読める（**両方共通**） |

**手順（A方式）:**
1. コンソール → Secrets → Create。`Name=GH_TOKEN` / `Value=<生トークン>`（`{{ }}`は書かない・クォート無し）
2. pod env で参照: `GH_TOKEN={{ RUNPOD_SECRET_GH_TOKEN }}`（`--env` JSON か Web UI の Environment Variables）
3. ローカル `.runpod.env` からは生トークンを消し、**`RUNPOD_API_KEY` だけ残す**

- `runpod_ops.py` の `CFG.use_runpod_secrets` は**既定 False（生値を渡す）**。True にするとこの参照を自動生成するが、下記の通り SDK では解決されないため Web UI 起動以外では使えない（True のまま `up` すると警告が出る）
- ✅ **実機確認（2026-06-01）: CLI/SDK の `--env` では `{{ RUNPOD_SECRET_x }}` は解決されない**。→ Web UI から起動（UIは確実に解決）するか、`use_runpod_secrets=False`（既定）で生値を渡すか、**鍵は scp で起動後に注入**する（§9.5 の確定手順）
- pod内では結局 env として読めるので、**最後の砦は最小スコープ＋短期失効トークン**（例: GitHub PAT は Fine-grained / 対象repoのみ / Contents:Read-only / 期限付き）

---

## 6. pod上で private repo を clone（HTTPS + PAT。SSH鍵不要）

使い捨て pod には **HTTPS + Fine-grained PAT** が定石（SSH Deploy Key より配布管理が楽）。

1. GitHub → Settings → Developer settings → **Fine-grained tokens** → 対象repoのみ / **Contents: Read-only** / 期限付き
2. RunPod Secret に `GH_TOKEN`（値=`github_pat_...`）、`GIT_REPO`（値=`github.com/<user>/<repo>.git`）を登録
3. pod env で参照注入 → `startup.sh` が自動 clone:
   ```bash
   # ★トークンは URL に埋め込まない（ps/エラー出力に露出＋除去後の再起動 pull が壊れる）
   #   credential helper なら argv にトークンが出ず、再起動時の pull もそのまま通る
   git config --global credential.helper '!f() { echo "username=x-access-token"; echo "password=${GH_TOKEN}"; }; f'
   git clone "https://${GIT_REPO}" "$CODE_DIR"
   ```
- ローカルで事前検証（課金なし）: `git ls-remote "https://x:${GH_TOKEN}@${GIT_REPO}" HEAD`（使い捨てコマンドなので URL 埋め込みでも可）

---

## 7. Network Volume（永続ストレージ）

- **$0.07/GB/月**（〜1TB）。データセット/ckpt を常駐させ pod 再作成のたびにアタッチ
- ⚠️ **Secure Cloud 専用**（Community では使えない）
- ⚠️ **Volume と pod は同一 DC 必須**（リージョン固定）→ `datacenter list`→Volume作成DC→同DCのGPU空きを `gpu list`、の順
- 複数 pod から**読み取り共有可**（同時書き込みは破損リスクで不可）
- ⚠️ **残高不足が続くと Volume 削除＝復元不可** → 自動チャージ設定必須
- 縮小不可（増やすのみ）。最初から余裕を持って作成

---

## 8. コスト管理（課金漏れを物理的に防ぐ）

- 課金は **per-second**（Network Volume のみ時間/月単位）
- **二重の自動停止**: `--stop-after <datetime>`（pod側） + `startup.sh` の `trap '... pod stop' EXIT`（学習終了/中断時）
- `runpodctl me` の `spendLimit` でアカウント上限、コンソールで自動チャージ閾値を設定
- spot的に使うなら ckpt 30分ごと + Network Volume 保存（中断時 SIGTERM 5秒 → ckpt再開で復帰）
- **`pod stop` だけでは課金は止まり切らない**: 停止 pod のディスク保管料が日割りで出続ける。使い終えた pod は回収後に `pod delete` まで行う（§14）
- **定点観測**: `bash tools/runpod/rp_credit_watch.sh` を cron 等で回す（例: 30分ごと）。残高・稼働レート・前回比・停止したまま残っている pod を数行で出す。出力をそのまま通知に流す（LLM に再計算させない）
  ```
  🔴 RunPod 10/18 09:00 JST ｜ 残高 **$15.50** ｜ 稼働 1台 $0.80/h ｜ 前回比 -0.40$(30分)
  ⚠️ **停止したまま残ってる pod が 1台**（ディスク保管料が出続けます）
  ```
  - 閾値は `RP_WARN_USD`（🟡 既定 20）/ `RP_CRIT_USD`（🔴 既定 10）。鍵は環境変数か `.runpod.env` から読み、値は出力しない
  - 時刻は `date -u -d '+9 hours'` で JST を明示計算（`TZ=Asia/Tokyo` は zoneinfo の無いコンテナで黙って UTC のままになる）

---

## 9. ハマりどころ（実地で踏んだ）
- **★bare `--image` は即EXITED**: 常駐プロセスが無いと pod が起動直後に終了する。**必ず `--template-id`（公式 `runpod-torch-v280` 等）を使う**。GUI起動はテンプレ既定なので動く＝CLIで `--image` 直指定したのが敗因だった（5090はGUIで取れたのに CLI で「消えた」ように見えたのはこれ）
- **`pod list` は EXITED を表示しない**（RUNNINGのみ）。終了/失敗の確認は `pod get <id>`。listが空でも EXITED pod が居る場合があるので `me` の spend と併せて見る。**停止 pod を含む全件は `pod list --all`**（`rp_credit_watch.sh` はこちらを使う）
- **runpodctl の版でフラグが変わる**: 新しめの版（2.14.0 で確認報告あり）では `pod create` の `--stop-after` / `--terminate-after` が削除されている。使う前に `runpodctl pod create --help` で有無を確認し、無い版では teardown を自分で必ず実行する（課金漏れの最終防衛が効かない）
- **deprecated コマンド**: `create pods`/`get pod`/`stop pod` は旧。新は `pod create`/`pod list`/`pod stop`
- **`gpu list` に価格なし**: 価格は公式pricing/コンソール。在庫は `stockStatus`
- **Volume は同一DC固定**: 別DCのGPUにアタッチ不可
- **`{{ RUNPOD_SECRET_x }}` はCLI/SDKでは解決されない（実機確認済 2026-06-01）**: Web UI 起動か、scpで起動後注入（§9.5）か、生値
- **残高ゼロで Volume 削除**: 自動チャージ必須
- **WSL から GitHub/pod への SSH**: `~/.ssh` が 9p drvfs(metadata無)だと chmod が効かず 777 → OpenSSH が拒否。**push/接続は Windows 側 or runpodctl(HTTPS) or Web Terminal で回避**。直すなら `/etc/wsl.conf` に `[automount]\noptions=metadata` → `wsl --shutdown`。**直さずに済ませるなら §12 の一時鍵（`/tmp` に置いて chmod 600）**
- **`gpu list` 結果は時々変動**: 同じ呼び出しでも在庫により出る種別が変わる

---

## 9.5 ★実証済みレシピ：Kaggle dataset → RunPod でモデル学習（2026-06-01 実機検証）

H100で end-to-end 成功（local subset→Kaggle upload→pod download→学習→best ckpt をscpで回収）。
**学習フレームワーク非依存**の、実走で踏んだ罠と確定手順:

**ローカル（upload）**
```bash
# データを zip 1本にして dataset-metadata.json と共に置く → 既定で private
python3 -m kaggle datasets create -p <stg_dir> --dir-mode skip
# ★Kaggleはupした.zipを自動展開する → datasetには中身(データ/設定ファイル)が直接入る
```
**pod（download→train）**
```bash
pip install -q --break-system-packages kaggle <学習ライブラリ>   # ★PEP668: runpod-torch templateは--break-system-packages必須
python -m kaggle datasets download -d <user>/<slug> -p .         # 鍵は scp で /root/.kaggle/kaggle.json に入れておく
unzip -o -q <slug>.zip -d data                                   # ★1段だけ（Kaggleが既に展開済なので二重zipにならない）
# ★学習設定ファイルのデータルートは絶対パスに（相対はCWD基準で誤解決）。例（YAML設定の場合）:
sed -i 's#^path:.*#path: /workspace/data#' data/<config>
<学習コマンド> ... data=/workspace/data/<config> ... project=/workspace/runs name=run   # 同名既存だと自動採番される例あり
# 成果物: /workspace/runs/.../best.* → scp でローカル/Kaggle/HFに退避
```
**確定罠（フレームワーク非依存）**:
1. `pip` は **`--break-system-packages`** 必須（PEP668。runpod-torch template）
2. **Kaggle の zip 展開挙動は一定しない**（自動展開される／`foo.zip`→`foo/` サブフォルダにネストされる／内部 zip が残る、のどれもあり得る）→ **DL 後はパスを決め打ちせず自動検出**する。例: `ROOT=$(dirname "$(find "$DS" -name '<目印ファイル>' | head -1)")`。内部に二重 zip が残っていたらもう1段 unzip（`pod_run.sh` がこの両方を実装済み）
3. **学習設定のデータルートは絶対パス**（相対 `.` はCWD基準で誤解決して not found になる）
4. **dataset 作成直後は処理待ちで download が 404**（`DownloadDataset` 404）→ 十分粘る（**5×20s で足りないことあり**）。`kaggle datasets files <slug>` が中身を返したら準備完了の合図。律速は up 帯域でなく **Kaggle 側の処理待ち**のことが多い（実測: 2GB の up が約51s でも、その後の処理待ちで DL は数分 404）
5. **owner id は実 username**（`kaggle.json` の `username` フィールド。メール handle とは別物）→ 違うと `Invalid Owner Id` で作成失敗。`dataset-metadata.json` の `"id"` は `<real_username>/<slug>`
6. **CLI/SDK `--env` は `{{ RUNPOD_SECRET_x }}` を解決しない** → 鍵は **scp で起動後注入**（`scp -i <key> -P <port> ~/.kaggle/kaggle.json root@<ip>:/root/.kaggle/`。argv に出さず mode 600 で入れるなら `rp_ssh.sh put`・§12）
7. **HF/timm の事前学習重みは未認証だと rate 制限で停滞**（モデルロード前で固まり `num_features` 等のログすら出ない＝ハングに見える）→ `HF_TOKEN` を Secret/scp で注入

---

## 10. クイックスタート（疎通テスト）
```bash
source .runpod.env
bash tools/runpod/smoke_test.sh                 # 最安GPUで起動→RUNNING→接続情報（★数円）
# ブラウザ Web Terminal で nvidia-smi 確認 → 終わったら:
bash tools/runpod/smoke_test.sh teardown <POD_ID>
```

---

## 11. ★多pod並列・デタッチ実行の落とし穴（実地で全部踏んだ）

複数 pod で並列学習する／ssh でバックグラウンド起動する時の事故集。
**学習フレームワーク非依存・RunPod 非依存の一般的な罠**なので、ssh で長時間ジョブを投げる全場面で効く。
3モデル×3pod並列の練習で「ワークフローは全段成功するのに完走しない」事象を起こしたが、**原因は環境でなく操作（人間側）の事故**だった。同じ轍を踏まないための鉄則:

### ★最重要: 「1 pod = 1 起動」。起動後は触らない
- 起動確認が取れず不安になって**再 launch を繰り返すと、同じ pod に学習プロセスが多重 stack** → 同一 GPU で競合して **SIGKILL（"Killed"）**。「ep01 は通るのに ep02 で必ず死ぬ」はメモリでも cgroup でもなくこれ（RAM/GPU に空きがあっても起きる）
- 対策: launch は**1回だけ**。確認が取れなくても再 launch しない（状態はログ読みで確認）。多重を疑ったら `pgrep -fc <学習スクリプト名>` で数を見て、2以上なら **PID 指定で全消ししてから1本だけ**起動し、以後触らない

### ★完全デタッチは `setsid CMD >log 2>&1 </dev/null &` の3点セット
- `nohup` **だけ**だと ssh 切断時に SIGHUP で死ぬことがある。`setsid`（新セッション＝controlling terminal から切り離す）が ssh 切断に最も強い
- **`</dev/null`（stdin リダイレクト）が無いと ssh が return せずハングする**（background プロセスが ssh channel の stdin を掴むため）。**必須**
- まとめ: `setsid <cmd> >run.log 2>&1 </dev/null &` で「切れても生存・ssh は即 return・ログは残る」

### ★起動確認は「別の ssh call」で。インライン echo は当てにならない
- `setsid ... & echo OK` の `echo` は backgrounding と競合して**取りこぼす**（"HUNG?" の誤判定になり、上の再 launch 事故を誘発）
- 正: launch（出力は捨てる）→ 数秒後に**別 call**で `head -1 run.log` を読み、開始マーカー行を確認する

### ★ssh は while-read ループの stdin を食う（古典バグ）
- `while read host; do ssh "$host" ...; done < pods.txt` は、**ループ内の ssh が pods.txt の残り行を stdin から食って**ループが途中終了する（p1 だけ起動して p2/p3 が起動されない）
- 対策: `mapfile -t PODS < pods.txt` で**配列化してから for** で回す。または各 ssh に `</dev/null` を付ける

### ★`pkill -f PAT` は自分の cmdline に自己マッチして自殺する
- `pkill -9 -f '_runner.sh'` を含むコマンド行は、**自身の cmdline にその文字列を持つため自プロセスを kill** して落ちる
- 対策: **PID 指定 kill**。`pkill -f` を使うなら、パターンを自 cmdline に出ない語にする

### 確定オペレーション手順（多pod並列で次回これだけ守る）
```
1. pod を起動（poll-create。GPU はフォールバック前提で複数候補を retry）
2. Kaggle dataset の準備完了を `kaggle datasets files <slug>` で確認してから pod を使う（§9.5 罠4）
3. 各pod: kaggle.json / HF_TOKEN を scp 注入 → pod_run.sh を setsid で **1回だけ** launch
4. 別 call で run.log の start 行を確認 → **数分 hands-off** → epoch 到達をログで確認（pkill / 再launch 厳禁）
5. 回収（Kaggle push or scp get）→ pod stop+delete ×N → `pod list --all` 空確認 → 一時鍵 clean
```
- 1〜5 を SSH で回すときは §12 の一時鍵を使う: 1 の前に `rp_key_guard.sh begin --owner <token> <tag>...`、5 の最後に `rp_key_guard.sh end --owner <token> <tag>...`

---

## 12. ★一時SSH鍵ワークフロー（`rp_ssh.sh` + `rp_key_guard.sh`）

WSL などで `~/.ssh` が **9p/drvfs マウントだと chmod が効かず 777 のまま** → OpenSSH が "UNPROTECTED PRIVATE KEY" で鍵を拒否する（§9）。
対策＝**秘密鍵は `/tmp`（通常 FS）に置き chmod 600**。鍵は**使い捨て**（その都度生成→登録→使用→破棄）。`rp_ssh.sh` に固定してある:

```bash
source .runpod.env
bash tools/runpod/rp_ssh.sh setup                 # 一時ed25519生成 + 公開鍵をRunPod登録(★pod作成の前に)
# ... runpodctl pod create ...（作成時にアカウントのSSH公開鍵がpodへ注入される）
IP=...; PORT=...                                   # runpodctl ssh info <id>
bash tools/runpod/rp_ssh.sh put ~/.kaggle/kaggle.json $IP $PORT /root/.kaggle/kaggle.json  # stdin経由=argvに鍵を出さない・mode600
bash tools/runpod/rp_ssh.sh exec $IP $PORT 'setsid bash /workspace/pod_run.sh >/workspace/run.log 2>&1 </dev/null &'
bash tools/runpod/rp_ssh.sh get $IP $PORT /workspace/out_<TAG> ./pod_out   # scp回収
bash tools/runpod/rp_ssh.sh clean                 # /tmp鍵rm + RunPod登録解除（★必ず最後に）
```

- **pod 作成の前に setup**: RunPod は pod 作成時にアカウントの公開鍵を注入する。作成後に登録しても既存 pod には入らない
- 鍵の値は出さない（fingerprint のみ表示）。秘匿ファイルの投入は `put`（中身を stdin で流す）を使い、argv / プロセス一覧に出さない
- 置き場は `RP_SSH_KEY` / `RP_KNOWN_HOSTS` で変更可（既定 `/tmp/.rp_ephemeral_key`）。**リポジトリ内に置かない**
- `clean` は RunPod 側の登録解除に失敗すると警告して非 0 で返す（握りつぶさない）。`runpodctl ssh list-keys` で `rp-ephemeral` が残っていないか確認

### ★共有鍵の排他（`rp_key_guard.sh`）— 稼働中 pod の鍵を差し替えない
一時鍵は**アカウント共有**なので、別のランチャが起動時に `clean` + `setup` を実行すると**稼働中 pod の鍵が差し替わり、接続不能で落ちる**（学習結果と無関係な orchestration failure。並列 pod 運用で実際に起きた）。
そのため setup/clean は **`rp_key_guard.sh` の flock 下でしか実行されない**（`rp_ssh.sh setup|clean` を直接呼んでも guard へ exec し直す）。

```bash
# 並列 pod を回すとき（owner = この試行に固有な token、tag = pod ごとの識別子）
bash tools/runpod/rp_key_guard.sh begin --owner run42 p1 p2 p3   # in-flight 0 を確認 → setup → 全 tag を mark（原子的）
# ... pod 作成・学習・回収 ...
bash tools/runpod/rp_key_guard.sh end   --owner run42 p1 p2 p3   # 自分の tag だけ unmark → 0 台になった時だけ clean
bash tools/runpod/rp_key_guard.sh status                          # in-flight 一覧
```

| 保証 | 中身 |
|---|---|
| 直列化 | setup/clean は `flock`（`.rp_key.lock`）下でのみ。lock 取得 120 秒で諦めて何もしない |
| 稼働中保護 | in-flight（`.rp_inflight/<tag>`）が 1 台でもあれば setup/clean を拒否（exit 3） |
| 原子性 | `begin` は setup と全 tag の mark を同一 lock 内で行い、途中失敗なら**書けた分を巻き戻して** clean・非 0 |
| owner 照合 | `end` / `unmark` は owner token が一致する tag しか外せない（別試行の同名 tag を巻き添えにしない） |
| 手動救済 | プロセスが死んで mark が残ったら、人が確認して `force-unmark <tag>`（自動経路からは呼ばない） |

依存: `flock`（util-linux）。状態ファイルは `tools/runpod/.gitignore` で除外済み。

---

## 13. ★実証済み: Kaggle dataset → RunPod学習 → model/log を Kaggle回収

縮小学習（RTX A4000 secure・コスト数セント）で end-to-end 成功した、**回収まで含めた**確定手順:

1. **ローカル**: 前処理済データ（例: float16 の npz キャッシュ）＋学習スクリプトを Kaggle private dataset に up（`kaggle datasets create -p <dir> --dir-mode skip`）
2. **pod**: 一時SSH鍵で接続（§12）→ kaggle.json を `put` で stdin 投入 → `pip install --break-system-packages kaggle` → `kaggle datasets download` → 学習 → `out/{best.*,train.log,result.json}`
3. **回収**: pod 上で出力を **Kaggle dataset に push**（`kaggle datasets create`）→ ローカルで `kaggle datasets download`。**model+log が durable に残り pod を即削除できる**（scp 回収より本番向き。小物なら `rp_ssh.sh get` でも可）
4. **teardown**: `runpodctl pod stop` → `pod delete` → `pod list --all` 空を確認 → `rp_ssh.sh clean`（並列なら `rp_key_guard.sh end`）

- 罠: CLI 作成 pod は `{{ RUNPOD_SECRET_x }}` を**解決しない**（§5）→ Kaggle 認証は stdin/scp で投入。`pip` は `--break-system-packages` 必須。Kaggle 出力 dataset も作成直後は**処理待ち**があり、DL はリトライ前提（§9.5 罠4）

---

## 14. 実通信で候補を選別してから学習する（大容量データ・多pod向け）

**GPU 在庫・GPU 名だけで決めず、本番と同じ配布元からの転送速度を先に測る。** 実測では同じ GPU 種別（RTX 5090）でも Kaggle からの本 DL が **約 1〜17 MB/s** と桁で分かれた。
機械・DC・時刻・経路で変わるため、**過去に速かった Pod ID や DC を恒久的な当たりとみなさない**。

### 起動前
1. 人間の既存承認を確認し、GPU 種別・同時台数・課金範囲を決める（承認範囲内なら再確認は不要。範囲外に出るなら止めて聞く）
2. `runpodctl pod list --all` で**停止 pod を含む**残存を確認する。通常の list が空でも、停止ディスクの保管料が残り得る。`network-volume list` も別途確認する
3. `gpu list` で現在の在庫・DC を取得する。モデル / ラベル / fold / キャッシュ / 事前学習重みはハッシュ（SHA256）で固定しておく
4. **テンプレの Python / PyTorch / CUDA を先に確認する**。厳密な環境一致が必要なら一致したイメージを選ぶ。起動後の不用意な torch 入替は数 GB の DL を生む。環境差を許容する場合も、元の学習との差を記録して「完全同条件」と呼ばない
5. ログ・状態・終了コード・回収先・自動 stop 時刻を決め、鍵は §12 の guard を通す。**自動 terminate で未回収 checkpoint を消さない**

### 候補 pod の短時間テスト
pod へ転送速度計測スクリプトと Kaggle 資格情報（mode 600）だけを投入し、**ライブラリ一式や全キャッシュの DL より先に**実行する。
計測の例: 本番と同じ配布元から、短い受信窓（例: 3 回 × 最大 20 秒・8 並列・1 stream 上限あり）で取得し、MB/s と通信エラー数を JSON に残す。接続時間も含めて測る。
**資格情報や署名 URL はログに出さない**。Pod ID・GPU・イメージ・DC・単価・日時も併記する。

- **ゲートは暫定で決めて明記する**（例: 「3 回の最小 8 MB/s 以上・中央値 15 MB/s 以上・通信エラー 0」）。これは最適性を検証した閾値ではない。必要速度は「データ量 ÷ 残り時間」から逆算して組み直す（例: 35 GB を 30 分で取るには約 20 MB/s）
- **HTTP 失敗は速度の遅さと区別する**（短時間制限・配布元エラーの可能性）。HTTP / 認証 / 依存エラーを「遅い GPU」と誤分類しない
- **短い Range 取得の高速度は、本 DL の継続速度を保証しない**。通過後も本 DL 開始 5 分後に実ファイル増分から ETA を再計算する。最初の数秒だけで断定しない

### 通過後／切替
- 通過 pod のみ全キャッシュ DL・環境構築へ進む。独立な DL と小さな依存導入は並行してよい。**学習開始前に全キャッシュの SHA256 と件数を確認**する
- 事前学習重みは**固定 revision を pod で直接取得 → ローカルと SHA256 照合**。ローカルからの SSH 転送が遅いとき、大きな重みを延々送り続けない
- DL・展開・学習・回収を含めて期限内に終わらない候補は、ログを回収して停止 / 削除する。学習が始まっている場合は checkpoint 保全が先。**遅い候補を抱えたまま増台しない**
- 作成エラー時は**実 pod 一覧を確認してから**再試行する（二重作成防止）
- 既に準備済みで速い pod を継続利用すると再 DL を省ける。使うなら、既存の「完了時に削除する」処理と競合しないよう**先に引継ぎを設計**する

### 完了・保管料の後始末
checkpoint・OOF・config・training_log・環境情報・ログを回収して SHA256 照合 → 対象 pod だけ削除 → `pod list --all` で消滅確認 → 使い終えた owner の鍵 guard 解除（`rp_key_guard.sh end`）、の順。
**停止だけでは保管料が残る**。削除直後の課金表示は古いことがあるので、削減額を確定として報告しない（`rp_credit_watch.sh` の次回値で確認）。Kaggle に保存済みの入力やローカル回収物は削除しない。

長時間ジョブは実 PID / PPID・ログ更新・終了状態の保存を確認してから「開始した」と報告する。SETUP / DOWNLOADING の段階を「学習中」と呼ばない。
