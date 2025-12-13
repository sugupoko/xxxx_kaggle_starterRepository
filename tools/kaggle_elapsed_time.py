import datetime
import time
from datetime import timezone
from pathlib import Path

# ここは SubmissionStatus を import しない
from kaggle.api.kaggle_api_extended import KaggleApi

# === 設定 ===
COMPETITION = "ここにコンペの名前を入れる。実行しておくとサブの時間が記録される。"
OUTPUT_DIR = Path("submission_complete_logs")
OUTPUT_DIR.mkdir(exist_ok=True)

# === Kaggle API 認証 ===
api = KaggleApi()
api.authenticate()


def normalize_submission_obj(obj):
    """提出オブジェクトから必要フィールドを吸い出して正規化"""
    sid_raw = getattr(obj, "id", None) or getattr(obj, "ref", None) or getattr(obj, "submissionId", None)
    sid = str(sid_raw) if sid_raw is not None else ""

    raw_status = getattr(obj, "status", None) or getattr(obj, "state", None)
    if raw_status is None:
        status = ""
    elif isinstance(raw_status, str):
        status = raw_status.lower()
    else:
        status = str(raw_status).lower()

    raw_time = (
        getattr(obj, "submissionTime", None)
        or getattr(obj, "date", None)
        or getattr(obj, "createdAt", None)
        or getattr(obj, "created", None)
    )
    if isinstance(raw_time, str):
        submit_time = datetime.datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    elif isinstance(raw_time, datetime.datetime):
        submit_time = raw_time
    else:
        submit_time = None

    score_raw = getattr(obj, "public_score", None) or getattr(obj, "publicScore", None) or getattr(obj, "score", None)
    try:
        score = float(score_raw)
    except Exception:
        score = None

    filename = getattr(obj, "fileName", None) or getattr(obj, "filename", None) or ""
    desc = getattr(obj, "description", None) or getattr(obj, "notes", None) or ""

    return sid, status, submit_time, score, filename, desc


def _competition_submissions_all(comp: str):
    """
    Kaggle API のバージョン差異に合わせて、提出一覧をできるだけ全部取得。
    - 新しめ: competition_submissions(comp, page_size=...)
    - 古め:   competition_submissions(comp)
    - さらに古め: competition_submissions(comp, page=1) をページ送り
    """
    # 1) page_size ありの形を試す
    try:
        items = api.competition_submissions(comp, page_size=1000)
        return list(items)
    except TypeError:
        pass

    # 2) 引数なし
    try:
        items = api.competition_submissions(comp)
        # これで全部返る版もある
        if items is not None:
            return list(items)
    except TypeError:
        pass

    # 3) page= を使ってページ送り（空になるまで）
    results = []
    page = 1
    while True:
        try:
            items = api.competition_submissions(comp, page=page)
        except TypeError:
            # どの形も通らない場合は諦めて空
            break
        if not items:
            break
        results.extend(items)
        page += 1
    return results


def get_all_submissions(comp: str):
    """提出一覧（互換ラッパ）"""
    return _competition_submissions_all(comp)


def safe_filename(s: str) -> str:
    """ファイル名に使えない/怪しい文字を簡易除去"""
    return "".join(c for c in s if c.isalnum() or c in ("-", "_", ".", " ")).strip() or "noname"


def write_completion_marker(
    sid: str,
    submit_time: datetime.datetime | None,
    now_utc_naive: datetime.datetime,
    elapsed_min: int | None,
    score: float | None,
    filename: str,
    desc: str,
):
    """完了時に結果ファイルを出力"""
    ts = submit_time or now_utc_naive
    stamp = ts.strftime("%Y%m%d-%H%M%S")
    base = safe_filename(filename or f"sid-{sid}")
    name = f"{stamp}_{(elapsed_min or 0)}min_complete_{base}"
    if score is not None:
        name += f"_LB{score:.5f}"
    outpath = OUTPUT_DIR / f"{name}.txt"

    content = [
        "status=complete",
        f"sid={sid}",
        f"elapsed_min={elapsed_min}",
        f"score={score if score is not None else ''}",
        f"desc={desc}",
        f"filename={filename}",
        f"timestamp={ts.isoformat()}",
    ]
    outpath.write_text("\n".join(content), encoding="utf-8")
    print(f"[written] {outpath}")


def check_submission_status(comp: str):
    """提出の状態を定期的にチェック"""
    tracked = []
    for obj in get_all_submissions(comp):
        sid, status, *_ = normalize_submission_obj(obj)
        if "complete" not in status and "error" not in status:
            tracked.append(sid)

    while tracked:
        now_utc = datetime.datetime.now(timezone.utc).replace(tzinfo=None)
        print(datetime.datetime.now(), "checking...")

        new_tracked = []
        for obj in get_all_submissions(comp):
            sid, status, submit_time, score, filename, desc = normalize_submission_obj(obj)
            elapsed = None
            if submit_time:
                elapsed = int((now_utc - submit_time.replace(tzinfo=None)).total_seconds() / 60) + 1

            if sid in tracked:
                if "complete" in status:
                    print(f"✅ 完了: LB={score}, run-time={elapsed}min desc={desc}")
                    write_completion_marker(sid, submit_time, now_utc, elapsed, score, filename, desc)
                elif "error" in status:
                    print(f"❌ エラー: desc={desc}, elapsed={elapsed}min")
                else:
                    print(f"⏳ RUNNING: desc={desc}, elapsed={elapsed}min")

            if "complete" not in status and "error" not in status:
                new_tracked.append(sid)

        tracked = new_tracked
        time.sleep(60)


def main():
    while True:
        active = []
        for obj in get_all_submissions(COMPETITION):
            _, status, *_ = normalize_submission_obj(obj)
            if "complete" not in status and "error" not in status:
                active.append(obj)

        if active:
            check_submission_status(COMPETITION)
        else:
            print(datetime.datetime.now(), "no active submissions")
            time.sleep(5 * 60)


if __name__ == "__main__":
    main()
