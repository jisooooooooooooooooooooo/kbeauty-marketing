"""
K-뷰티 위클리 뉴스레터 자동화 메인 orchestration.

실행 순서:
1. TikTok/Google Trends 수집
2. Google News RSS + Reddit 수집
3. Claude API로 HTML 뉴스레터 생성
4. Gmail 발송 (--dry-run 시 파일 저장)
5. Google Sheets 발송 이력 기록

사용법:
    python phase1_newsletter/main.py              # 정상 실행
    python phase1_newsletter/main.py --dry-run    # 발송 없이 HTML 파일 저장
"""

import sys
import os
import logging
import argparse
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("main")


def setup_output_dir():
    """output 디렉토리 생성"""
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def step_1_collect_trends() -> dict:
    """Step 1: TikTok + Google Trends 수집"""
    logger.info("=" * 50)
    logger.info("Step 1: TikTok/Google Trends 수집 시작")

    try:
        from phase1_newsletter.tiktok_trends import collect_trends

        data = collect_trends()
        hashtag_count = len(data.get("hashtags", []))
        gtrend_count = len(data.get("google_trends", []))
        logger.info(
            f"Step 1 완료: 해시태그 {hashtag_count}개, Google Trends {gtrend_count}개"
        )
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Step 1 실패: {e}")
        return {"success": False, "error": str(e), "data": _fallback_trends()}


def step_2_collect_news() -> dict:
    """Step 2: Google News + Reddit 수집"""
    logger.info("=" * 50)
    logger.info("Step 2: 뉴스/Reddit 수집 시작")

    try:
        from phase1_newsletter.news_collector import collect_all

        data = collect_all()
        news_count = len(data.get("news", []))
        reddit_count = len(data.get("reddit", []))
        logger.info(f"Step 2 완료: 뉴스 {news_count}개, Reddit {reddit_count}개")
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Step 2 실패: {e}")
        return {"success": False, "error": str(e), "data": _fallback_news()}


def step_3_generate_newsletter(trend_data: dict, news_data: dict) -> dict:
    """Step 3: Claude API로 HTML 뉴스레터 생성"""
    logger.info("=" * 50)
    logger.info("Step 3: Claude API 뉴스레터 생성 시작")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Step 3 실패: GEMINI_API_KEY 환경변수 없음")
        return {"success": False, "error": "GEMINI_API_KEY 없음", "html": None}

    try:
        from phase1_newsletter.summarizer import generate_newsletter

        html = generate_newsletter(trend_data, news_data)
        logger.info(f"Step 3 완료: HTML 생성 ({len(html):,} 바이트)")
        return {"success": True, "html": html}
    except Exception as e:
        logger.error(f"Step 3 실패: {e}")
        return {"success": False, "error": str(e), "html": None}


def step_4_send_or_save(html: str, dry_run: bool, output_dir: Path) -> dict:
    """Step 4: 이메일 발송 또는 dry-run 파일 저장"""
    logger.info("=" * 50)

    if dry_run:
        logger.info("Step 4: [DRY-RUN] 이메일 발송 건너뜀 → HTML 파일 저장")
        output_path = output_dir / "newsletter_preview.html"
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"Step 4 완료: {output_path}")
            return {"success": True, "mode": "dry-run", "path": str(output_path)}
        except Exception as e:
            logger.error(f"Step 4 실패 (파일 저장): {e}")
            return {"success": False, "error": str(e)}
    else:
        logger.info("Step 4: Gmail 발송 시작")
        try:
            from phase1_newsletter.mailer import send_newsletter

            result = send_newsletter(html)
            if result:
                logger.info("Step 4 완료: 이메일 발송 성공")
                return {"success": True, "mode": "send"}
            else:
                logger.error("Step 4 실패: 이메일 발송 실패")
                return {"success": False, "error": "발송 실패"}
        except Exception as e:
            logger.error(f"Step 4 실패: {e}")
            return {"success": False, "error": str(e)}


def step_5_log_to_sheets(
    news_count: int,
    trend_count: int,
    send_status: str,
    note: str = "",
) -> dict:
    """Step 5: Google Sheets 발송 이력 기록"""
    logger.info("=" * 50)
    logger.info("Step 5: Google Sheets 이력 기록 시작")

    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheets_id:
        logger.warning("Step 5 건너뜀: GOOGLE_SHEETS_ID 환경변수 없음")
        return {"success": False, "skipped": True}

    try:
        from shared.sheets import log_newsletter_send

        result = log_newsletter_send(news_count, trend_count, send_status, note)
        if result:
            logger.info("Step 5 완료: Google Sheets 기록 성공")
            return {"success": True}
        else:
            logger.error("Step 5 실패: Google Sheets 기록 실패")
            return {"success": False}
    except Exception as e:
        logger.warning(f"Step 5 실패 (무시하고 계속): {e}")
        return {"success": False, "error": str(e)}


def _fallback_trends() -> dict:
    """트렌드 수집 실패 시 기본값"""
    return {
        "hashtags": [
            {"hashtag": "#kbeauty", "relevance_score": 6, "trend_direction": "유지", "current_interest": 0},
            {"hashtag": "#ampoule", "relevance_score": 9, "trend_direction": "유지", "current_interest": 0},
            {"hashtag": "#koreanskincare", "relevance_score": 6, "trend_direction": "유지", "current_interest": 0},
        ],
        "google_trends": [],
        "collected_at": datetime.now().isoformat(),
        "source_note": "데이터 수집 실패 (기본값 사용)",
    }


def _fallback_news() -> dict:
    """뉴스 수집 실패 시 기본값"""
    return {
        "news": [],
        "reddit": [],
        "total_count": 0,
        "collected_at": datetime.now().isoformat(),
    }


def run(dry_run: bool = False):
    """메인 실행 함수"""
    start_time = datetime.now()
    output_dir = setup_output_dir()

    logger.info("K-뷰티 위클리 뉴스레터 자동화 시작")
    logger.info(f"모드: {'DRY-RUN (발송 없음)' if dry_run else '실제 발송'}")
    logger.info(f"시작 시각: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # Step 1: 트렌드 수집
    r1 = step_1_collect_trends()
    results["trends"] = r1
    trend_data = r1["data"]

    # Step 2: 뉴스/Reddit 수집
    r2 = step_2_collect_news()
    results["news"] = r2
    news_data = r2["data"]

    # Step 3: 뉴스레터 HTML 생성
    r3 = step_3_generate_newsletter(trend_data, news_data)
    results["newsletter"] = r3

    if not r3["success"] or not r3.get("html"):
        logger.error("뉴스레터 생성 실패. 프로세스 중단.")
        _print_summary(results, start_time)
        sys.exit(1)

    # Step 4: 발송 또는 저장
    r4 = step_4_send_or_save(r3["html"], dry_run, output_dir)
    results["send"] = r4

    # Step 5: Google Sheets 기록
    send_status = "dry-run" if dry_run else ("성공" if r4["success"] else "실패")
    note = r4.get("path", "") if dry_run else r4.get("error", "")
    r5 = step_5_log_to_sheets(
        news_count=news_data.get("total_count", 0),
        trend_count=len(trend_data.get("hashtags", [])),
        send_status=send_status,
        note=note,
    )
    results["sheets"] = r5

    _print_summary(results, start_time, dry_run)

    # 실패 시 비정상 종료
    if not r4["success"]:
        sys.exit(1)


def _print_summary(results: dict, start_time: datetime, dry_run: bool = False):
    """실행 결과 요약 출력"""
    elapsed = (datetime.now() - start_time).total_seconds()

    logger.info("=" * 50)
    logger.info("실행 결과 요약")
    logger.info("=" * 50)

    steps = [
        ("Step 1 TikTok/Trends", results.get("trends", {})),
        ("Step 2 뉴스/Reddit", results.get("news", {})),
        ("Step 3 뉴스레터 생성", results.get("newsletter", {})),
        ("Step 4 발송/저장", results.get("send", {})),
        ("Step 5 Sheets 기록", results.get("sheets", {})),
    ]

    all_success = True
    for step_name, result in steps:
        if result.get("skipped"):
            status = "⏭  건너뜀"
        elif result.get("success"):
            status = "✅ 성공"
        else:
            status = "❌ 실패"
            all_success = False
        logger.info(f"{step_name}: {status}")

    if dry_run and results.get("send", {}).get("path"):
        logger.info(f"\n📄 미리보기 파일: {results['send']['path']}")

    logger.info(f"\n총 소요시간: {elapsed:.1f}초")
    logger.info("=" * 50)

    if all_success:
        logger.info("✅ 모든 단계 완료")
    else:
        logger.warning("⚠️  일부 단계 실패 (로그 확인 필요)")


def main():
    parser = argparse.ArgumentParser(
        description="K-뷰티 위클리 뉴스레터 자동화",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python phase1_newsletter/main.py --dry-run   # HTML 미리보기 생성
  python phase1_newsletter/main.py             # 이메일 발송
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="이메일 발송 없이 output/newsletter_preview.html 파일로 저장",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
