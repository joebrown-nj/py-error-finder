import argparse
import subprocess
import sys
import threading
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SITEMAP_SCRIPT = ROOT_DIR / "sitemap" / "index.py"
HTTP_ERRORS_SCRIPT = ROOT_DIR / "http_errors" / "index.py"


def stream_output(prefix, pipe):
    try:
        for line in pipe:
            print(f"[{prefix}] {line.rstrip()}")
    finally:
        pipe.close()


def start_process(script_path, url, max_pages):
    command = [sys.executable, str(script_path), url, "--max-pages", str(max_pages)]
    return subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Run the sitemap and error crawlers together."
    )
    parser.add_argument("url", help="Starting URL")
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--sitemap-max-pages", type=int)
    parser.add_argument("--http-errors-max-pages", type=int)

    args = parser.parse_args()

    sitemap_max_pages = args.sitemap_max_pages or args.max_pages
    http_errors_max_pages = args.http_errors_max_pages or args.max_pages

    processes = {
        "sitemap": start_process(SITEMAP_SCRIPT, args.url, sitemap_max_pages),
        "http_errors": start_process(HTTP_ERRORS_SCRIPT, args.url, http_errors_max_pages),
    }

    readers = []
    for name, process in processes.items():
        reader = threading.Thread(
            target=stream_output,
            args=(name, process.stdout),
            daemon=True,
        )
        readers.append(reader)
        reader.start()

    exit_codes = {}
    for name, process in processes.items():
        exit_codes[name] = process.wait()

    for reader in readers:
        reader.join()

    failed = {name: code for name, code in exit_codes.items() if code != 0}
    if failed:
        for name, code in failed.items():
            print(f"{name} exited with code {code}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()