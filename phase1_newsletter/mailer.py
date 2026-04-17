"""
Gmail SMTP로 HTML 뉴스레터 발송 모듈.
- .env에서 GMAIL_USER, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL 로드
- HTML + plaintext MIMEMultipart
- 발송 성공/실패 로그 출력
"""

import os
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _html_to_plaintext(html: str) -> str:
    """HTML에서 태그 제거하여 plaintext 변환 (간이 방식)"""
    import re

    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def send_newsletter(html_content: str, subject: str | None = None) -> bool:
    """
    Gmail SMTP로 HTML 뉴스레터 발송.

    Args:
        html_content: 발송할 HTML 문자열
        subject: 이메일 제목 (None이면 기본 형식 사용)

    Returns:
        발송 성공 여부 (bool)
    """
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL")

    # 환경변수 검증
    missing = []
    if not gmail_user:
        missing.append("GMAIL_USER")
    if not gmail_password:
        missing.append("GMAIL_APP_PASSWORD")
    if not recipient:
        missing.append("RECIPIENT_EMAIL")

    if missing:
        logger.error(f"이메일 발송 실패: 환경변수 누락 - {', '.join(missing)}")
        return False

    # 제목 생성
    today = datetime.now().strftime("%Y년 %m월 %d일")
    if subject is None:
        subject = f"[K-뷰티 위클리] 북미 트렌드 리포트 - {today}"

    # MIMEMultipart 이메일 구성
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient

    # plaintext 파트 (HTML 미지원 클라이언트 대비)
    plain_text = _html_to_plaintext(html_content)
    part1 = MIMEText(plain_text, "plain", "utf-8")
    part2 = MIMEText(html_content, "html", "utf-8")

    # MIMEMultipart에서 마지막 파트가 우선 렌더링됨
    msg.attach(part1)
    msg.attach(part2)

    # Gmail SMTP 발송
    try:
        logger.info(f"Gmail SMTP 연결 시도: smtp.gmail.com:587")
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, [recipient], msg.as_string())

        logger.info(f"이메일 발송 성공 → {recipient}")
        logger.info(f"제목: {subject}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Gmail 인증 실패: {e}")
        logger.error(
            "Gmail 앱 비밀번호를 확인하세요. "
            "2단계 인증 활성화 후 https://myaccount.google.com/apppasswords 에서 생성 필요."
        )
        return False
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"수신자 거부됨: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP 오류: {e}")
        return False
    except TimeoutError:
        logger.error("Gmail SMTP 연결 타임아웃")
        return False
    except Exception as e:
        logger.error(f"이메일 발송 중 예상치 못한 오류: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 테스트: 샘플 HTML 발송
    sample_html = """<!DOCTYPE html>
<html><body>
<h1>K-뷰티 위클리 테스트</h1>
<p>이것은 테스트 이메일입니다.</p>
</body></html>"""

    result = send_newsletter(sample_html, subject="[테스트] K-뷰티 위클리 발송 테스트")
    print(f"발송 결과: {'성공' if result else '실패'}")
