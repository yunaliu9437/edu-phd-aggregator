import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
import feedparser
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "jobs.json")

HEADERS = {
    "User-Agent": "EduPhdAggregator/1.0 (contact: your-email@example.com)"
}

EDUCATION_KEYWORDS = [
    "education", "educational", "pedagogy", "pedagogical", "didactic",
    "teacher education", "learning science", "curriculum",
    "educational psychology", "higher education", "special education",
    "inclusive education", "adult education", "early childhood education",
    "educational technology", "vocational education", "language education",
    "mathematics education", "science education", "education policy",
    "educational leadership", "teaching and learning", "instructional design"
]

PHD_KEYWORDS = [
    "phd", "ph.d", "doctoral", "doctorate", "early stage researcher",
    "phd candidate", "phd fellow", "phd fellowship", "doctoral researcher"
]

EXCLUDE_KEYWORDS = [
    "postdoc", "post-doctoral", "postdoctoral", "professor",
    "lecturer", "assistant professor", "associate professor"
]

SOURCES = [
    {
        "name": "EURAXESS",
        "type": "rss",
        "url": "https://euraxess.ec.europa.eu/search?keys=education",
        "enabled": True,
    },
    {
        "name": "FindAPhD",
        "type": "rss",
        "url": "https://www.findaphd.com/phds/education/?10M7m0&Keywords=educational+technology",
        "enabled": True,
    },
    {
        "name": "jobs.ac.uk",
        "type": "rss",
        "url": "https://www.jobs.ac.uk/search/rss?keywords=education%20phd",
        "enabled": True,
    },
    {
        "name": "Academic Positions",
        "type": "rss",
        "url": "https://academicpositions.com/find-jobs?page=1&positions[0]=phd&search=educational+technology&fields[0]=education&fields[1]=educational-technology&fields[2]=digital-education",
        "enabled": True,
    },
    # 如果某个源失效，可以将其 enabled 改为 False，或直接删除该段
]

def is_phd(job):
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    if any(k in text for k in EXCLUDE_KEYWORDS):
        return False
    return any(k in text for k in PHD_KEYWORDS)


def is_education(job):
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return any(k in text for k in EDUCATION_KEYWORDS)


def fetch_rss(source):
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"RSS 获取失败 {source['name']}: {e}")
        return []

    jobs = []
    for entry in feed.entries:
        title = entry.get("title", "")
        url = entry.get("link", "")
        posted = entry.get("published") or entry.get("updated") or ""
        description = entry.get("summary", "")
        jobs.append({
            "title": title,
            "url": url,
            "source": source["name"],
            "posted": posted,
            "deadline": "",
            "description": description,
        })
    return jobs


def fetch_html(source):
    if source.get("item_selector") == "TODO":
        print(f"跳过 {source['name']}: 未配置 HTML 选择器")
        return []

    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"HTML 获取失败 {source['name']}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    jobs = []
    for item in soup.select(source["item_selector"]):
        a = item.select_one(source.get("title_selector", "a"))
        if not a:
            continue

        title = a.get_text(strip=True)
        url = a.get("href", "")
        if url.startswith("/"):
            url = urljoin(source["url"], url)

        date_el = item.select_one(source.get("date_selector", "time"))
        posted = date_el.get_text(strip=True) if date_el else ""

        jobs.append({
            "title": title,
            "url": url,
            "source": source["name"],
            "posted": posted,
            "deadline": "",
            "description": "",
        })
    return jobs


def fetch_description(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"]

        return soup.get_text(" ", strip=True)[:2000]
    except Exception as e:
        print(f"详情页获取失败 {url}: {e}")
        return ""


def load_existing():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_jobs(jobs):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def main():
    existing = load_existing()
    existing_urls = {j.get("url") for j in existing if j.get("url")}

    fetched = []
    for source in SOURCES:
        if not source.get("enabled"):
            continue
        try:
            if source["type"] == "rss":
                fetched.extend(fetch_rss(source))
            elif source["type"] == "html":
                fetched.extend(fetch_html(source))
            time.sleep(1)
        except Exception as e:
            print(f"抓取失败 {source['name']}: {e}")

    target_jobs = []
    for job in fetched:
        if not is_phd(job):
            continue

        if is_education(job):
            target_jobs.append(job)
        else:
            desc = fetch_description(job["url"])
            job["description"] = desc
            if is_education(job):
                target_jobs.append(job)
            time.sleep(0.5)

    now = datetime.now(timezone.utc).isoformat()
    for job in target_jobs:
        job["scraped_at"] = now

    seen = set(existing_urls)
    new_jobs = []
    for job in target_jobs:
        if job.get("url") and job["url"] not in seen:
            seen.add(job["url"])
            new_jobs.append(job)

    combined = new_jobs + existing
    combined.sort(key=lambda x: x.get("posted") or x.get("scraped_at", ""), reverse=True)

    save_jobs(combined)
    print(f"抓取 {len(fetched)} 条，目标岗位 {len(target_jobs)} 条，新增 {len(new_jobs)} 条")


if __name__ == "__main__":
    main()
