#!/bin/bash
pip install -r requirements.txt
echo "의존성 설치 완료"
echo ""
echo "다음 단계:"
echo "1. cp .env.example .env 후 API 키 입력"
echo "2. credentials/ 폴더에 Google 서비스 계정 JSON 저장"
echo "3. python phase1_newsletter/main.py --dry-run 으로 테스트"
echo ""
# crontab 등록 (매주 일요일 오전 8시)
CRON_JOB="0 8 * * 0 cd $(pwd) && python phase1_newsletter/main.py >> logs/newsletter.log 2>&1"
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
echo "crontab 등록 완료: 매주 일요일 오전 8시 자동 실행"
