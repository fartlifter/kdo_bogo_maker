import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime, time
from zoneinfo import ZoneInfo
import time as t
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# === 인증 정보 ===
client_id = "2cOdx0zvzhB_A8zQY1kK"
client_secret = "2tutLQTUPy"

def parse_pubdate(pubdate_str):
    try:
        return datetime.strptime(pubdate_str, "%a, %d %b %Y %H:%M:%S %z")
    except:
        return None

def extract_article_text(url):
    try:
        if "n.news.naver.com" not in url:
            return None
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if html.status_code == 200:
            soup = BeautifulSoup(html.text, "html.parser")
            content_div = soup.find("div", id="newsct_article")
            return content_div.get_text(separator="\n", strip=True) if content_div else None
    except:
        pass
    return None

def extract_media_name(url):
    try:
        domain = url.split("//")[-1].split("/")[0]
        parts = domain.split(".")
        media_key = (
            parts[2] if parts[0] == "www" and parts[1] == "news"
            else parts[1] if parts[0] in ("www", "news")
            else parts[0]
        )
        media_mapping = {
            "chosun": "조선", "joongang": "중앙", "donga": "동아", "hani": "한겨레",
            "khan": "경향", "hankookilbo": "한국", "segye": "세계", "seoul": "서울",
            "kmib": "국민", "munhwa": "문화", "kbs": "KBS", "sbs": "SBS",
            "imnews": "MBC", "jtbc": "JTBC", "ichannela": "채널A", "tvchosun": "TV조선",
            "mk": "매경", "sedaily": "서경", "hankyung": "한경", "news1": "뉴스1",
            "newsis": "뉴시스", "yna": "연합", "mt": "머투", "weekly": "주간조선"
        }
        return media_mapping.get(media_key.lower(), media_key.upper())
    except:
        return "[매체추출실패]"

def safe_api_request(url, headers, params, max_retries=3):
    for _ in range(max_retries):
        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                return res
            t.sleep(0.5)
        except:
            t.sleep(0.5)
    return res

def fetch_and_filter(item, start_dt, end_dt, selected_keywords, use_keyword_filter):
    title = BeautifulSoup(item["title"], "html.parser").get_text()
    if "[단독]" not in title:
        return None
    pub_dt = parse_pubdate(item.get("pubDate"))
    if not pub_dt or not (start_dt <= pub_dt <= end_dt):
        return None
    link = item.get("link")
    if not link or "n.news.naver.com" not in link:
        return None
    body = extract_article_text(link)
    if not body:
        return None
    matched_keywords = []
    if use_keyword_filter and selected_keywords:
        matched_keywords = [kw for kw in selected_keywords if kw in body]
        if not matched_keywords:
            return None
    highlighted_body = body
    for kw in matched_keywords:
        highlighted_body = highlighted_body.replace(kw, f"<mark>{kw}</mark>")
    media = extract_media_name(item.get("originallink", ""))
    return {
        "키워드": "[단독]",
        "매체": media,
        "제목": title,
        "날짜": pub_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "본문": body,
        "필터일치": ", ".join(matched_keywords),
        "링크": link,
        "하이라이트": highlighted_body,
        "pub_dt": pub_dt
    }

# === 키워드 목록 ===
all_keywords = [
    '기획재정부', '해양수산부', '농림축산식품부', '국토교통부', '과학기술정보통신부',
    '방송통신위원회', '통계청', '국세청', '관세청', '공정거래위원회', '한국소비자원', '농촌진흥청', 'KDI'
]

# === 기본 선택 키워드 ===
default_selection = [
    '기획재정부', '해양수산부', '농림축산식품부', '국토교통부',
    '통계청', '국세청', '관세청', '공정거래위원회', '농촌진흥청', 'KDI'
]

# === default 유효성 검증 ===
valid_default_selection = [kw for kw in default_selection if kw in all_keywords]
invalid_defaults = [kw for kw in default_selection if kw not in all_keywords]
if invalid_defaults:
    st.warning(f"⚠️ 기본 키워드 중 all_keywords에 없는 값이 있습니다: {invalid_defaults}")

# === UI ===
st.title("📰 [단독] 뉴스 수집기_강동용 ver")
st.markdown("✅ [단독] 기사를 수집하고 선택한 키워드가 본문에 포함된 기사만 필터링합니다.")

now = datetime.now(ZoneInfo("Asia/Seoul"))
today = now.date()

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("시작 날짜", value=today)
    start_time = st.time_input("시작 시각", value=time(0, 0))
    start_dt = datetime.combine(start_date, start_time).replace(tzinfo=ZoneInfo("Asia/Seoul"))

with col2:
    end_date = st.date_input("종료 날짜", value=today, key="end_date")
    end_time = st.time_input("종료 시각", value=time(now.hour, now.minute))
    end_dt = datetime.combine(end_date, end_time).replace(tzinfo=ZoneInfo("Asia/Seoul"))

selected_keywords = st.multiselect("📂 키워드 선택", all_keywords, default=valid_default_selection)
use_keyword_filter = st.checkbox("📎 키워드 포함 기사만 필터링", value=True)

if st.button("✅ [단독] 뉴스 수집 시작"):
    with st.spinner("뉴스 수집 중..."):
        status_text = st.empty()
        progress_bar = st.progress(0)
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret
        }
        seen_links = set()
        all_articles = []
        total = 0

        for start_index in range(1, 1001, 100):
            progress_bar.progress(min(start_index / 1000, 1.0))
            status_text.markdown(f"🟡 수집 중... **{total}건 수집됨**")
            params = {
                "query": "[단독]",
                "sort": "date",
                "display": 100,
                "start": start_index
            }
            res = safe_api_request("https://openapi.naver.com/v1/search/news.json", headers, params)
            if res.status_code != 200:
                st.warning(f"API 호출 실패: {res.status_code}")
                break
            items = res.json().get("items", [])
            if not items:
                break

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(fetch_and_filter, item, start_dt, end_dt, selected_keywords, use_keyword_filter)
                    for item in items
                ]
                for future in as_completed(futures):
                    result = future.result()
                    if result and result["링크"] not in seen_links:
                        seen_links.add(result["링크"])
                        all_articles.append(result)
                        st.markdown(f"**△{result['매체']}/{result['제목']}**")
                        st.caption(result["날짜"])
                        st.markdown(f"🔗 [원문 보기]({result['링크']})")
                        if result["필터일치"]:
                            st.write(f"**일치 키워드:** {result['필터일치']}")
                        st.markdown(f"- {result['하이라이트']}", unsafe_allow_html=True)
                        total += 1
                        status_text.markdown(f"🟡 수집 중... **{total}건 수집됨**")

        progress_bar.empty()
        status_text.markdown(f"✅ 수집 완료: 총 **{total}건**")
        st.success(f"✅ 수집 완료: 총 {total}건")

        if all_articles:
            text_block = ""
            for row in all_articles:
                clean_title = re.sub(r"\[단독\]|\(단독\)|【단독】|ⓧ단독|^단독\s*[:-]?", "", row['제목']).strip()
                text_block += f"@{row['매체']}/{clean_title}\n{row['날짜']}\n- {row['본문']}\n\n"
            st.text_area("📋 복사용 전체 기사", text_block.strip(), height=300, key="copy_area")
            st.code(text_block.strip(), language="markdown")
            st.caption("위 내용을 복사해서 사용하세요.")
