"""
북미 영어권 뉴스 + Reddit 수집 모듈
- Google News RSS (US 한정, 최근 7일)
- Reddit PRAW (SkincareAddiction, muacjdiscussion, Sephora, kbeauty)
"""

import os
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Google News RSS 검색 키워드
NEWS_KEYWORDS = [
    "K-beauty",
    "Korean skincare",
    "Korean beauty TikTok",
    "pore serum",
    "glass skin",
    "ampoule serum",
]

# Reddit 타겟 서브레딧
SUBREDDITS = ["SkincareAddiction", "muacjdiscussion", "Sephora", "kbeauty"]

# Reddit 필터 키워드
REDDIT_FILTER_KEYWORDS = [
    "ampoule", "serum", "pore", "essence", "niacinamide",
    "snail mucin", "centella", "glass skin", "k-beauty", "kbeauty",
    "COSRX", "Anua", "Skin1004",
]

GOOGLE_NEWS_BASE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def _is_within_7_days(date_str: str) -> bool:
    """날짜 문자열이 최근 7일 이내인지 확인"""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return dt >= cutoff
    except Exception:
        return True  # 파싱 실패 시 포함


def _clean_text(text: str) -> str:
    """HTML 태그 제거 및 공백 정리"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def collect_google_news() -> list[dict]:
    """Google News RSS에서 K-뷰티 관련 뉴스 수집"""
    articles = []
    seen_urls = set()

    for keyword in NEWS_KEYWORDS:
        try:
            url = GOOGLE_NEWS_BASE.format(query=quote(keyword))
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; kbeauty-newsletter/1.0)"},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning(f"Google News RSS 오류 ({keyword}): HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.content, "lxml-xml")
            items = soup.find_all("item")

            for item in items:
                title = _clean_text(item.find("title").get_text() if item.find("title") else "")
                link = item.find("link").get_text() if item.find("link") else ""
                pub_date = item.find("pubDate").get_text() if item.find("pubDate") else ""
                description = _clean_text(
                    item.find("description").get_text() if item.find("description") else ""
                )

                if not title or not link:
                    continue
                if link in seen_urls:
                    continue
                if pub_date and not _is_within_7_days(pub_date):
                    continue

                seen_urls.add(link)
                articles.append({
                    "title": title,
                    "url": link,
                    "date": pub_date,
                    "source": "google_news",
                    "keyword": keyword,
                    "summary": description[:200],
                })

            logger.info(f"Google News 수집 ({keyword}): {len(items)}개 항목")

        except Exception as e:
            logger.warning(f"Google News 수집 오류 ({keyword}): {e}")

    logger.info(f"Google News 총 수집: {len(articles)}개 (중복 제거 완료)")
    return articles


def collect_reddit_posts() -> list[dict]:
    """Reddit PRAW로 K-뷰티 관련 포스트 수집"""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "kbeauty-newsletter/1.0")

    if not client_id or not client_secret:
        logger.warning("Reddit API 키 없음 → Reddit 수집 건너뜀")
        return []

    try:
        import praw
    except ImportError:
        logger.warning("praw 미설치 → Reddit 수집 건너뜀")
        return []

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except Exception as e:
        logger.warning(f"Reddit 초기화 오류: {e}")
        return []

    posts = []
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
    filter_pattern = re.compile(
        "|".join(re.escape(kw) for kw in REDDIT_FILTER_KEYWORDS),
        re.IGNORECASE,
    )

    for sub_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.new(limit=100):
                # 7일 이내 필터
                if post.created_utc < cutoff_ts:
                    continue
                # 업보트 50 이상 필터
                if post.score < 50:
                    continue
                # 영어 포스트만 (제목 기준 ASCII 비율)
                if len(post.title) > 0:
                    ascii_ratio = sum(ord(c) < 128 for c in post.title) / len(post.title)
                    if ascii_ratio < 0.7:
                        continue
                # 필터 키워드 포함 여부
                combined_text = f"{post.title} {post.selftext[:500]}"
                if not filter_pattern.search(combined_text):
                    continue

                summary = _clean_text(post.selftext[:200]) if post.selftext else "(링크 포스트)"
                posts.append({
                    "title": post.title,
                    "url": f"https://reddit.com{post.permalink}",
                    "date": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
                    "source": f"reddit/{sub_name}",
                    "score": post.score,
                    "summary": summary,
                    "num_comments": post.num_comments,
                })

            logger.info(f"Reddit r/{sub_name} 수집 완료")

        except Exception as e:
            logger.warning(f"Reddit r/{sub_name} 오류: {e}")

    # 업보트 순 정렬
    posts.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"Reddit 총 수집: {len(posts)}개")
    return posts


def collect_all() -> dict:
    """
    뉴스 + Reddit 통합 수집.

    Returns:
        {
            "news": [...],
            "reddit": [...],
            "total_count": int,
            "collected_at": str,
        }
    """
    logger.info("뉴스 + Reddit 수집 시작")

    news = collect_google_news()
    reddit = collect_reddit_posts()

    return {
        "news": news,
        "reddit": reddit,
        "total_count": len(news) + len(reddit),
        "collected_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = collect_all()
    print(f"\n뉴스: {len(data['news'])}개")
    for item in data["news"][:3]:
        print(f"  [{item['date'][:10]}] {item['title'][:60]}")
    print(f"\nReddit: {len(data['reddit'])}개")
    for item in data["reddit"][:3]:
        print(f"  [{item['score']}↑] {item['title'][:60]}")
