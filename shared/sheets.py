"""
Google Sheets 공통 모듈.
- gspread + google-auth 사용
- .env에서 GOOGLE_SHEETS_ID, GOOGLE_SERVICE_ACCOUNT_JSON 로드
"""

import os
import json
import logging
from typing import Any

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 뉴스레터 발송 이력 시트
NEWSLETTER_LOG_SHEET = "newsletter_log"
NEWSLETTER_LOG_COLUMNS = ["날짜", "수집된_뉴스_수", "트렌드_수", "발송_상태", "비고"]


def _get_client():
    """gspread 클라이언트 초기화"""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError(
            "gspread 또는 google-auth 미설치. "
            "pip install gspread google-auth google-auth-oauthlib 실행 필요."
        )

    service_account_path = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON", "./credentials/google-service-account.json"
    )

    if not os.path.exists(service_account_path):
        raise FileNotFoundError(
            f"Google 서비스 계정 JSON 파일 없음: {service_account_path}\n"
            f"credentials/ 폴더에 Google 서비스 계정 JSON 파일을 배치하세요."
        )

    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_file(service_account_path, scopes=scopes)
    client = gspread.authorize(creds)
    return client


def _get_spreadsheet():
    """스프레드시트 객체 반환"""
    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheets_id:
        raise ValueError("GOOGLE_SHEETS_ID 환경변수가 설정되지 않았습니다.")

    client = _get_client()
    return client.open_by_key(sheets_id)


def _ensure_sheet_exists(spreadsheet, sheet_name: str, headers: list[str] | None = None):
    """시트가 없으면 생성하고 헤더 추가"""
    try:
        sheet = spreadsheet.worksheet(sheet_name)
        return sheet
    except Exception:
        # 시트 없음 → 새로 생성
        logger.info(f"시트 '{sheet_name}' 생성 중...")
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
        if headers:
            sheet.append_row(headers)
            logger.info(f"시트 '{sheet_name}' 헤더 추가: {headers}")
        return sheet


def append_row(sheet_name: str, data: list[Any]) -> bool:
    """
    시트에 행 추가.

    Args:
        sheet_name: 시트 이름
        data: 추가할 데이터 리스트

    Returns:
        성공 여부
    """
    try:
        spreadsheet = _get_spreadsheet()
        headers = NEWSLETTER_LOG_COLUMNS if sheet_name == NEWSLETTER_LOG_SHEET else None
        sheet = _ensure_sheet_exists(spreadsheet, sheet_name, headers)
        sheet.append_row(data)
        logger.info(f"Google Sheets '{sheet_name}' 행 추가 완료: {data[:3]}...")
        return True
    except Exception as e:
        logger.error(f"Google Sheets append_row 오류 ({sheet_name}): {e}")
        return False


def read_sheet(sheet_name: str) -> list[list[Any]]:
    """
    시트 전체 데이터 읽기.

    Args:
        sheet_name: 시트 이름

    Returns:
        2D 리스트 (헤더 포함)
    """
    try:
        spreadsheet = _get_spreadsheet()
        sheet = spreadsheet.worksheet(sheet_name)
        data = sheet.get_all_values()
        logger.info(f"Google Sheets '{sheet_name}' 읽기 완료: {len(data)}행")
        return data
    except Exception as e:
        logger.error(f"Google Sheets read_sheet 오류 ({sheet_name}): {e}")
        return []


def clear_and_write(sheet_name: str, data: list[list[Any]]) -> bool:
    """
    시트를 초기화하고 새 데이터 쓰기.

    Args:
        sheet_name: 시트 이름
        data: 쓸 데이터 (2D 리스트, 첫 행은 헤더)

    Returns:
        성공 여부
    """
    try:
        spreadsheet = _get_spreadsheet()
        try:
            sheet = spreadsheet.worksheet(sheet_name)
        except Exception:
            sheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)

        sheet.clear()
        if data:
            sheet.update("A1", data)
        logger.info(f"Google Sheets '{sheet_name}' 데이터 쓰기 완료: {len(data)}행")
        return True
    except Exception as e:
        logger.error(f"Google Sheets clear_and_write 오류 ({sheet_name}): {e}")
        return False


def log_newsletter_send(
    news_count: int,
    trend_count: int,
    send_status: str,
    note: str = "",
) -> bool:
    """
    뉴스레터 발송 이력 기록.

    Args:
        news_count: 수집된 뉴스 수
        trend_count: 수집된 트렌드 수
        send_status: 발송 상태 ("성공" / "실패" / "dry-run")
        note: 추가 메모

    Returns:
        성공 여부
    """
    from datetime import datetime

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        news_count,
        trend_count,
        send_status,
        note,
    ]
    return append_row(NEWSLETTER_LOG_SHEET, row)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 연결 테스트
    try:
        result = log_newsletter_send(
            news_count=10,
            trend_count=12,
            send_status="테스트",
            note="연결 테스트",
        )
        print(f"Google Sheets 연결 테스트: {'성공' if result else '실패'}")
    except Exception as e:
        print(f"Google Sheets 연결 실패: {e}")
        print("GOOGLE_SHEETS_ID와 서비스 계정 JSON 파일을 확인하세요.")
