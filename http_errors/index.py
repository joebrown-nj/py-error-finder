#!/usr/bin/env python3

"""
Website Broken Link & Error Crawler
-----------------------------------

Features:
- Crawls an entire domain
- Checks every discovered:
    - link (a href)
    - image (img src)
    - script (script src)
    - stylesheet (link href rel=stylesheet)
- Detects 4xx/5xx responses
- Saves an errors report to CSV
- Respects same-domain crawling for page traversal
- Avoids duplicate crawling/checking

Usage:
    python crawl_site.py [URL]

Optional:
    python crawl_site.py [URL] --max-pages 1000
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import csv
import argparse
import time
from datetime import datetime
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawler_common import DEFAULT_HEADERS, format_duration, normalize_url

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

HEADERS = DEFAULT_HEADERS

visited = set()
errors = []
checked_resources = set()
method_mismatches = []


def is_same_domain(base_domain, url):
    return urlparse(url).netloc == base_domain


def log_http_error(
    checked_url,
    final_url,
    status,
    resource_type,
    crawled_url,
    raw_reference="",
    link_text="",
    head_status="",
    get_status="",
    failure_reason="",
):
    if 400 <= status < 600:
        errors.append({
            "url": checked_url,
            "final_url": final_url,
            "status": status,
            "type": resource_type,
            "crawled_url": crawled_url,
            "raw_reference": raw_reference,
            "link_text": link_text,
            "head_status": head_status,
            "get_status": get_status,
            "failure_reason": failure_reason,
        })


def log_method_mismatch(
    checked_url,
    crawled_url,
    resource_type,
    head_status,
    get_status,
    head_final_url,
    get_final_url,
    head_redirect_chain,
    get_redirect_chain,
    head_server,
    get_server,
    head_cache_control,
    get_cache_control,
    head_cf_cache_status,
    get_cf_cache_status,
    head_via,
    get_via,
    head_x_cache,
    get_x_cache,
    raw_reference="",
    link_text="",
):
    method_mismatches.append({
        "url": checked_url,
        "crawled_url": crawled_url,
        "type": resource_type,
        "head_status": head_status,
        "get_status": get_status,
        "head_final_url": head_final_url,
        "get_final_url": get_final_url,
        "head_redirect_chain": head_redirect_chain,
        "get_redirect_chain": get_redirect_chain,
        "head_server": head_server,
        "get_server": get_server,
        "head_cache_control": head_cache_control,
        "get_cache_control": get_cache_control,
        "head_cf_cache_status": head_cf_cache_status,
        "get_cf_cache_status": get_cf_cache_status,
        "head_via": head_via,
        "get_via": get_via,
        "head_x_cache": head_x_cache,
        "get_x_cache": get_x_cache,
        "raw_reference": raw_reference,
        "link_text": link_text,
        "note": "HEAD returned error while GET succeeded",
    })


def format_redirect_chain(response):
    if response is None:
        return ""

    chain = [f"{item.status_code}:{item.url}" for item in response.history]
    chain.append(f"{response.status_code}:{response.url}")
    return " -> ".join(chain)


def get_response_header(response, name):
    if response is None:
        return ""

    value = response.headers.get(name, "")
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)

    return str(value)


def check_resource(url, resource_type, crawled_from, raw_reference="", link_text=""):
    if url in checked_resources:
        return

    checked_resources.add(url)

    try:
        head_response = requests.head(
            url,
            headers=HEADERS,
            timeout=10,
            allow_redirects=True
        )
        head_status = head_response.status_code
        get_status = ""
        failure_reason = ""
        final_response = head_response

        # Some servers return false errors on HEAD. Re-check with GET before logging.
        if head_status in (405, 501) or 400 <= head_status < 600:
            get_response = requests.get(
                url,
                headers=HEADERS,
                timeout=10,
                allow_redirects=True,
                stream=True
            )
            get_status = get_response.status_code
            final_response = get_response

            if 400 <= head_status < 600 and get_status < 400:
                log_method_mismatch(
                    checked_url=url,
                    crawled_url=crawled_from,
                    resource_type=resource_type,
                    head_status=head_status,
                    get_status=get_status,
                    head_final_url=head_response.url,
                    get_final_url=get_response.url,
                    head_redirect_chain=format_redirect_chain(head_response),
                    get_redirect_chain=format_redirect_chain(get_response),
                    head_server=get_response_header(head_response, "Server"),
                    get_server=get_response_header(get_response, "Server"),
                    head_cache_control=get_response_header(head_response, "Cache-Control"),
                    get_cache_control=get_response_header(get_response, "Cache-Control"),
                    head_cf_cache_status=get_response_header(head_response, "CF-Cache-Status"),
                    get_cf_cache_status=get_response_header(get_response, "CF-Cache-Status"),
                    head_via=get_response_header(head_response, "Via"),
                    get_via=get_response_header(get_response, "Via"),
                    head_x_cache=get_response_header(head_response, "X-Cache"),
                    get_x_cache=get_response_header(get_response, "X-Cache"),
                    raw_reference=raw_reference,
                    link_text=link_text,
                )
                return

            if head_status in (405, 501):
                failure_reason = "HEAD not allowed; validated with GET"
            elif 400 <= head_status < 600 and get_status >= 400:
                failure_reason = f"HEAD {head_status}, GET {get_status}"

        if 400 <= final_response.status_code < 600:
            log_http_error(
                checked_url=url,
                final_url=final_response.url,
                status=final_response.status_code,
                resource_type=resource_type,
                crawled_url=crawled_from,
                raw_reference=raw_reference,
                link_text=link_text,
                head_status=head_status,
                get_status=get_status,
                failure_reason=failure_reason,
            )

    except requests.exceptions.RequestException:
        pass


def get_links(url, crawled_from, base_domain):
    links_to_crawl = set()

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=10,
            allow_redirects=True
        )

        log_http_error(
            checked_url=url,
            final_url=response.url,
            status=response.status_code,
            resource_type="PAGE",
            crawled_url=crawled_from,
            failure_reason="Page request failed",
        )

        if response.status_code >= 400:
            return links_to_crawl

        content_type = response.headers.get("Content-Type", "")

        if "text/html" not in content_type:
            return links_to_crawl

        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup.find_all("a"):
            raw_link = element.get("href")
            if not raw_link:
                continue

            full_url = urljoin(url, raw_link)
            parsed = urlparse(full_url)
            if parsed.scheme not in ["http", "https"]:
                continue

            clean_url = normalize_url(full_url)

            # Only validate and crawl hrefs from the same domain.
            if not is_same_domain(base_domain, clean_url):
                continue

            check_resource(
                clean_url,
                "HREF",
                url,
                raw_reference=raw_link,
                link_text=element.get_text(" ", strip=True),
            )
            links_to_crawl.add(clean_url)

        for element in soup.find_all("img"):
            raw_link = element.get("src")
            if not raw_link:
                continue

            full_url = urljoin(url, raw_link)
            parsed = urlparse(full_url)
            if parsed.scheme not in ["http", "https"]:
                continue

            clean_url = normalize_url(full_url)
            check_resource(clean_url, "IMG", url, raw_reference=raw_link)

        for element in soup.find_all("script"):
            raw_link = element.get("src")
            if not raw_link:
                continue

            full_url = urljoin(url, raw_link)
            parsed = urlparse(full_url)
            if parsed.scheme not in ["http", "https"]:
                continue

            clean_url = normalize_url(full_url)
            check_resource(clean_url, "JS", url, raw_reference=raw_link)

        for element in soup.find_all("link"):
            rel_values = element.get("rel", [])
            href = element.get("href")

            if not href:
                continue

            # Restrict to stylesheets to match CSS requirement.
            rel_lower = [value.lower() for value in rel_values]
            if "stylesheet" not in rel_lower and not href.lower().endswith(".css"):
                continue

            full_url = urljoin(url, href)
            parsed = urlparse(full_url)
            if parsed.scheme not in ["http", "https"]:
                continue

            clean_url = normalize_url(full_url)
            check_resource(clean_url, "CSS", url, raw_reference=href)

    except requests.exceptions.RequestException:
        pass

    return links_to_crawl


def crawl(start_url, max_pages=500, run_start_time=None):
    parsed_start = urlparse(start_url)
    domain = parsed_start.netloc
    normalized_start = normalize_url(start_url)

    if run_start_time is None:
        run_start_time = time.time()

    queue = deque([(normalized_start, normalized_start)])

    while queue and len(visited) < max_pages:
        current, crawled_from = queue.popleft()

        if current in visited:
            continue

        visited.add(current)

        elapsed = format_duration(time.time() - run_start_time)

        print(f"[{len(visited)}] Crawling: {current} | Elapsed: {elapsed}")

        links = get_links(current, crawled_from, domain)

        for link in links:
            if (
                link not in visited and
                is_same_domain(domain, link)
            ):
                queue.append((link, current))

        time.sleep(0.25)


def save_csv(filename, rows, headers):
    REPORTS_DIR.mkdir(exist_ok=True)

    with open(REPORTS_DIR / filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main():
    visited.clear()
    errors.clear()
    checked_resources.clear()
    method_mismatches.clear()

    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Starting URL")
    parser.add_argument("--max-pages", type=int, default=500)

    args = parser.parse_args()

    run_start_time = time.time()

    crawl(args.url, args.max_pages, run_start_time)

    timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    errors_filename = f"{timestamp_prefix}_crawl_errors.csv"
    mismatch_filename = f"{timestamp_prefix}_head_get_mismatches.csv"

    save_csv(
        errors_filename,
        errors,
        [
            "url",
            "final_url",
            "status",
            "type",
            "crawled_url",
            "raw_reference",
            "link_text",
            "head_status",
            "get_status",
            "failure_reason",
        ]
    )

    save_csv(
        mismatch_filename,
        method_mismatches,
        [
            "url",
            "crawled_url",
            "type",
            "head_status",
            "get_status",
            "head_final_url",
            "get_final_url",
            "head_redirect_chain",
            "get_redirect_chain",
            "head_server",
            "get_server",
            "head_cache_control",
            "get_cache_control",
            "head_cf_cache_status",
            "get_cf_cache_status",
            "head_via",
            "get_via",
            "head_x_cache",
            "get_x_cache",
            "raw_reference",
            "link_text",
            "note",
        ]
    )

    print("\nDone.")
    print(f"Pages Crawled: {len(visited)}")
    print(f"Errors Found: {len(errors)}")
    print(f"HEAD/GET Mismatches: {len(method_mismatches)}")
    print(f"Total Run Time: {format_duration(time.time() - run_start_time)}")

    print("\nReports Generated:")
    print(f"- {REPORTS_DIR / errors_filename}")
    print(f"- {REPORTS_DIR / mismatch_filename}")


if __name__ == "__main__":
    main()
