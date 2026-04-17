"""
아마존 US 뷰티 베스트셀러 TOP 100 스크래퍼.
- requests + BeautifulSoup (기본, 페이지당 ~30개)
- Selenium headless Chrome fallback (페이지당 50개 → 전체 100개 확보)
- fake_useragent 로테이션
- 2-3초 랜덤 딜레이, 최대 3회 재시도
"""

import time
import random
import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 수집 URL (페이지 1, 2 → TOP 100)
BESTSELLER_URLS = [
    "https://www.amazon.com/Best-Sellers-Beauty-Personal-Care/zgbs/beauty/ref=zg_bs_pg_1_beauty?_encoding=UTF8&pg=1",
    "https://www.amazon.com/Best-Sellers-Beauty-Personal-Care/zgbs/beauty/ref=zg_bs_pg_2_beauty?_encoding=UTF8&pg=2",
]

# K-뷰티 브랜드 목록 (소문자 통일 — 매칭 시 name.lower()와 비교)
KBEAUTY_BRANDS = [
    # 메인 브랜드
    "cosrx", "anua", "skin1004", "some by mi", "isntree", "torriden",
    "medicube", "beauty of joseon", "purito", "laneige", "innisfree",
    "etude", "missha", "the face shop", "klairs", "round lab",
    "abib", "jumiso", "axis-y", "axis y",
    # 확장 브랜드
    "biodance", "dr.althea", "dr. althea", "equalberry", "eqqualberry",
    "heimish", "i'm from", "im from", "ma:nyo", "manyo",
    "benton", "by wishtrend", "haruharu wonder", "haruharu", "numbuzin",
    "rovectin", "acwell", "re:p", "rep skincare",
    "goodal", "nacific", "neogen", "tocobo", "mixsoon",
    "skin&lab", "skin & lab", "tirtir", "mary&may", "mary & may",
    "illiyoon", "derma:b", "dermab",
    "holika holika", "tony moly", "nature republic", "skinfood",
    "vt cosmetics", "vt cosme", "mediheal", "leaders",
    "dr.jart", "dr. jart", "su:m37", "sum37",
    "sulwhasoo", "hanyul", "iope", "amorepacific", "history of whoo",
    "dr.melaxin", "dr. melaxin", "celimax",
]

# K-뷰티 감지 키워드 (브랜드명 외 제품명/설명에서 매칭)
KBEAUTY_KEYWORDS = ["korean", "k-beauty", "k beauty", "korea"]

# Fallback User-Agent 리스트 (fake_useragent 실패 시)
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def _get_user_agent() -> str:
    """fake_useragent 우선, 실패 시 fallback 리스트 사용"""
    try:
        from fake_useragent import UserAgent
        ua = UserAgent()
        return ua.chrome
    except Exception:
        return random.choice(FALLBACK_USER_AGENTS)


def _get_headers(referer: str = "") -> dict:
    """요청 헤더 생성"""
    headers = {
        "User-Agent": _get_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _fetch_page(url: str, max_retries: int = 3) -> BeautifulSoup | None:
    """페이지 가져오기 (최대 3회 재시도)"""
    for attempt in range(max_retries):
        try:
            delay = random.uniform(2.0, 3.5)
            if attempt > 0:
                delay = random.uniform(4.0, 7.0)
                logger.info(f"재시도 {attempt}/{max_retries} (대기 {delay:.1f}초)")
            time.sleep(delay)

            headers = _get_headers(
                referer="https://www.amazon.com/" if attempt > 0 else ""
            )
            session = requests.Session()
            session.headers.update(headers)

            resp = session.get(url, timeout=20, allow_redirects=True)

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "lxml")
                # 봇 차단 감지
                if _is_blocked(soup):
                    logger.warning(f"봇 차단 감지 (시도 {attempt + 1})")
                    continue
                return soup
            elif resp.status_code == 503:
                logger.warning(f"503 Service Unavailable (시도 {attempt + 1})")
            else:
                logger.warning(f"HTTP {resp.status_code} (시도 {attempt + 1})")

        except requests.exceptions.Timeout:
            logger.warning(f"타임아웃 (시도 {attempt + 1})")
        except requests.exceptions.RequestException as e:
            logger.warning(f"요청 오류 (시도 {attempt + 1}): {e}")

    return None


def _is_blocked(soup: BeautifulSoup) -> bool:
    """아마존 봇 차단 페이지 감지"""
    title = soup.find("title")
    if title:
        title_text = title.get_text().lower()
        if any(kw in title_text for kw in ["robot check", "sorry", "captcha", "access denied"]):
            return True
    # 차단 페이지 특징적 요소
    if soup.find("form", {"action": "/errors/validateCaptcha"}):
        return True
    return False


def _fetch_page_selenium(url: str) -> BeautifulSoup | None:
    """
    Selenium headless Chrome으로 JS 렌더링 + 스크롤 후 파싱.
    requests로 30개밖에 못 가져올 때 fallback으로 사용 (페이지당 최대 50개 확보).
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
    except ImportError:
        logger.warning("selenium 미설치 → 스킵")
        return None

    logger.info(f"Selenium fallback 사용: {url[:60]}...")
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(f"user-agent={_get_user_agent()}")
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        driver.set_window_size(1920, 1080)
        driver.get(url)
        time.sleep(4)  # 초기 로드 대기

        # 스크롤 다운해서 lazy-load 아이템을 순차적으로 트리거 (페이지당 50개)
        # 최소 6스텝은 스크롤해서 전체 아이템 로드 보장
        prev_count = 0
        stall_steps = 0
        for step in range(12):
            items = driver.find_elements(By.CSS_SELECTOR, "div.zg-grid-general-faceout")
            cur_count = len(items)
            if cur_count >= 50:
                break
            if cur_count == prev_count:
                stall_steps += 1
                if stall_steps >= 4 and step >= 6:
                    # 충분히 스크롤했는데 더 이상 새 아이템이 없으면 중단
                    break
            else:
                stall_steps = 0
            prev_count = cur_count
            driver.execute_script(f"window.scrollTo(0, {(step + 1) * 700});")
            time.sleep(1.5)

        html = driver.page_source
        soup = BeautifulSoup(html, "lxml")

        if _is_blocked(soup):
            logger.warning("Selenium: 봇 차단 감지")
            return None

        item_count = len(soup.select("div.zg-grid-general-faceout"))
        logger.info(f"Selenium 로드 완료: {item_count}개 컨테이너")
        return soup

    except Exception as e:
        logger.warning(f"Selenium 오류: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _parse_price(text: str) -> str:
    """가격 텍스트 정제"""
    if not text:
        return "N/A"
    text = text.strip()
    match = re.search(r"\$[\d,]+\.?\d*", text)
    return match.group(0) if match else text[:20]


def _parse_rating(text: str) -> str:
    """별점 텍스트 정제"""
    if not text:
        return "N/A"
    match = re.search(r"[\d.]+", text)
    return match.group(0) if match else "N/A"


def _parse_review_count(text: str) -> str:
    """리뷰 수 텍스트 정제"""
    if not text:
        return "0"
    text = re.sub(r"[,\s]", "", text)
    match = re.search(r"\d+", text)
    return match.group(0) if match else "0"


def _extract_asin(url: str) -> str:
    """URL에서 ASIN 추출"""
    match = re.search(r"/dp/([A-Z0-9]{10})", url)
    if match:
        return match.group(1)
    match = re.search(r"/product/([A-Z0-9]{10})", url)
    return match.group(1) if match else "N/A"


def _parse_items(soup: BeautifulSoup, page_offset: int = 0) -> list[dict]:
    """BeautifulSoup에서 베스트셀러 아이템 파싱"""
    items = []

    # 아마존 베스트셀러 아이템 컨테이너 선택자 — 가장 많은 결과를 반환하는 셀렉터 단독 사용
    candidate_selectors = [
        "div.zg-grid-general-faceout",
        "li.zg-item-immersion",
        "div[class*='zg-item']",
        "div.p13n-sc-uncoverable-faceout",
    ]
    best_containers: list = []
    for sel in candidate_selectors:
        found = soup.select(sel)
        if len(found) > len(best_containers):
            best_containers = found
    containers = best_containers

    if not containers:
        # 대체 선택자: data-asin 속성이 있는 div (10자리 ASIN), 중복 제거
        seen_asins_local: set[str] = set()
        for c in soup.select("div[data-asin]"):
            a = c.get("data-asin", "")
            if len(a) == 10 and a not in seen_asins_local:
                seen_asins_local.add(a)
                containers.append(c)

    logger.info(f"파싱된 아이템 컨테이너: {len(containers)}개")

    for idx, container in enumerate(containers):
        try:
            rank = page_offset + idx + 1

            # 순위 텍스트로 오버라이드
            rank_el = container.select_one("span.zg-bdg-text") or \
                      container.select_one("span[class*='rank']") or \
                      container.select_one(".zg-badge-text")
            if rank_el:
                rank_text = re.sub(r"[#,\s]", "", rank_el.get_text())
                if rank_text.isdigit():
                    rank = int(rank_text)

            # 제품명
            name_el = container.select_one("div._cDEzb_p13n-sc-css-line-clamp-3_g3dy1") or \
                      container.select_one("span.a-size-base.a-color-base") or \
                      container.select_one("div[class*='line-clamp']") or \
                      container.select_one("a.a-link-normal span") or \
                      container.select_one("div.p13n-sc-truncate")
            name = name_el.get_text(strip=True) if name_el else "N/A"

            # URL & ASIN
            link_el = container.select_one("a.a-link-normal[href*='/dp/']") or \
                      container.select_one("a[href*='/dp/']")
            href = link_el.get("href", "") if link_el else ""
            asin = _extract_asin(href)
            product_url = f"https://www.amazon.com{href}" if href.startswith("/") else href

            # ASIN이 없으면 data-asin 속성에서 추출
            if asin == "N/A":
                asin = container.get("data-asin", "N/A")

            # 가격
            price_el = container.select_one("span.p13n-sc-price") or \
                       container.select_one("span._cDEzb_p13n-sc-price_3mJ9Z") or \
                       container.select_one("span[class*='price']")
            price = _parse_price(price_el.get_text() if price_el else "")

            # 별점
            rating_el = container.select_one("span.a-icon-alt") or \
                        container.select_one("i.a-icon-star span")
            rating = _parse_rating(rating_el.get_text() if rating_el else "")

            # 리뷰 수
            review_el = container.select_one("span.a-size-small") or \
                        container.select_one("a[href*='#customerReviews'] span")
            review_count = _parse_review_count(review_el.get_text() if review_el else "")

            # 브랜드 (제품명에서 추출 시도)
            brand = _detect_brand_from_name(name)

            if name == "N/A" and asin == "N/A":
                continue

            items.append({
                "rank": rank,
                "name": name,
                "brand": brand,
                "price": price,
                "rating": rating,
                "review_count": review_count,
                "asin": asin,
                "url": product_url if product_url else f"https://www.amazon.com/dp/{asin}",
                "is_kbeauty": is_kbeauty_product(name, brand),
            })

        except Exception as e:
            logger.debug(f"아이템 파싱 오류 (idx={idx}): {e}")
            continue

    return items


def _detect_brand_from_name(name: str) -> str:
    """제품명에서 K-뷰티 브랜드 감지"""
    name_lower = name.lower()
    for brand in KBEAUTY_BRANDS:
        if brand in name_lower:
            # 원본 케이스로 반환
            idx = name_lower.find(brand)
            return name[idx: idx + len(brand)].title()
    return "Unknown"


def is_kbeauty_product(name: str, brand: str = "") -> bool:
    """K-뷰티 제품 여부 판단 (브랜드 리스트 + 키워드 병행)"""
    check_text = f"{name} {brand}".lower()
    if any(kb in check_text for kb in KBEAUTY_BRANDS):
        return True
    if any(kw in check_text for kw in KBEAUTY_KEYWORDS):
        return True
    return False


def _scrape_all_pages_selenium() -> list[dict]:
    """
    단일 Selenium 세션으로 모든 페이지를 방문해 TOP 100 수집.
    페이지마다 스크롤해서 lazy-load 아이템 포함 (페이지당 50개).
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
    except ImportError:
        logger.warning("selenium 미설치 → 스킵")
        return []

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(f"user-agent={_get_user_agent()}")
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    all_items: list[dict] = []
    seen_asins: set[str] = set()
    driver = None

    try:
        driver = webdriver.Chrome(options=opts)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        driver.set_window_size(1920, 1080)

        for page_idx, url in enumerate(BESTSELLER_URLS):
            logger.info(f"[Selenium] 페이지 {page_idx + 1} 방문: {url[:60]}...")
            driver.get(url)
            time.sleep(4)

            if _is_blocked(BeautifulSoup(driver.page_source, "lxml")):
                logger.warning(f"[Selenium] 페이지 {page_idx + 1}: 봇 차단 감지, 스킵")
                continue

            # 스크롤하여 lazy-load 아이템 트리거
            stall_steps = 0
            prev_count = 0
            for step in range(12):
                items_els = driver.find_elements(By.CSS_SELECTOR, "div.zg-grid-general-faceout")
                cur_count = len(items_els)
                if cur_count >= 50:
                    break
                if cur_count == prev_count:
                    stall_steps += 1
                    if stall_steps >= 4 and step >= 6:
                        break
                else:
                    stall_steps = 0
                prev_count = cur_count
                driver.execute_script(f"window.scrollTo(0, {(step + 1) * 700});")
                time.sleep(1.5)

            soup = BeautifulSoup(driver.page_source, "lxml")
            page_offset = page_idx * 50
            items = _parse_items(soup, page_offset)
            unique_count = len({i["asin"] for i in items if i["asin"] != "N/A"})
            logger.info(f"[Selenium] 페이지 {page_idx + 1}: {unique_count}개 고유 파싱")

            for item in items:
                if item["asin"] not in seen_asins and item["asin"] != "N/A":
                    seen_asins.add(item["asin"])
                    all_items.append(item)
                elif item["asin"] == "N/A":
                    all_items.append(item)

            if page_idx < len(BESTSELLER_URLS) - 1:
                delay = random.uniform(5.0, 8.0)
                logger.info(f"다음 페이지 전 대기: {delay:.1f}초")
                time.sleep(delay)

    except Exception as e:
        logger.warning(f"[Selenium] 전체 세션 오류: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return all_items


def scrape_bestsellers() -> list[dict]:
    """
    아마존 US 뷰티 베스트셀러 TOP 100 수집.
    Selenium(단일 세션 + 스크롤)으로 페이지당 50개 → 전체 100개 확보.
    Selenium 실패 시 requests로 fallback (페이지당 30개, 최대 60개).

    Returns:
        list[dict]: 순위 순으로 정렬된 제품 리스트
    """
    # ── 1차 시도: Selenium 단일 세션 (100개 목표) ─────────
    logger.info("Selenium 단일 세션으로 TOP 100 수집 시도")
    all_items = _scrape_all_pages_selenium()

    total_unique = len({i["asin"] for i in all_items if i["asin"] != "N/A"})
    logger.info(f"Selenium 수집 결과: {total_unique}개 고유")

    # ── 2차 fallback: Selenium 실패 또는 아이템 부족 시 requests 사용 ──
    if total_unique < 30:
        logger.warning("Selenium 결과 부족 → requests fallback")
        all_items = []
        seen_asins: set[str] = set()

        for page_idx, url in enumerate(BESTSELLER_URLS):
            logger.info(f"페이지 {page_idx + 1} 수집 중 (requests): {url[:60]}...")
            soup = _fetch_page(url)

            if soup is None:
                logger.warning(f"페이지 {page_idx + 1} 수집 실패 (스킵)")
                continue

            page_offset = page_idx * 50
            items = _parse_items(soup, page_offset)
            unique_count = len({i["asin"] for i in items if i["asin"] != "N/A"})
            logger.info(f"페이지 {page_idx + 1}: {unique_count}개 고유 파싱 (requests)")

            for item in items:
                if item["asin"] not in seen_asins and item["asin"] != "N/A":
                    seen_asins.add(item["asin"])
                    all_items.append(item)
                elif item["asin"] == "N/A":
                    all_items.append(item)

            if page_idx < len(BESTSELLER_URLS) - 1:
                delay = random.uniform(2.5, 4.0)
                logger.info(f"다음 페이지 전 대기: {delay:.1f}초")
                time.sleep(delay)

    # ── 순위 기준 정렬 ────────────────────────────────────
    all_items.sort(key=lambda x: x["rank"])
    logger.info(f"총 수집 완료: {len(all_items)}개 (K-뷰티: {sum(1 for i in all_items if i['is_kbeauty'])}개)")

    return all_items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    items = scrape_bestsellers()
    print(f"\n총 {len(items)}개 수집")
    kbeauty = [i for i in items if i["is_kbeauty"]]
    print(f"K-뷰티 제품: {len(kbeauty)}개")
    for item in kbeauty[:5]:
        print(f"  #{item['rank']} {item['name'][:50]} | {item['brand']} | {item['price']}")
