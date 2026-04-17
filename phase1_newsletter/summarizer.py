"""
Google Gemini API로 수집된 트렌드/뉴스 데이터를 마케터용 HTML 뉴스레터로 요약.
- 모델: gemini-1.5-flash
- 언어: 한국어 출력
- 출력: HTML 이메일 형식
"""

import os
import logging
from datetime import datetime

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = "gemini-flash-latest"

SYSTEM_INSTRUCTION = """당신은 K-뷰티 브랜드의 북미 시장 마케팅 전략가입니다.
판매 제품: 앰플, 세럼, 모공 앰플 (K-뷰티)
타겟 시장: 북미 (US 중심)
경쟁 브랜드: COSRX, Anua, Skin1004, Some By Mi, Isntree, Torriden

수집된 TikTok 트렌드, 구글 트렌드, 뉴스, Reddit 데이터를 분석하여
마케터가 즉시 활용할 수 있는 인사이트를 한국어로 제공합니다.
HTML 뉴스레터 형식으로 작성하되, 실용적이고 구체적인 액션 포인트를 포함하세요."""

HTML_TEMPLATE_HEADER = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>K-뷰티 위클리 - 북미 트렌드 리포트</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', Arial, sans-serif;
         background-color: #f8f4f0; margin: 0; padding: 0; color: #333; }}
  .container {{ max-width: 680px; margin: 0 auto; background: #fff; }}
  .header {{ background: linear-gradient(135deg, #ff6b9d, #c44ba5);
             padding: 32px 24px; text-align: center; }}
  .header h1 {{ color: #fff; margin: 0; font-size: 22px; font-weight: 700; }}
  .header p {{ color: rgba(255,255,255,0.85); margin: 8px 0 0; font-size: 14px; }}
  .section {{ padding: 24px; border-bottom: 1px solid #f0e8e8; }}
  .section-title {{ font-size: 16px; font-weight: 700; margin: 0 0 16px;
                    padding: 8px 12px; border-radius: 6px; color: #fff; }}
  .s1 .section-title {{ background: #ff6b9d; }}
  .s2 .section-title {{ background: #7c3aed; }}
  .s3 .section-title {{ background: #0891b2; }}
  .s4 .section-title {{ background: #059669; }}
  .s5 .section-title {{ background: #d97706; }}
  .hashtag-chip {{ display: inline-block; background: #fdf2f8; border: 1px solid #fbcfe8;
                   color: #9d174d; padding: 4px 10px; border-radius: 20px; font-size: 13px;
                   margin: 3px 3px 3px 0; font-weight: 500; }}
  .hashtag-up {{ background: #f0fdf4; border-color: #86efac; color: #166534; }}
  .hashtag-down {{ background: #fef2f2; border-color: #fca5a5; color: #991b1b; }}
  .news-item {{ background: #f9fafb; border-left: 3px solid #0891b2; padding: 12px 14px;
                margin: 10px 0; border-radius: 0 6px 6px 0; }}
  .news-item a {{ color: #0891b2; text-decoration: none; font-weight: 600; font-size: 14px; }}
  .news-item .meta {{ color: #6b7280; font-size: 12px; margin-top: 4px; }}
  .reddit-item {{ background: #f5f3ff; border-left: 3px solid #7c3aed; padding: 12px 14px;
                  margin: 10px 0; border-radius: 0 6px 6px 0; }}
  .reddit-item .score {{ background: #7c3aed; color: #fff; padding: 2px 7px;
                         border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .action-box {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
                 padding: 14px 16px; margin: 10px 0; }}
  .action-box strong {{ color: #92400e; }}
  .hook-box {{ background: #ecfdf5; border: 1px solid #6ee7b7; border-radius: 8px;
               padding: 12px 16px; margin: 8px 0; font-style: italic; color: #065f46; }}
  .trend-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
                  font-size: 11px; font-weight: 600; margin-left: 6px; }}
  .trend-up {{ background: #dcfce7; color: #166534; }}
  .trend-down {{ background: #fee2e2; color: #991b1b; }}
  .trend-stable {{ background: #f3f4f6; color: #4b5563; }}
  .footer {{ padding: 20px 24px; text-align: center; color: #9ca3af; font-size: 12px;
             background: #f9fafb; }}
  @media (max-width: 600px) {{
    .section {{ padding: 16px; }}
    .header h1 {{ font-size: 18px; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🌸 K-뷰티 위클리</h1>
    <p>북미 TikTok & 소비자 트렌드 리포트 | {date}</p>
  </div>"""

HTML_TEMPLATE_FOOTER = """
  <div class="footer">
    <p>K-뷰티 마케팅팀 · 자동 생성 리포트<br>
    데이터 기준: 최근 7일 | 다음 발행: 다음 주 일요일</p>
  </div>
</div>
</body>
</html>"""


def _build_prompt(trend_data: dict, news_data: dict) -> str:
    """Gemini에게 전달할 프롬프트 구성"""

    # 해시태그 데이터 요약
    hashtags_text = ""
    for item in trend_data.get("hashtags", [])[:12]:
        direction_emoji = {"상승": "📈", "하락": "📉", "유지": "➡️"}.get(
            item["trend_direction"], "➡️"
        )
        hashtags_text += (
            f"- {item['hashtag']} | 관련도: {item['relevance_score']}/10 | "
            f"{direction_emoji} {item['trend_direction']} | "
            f"관심도: {item.get('current_interest', 'N/A')}\n"
        )

    # Google Trends 데이터
    gtrends_text = ""
    for item in trend_data.get("google_trends", []):
        direction_emoji = {"상승": "📈", "하락": "📉", "유지": "➡️"}.get(
            item["trend_direction"], "➡️"
        )
        gtrends_text += (
            f"- {item['hashtag']} | 현재 관심도: {item.get('current_interest', 0)} | "
            f"최고: {item.get('peak_interest', 0)} | {direction_emoji} {item['trend_direction']}\n"
        )

    # 뉴스 데이터
    news_text = ""
    for item in news_data.get("news", [])[:8]:
        news_text += f"- [{item['date'][:10] if item['date'] else 'N/A'}] {item['title']}\n"
        if item.get("summary"):
            news_text += f"  → {item['summary'][:150]}\n"
        news_text += f"  URL: {item['url']}\n"

    # Reddit 데이터
    reddit_text = ""
    for item in news_data.get("reddit", [])[:6]:
        reddit_text += (
            f"- [{item['source']}] {item['title']}\n"
            f"  업보트: {item.get('score', 0)} | 댓글: {item.get('num_comments', 0)}\n"
        )
        if item.get("summary") and item["summary"] != "(링크 포스트)":
            reddit_text += f"  내용: {item['summary'][:150]}\n"

    source_note = trend_data.get("source_note", "")

    prompt = f"""아래 데이터를 분석하여 K-뷰티 마케터를 위한 주간 HTML 뉴스레터를 작성하세요.

## 데이터 수집 정보
- 수집 일시: {trend_data.get('collected_at', datetime.now().isoformat())[:16]}
- 트렌드 데이터 출처: {source_note}
- 수집된 뉴스/Reddit 수: {news_data.get('total_count', 0)}개

---

## [TikTok 타겟 해시태그 + Google Trends US 데이터]
{hashtags_text if hashtags_text else "데이터 없음"}

## [Google Trends 키워드 데이터]
{gtrends_text if gtrends_text else "데이터 없음"}

## [북미 K-뷰티 뉴스]
{news_text if news_text else "데이터 없음"}

## [Reddit 소비자 반응]
{reddit_text if reddit_text else "데이터 없음"}

---

## 출력 형식 요구사항

아래 5개 섹션을 포함하는 HTML을 작성하세요.
각 섹션은 <div class="section s[번호]">로 감싸고, 다음 구조를 따르세요:

**섹션 1 - 이번 주 북미 TikTok 핫 해시태그** (class="s1")
- 상위 7-10개 해시태그를 <span class="hashtag-chip hashtag-up/hashtag-down">으로 표시
- 각 해시태그 옆에 <span class="trend-badge trend-up/trend-down/trend-stable">트렌드</span>
- 우리 제품(앰플/세럼/모공케어)과의 연관성 1-2문장 설명

**섹션 2 - 북미 소비자 반응** (class="s2")
- Reddit 주요 포스트 3-4개를 <div class="reddit-item">으로 표시
- <span class="score">↑업보트수</span> 태그 포함
- 앰플/세럼/모공케어 관련 인사이트 강조

**섹션 3 - 북미 미디어 K-뷰티 동향** (class="s3")
- 주요 뉴스 3-5개를 <div class="news-item">으로 표시
- 뉴스 제목에 <a href="URL">링크</a> 추가
- <div class="meta">날짜 | 출처</div> 포함
- 각 뉴스의 마케팅 시사점 1문장

**섹션 4 - Google Trends 인사이트** (class="s4")
- 이번 주 상승/하락 키워드 분석
- 검색량 급상승 키워드의 마케팅 활용 방안

**섹션 5 - 이번 주 마케터 액션 포인트** (class="s5")
- <div class="action-box">어필리에이터에게 강조할 해시태그 TOP 5 (# 포함)</div>
- <div class="hook-box">콘텐츠 훅(hook) 2-3개 (따옴표 형식으로)</div>
- <div class="action-box">주의할 경쟁 브랜드 동향 (COSRX, Anua, Skin1004, Some By Mi, Isntree, Torriden 중 관련된 것)</div>

HTML 태그만 출력하세요 (<!DOCTYPE>이나 <html> 없이, <div class="container"> 내부 섹션들만).
반드시 한국어로 작성하세요."""

    return prompt


def generate_newsletter(trend_data: dict, news_data: dict) -> str:
    """
    Gemini API로 HTML 뉴스레터 생성.

    Args:
        trend_data: tiktok_trends.collect_trends() 반환값
        news_data: news_collector.collect_all() 반환값

    Returns:
        완성된 HTML 문자열
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)

    prompt = _build_prompt(trend_data, news_data)
    today = datetime.now().strftime("%Y년 %m월 %d일")

    logger.info(f"Gemini API 호출 시작 (모델: {MODEL})")

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            max_output_tokens=8000,
            temperature=0.7,
        ),
    )

    html_body = response.text
    usage = response.usage_metadata
    logger.info(
        f"Gemini API 완료 | 입력 토큰: {usage.prompt_token_count} | "
        f"출력 토큰: {usage.candidates_token_count}"
    )

    # 전체 HTML 조립
    html_output = (
        HTML_TEMPLATE_HEADER.format(date=today)
        + "\n"
        + html_body.strip()
        + HTML_TEMPLATE_FOOTER
    )

    logger.info(f"뉴스레터 HTML 생성 완료 ({len(html_output):,} 바이트)")
    return html_output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 테스트용 더미 데이터
    dummy_trends = {
        "hashtags": [
            {"hashtag": "#ampoule", "relevance_score": 9, "trend_direction": "상승", "current_interest": 85},
            {"hashtag": "#kbeautyserum", "relevance_score": 9, "trend_direction": "상승", "current_interest": 72},
            {"hashtag": "#poreminimizer", "relevance_score": 9, "trend_direction": "유지", "current_interest": 60},
            {"hashtag": "#glasskin", "relevance_score": 6, "trend_direction": "상승", "current_interest": 90},
            {"hashtag": "#koreanskincare", "relevance_score": 6, "trend_direction": "유지", "current_interest": 78},
        ],
        "google_trends": [
            {"hashtag": "pore serum", "trend_direction": "상승", "current_interest": 82, "peak_interest": 95},
            {"hashtag": "Korean ampoule", "trend_direction": "상승", "current_interest": 70, "peak_interest": 80},
        ],
        "collected_at": datetime.now().isoformat(),
        "source_note": "Google Trends (테스트 데이터)",
    }
    dummy_news = {
        "news": [
            {
                "title": "K-Beauty TikTok trends dominate US skincare market in 2024",
                "url": "https://example.com/kbeauty-tiktok",
                "date": "Mon, 14 Apr 2025 10:00:00 +0000",
                "source": "google_news",
                "summary": "Korean skincare brands seeing massive growth on TikTok with pore-focused products...",
            }
        ],
        "reddit": [
            {
                "title": "COSRX Snail Mucin vs Skin1004 Centella - which is better for pores?",
                "url": "https://reddit.com/r/SkincareAddiction/test",
                "date": "2025-04-12T10:00:00+00:00",
                "source": "reddit/SkincareAddiction",
                "score": 342,
                "num_comments": 89,
                "summary": "I've been comparing these two serums for pore minimizing...",
            }
        ],
        "total_count": 2,
        "collected_at": datetime.now().isoformat(),
    }

    html = generate_newsletter(dummy_trends, dummy_news)
    output_path = "output/newsletter_test.html"
    import os
    os.makedirs("output", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"테스트 뉴스레터 저장: {output_path}")
