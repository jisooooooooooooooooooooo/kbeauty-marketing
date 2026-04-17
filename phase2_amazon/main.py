"""
아마존 K-뷰티 베스트셀러 트래커 메인 orchestration.

실행 순서:
1. 아마존 TOP 100 스크래핑
2. K-뷰티 필터링
3. 전날 대비 변동 감지
4. HTML 리포트 생성
5. 변동 시 이메일 알림
6. Google Sheets 기록

사용법:
    python phase2_amazon/main.py            # 정상 실행
    python phase2_amazon/main.py --dry-run  # 이메일 발송 없이 HTML만 저장
"""

import sys
import os
import logging
import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()


def get_et_date_label() -> tuple[str, str]:
    """ET(미국 동부) 기준 날짜 반환. (날짜문자열, 전체 라벨) 튜플."""
    et_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y년 %m월 %d일")
    label = f"미국 현지 기준 어제 ({et_date})"
    return et_date, label

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("amazon_main")

# HTML 스타일
HTML_STYLE = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', Arial, sans-serif;
         background: #f0f4f8; margin: 0; padding: 0; color: #1a202c; }
  .container { max-width: 800px; margin: 0 auto; background: #fff; }
  .header { background: linear-gradient(135deg, #f97316, #ea580c);
            padding: 28px 24px; text-align: center; }
  .header h1 { color: #fff; margin: 0; font-size: 20px; font-weight: 700; }
  .header p { color: rgba(255,255,255,0.85); margin: 6px 0 0; font-size: 13px; }
  .summary-bar { display: flex; gap: 0; border-bottom: 2px solid #fed7aa; }
  .stat-box { flex: 1; padding: 16px 12px; text-align: center; border-right: 1px solid #fed7aa; }
  .stat-box:last-child { border-right: none; }
  .stat-num { font-size: 28px; font-weight: 800; color: #ea580c; }
  .stat-label { font-size: 11px; color: #6b7280; margin-top: 2px; }
  .section { padding: 20px 24px; border-bottom: 1px solid #e5e7eb; }
  .section-title { font-size: 15px; font-weight: 700; padding: 7px 12px;
                   border-radius: 6px; color: #fff; margin: 0 0 14px; display: inline-block; }
  .t1 { background: #ea580c; }
  .t2 { background: #16a34a; }
  .t3 { background: #dc2626; }
  .t4 { background: #7c3aed; }
  .t5 { background: #0891b2; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { background: #fff7ed; color: #9a3412; font-weight: 600;
       padding: 8px 10px; text-align: left; border-bottom: 2px solid #fed7aa; }
  td { padding: 7px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
  tr:hover td { background: #fffbf5; }
  .rank-badge { display: inline-block; background: #ea580c; color: #fff;
                border-radius: 4px; padding: 1px 6px; font-weight: 700; font-size: 12px; }
  .rank-badge.top10 { background: #dc2626; }
  .rank-badge.top50 { background: #d97706; }
  .change-up { color: #16a34a; font-weight: 600; }
  .change-down { color: #dc2626; font-weight: 600; }
  .change-new { color: #7c3aed; font-weight: 600; }
  .brand-tag { display: inline-block; background: #fef3c7; border: 1px solid #fcd34d;
               color: #92400e; padding: 1px 7px; border-radius: 10px; font-size: 11px; }
  .competitor-tag { background: #fee2e2; border-color: #fca5a5; color: #991b1b; }
  .product-name a { color: #1d4ed8; text-decoration: none; font-size: 12px; }
  .product-name a:hover { text-decoration: underline; }
  .share-bar { background: #f3f4f6; border-radius: 20px; height: 12px; margin: 6px 0; overflow: hidden; }
  .share-fill { background: linear-gradient(90deg, #ea580c, #f97316); height: 100%; border-radius: 20px; }
  .no-data { color: #9ca3af; font-style: italic; padding: 12px 0; }
  .footer { padding: 16px 24px; text-align: center; color: #9ca3af;
            font-size: 11px; background: #f9fafb; }
  @media (max-width: 600px) {
    .summary-bar { flex-wrap: wrap; }
    .stat-box { min-width: 45%; }
    table { font-size: 11px; }
  }
</style>
"""


def _rank_badge(rank: int) -> str:
    cls = "top10" if rank <= 10 else ("top50" if rank <= 50 else "")
    return f'<span class="rank-badge {cls}">#{rank}</span>'


def _brand_tag(brand: str, is_competitor: bool = False) -> str:
    cls = "competitor-tag" if is_competitor else ""
    return f'<span class="brand-tag {cls}">{brand}</span>'


def _is_competitor(brand: str) -> bool:
    from phase2_amazon.tracker import COMPETITOR_BRANDS
    return any(c in brand.lower() for c in COMPETITOR_BRANDS)


def generate_html_report(
    today_items: list[dict],
    changes: dict,
    summary: dict,
) -> str:
    """HTML 리포트 생성"""
    today, today_label = get_et_date_label()
    kbeauty = summary["top_kbeauty"]
    all_kbeauty = [i for i in today_items if i.get("is_kbeauty")]
    share = summary["kbeauty_share"]

    # ── 요약 바 ──────────────────────────────────────────
    summary_bar = f"""
<div class="summary-bar">
  <div class="stat-box">
    <div class="stat-num">{summary['kbeauty_count']}</div>
    <div class="stat-label">K-뷰티 진입 수</div>
  </div>
  <div class="stat-box">
    <div class="stat-num">{summary['total_top100']}</div>
    <div class="stat-label">전체 TOP 수집</div>
  </div>
  <div class="stat-box">
    <div class="stat-num">{share}%</div>
    <div class="stat-label">K-뷰티 점유율</div>
  </div>
  <div class="stat-box">
    <div class="stat-num">{len(changes.get('new_entries', []))}</div>
    <div class="stat-label">신규 진입</div>
  </div>
</div>
"""

    # ── 섹션 1: 오늘의 K-뷰티 순위표 ────────────────────
    rows_html = ""
    for item in sorted(all_kbeauty, key=lambda x: x["rank"]):
        competitor = _is_competitor(item.get("brand", ""))
        name_cell = f'<div class="product-name"><a href="{item["url"]}" target="_blank">{item["name"][:60]}</a></div>'
        rows_html += f"""
<tr>
  <td>{_rank_badge(item['rank'])}</td>
  <td>{name_cell}</td>
  <td>{_brand_tag(item.get('brand','?'), competitor)}</td>
  <td>{item['price']}</td>
  <td>⭐ {item['rating']}</td>
  <td>{int(item['review_count']):,}건</td>
</tr>"""

    section1 = f"""
<div class="section">
  <div class="section-title t1">📦 오늘의 K-뷰티 베스트셀러 순위</div>
  <div class="share-bar"><div class="share-fill" style="width:{min(share*3,100)}%"></div></div>
  <p style="font-size:12px;color:#6b7280;margin:4px 0 12px">
    TOP {summary['total_top100']} 중 K-뷰티 {summary['kbeauty_count']}개 ({share}%) 진입
  </p>
  {'<table><thead><tr><th>순위</th><th>제품명</th><th>브랜드</th><th>가격</th><th>별점</th><th>리뷰</th></tr></thead><tbody>' + rows_html + '</tbody></table>' if all_kbeauty else '<p class="no-data">수집된 K-뷰티 제품이 없습니다.</p>'}
</div>"""

    # ── 섹션 2: 신규 진입 ────────────────────────────────
    new_html = ""
    for item in changes.get("new_entries", []):
        competitor = _is_competitor(item.get("brand", ""))
        new_html += f"""
<tr>
  <td>{_rank_badge(item['rank'])}</td>
  <td><a href="{item['url']}" target="_blank">{item['name'][:55]}</a></td>
  <td>{_brand_tag(item.get('brand','?'), competitor)}</td>
  <td>{item['price']}</td>
  <td><span class="change-new">🆕 신규</span></td>
</tr>"""

    first_run_note = "<p style='font-size:12px;color:#9ca3af;margin-bottom:10px'>※ 첫 실행 — 다음 실행부터 전일 대비 변동이 표시됩니다.</p>" if changes.get("is_first_run") else ""
    section2 = f"""
<div class="section">
  <div class="section-title t2">🆕 신규 진입 K-뷰티 제품</div>
  {first_run_note}
  {'<table><thead><tr><th>순위</th><th>제품명</th><th>브랜드</th><th>가격</th><th>변동</th></tr></thead><tbody>' + new_html + '</tbody></table>' if changes.get('new_entries') else '<p class="no-data">신규 진입 제품 없음</p>'}
</div>"""

    # ── 섹션 3: 순위 변동 TOP 5 ─────────────────────────
    change_html = ""
    for item in changes.get("rank_up", []):
        change_html += f"""
<tr>
  <td>{_rank_badge(item['rank'])}</td>
  <td><a href="{item['url']}" target="_blank">{item['name'][:55]}</a></td>
  <td>{_brand_tag(item.get('brand','?'), _is_competitor(item.get('brand','')))}</td>
  <td>#{item.get('yesterday_rank','?')}</td>
  <td><span class="change-up">▲ {item.get('rank_change',0)}위</span></td>
</tr>"""
    for item in changes.get("rank_down", []):
        change_html += f"""
<tr>
  <td>{_rank_badge(item['rank'])}</td>
  <td><a href="{item['url']}" target="_blank">{item['name'][:55]}</a></td>
  <td>{_brand_tag(item.get('brand','?'), _is_competitor(item.get('brand','')))}</td>
  <td>#{item.get('yesterday_rank','?')}</td>
  <td><span class="change-down">▼ {abs(item.get('rank_change',0))}위</span></td>
</tr>"""

    section3 = f"""
<div class="section">
  <div class="section-title t3">📊 순위 변동 TOP 5 (±{10}위 이상)</div>
  {'<table><thead><tr><th>현재</th><th>제품명</th><th>브랜드</th><th>전일</th><th>변동</th></tr></thead><tbody>' + change_html + '</tbody></table>' if change_html else '<p class="no-data">10위 이상 변동 없음</p>'}
</div>"""

    # ── 섹션 4: 경쟁 브랜드 동향 ────────────────────────
    comp_html = ""
    for item in changes.get("competitor_new", []):
        comp_html += f"""
<tr>
  <td>{_rank_badge(item['rank'])}</td>
  <td><a href="{item['url']}" target="_blank">{item['name'][:55]}</a></td>
  <td>{_brand_tag(item.get('brand','?'), True)}</td>
  <td>{item['price']}</td>
  <td>⭐ {item['rating']} ({int(item['review_count']):,}건)</td>
</tr>"""

    section4 = f"""
<div class="section">
  <div class="section-title t4">🎯 경쟁 브랜드 신규 진입</div>
  {'<table><thead><tr><th>순위</th><th>제품명</th><th>브랜드</th><th>가격</th><th>평점</th></tr></thead><tbody>' + comp_html + '</tbody></table>' if changes.get('competitor_new') else '<p class="no-data">경쟁 브랜드 신규 진입 없음</p>'}
</div>"""

    # ── 섹션 5: 브랜드 점유율 ────────────────────────────
    brand_html = ""
    for brand, count in summary["brand_breakdown"][:8]:
        pct = round(count / summary["kbeauty_count"] * 100) if summary["kbeauty_count"] > 0 else 0
        comp_cls = "competitor-tag" if _is_competitor(brand) else ""
        brand_html += f"""
<tr>
  <td><span class="brand-tag {comp_cls}">{brand}</span></td>
  <td>{count}개</td>
  <td>
    <div class="share-bar" style="width:200px">
      <div class="share-fill" style="width:{pct*2}px;max-width:100%"></div>
    </div>
  </td>
  <td style="color:#6b7280;font-size:12px">{pct}%</td>
</tr>"""

    section5 = f"""
<div class="section">
  <div class="section-title t5">🏷️ 브랜드별 점유율</div>
  {'<table><thead><tr><th>브랜드</th><th>제품 수</th><th>비율</th><th></th></tr></thead><tbody>' + brand_html + '</tbody></table>' if brand_html else '<p class="no-data">데이터 없음</p>'}
</div>"""

    # ── 전체 조립 ─────────────────────────────────────────
    scraped_note = f"수집 {summary['total_top100']}개 | K-뷰티 {summary['kbeauty_count']}개 ({share}%)"
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>아마존 K-뷰티 베스트셀러 트래커 - {today}</title>
{HTML_STYLE}
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🛒 아마존 K-뷰티 베스트셀러 트래커</h1>
    <p>{today_label} 아마존 베스트셀러 순위 · {scraped_note}</p>
  </div>
  {summary_bar}
  {section1}
  {section2}
  {section3}
  {section4}
  {section5}
  <div class="footer">K-뷰티 마케팅팀 · 자동 생성 리포트 · 데이터: Amazon Best Sellers</div>
</div>
</body>
</html>"""
    return html


def generate_all_products_html(items: list[dict]) -> str:
    """전체 수집 제품 목록 HTML 생성 (K-뷰티 하이라이트)"""
    today, today_label = get_et_date_label()
    kbeauty_count = sum(1 for i in items if i.get("is_kbeauty"))

    rows_html = ""
    for item in items:
        is_k = item.get("is_kbeauty", False)
        row_style = ' style="background:#fff7ed;"' if is_k else ""
        badge = '<span style="display:inline-block;background:#ea580c;color:#fff;border-radius:3px;padding:1px 5px;font-size:10px;font-weight:700;margin-left:4px;">K</span>' if is_k else ""
        name_cell = f'<a href="{item["url"]}" target="_blank" style="color:#1d4ed8;text-decoration:none;">{item["name"][:70]}</a>{badge}'
        rows_html += f"""<tr{row_style}>
  <td class="col-rank">{item['rank']}</td>
  <td>{name_cell}</td>
  <td class="col-price">{item['price']}</td>
  <td class="col-rating">⭐ {item['rating']}</td>
  <td class="col-reviews">{item['review_count']}</td>
</tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>아마존 전체 제품 목록 - {today}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, Arial, sans-serif;
         background:#f0f4f8; margin:0; padding:12px; color:#1a202c; }}
  .wrap {{ max-width:960px; margin:0 auto; background:#fff; border-radius:8px;
           box-shadow:0 1px 4px rgba(0,0,0,.1); overflow:hidden; }}
  .hdr {{ background:linear-gradient(135deg,#1d4ed8,#1e40af); padding:20px;
          color:#fff; }}
  .hdr h1 {{ margin:0; font-size:17px; }}
  .hdr p {{ margin:6px 0 0; font-size:12px; opacity:.85; }}
  .table-wrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; min-width:360px; }}
  th {{ background:#eff6ff; color:#1e40af; font-weight:600; padding:9px 10px;
        text-align:left; border-bottom:2px solid #bfdbfe; position:sticky; top:0; white-space:nowrap; }}
  td {{ padding:8px 10px; border-bottom:1px solid #f3f4f6; vertical-align:middle; }}
  tr:hover td {{ background:#f8faff; }}
  .col-rank {{ text-align:center; font-weight:700; color:#6b7280; width:40px; }}
  .col-price {{ white-space:nowrap; }}
  .col-rating {{ white-space:nowrap; font-size:14px; }}
  .col-reviews {{ white-space:nowrap; color:#6b7280; }}
  .legend {{ padding:12px 16px; font-size:12px; color:#6b7280; border-top:1px solid #e5e7eb; }}
  @media (max-width:600px) {{
    body {{ padding:0; }}
    .wrap {{ border-radius:0; box-shadow:none; }}
    .hdr {{ padding:14px; }}
    .hdr h1 {{ font-size:15px; }}
    td, th {{ padding:6px 8px; font-size:12px; }}
    .col-rating {{ font-size:13px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>🛒 아마존 뷰티 베스트셀러 전체 목록</h1>
    <p>{today_label} 아마존 베스트셀러 순위 · 전체 {len(items)}개 수집 · K-뷰티 {kbeauty_count}개
       <span style="background:#ea580c;border-radius:3px;padding:1px 5px;font-size:10px;font-weight:700;margin-left:6px;">K</span> 표시
    </p>
  </div>
  <div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>순위</th>
        <th>제품명</th>
        <th>가격</th>
        <th>별점</th>
        <th>리뷰 수</th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
  </div>
  <div class="legend">
    ※ 주황 행 = K-뷰티 감지 제품 &nbsp;|&nbsp;
    <span style="background:#ea580c;color:#fff;border-radius:3px;padding:1px 5px;font-size:10px;font-weight:700;">K</span> 뱃지 = K-뷰티 &nbsp;|&nbsp;
    제품명 클릭 시 아마존 링크
  </div>
</div>
</body>
</html>"""


def build_email_html(changes: dict, summary: dict, today_items: list[dict]) -> str:
    """이메일용 HTML 생성 (K-뷰티 TOP 5 + 리포트 링크 포함)"""
    today, today_label = get_et_date_label()

    PREVIEW_URL = "https://jisooooooooooooooooooooo.github.io/kbeauty-marketing/amazon_preview.html"
    ALL_PRODUCTS_URL = "https://jisooooooooooooooooooooo.github.io/kbeauty-marketing/all_products.html"

    # ── K-뷰티 TOP 5 ──────────────────────────────────────
    kbeauty_sorted = sorted(
        [i for i in today_items if i.get("is_kbeauty")],
        key=lambda x: x["rank"]
    )[:5]

    top5_rows = ""
    for i, item in enumerate(kbeauty_sorted, 1):
        top5_rows += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f3f4f6;text-align:center;"
            f"font-weight:700;color:#ea580c;'>#{item['rank']}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f3f4f6;'>"
            f"<a href='{item['url']}' style='color:#1d4ed8;text-decoration:none;'>{item['name'][:55]}</a>"
            f"</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f3f4f6;color:#92400e;"
            f"font-size:12px;white-space:nowrap;'>{item.get('brand','?')}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f3f4f6;white-space:nowrap;'>"
            f"{item['price']}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #f3f4f6;white-space:nowrap;'>"
            f"⭐ {item['rating']}</td>"
            f"</tr>"
        )

    top5_table = f"""
<table style='width:100%;border-collapse:collapse;font-size:13px;margin-top:8px;'>
  <thead>
    <tr style='background:#fff7ed;'>
      <th style='padding:7px 10px;border-bottom:2px solid #fed7aa;color:#9a3412;text-align:center;'>순위</th>
      <th style='padding:7px 10px;border-bottom:2px solid #fed7aa;color:#9a3412;text-align:left;'>제품명</th>
      <th style='padding:7px 10px;border-bottom:2px solid #fed7aa;color:#9a3412;'>브랜드</th>
      <th style='padding:7px 10px;border-bottom:2px solid #fed7aa;color:#9a3412;'>가격</th>
      <th style='padding:7px 10px;border-bottom:2px solid #fed7aa;color:#9a3412;'>별점</th>
    </tr>
  </thead>
  <tbody>
    {top5_rows if top5_rows else "<tr><td colspan='5' style='padding:10px;color:#9ca3af;'>K-뷰티 제품 없음</td></tr>"}
  </tbody>
</table>"""

    # ── 신규 진입 목록 ────────────────────────────────────
    new_list = ""
    for item in changes.get("new_entries", [])[:5]:
        new_list += f"<li style='margin:3px 0;'>#{item['rank']} {item['name'][:50]} <span style='color:#6b7280;'>({item.get('brand','?')})</span></li>"

    # ── 순위 변동 ─────────────────────────────────────────
    change_list = ""
    for item in changes.get("rank_up", [])[:3]:
        change_list += f"<li style='margin:3px 0;'>#{item['rank']} {item['name'][:45]} <span style='color:#16a34a;font-weight:600;'>▲{item.get('rank_change',0)}위</span></li>"
    for item in changes.get("rank_down", [])[:3]:
        change_list += f"<li style='margin:3px 0;'>#{item['rank']} {item['name'][:45]} <span style='color:#dc2626;font-weight:600;'>▼{abs(item.get('rank_change',0))}위</span></li>"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',Arial,sans-serif;
             background:#f0f4f8;margin:0;padding:20px;color:#1a202c;">
<div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;
            box-shadow:0 1px 4px rgba(0,0,0,.1);overflow:hidden;">

  <!-- 헤더 -->
  <div style="background:linear-gradient(135deg,#f97316,#ea580c);padding:24px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:20px;font-weight:700;">
      🛒 아마존 K-뷰티 베스트셀러 트래커
    </h1>
    <p style="color:rgba(255,255,255,.85);margin:6px 0 0;font-size:13px;">
      {today_label} 아마존 베스트셀러 순위 · TOP {summary['total_top100']} 수집 · K-뷰티 {summary['kbeauty_count']}개 ({summary['kbeauty_share']}%)
    </p>
  </div>

  <!-- 요약 수치 -->
  <div style="display:flex;border-bottom:2px solid #fed7aa;">
    <div style="flex:1;padding:14px 10px;text-align:center;border-right:1px solid #fed7aa;">
      <div style="font-size:26px;font-weight:800;color:#ea580c;">{summary['kbeauty_count']}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:2px;">K-뷰티 진입</div>
    </div>
    <div style="flex:1;padding:14px 10px;text-align:center;border-right:1px solid #fed7aa;">
      <div style="font-size:26px;font-weight:800;color:#ea580c;">{summary['total_top100']}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:2px;">전체 수집</div>
    </div>
    <div style="flex:1;padding:14px 10px;text-align:center;border-right:1px solid #fed7aa;">
      <div style="font-size:26px;font-weight:800;color:#ea580c;">{summary['kbeauty_share']}%</div>
      <div style="font-size:11px;color:#6b7280;margin-top:2px;">K-뷰티 점유율</div>
    </div>
    <div style="flex:1;padding:14px 10px;text-align:center;">
      <div style="font-size:26px;font-weight:800;color:#ea580c;">{len(changes.get('new_entries', []))}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:2px;">신규 진입</div>
    </div>
  </div>

  <!-- K-뷰티 TOP 5 -->
  <div style="padding:20px 24px;border-bottom:1px solid #e5e7eb;">
    <div style="display:inline-block;background:#ea580c;color:#fff;font-size:14px;
                font-weight:700;padding:5px 12px;border-radius:6px;margin-bottom:12px;">
      📦 오늘의 K-뷰티 TOP 5
    </div>
    {top5_table}
  </div>

  <!-- 신규 진입 -->
  <div style="padding:20px 24px;border-bottom:1px solid #e5e7eb;">
    <div style="display:inline-block;background:#16a34a;color:#fff;font-size:14px;
                font-weight:700;padding:5px 12px;border-radius:6px;margin-bottom:10px;">
      🆕 신규 진입 K-뷰티
    </div>
    {'<ul style="margin:0;padding-left:18px;">' + new_list + '</ul>' if new_list else '<p style="color:#9ca3af;font-style:italic;margin:0;">신규 진입 없음</p>'}
  </div>

  <!-- 순위 변동 -->
  <div style="padding:20px 24px;border-bottom:1px solid #e5e7eb;">
    <div style="display:inline-block;background:#dc2626;color:#fff;font-size:14px;
                font-weight:700;padding:5px 12px;border-radius:6px;margin-bottom:10px;">
      📊 순위 변동
    </div>
    {'<ul style="margin:0;padding-left:18px;">' + change_list + '</ul>' if change_list else '<p style="color:#9ca3af;font-style:italic;margin:0;">10위 이상 변동 없음</p>'}
  </div>

  <!-- 리포트 링크 -->
  <div style="padding:20px 24px;border-bottom:1px solid #e5e7eb;background:#fffbf5;">
    <p style="margin:0 0 10px;font-weight:700;font-size:14px;">📄 상세 리포트 열기</p>
    <p style="margin:4px 0;">
      <a href="{PREVIEW_URL}"
         style="display:inline-block;background:#ea580c;color:#fff;padding:8px 16px;
                border-radius:5px;text-decoration:none;font-size:13px;font-weight:600;">
        🛒 오늘의 K-뷰티 베스트셀러 리포트
      </a>
    </p>
    <p style="margin:8px 0 0;">
      <a href="{ALL_PRODUCTS_URL}"
         style="display:inline-block;background:#1d4ed8;color:#fff;padding:8px 16px;
                border-radius:5px;text-decoration:none;font-size:13px;font-weight:600;">
        📋 전체 TOP 100 목록
      </a>
    </p>
  </div>

  <!-- 푸터 -->
  <div style="padding:14px 24px;text-align:center;color:#9ca3af;font-size:11px;background:#f9fafb;">
    K-뷰티 마케팅팀 · 자동 생성 리포트 · 데이터: Amazon Best Sellers
  </div>
</div>
</body>
</html>"""
    return html


def run(dry_run: bool = False):
    start_time = datetime.now()
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    logger.info("아마존 K-뷰티 베스트셀러 트래커 시작")
    logger.info(f"모드: {'DRY-RUN' if dry_run else '실제 실행'}")
    results = {}

    # ── Step 1: 스크래핑 ─────────────────────────────────
    logger.info("=" * 50)
    logger.info("Step 1: 아마존 베스트셀러 스크래핑")
    try:
        from phase2_amazon.amazon_scraper import scrape_bestsellers
        items = scrape_bestsellers()
        kbeauty_items = [i for i in items if i.get("is_kbeauty")]
        logger.info(f"Step 1 완료: 전체 {len(items)}개, K-뷰티 {len(kbeauty_items)}개")
        results["scrape"] = {"success": True, "total": len(items), "kbeauty": len(kbeauty_items)}
    except Exception as e:
        logger.error(f"Step 1 실패: {e}")
        results["scrape"] = {"success": False, "error": str(e)}
        _print_summary(results, start_time)
        sys.exit(1)

    # ── Step 2: 변동 감지 + 히스토리 저장 ────────────────
    logger.info("=" * 50)
    logger.info("Step 2: 변동 감지 및 히스토리 저장")
    try:
        from phase2_amazon.tracker import detect_changes, save_today_data, get_kbeauty_summary, log_to_sheets
        changes = detect_changes(items)
        save_today_data(items)
        summary = get_kbeauty_summary(items)
        logger.info(f"Step 2 완료: 신규 {len(changes['new_entries'])}개, 급상승 {len(changes['rank_up'])}개, 급하락 {len(changes['rank_down'])}개")
        results["track"] = {"success": True, "has_changes": changes["has_changes"]}
    except Exception as e:
        logger.error(f"Step 2 실패: {e}")
        results["track"] = {"success": False, "error": str(e)}
        changes = {"new_entries": [], "rank_up": [], "rank_down": [], "competitor_new": [], "has_changes": False, "is_first_run": True}
        summary = {"total_top100": len(items), "kbeauty_count": len(kbeauty_items), "kbeauty_share": 0, "top_kbeauty": kbeauty_items[:10], "brand_breakdown": []}

    # ── Step 3: HTML 리포트 생성 ─────────────────────────
    logger.info("=" * 50)
    logger.info("Step 3: HTML 리포트 생성")
    try:
        html = generate_html_report(items, changes, summary)
        output_path = output_dir / "amazon_preview.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"Step 3 완료: {output_path} ({len(html):,} 바이트)")

        all_html = generate_all_products_html(items)
        all_path = output_dir / "all_products.html"
        with open(all_path, "w", encoding="utf-8") as f:
            f.write(all_html)
        logger.info(f"Step 3 전체목록: {all_path} ({len(all_html):,} 바이트)")

        results["html"] = {"success": True, "path": str(output_path), "all_path": str(all_path)}
    except Exception as e:
        logger.error(f"Step 3 실패: {e}")
        results["html"] = {"success": False, "error": str(e)}

    # ── Step 4: 이메일 발송 ──────────────────────────────
    logger.info("=" * 50)
    if dry_run:
        logger.info("Step 4: [DRY-RUN] 이메일 발송 건너뜀")
        results["email"] = {"success": True, "skipped": True}
    else:
        logger.info("Step 4: 이메일 발송 (매일 발송)")
        try:
            from phase1_newsletter.mailer import send_newsletter
            _, today_label = get_et_date_label()
            email_html = build_email_html(changes, summary, items)
            sent = send_newsletter(
                email_html,
                subject=f"[K-뷰티 알림] {today_label} 아마존 베스트셀러 순위",
            )
            results["email"] = {"success": sent}
            logger.info(f"Step 4 완료: {'발송 성공' if sent else '발송 실패'}")
        except Exception as e:
            logger.error(f"Step 4 실패: {e}")
            results["email"] = {"success": False, "error": str(e)}

    # ── Step 5: Google Sheets ────────────────────────────
    logger.info("=" * 50)
    logger.info("Step 5: Google Sheets 기록")
    try:
        from phase2_amazon.tracker import log_to_sheets
        ok = log_to_sheets(items, changes)
        results["sheets"] = {"success": ok}
        logger.info(f"Step 5 완료: {'성공' if ok else '건너뜀'}")
    except Exception as e:
        logger.warning(f"Step 5 실패 (무시): {e}")
        results["sheets"] = {"success": False}

    _print_summary(results, start_time, dry_run)


def _print_summary(results: dict, start_time: datetime, dry_run: bool = False):
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 50)
    logger.info("실행 결과 요약")
    logger.info("=" * 50)

    steps = [
        ("Step 1 스크래핑", results.get("scrape", {})),
        ("Step 2 변동 감지", results.get("track", {})),
        ("Step 3 HTML 생성", results.get("html", {})),
        ("Step 4 이메일", results.get("email", {})),
        ("Step 5 Sheets", results.get("sheets", {})),
    ]
    for name, r in steps:
        if r.get("skipped"):
            status = "⏭  건너뜀"
        elif r.get("success"):
            status = "✅ 성공"
        else:
            status = "❌ 실패"
        logger.info(f"{name}: {status}")

    if results.get("html", {}).get("path"):
        logger.info(f"\n📄 리포트: {results['html']['path']}")
    if results.get("html", {}).get("all_path"):
        logger.info(f"📋 전체목록: {results['html']['all_path']}")
    scrape = results.get("scrape", {})
    if scrape.get("success"):
        logger.info(f"📦 수집: 전체 {scrape.get('total',0)}개 | K-뷰티 {scrape.get('kbeauty',0)}개")
    logger.info(f"\n총 소요시간: {elapsed:.1f}초")
    logger.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="아마존 K-뷰티 베스트셀러 트래커")
    parser.add_argument("--dry-run", action="store_true", help="이메일 발송 없이 HTML만 저장")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
