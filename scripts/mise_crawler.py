"""
Legal, ethical crawler for mise.ax + e-tjanster.ax
Fixes: URL normalization (no more www/http/https duplicates),
multi-domain support, expanded file type handling.
"""

import os
import time
import csv
import urllib.robotparser
from urllib.parse import urljoin, urlparse, urlunparse
from collections import deque

import requests
from bs4 import BeautifulSoup
import trafilatura

BASE_URL = "https://www.mise.ax"
ALLOWED_DOMAINS = ["mise.ax", "e-tjanster.ax"]
USER_AGENT = "MiseRAGResearchBot/1.0 (+contact: your-email@example.com)"
REQUEST_DELAY = 1.5
MAX_PAGES = 1000

OUT_PAGES = "output/mise_pages"
OUT_PDFS = "output/mise_pdfs"
OUT_DOCS = "output/mise_docs"
LOG_FILE = "output/crawl_log.csv"

os.makedirs(OUT_PAGES, exist_ok=True)
os.makedirs(OUT_PDFS, exist_ok=True)
os.makedirs(OUT_DOCS, exist_ok=True)

DOC_EXTENSIONS = {
    ".doc": OUT_DOCS,
    ".docx": OUT_DOCS,
    ".xls": OUT_DOCS,
    ".xlsx": OUT_DOCS,
}


def normalize_url(url):
    parsed = urlparse(url)
    scheme = "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


def load_robots(base_url):
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(urljoin(base_url, "/robots.txt"))
    try:
        rp.read()
    except Exception:
        rp = None
    return rp


def is_allowed(rp, url):
    if rp is None:
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def safe_filename(url):
    parsed = urlparse(url)
    name = (parsed.netloc + "_" + parsed.path).strip("/").replace("/", "_") or "home"
    return name


def get_file_extension(url, content_type):
    path = urlparse(url).path.lower()
    for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx"]:
        if path.endswith(ext):
            return ext
    if "pdf" in content_type:
        return ".pdf"
    if "wordprocessingml" in content_type:
        return ".docx"
    if "msword" in content_type:
        return ".doc"
    if "spreadsheetml" in content_type:
        return ".xlsx"
    if "ms-excel" in content_type:
        return ".xls"
    return None


def crawl(base_url, max_pages=MAX_PAGES):
    robots_cache = {}
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    visited = set()
    queue = deque([normalize_url(base_url)])
    log_rows = []

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        norm_url = normalize_url(url)
        if norm_url in visited:
            continue
        visited.add(norm_url)

        parsed = urlparse(norm_url)
        if not any(d in parsed.netloc for d in ALLOWED_DOMAINS):
            continue

        domain_key = parsed.netloc
        if domain_key not in robots_cache:
            robots_cache[domain_key] = load_robots(f"https://{domain_key}")
        rp = robots_cache[domain_key]

        if not is_allowed(rp, norm_url):
            log_rows.append([norm_url, "skipped_robots_disallow", ""])
            continue

        try:
            resp = session.get(norm_url, timeout=15)
        except Exception as e:
            log_rows.append([norm_url, f"error:{e}", ""])
            time.sleep(REQUEST_DELAY)
            continue

        content_type = resp.headers.get("Content-Type", "").lower()
        ext = get_file_extension(norm_url, content_type)

        if ext == ".pdf":
            fname = safe_filename(norm_url) + ".pdf"
            with open(os.path.join(OUT_PDFS, fname), "wb") as f:
                f.write(resp.content)
            log_rows.append([norm_url, resp.status_code, "pdf_saved"])
        elif ext in DOC_EXTENSIONS:
            fname = safe_filename(norm_url) + ext
            with open(os.path.join(OUT_DOCS, fname), "wb") as f:
                f.write(resp.content)
            log_rows.append([norm_url, resp.status_code, f"doc_saved{ext}"])
        elif "text/html" in content_type:
            text = trafilatura.extract(resp.text, url=norm_url, include_comments=False)
            if text:
                fname = safe_filename(norm_url) + ".txt"
                with open(os.path.join(OUT_PAGES, fname), "w", encoding="utf-8") as f:
                    f.write(text)
                log_rows.append([norm_url, resp.status_code, "html_text_saved"])
            else:
                log_rows.append([norm_url, resp.status_code, "html_no_text_extracted"])

            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(norm_url, a["href"])
                link_norm = normalize_url(link)
                link_parsed = urlparse(link_norm)
                if (
                    any(d in link_parsed.netloc for d in ALLOWED_DOMAINS)
                    and link_norm not in visited
                ):
                    queue.append(link_norm)
        else:
            log_rows.append(
                [norm_url, resp.status_code, f"skipped_content_type:{content_type}"]
            )

        time.sleep(REQUEST_DELAY)

    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "status", "action"])
        writer.writerows(log_rows)

    return len(visited), log_rows


if __name__ == "__main__":
    visited_count, logs = crawl(BASE_URL)
    print(f"Visited {visited_count} unique URLs")
    print(f"Pages saved: {len(os.listdir(OUT_PAGES))}")
    print(f"PDFs saved: {len(os.listdir(OUT_PDFS))}")
    print(f"Docs saved: {len(os.listdir(OUT_DOCS))}")
