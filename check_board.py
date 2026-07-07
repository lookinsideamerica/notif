import os
import re
import json
import requests

# ===== 설정 =====
BOARD_URL = "https://lawschool.chungbuk.ac.kr/bbs/board.php?bo_table=060102"
STATE_FILE = "last_seen.json"

# 환경변수로 전달받음 (GitHub Actions Secrets에서 설정)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
if not NTFY_TOPIC:
    raise SystemExit("NTFY_TOPIC 환경변수가 설정되어 있지 않습니다.")


def fetch_posts():
    """게시판 목록 페이지에서 (wr_id, 제목) 목록을 추출한다."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    res = requests.get(BOARD_URL, headers=headers, timeout=20)
    res.raise_for_status()
    html = res.text

    # <a ... href="...board.php?bo_table=060102&wr_id=1234..." ...>제목</a>
    pattern = re.compile(
        r'href="[^"]*wr_id=(\d+)[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]+?)\s*(?:<|$)',
        re.IGNORECASE,
    )

    posts = []
    seen_ids = set()
    for m in pattern.finditer(html):
        wr_id = int(m.group(1))
        title = m.group(2).strip()
        if not title or wr_id in seen_ids:
            continue
        seen_ids.add(wr_id)
        posts.append((wr_id, title))

    # 번호 큰 순(최신 글 먼저) 정렬
    posts.sort(key=lambda x: x[0], reverse=True)
    return posts


def load_last_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("last_id", 0)
    return 0


def save_last_seen(last_id):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_id": last_id}, f)


def send_notification(title, wr_id):
    """
    ntfy의 JSON publish 방식 사용.
    HTTP 헤더에 한글을 직접 넣으면 깨지거나 전송 실패할 수 있어서,
    JSON 본문으로 보내면 한글(제목)이 안전하게 전달되고
    알림의 '제목' 자리에 게시글 제목이 바로 표시된다.
    """
    link = f"{BOARD_URL}&wr_id={wr_id}"
    payload = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": "충북대 법전원 석사 게시판에 새 글이 올라왔어요.",
        "click": link,
        "priority": 4,
    }
    try:
        res = requests.post("https://ntfy.sh", json=payload, timeout=15)
        res.raise_for_status()
        print(f"알림 전송: {title}")
    except Exception as e:
        print(f"알림 전송 실패: {e}")


def main():
    posts = fetch_posts()
    if not posts:
        print("게시글을 찾지 못했습니다. 페이지 구조가 바뀌었을 수 있습니다.")
        return

    last_seen = load_last_seen()
    new_posts = [p for p in posts if p[0] > last_seen]

    if last_seen == 0:
        # 최초 실행: 알림 없이 현재 최신 글 번호만 저장
        print("최초 실행입니다. 현재 최신 글 번호만 기록합니다 (알림 없음).")
    elif new_posts:
        # 오래된 글부터 순서대로 알림
        for wr_id, title in sorted(new_posts):
            send_notification(title, wr_id)
    else:
        print("새 글이 없습니다.")

    newest_id = max(p[0] for p in posts)
    save_last_seen(newest_id)


if __name__ == "__main__":
    main()
