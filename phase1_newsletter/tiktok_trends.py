"""
TikTok 트렌딩 해시태그 + Google Trends 수집 모듈
- TikTok Creative Center 스크래핑 시도 (Selenium → requests 순)
- 막히면 pytrends로 Google Trends US 데이터로 대체
"""

import time
import logging
from datetime import datetime
from typing import Optional

import requests
from pytrends.request import TrendReq

logger = logging.getLogger(__name__)

# 우선 타겟 해시태그
TARGET_HASHTAGS = [
    "glasskin",
    "poreshrinking",
    "poreminimizer",
    "kbeautyserum",
    "ampoule",
    "skinessence",
    "serumtok",
    "kbeauty",
    "koreanskincare",
    "skincareroutine",
    "grwm",
    "skintok",
]

# Google Trends 키워드
GOOGLE_TRENDS_KEYWORDS = [
    "pore serum",
    "glass skin serum",
    "Korean ampoule",
    "pore minimizer serum",
    "niacinamide serum",
    "Korean skincare",
]

# 제품 카테고리 관련 키워드 (관련도 점수 산출용)
PRODUCT_RELATED_KEYWORDS = {
    "high": ["ampoule", "pore", "serum", "essence", "kbeautyserum", "serumtok", "poreminimizer", "poreshrinking", "skinessence"],
    "medium": ["kbeauty", "koreanskincare", "glasskin", "skintok"],
    "low": ["skincareroutine", "grwm"],
}


def _get_relevance_score(hashtag: str) -> int:
    """해시태그의 제품 관련도 점수 반환 (1-10)"""
    tag_lower = hashtag.lower().lstrip("#")
    for tag in PRODUCT_RELATED_KEYWORDS["high"]:
        if tag in tag_lower or tag_lower in tag:
            return 9
    for tag in PRODUCT_RELATED_KEYWORDS["medium"]:
        if tag in tag_lower or tag_lower in tag:
            return 6
    for tag in PRODUCT_RELATED_KEYWORDS["low"]:
        if tag in tag_lower or tag_lower in tag:
            return 3
    return 5


def _scrape_tiktok_creative_center() -> Optional[list[dict]]:
    """
    TikTok Creative Center에서 해시태그 트렌드 스크래핑 시도.
    TikTok은 강력한 봇 차단이 있으므로 실패 시 None 반환.
    """
    url = "https://ads.tiktok.com/business/creativecenter/trends/hashtag/pc/en?region=US"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://ads.tiktok.com/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"TikTok Creative Center 접근 실패: HTTP {resp.status_code}")
            return None
        # TikTok은 JS 렌더링 필요 — requests로는 실제 데이터 파싱 불가
        # 응답 본문에 트렌드 데이터가 없으면 None 반환
        if "trendingHashtag" not in resp.text and "hashtag" not in resp.text.lower():
            logger.info("TikTok Creative Center: JS 렌더링 필요, pytrends로 전환")
            return None
        return None  # 실제 파싱은 JS 렌더링 없이 불가
    except Exception as e:
        logger.warning(f"TikTok Creative Center 요청 오류: {e}")
        return None


def _get_pytrends_data() -> list[dict]:
    """
    pytrends로 Google Trends US 데이터 수집.
    TikTok 데이터 대체 + 보완 역할.
    """
    results = []
    pytrends = TrendReq(hl="en-US", tz=360)  # US Central Time

    # pytrends는 한 번에 최대 5개 키워드
    keyword_chunks = [
        GOOGLE_TRENDS_KEYWORDS[:5],
        GOOGLE_TRENDS_KEYWORDS[5:],
    ]

    for chunk in keyword_chunks:
        if not chunk:
            continue
        try:
            pytrends.build_payload(
                chunk,
                cat=0,
                timeframe="now 7-d",
                geo="US",
                gprop="",
            )
            interest_df = pytrends.interest_over_time()
            if interest_df.empty:
                logger.warning(f"Google Trends 데이터 없음: {chunk}")
                continue

            for kw in chunk:
                if kw not in interest_df.columns:
                    continue
                series = interest_df[kw]
                current_val = int(series.iloc[-1]) if len(series) > 0 else 0
                prev_val = int(series.iloc[0]) if len(series) > 0 else 0

                if current_val > prev_val * 1.1:
                    direction = "상승"
                elif current_val < prev_val * 0.9:
                    direction = "하락"
                else:
                    direction = "유지"

                results.append({
                    "hashtag": kw,
                    "source": "google_trends",
                    "relevance_score": _get_relevance_score(kw.replace(" ", "")),
                    "trend_direction": direction,
                    "current_interest": current_val,
                    "peak_interest": int(series.max()),
                    "collected_at": datetime.now().isoformat(),
                })
            time.sleep(1)  # 요청 간격 준수
        except Exception as e:
            logger.warning(f"pytrends 오류 ({chunk}): {e}")

    return results


def _build_hashtag_data_from_targets() -> list[dict]:
    """
    타겟 해시태그 목록을 기반으로 pytrends 보완 데이터 생성.
    TikTok 직접 수집이 불가할 때 해시태그를 Google Trends 키워드로 변환하여 조회.
    """
    results = []
    pytrends = TrendReq(hl="en-US", tz=360)

    # 해시태그를 공백 포함 검색어로 변환
    hashtag_to_query = {
        "glasskin": "glass skin",
        "poreshrinking": "pore shrinking",
        "poreminimizer": "pore minimizer",
        "kbeautyserum": "kbeauty serum",
        "ampoule": "ampoule",
        "skinessence": "skin essence",
        "serumtok": "serum tiktok",
        "kbeauty": "kbeauty",
        "koreanskincare": "korean skincare",
        "skincareroutine": "skincare routine",
        "grwm": "grwm skincare",
        "skintok": "skintok",
    }

    chunks = []
    items = list(hashtag_to_query.items())
    for i in range(0, len(items), 5):
        chunks.append(items[i : i + 5])

    for chunk in chunks:
        tags = [item[0] for item in chunk]
        queries = [item[1] for item in chunk]
        try:
            pytrends.build_payload(
                queries,
                cat=0,
                timeframe="now 7-d",
                geo="US",
                gprop="",
            )
            interest_df = pytrends.interest_over_time()

            for tag, query in zip(tags, queries):
                if interest_df.empty or query not in interest_df.columns:
                    # 데이터 없어도 타겟 해시태그는 포함
                    results.append({
                        "hashtag": f"#{tag}",
                        "source": "tiktok_target",
                        "relevance_score": _get_relevance_score(tag),
                        "trend_direction": "유지",
                        "current_interest": 0,
                        "peak_interest": 0,
                        "collected_at": datetime.now().isoformat(),
                    })
                    continue

                series = interest_df[query]
                current_val = int(series.iloc[-1]) if len(series) > 0 else 0
                prev_val = int(series.iloc[0]) if len(series) > 0 else 0

                if current_val > prev_val * 1.1:
                    direction = "상승"
                elif current_val < prev_val * 0.9:
                    direction = "하락"
                else:
                    direction = "유지"

                results.append({
                    "hashtag": f"#{tag}",
                    "source": "tiktok_target",
                    "relevance_score": _get_relevance_score(tag),
                    "trend_direction": direction,
                    "current_interest": current_val,
                    "peak_interest": int(series.max()),
                    "collected_at": datetime.now().isoformat(),
                })
            time.sleep(1)
        except Exception as e:
            logger.warning(f"해시태그 트렌드 조회 오류: {e}")
            # 오류 시에도 타겟 해시태그는 기본값으로 추가
            for tag in tags:
                results.append({
                    "hashtag": f"#{tag}",
                    "source": "tiktok_target",
                    "relevance_score": _get_relevance_score(tag),
                    "trend_direction": "유지",
                    "current_interest": 0,
                    "peak_interest": 0,
                    "collected_at": datetime.now().isoformat(),
                })

    return results


def collect_trends() -> dict:
    """
    트렌드 데이터 수집 메인 함수.

    Returns:
        {
            "hashtags": [...],       # TikTok 타겟 해시태그 + 트렌드 방향
            "google_trends": [...],  # Google Trends 키워드 데이터
            "collected_at": str,
            "source_note": str,
        }
    """
    logger.info("트렌드 데이터 수집 시작")

    # 1. TikTok Creative Center 스크래핑 시도
    tiktok_data = _scrape_tiktok_creative_center()

    if tiktok_data:
        logger.info(f"TikTok Creative Center 수집 성공: {len(tiktok_data)}개")
        source_note = "TikTok Creative Center (직접 수집)"
        hashtag_data = tiktok_data
    else:
        # 2. pytrends로 타겟 해시태그 트렌드 수집
        logger.info("TikTok Creative Center 접근 불가 → pytrends 대체 수집")
        source_note = "Google Trends (TikTok Creative Center 접근 불가로 대체)"
        hashtag_data = _build_hashtag_data_from_targets()
        logger.info(f"타겟 해시태그 트렌드 수집 완료: {len(hashtag_data)}개")

    # 3. Google Trends 키워드 데이터 추가 수집
    google_trends_data = _get_pytrends_data()
    logger.info(f"Google Trends 키워드 수집 완료: {len(google_trends_data)}개")

    # 관련도 점수 기준 정렬
    hashtag_data.sort(key=lambda x: x["relevance_score"], reverse=True)

    return {
        "hashtags": hashtag_data,
        "google_trends": google_trends_data,
        "collected_at": datetime.now().isoformat(),
        "source_note": source_note,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = collect_trends()
    print(f"\n수집된 해시태그: {len(data['hashtags'])}개")
    for item in data["hashtags"][:5]:
        print(f"  {item['hashtag']} | 관련도: {item['relevance_score']} | 트렌드: {item['trend_direction']}")
    print(f"\nGoogle Trends 키워드: {len(data['google_trends'])}개")
    for item in data["google_trends"][:3]:
        print(f"  {item['hashtag']} | 관심도: {item['current_interest']} | 트렌드: {item['trend_direction']}")
