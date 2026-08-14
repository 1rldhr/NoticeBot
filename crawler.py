import requests
import json
import os
from bs4 import BeautifulSoup
import config  # 방금 만든 config.py 불러오기
import os

# 로컬 컴퓨터에서는 secrets.py 파일에서, 깃허브에서 자동 실행될 때는
# 깃허브의 안전한 저장소(Secrets)에서 값을 가져옵니다.
try:
    import my_secrets
    TELEGRAM_TOKEN = my_secrets.TELEGRAM_TOKEN
    TELEGRAM_CHAT_ID = my_secrets.TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"
}

BOARDS = {
    "전체공지": "https://scatch.ssu.ac.kr/%EA%B3%B5%EC%A7%80%EC%82%AC%ED%95%AD/",
    "산공학과공지": "https://iise.ssu.ac.kr/cummunity/notice/",
}

SEEN_FILE = "seen_notices.json"  # 이미 본 공지 링크를 저장해두는 파일


def load_seen():
    """이전에 이미 봤던 공지 링크 목록 불러오기"""
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen_set):
    """본 공지 링크 목록 저장하기"""
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_set), f, ensure_ascii=False)


def get_notices(board_name, url):
    response = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    links = soup.select("a[href*='slug=']")

    notices = []
    for link in links:
        title = link.get_text(strip=True)
        href = link.get("href")
        if title and href:
            notices.append({"board": board_name, "title": title, "url": href})
    return notices


def calculate_importance(notice):
    """제목을 보고 나한테 얼마나 중요한 공지인지 점수 매기기"""
    score = 0
    title = notice["title"]

    # 관심 카테고리에 해당하면 +2점
    for category in config.INTERESTED_CATEGORIES:
        if category in title:
            score += 2
            break  # 카테고리는 중복으로 안 세고 한 번만

    # 관심 키워드가 포함되면 +3점씩
    for keyword in config.KEYWORDS:
        if keyword in title:
            score += 3

    return score

def send_telegram(notice):
    """공지 하나를 텔레그램 메시지로 보내는 함수"""
    text = f"📢 [{notice['board']}] {notice['title']}\n{notice['url']}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    requests.post(url, data=payload)

ICS_FILE = "calendar.ics"


def add_to_calendar(notice):
    """공지 하나를 캘린더 이벤트로 calendar.ics 파일에 추가하는 함수"""
    today = datetime.now().strftime("%Y%m%d")

    # 제목/링크에 있는 특수문자(콤마, 세미콜론)는 이스케이프 처리
    title = notice["title"].replace(",", "\\,").replace(";", "\\;")

    event = f"""BEGIN:VEVENT
UID:{notice['url']}
DTSTAMP:{today}T000000Z
DTSTART;VALUE=DATE:{today}
DTEND;VALUE=DATE:{today}
SUMMARY:[{notice['board']}] {title}
DESCRIPTION:{notice['url']}
END:VEVENT
"""

    # 파일이 없으면 새로 만들고, 있으면 END:VCALENDAR 앞에 끼워넣기
    if not os.path.exists(ICS_FILE):
        with open(ICS_FILE, "w", encoding="utf-8") as f:
            f.write("BEGIN:VCALENDAR\nVERSION:2.0\n")
            f.write(event)
            f.write("END:VCALENDAR\n")
    else:
        with open(ICS_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("END:VCALENDAR", event + "END:VCALENDAR")
        with open(ICS_FILE, "w", encoding="utf-8") as f:
            f.write(content)

if __name__ == "__main__":
    seen = load_seen()
    all_notices = []

    for name, url in BOARDS.items():
        notices = get_notices(name, url)
        all_notices.extend(notices)

    # 처음 본 공지만 골라내기
    new_notices = [n for n in all_notices if n["url"] not in seen]

    # 각 공지에 중요도 점수 매기기
    for n in new_notices:
        n["score"] = calculate_importance(n)

    # 중요도 높은 순으로 정렬
    new_notices.sort(key=lambda n: n["score"], reverse=True)

    print(f"새 공지 {len(new_notices)}개 발견\n")
    for n in new_notices:
        star = "⭐" * n["score"] if n["score"] > 0 else ""
        print(f"[{n['board']}] {n['title']}  {star}")
        print(f"  -> {n['url']}\n")

        if n["score"] > 0:  # 중요도 있는 것만 텔레그램 + 캘린더에 등록
            send_telegram(n)
            add_to_calendar(n)

    # 이번에 본 공지들을 저장 (다음 실행 때는 다시 안 뜨게)
    seen.update(n["url"] for n in all_notices)
    save_seen(seen)