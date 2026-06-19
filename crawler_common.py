from urllib.parse import urlparse


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SiteCrawler/1.0)"
}


def format_duration(seconds):
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def normalize_url(url):
    if not url:
        return url

    parsed = urlparse(url.strip())
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"

    return normalized.rstrip("/")