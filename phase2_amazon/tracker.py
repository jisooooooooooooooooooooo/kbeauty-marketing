"""
아마존 베스트셀러 순위 변동 감지 및 Google Sheets 기록.
- data/amazon_history.json 에 날짜별 저장
- 전날 대비 변동 감지 (신규 진입, 급상승, 급하락, 경쟁 브랜드 신규)
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
HISTORY_FILE = DATA_DIR / "amazon_history.json"
CHANGE_THRESHOLD = 10  # 10위 이상 변동 시 알림

# 경쟁 브랜드 (소문자)
COMPETITOR_BRANDS = [
    "cosrx", "anua", "skin1004", "some by mi", "isntree", "torriden",
    "medicube", "beauty of joseon", "purito",
]


def _load_history() -> dict:
    """히스토리 파일 로드"""
    DATA_DIR.mkdir(exist_ok=True)
    if not HISTORY_FILE.exists():
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"히스토리 파일 로드 실패: {e}")
        return {}


def _save_history(history: dict):
    """히스토리 파일 저장"""
    DATA_DIR.mkdir(exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _get_yesterday_key() -> str:
    """어제 날짜 키 반환"""
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _get_today_key() -> str:
    """오늘 날짜 키 반환"""
    return datetime.now().strftime("%Y-%m-%d")


def save_today_data(items: list[dict]):
    """오늘 수집 데이터를 히스토리에 저장"""
    history = _load_history()
    today = _get_today_key()

    # K-뷰티 제품만 저장 (전체 저장 시 용량 고려)
    kbeauty_items = [i for i in items if i.get("is_kbeauty")]
    # 전체 TOP 100도 ASIN+순위만 저장 (변동 추적용)
    all_ranks = {i["asin"]: i["rank"] for i in items if i["asin"] != "N/A"}

    history[today] = {
        "kbeauty": kbeauty_items,
        "all_ranks": all_ranks,
        "total_count": len(items),
        "kbeauty_count": len(kbeauty_items),
        "saved_at": datetime.now().isoformat(),
    }

    # 30일 이상 된 데이터 정리
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    history = {k: v for k, v in history.items() if k >= cutoff}

    _save_history(history)
    logger.info(f"오늘 데이터 저장: {today} (K-뷰티 {len(kbeauty_items)}개)")


def detect_changes(today_items: list[dict]) -> dict:
    """
    전날 대비 변동 감지.

    Returns:
        {
            "new_entries": [...],        # 신규 진입 K-뷰티
            "rank_up": [...],            # 10위 이상 급상승
            "rank_down": [...],          # 10위 이상 급하락
            "competitor_new": [...],     # 경쟁 브랜드 신규 진입
            "has_changes": bool,
        }
    """
    history = _load_history()
    yesterday = _get_yesterday_key()

    today_kbeauty = [i for i in today_items if i.get("is_kbeauty")]

    # 전날 데이터 없으면 변동 감지 불가
    if yesterday not in history:
        logger.info("전날 데이터 없음 → 변동 감지 건너뜀 (첫 실행)")
        return {
            "new_entries": today_kbeauty,
            "rank_up": [],
            "rank_down": [],
            "competitor_new": today_kbeauty,
            "has_changes": True,
            "is_first_run": True,
        }

    yesterday_data = history[yesterday]
    yesterday_kbeauty = {i["asin"]: i for i in yesterday_data.get("kbeauty", []) if i["asin"] != "N/A"}
    yesterday_all_ranks = yesterday_data.get("all_ranks", {})

    new_entries = []
    rank_up = []
    rank_down = []
    competitor_new = []

    for item in today_kbeauty:
        asin = item["asin"]
        today_rank = item["rank"]
        brand_lower = item.get("brand", "").lower()

        if asin == "N/A":
            continue

        if asin not in yesterday_kbeauty and asin not in yesterday_all_ranks:
            # 완전 신규 진입
            new_entries.append({**item, "change_type": "신규 진입"})
            if any(c in brand_lower for c in COMPETITOR_BRANDS):
                competitor_new.append({**item, "change_type": "경쟁 브랜드 신규"})

        elif asin in yesterday_all_ranks:
            yesterday_rank = yesterday_all_ranks[asin]
            diff = yesterday_rank - today_rank  # 양수 = 상승

            if diff >= CHANGE_THRESHOLD:
                rank_up.append({
                    **item,
                    "yesterday_rank": yesterday_rank,
                    "rank_change": diff,
                    "change_type": f"↑{diff}위 급상승",
                })
            elif diff <= -CHANGE_THRESHOLD:
                rank_down.append({
                    **item,
                    "yesterday_rank": yesterday_rank,
                    "rank_change": diff,
                    "change_type": f"↓{abs(diff)}위 급하락",
                })

    # 급상승/급하락 TOP 5 정렬
    rank_up.sort(key=lambda x: x["rank_change"], reverse=True)
    rank_down.sort(key=lambda x: x["rank_change"])

    has_changes = bool(new_entries or rank_up or rank_down or competitor_new)
    logger.info(
        f"변동 감지: 신규 {len(new_entries)}개 | "
        f"급상승 {len(rank_up)}개 | 급하락 {len(rank_down)}개 | "
        f"경쟁 신규 {len(competitor_new)}개"
    )

    return {
        "new_entries": new_entries,
        "rank_up": rank_up[:5],
        "rank_down": rank_down[:5],
        "competitor_new": competitor_new,
        "has_changes": has_changes,
        "is_first_run": False,
    }


def get_kbeauty_summary(today_items: list[dict]) -> dict:
    """오늘의 K-뷰티 순위 요약 생성"""
    kbeauty = [i for i in today_items if i.get("is_kbeauty")]
    total = len(today_items)

    # 브랜드별 집계
    brand_counts: dict[str, int] = {}
    for item in kbeauty:
        brand = item.get("brand", "Unknown")
        brand_counts[brand] = brand_counts.get(brand, 0) + 1

    return {
        "total_top100": total,
        "kbeauty_count": len(kbeauty),
        "kbeauty_share": round(len(kbeauty) / total * 100, 1) if total > 0 else 0,
        "top_kbeauty": sorted(kbeauty, key=lambda x: x["rank"])[:10],
        "brand_breakdown": sorted(brand_counts.items(), key=lambda x: -x[1]),
    }


def log_to_sheets(today_items: list[dict], changes: dict) -> bool:
    """Google Sheets에 오늘 K-뷰티 순위 기록"""
    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheets_id:
        logger.warning("GOOGLE_SHEETS_ID 없음 → Sheets 기록 건너뜀")
        return False

    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from shared.sheets import append_row, clear_and_write

        today = _get_today_key()
        kbeauty_items = [i for i in today_items if i.get("is_kbeauty")]

        # 변동 사항 텍스트 생성
        def get_change_note(item: dict) -> str:
            asin = item["asin"]
            # rank_up/down/new_entries에서 해당 ASIN 찾기
            for entry in changes.get("new_entries", []):
                if entry["asin"] == asin:
                    return "신규 진입"
            for entry in changes.get("rank_up", []):
                if entry["asin"] == asin:
                    return entry.get("change_type", "")
            for entry in changes.get("rank_down", []):
                if entry["asin"] == asin:
                    return entry.get("change_type", "")
            return "-"

        rows = [
            [
                today,
                item["rank"],
                item["name"][:80],
                item["brand"],
                item["price"],
                item["rating"],
                item["review_count"],
                get_change_note(item),
            ]
            for item in sorted(kbeauty_items, key=lambda x: x["rank"])
        ]

        for row in rows:
            append_row("amazon_tracker", row)

        logger.info(f"Google Sheets 기록 완료: {len(rows)}행")
        return True

    except Exception as e:
        logger.warning(f"Google Sheets 기록 실패: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    history = _load_history()
    print(f"저장된 날짜: {list(history.keys())}")
