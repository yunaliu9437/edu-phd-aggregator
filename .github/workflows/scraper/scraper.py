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

# 教育学相关关键词
EDUCATION_KEYWORDS = [
    "education", "educational", "pedagogy", "pedagogical", "didactic",
    "teacher education", "learning science", "curriculum",
    "educational psychology", "higher education", "special education",
    "inclusive education", "adult education", "early childhood education",
    "educational technology", "vocational education", "language education",
    "mathematics education", "science education", "education policy",
    "educational leadership", "teaching and learning", "instructional design"
]

# 博士岗位关键词
PHD_KEYWORDS = [
    "phd", "ph.d", "doctoral", "doctorate", "early stage researcher",
    "phd candidate", "phd fellow", "phd fellowship", "doctoral researcher"
]

# 排除岗位
EXCLUDE_KEYWORDS = [
    "postdoc", "post-doctoral", "postdoctoral", "professor",
    "lecturer", "assistant professor", "associate professor"
]

# 数据源配置
SOURCES = [
    {
        "name": "EURAXESS",
        "type": "rss",
        # 搜索 education PhD 的 RSS 链接，已经帮你准备好了
        "url": "https://euraxess.ec.europa.eu/jobs/rss?keys=education%20phd",
        "enabled": True,   # 启用
    },
    # 你可以以后在这里添加更多源
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
    """抓取 RSS 源"""
    feed = feedparser.parse(source["url"])
    if feed.bozo:
        print(f"RSS 解析警告 {source['name']}: {feed.bozo_exception}")

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
    """抓取 HTML 页面（需要配置 CSS 选择器）"""
    if source.get("item_selector") == "TODO":
        print(f"跳过 {source['name']}: 未配置 HTML 选择器")
        return []

    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
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
    """抓取详情页描述，用于二次过滤教育学岗位"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"]

        return soup.get_text(" ", strip=True)[:2000]
    except Exception:
        return ""


def load_existing():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
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
            time.sleep(1)  # 限速，避免请求过快
        except Exception as e:
            print(f"抓取失败 {source['name']}: {e}")

    target_jobs = []
    for job in fetched:
        # 第一步：必须是博士岗位
        if not is_phd(job):
            continue

        # 第二步：优先通过标题判断教育学
        if is_education(job):
            target_jobs.append(job)
        else:
            # 如果标题不含教育学关键词，但博士岗位明确，则抓详情页描述二次判断
            desc = fetch_description(job["url"])
            job["description"] = desc
            if is_education(job):
                target_jobs.append(job)
            time.sleep(0.5)

    # 添加抓取时间
    now = datetime.now(timezone.utc).isoformat()
    for job in target_jobs:
        job["scraped_at"] = now

    # 去重
    seen = set(existing_urls)
    new_jobs = []
    for job in target_jobs:
        if job.get("url") and job["url"] not in seen:
            seen.add(job["url"])
            new_jobs.append(job)

    # 合并并按发布时间排序
    combined = new_jobs + existing
    combined.sort(key=lambda x: x.get("posted") or x.get("scraped_at", ""), reverse=True)

    save_jobs(combined)
    print(f"抓取 {len(fetched)} 条，目标岗位 {len(target_jobs)} 条，新增 {len(new_jobs)} 条")


if __name__ == "__main__":
    main()
