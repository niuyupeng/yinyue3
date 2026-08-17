from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


CPDL_BASE_URL = "https://www.cpdl.org"
DEFAULT_CATEGORY_URL = "https://www.cpdl.org/wiki/index.php/Category:SATB"
DEFAULT_USER_AGENT = "Mozilla/5.0 Codex Project1 CPDL MusicXML intake"

FetchText = Callable[[str], str]
FetchBytes = Callable[[str], bytes]


def prepare_cpdl_musicxml_subset(
    *,
    out_dir: str | Path,
    summary_json: str | Path,
    category_url: str = DEFAULT_CATEGORY_URL,
    max_category_pages: int = 3,
    max_work_pages: int = 200,
    max_files: int = 40,
    max_files_per_work: int = 1,
    request_delay_seconds: float = 0.5,
    include_copyright_regex: str = r"(?i)(Public Domain|CPDL)",
    exclude_title_regex: str = r"(?i)\bBach\b|Johann_Sebastian_Bach|185_Bach_Chorales",
    clean: bool = False,
    fetch_text: FetchText | None = None,
    fetch_bytes: FetchBytes | None = None,
) -> dict[str, Any]:
    out_path = Path(out_dir)
    summary_path = Path(summary_json)
    if clean and out_path.exists():
        for child in out_path.iterdir():
            if child.is_file():
                child.unlink()
    out_path.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    fetch_text = fetch_text or default_fetch_text
    fetch_bytes = fetch_bytes or default_fetch_bytes
    include_pattern = re.compile(include_copyright_regex) if include_copyright_regex else None
    exclude_pattern = re.compile(exclude_title_regex) if exclude_title_regex else None

    category_pages = crawl_category_pages(
        category_url=category_url,
        max_category_pages=max_category_pages,
        fetch_text=fetch_text,
        request_delay_seconds=request_delay_seconds,
    )
    work_links = unique_work_links(category_pages)
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    selected_count = 0
    downloaded_urls: set[str] = set()

    for work in work_links[: max(0, int(max_work_pages))]:
        if selected_count >= max_files:
            break
        work_url = work["url"]
        title = work["title"]
        if exclude_pattern and exclude_pattern.search(title):
            skipped.append({"title": title, "url": work_url, "reason": "title excluded"})
            continue
        try:
            body = fetch_text(work_url)
        except Exception as exc:
            skipped.append({"title": title, "url": work_url, "reason": f"fetch failed: {type(exc).__name__}: {exc}"})
            continue
        candidates = extract_mxl_candidates(body, work_url)
        if not candidates:
            skipped.append({"title": title, "url": work_url, "reason": "no MXL links"})
            continue
        accepted_for_work = 0
        for candidate in candidates:
            if selected_count >= max_files or accepted_for_work >= max_files_per_work:
                break
            copyright_text = candidate.get("copyright", "")
            if include_pattern and not copyright_text:
                skipped.append({"title": title, "url": work_url, "reason": "copyright missing"})
                continue
            if include_pattern and copyright_text and not include_pattern.search(copyright_text):
                skipped.append({"title": title, "url": work_url, "reason": f"copyright skipped: {copyright_text}"})
                continue
            mxl_url = candidate["url"]
            if mxl_url in downloaded_urls:
                continue
            filename = make_safe_filename(selected_count + 1, title, mxl_url)
            target = out_path / filename
            try:
                payload = fetch_bytes(mxl_url)
                target.write_bytes(payload)
            except Exception as exc:
                skipped.append(
                    {"title": title, "url": mxl_url, "reason": f"download failed: {type(exc).__name__}: {exc}"}
                )
                continue
            downloaded_urls.add(mxl_url)
            selected_count += 1
            accepted_for_work += 1
            records.append(
                {
                    "index": selected_count,
                    "title": title,
                    "work_url": work_url,
                    "mxl_url": mxl_url,
                    "local_path": target.as_posix(),
                    "bytes": target.stat().st_size,
                    "copyright": copyright_text or "not parsed",
                    "posted": candidate.get("posted", ""),
                    "cpdl_number": candidate.get("cpdl_number", ""),
                }
            )
            sleep_if_needed(request_delay_seconds)

    summary = {
        "schema": "project1_cpdl_musicxml_subset_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "subset_prepared" if records else "no_files_selected",
        "source_name": "Choral Public Domain Library (CPDL)",
        "source_record_url": "https://www.cpdl.org/wiki/index.php/Main_Page",
        "source_license": "mixed; per-score CPDL copyright field captured in records",
        "discovery_category_url": category_url,
        "selected_musicxml_dir": out_path.resolve().as_posix(),
        "selected_mxl_count": len(records),
        "category_pages_scanned": len(category_pages),
        "work_pages_considered": min(len(work_links), max_work_pages),
        "max_files": int(max_files),
        "max_files_per_work": int(max_files_per_work),
        "include_copyright_regex": include_copyright_regex,
        "exclude_title_regex": exclude_title_regex,
        "records": records,
        "skipped": skipped[:200],
        "notes": [
            "This CPDL subset is a score-level SATB MusicXML/MXL candidate source prepared for intake testing.",
            "It is deliberately separated from the BCFB pilot because BCFB remains Bach chorale material.",
            "Do not cite CPDL candidate files as publishable external-corpus evidence until intake, dataset build, training, baseline evaluation, and license review are complete.",
            "Roman numeral and chord-label limitations are determined downstream by the MusicXML intake and dataset builder.",
        ],
    }
    write_outputs(summary, summary_path)
    return summary


def crawl_category_pages(
    *,
    category_url: str,
    max_category_pages: int,
    fetch_text: FetchText,
    request_delay_seconds: float,
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    current_url = category_url
    seen: set[str] = set()
    for _ in range(max(0, int(max_category_pages))):
        if current_url in seen:
            break
        seen.add(current_url)
        body = fetch_text(current_url)
        pages.append({"url": current_url, "html": body})
        next_url = extract_next_category_url(body, current_url)
        if not next_url:
            break
        current_url = next_url
        sleep_if_needed(request_delay_seconds)
    return pages


def unique_work_links(category_pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    for page in category_pages:
        for item in extract_work_links(str(page.get("html", "")), str(page.get("url", ""))):
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            links.append(item)
    return links


def extract_work_links(body: str, base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    page_section = body
    marker = 'id="mw-pages"'
    marker_index = body.find(marker)
    if marker_index >= 0:
        page_section = body[marker_index:]
    for match in re.finditer(r'<a\s+href="([^"]+)"\s+title="([^"]+)">([^<]+)</a>', page_section):
        href = html.unescape(match.group(1))
        title = strip_tags(html.unescape(match.group(2)))
        if not href.startswith("/wiki/index.php/") or href.startswith("/wiki/index.php/Category:"):
            continue
        if ":" in urllib.parse.unquote(href.rsplit("/", 1)[-1]) and not href.startswith("/wiki/index.php/%27"):
            continue
        links.append({"title": title, "url": absolute_url(href, base_url)})
    return links


def extract_next_category_url(body: str, base_url: str) -> str:
    for match in re.finditer(r'<a\s+href="([^"]+)"[^>]*>\s*next page\s*</a>', body, flags=re.I):
        return absolute_url(html.unescape(match.group(1)), base_url)
    return ""


def extract_mxl_candidates(body: str, base_url: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for match in re.finditer(r'<a\s+href="([^"]+\.mxl)"[^>]*title="([^"]+)"[^>]*>', body, flags=re.I):
        href = html.unescape(match.group(1))
        start = max(0, body.rfind("<li", 0, match.start()))
        end = body.find("</dd>", match.end())
        if end < 0:
            end = min(len(body), match.end() + 1500)
        context = body[start:end]
        candidates.append(
            {
                "url": absolute_url(href, base_url),
                "title": strip_tags(html.unescape(match.group(2))),
                "copyright": extract_label_text(context, "Copyright"),
                "posted": extract_posted_date(context),
                "cpdl_number": extract_cpdl_number(context),
            }
        )
    return candidates


def extract_label_text(context: str, label: str) -> str:
    pattern = rf"<b>\s*{re.escape(label)}:\s*</b>(.*?)(?:</dd>|<br\s*/?>|$)"
    match = re.search(pattern, context, flags=re.I | re.S)
    if not match:
        return ""
    return normalize_spaces(strip_tags(html.unescape(match.group(1))))


def extract_posted_date(context: str) -> str:
    match = re.search(r"\(Posted\s+([0-9-]+)\)", context, flags=re.I)
    return match.group(1) if match else ""


def extract_cpdl_number(context: str) -> str:
    match = re.search(r"CPDL\s*#.*?>([0-9]+)<", context, flags=re.I | re.S)
    return match.group(1) if match else ""


def make_safe_filename(index: int, title: str, url: str) -> str:
    source_name = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name)
    stem = Path(source_name).stem or title
    stem = normalize_spaces(stem)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if not stem:
        stem = "score"
    return f"cpdl_{index:03d}_{stem[:80]}.mxl"


def absolute_url(href: str, base_url: str) -> str:
    return urllib.parse.urljoin(base_url or CPDL_BASE_URL, href)


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def sleep_if_needed(seconds: float) -> None:
    if seconds > 0:
        time.sleep(float(seconds))


def default_fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def default_fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError:
        # Some CPDL files respond more consistently through /wiki/ path redirects.
        raise


def write_outputs(summary: dict[str, Any], out_json: Path) -> None:
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out_json.with_suffix(".csv").write_text(make_csv(summary), encoding="utf-8")
    out_json.with_suffix(".md").write_text(make_markdown(summary), encoding="utf-8")


def make_csv(summary: dict[str, Any]) -> str:
    from io import StringIO

    buffer = StringIO()
    fieldnames = [
        "index",
        "title",
        "work_url",
        "mxl_url",
        "local_path",
        "bytes",
        "copyright",
        "posted",
        "cpdl_number",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in summary.get("records", []):
        if isinstance(row, dict):
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return buffer.getvalue()


def make_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Project1 CPDL MusicXML Candidate Subset",
        "",
        f"Status: `{summary.get('status')}`",
        f"Source: {summary.get('source_name')}",
        f"Discovery category: {summary.get('discovery_category_url')}",
        f"Selected MXL files: {summary.get('selected_mxl_count')}",
        f"Selected directory: `{summary.get('selected_musicxml_dir')}`",
        f"Copyright filter: `{summary.get('include_copyright_regex')}`",
        f"Excluded titles: `{summary.get('exclude_title_regex')}`",
        "",
        "## Claim Boundary",
        "",
    ]
    lines.extend(f"- {item}" for item in summary.get("notes", []))
    lines.extend(["", "## Selected Records", "", "| # | Title | Copyright | File |", "|---:|---|---|---|"])
    for row in summary.get("records", [])[:100]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).replace("|", "/")
        copyright_text = str(row.get("copyright", "")).replace("|", "/")
        lines.append(f"| {row.get('index')} | {title} | {copyright_text} | `{row.get('local_path')}` |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a CPDL SATB MusicXML/MXL candidate subset for Project1.")
    parser.add_argument("--out-dir", default="data/raw/cpdl_selected_musicxml")
    parser.add_argument("--summary-json", default="results/project1_cpdl_musicxml_subset_latest.json")
    parser.add_argument("--category-url", default=DEFAULT_CATEGORY_URL)
    parser.add_argument("--max-category-pages", type=int, default=3)
    parser.add_argument("--max-work-pages", type=int, default=200)
    parser.add_argument("--max-files", type=int, default=40)
    parser.add_argument("--max-files-per-work", type=int, default=1)
    parser.add_argument("--request-delay-seconds", type=float, default=0.5)
    parser.add_argument("--include-copyright-regex", default=r"(?i)(Public Domain|CPDL)")
    parser.add_argument("--exclude-title-regex", default=r"(?i)\bBach\b|Johann_Sebastian_Bach|185_Bach_Chorales")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    summary = prepare_cpdl_musicxml_subset(
        out_dir=args.out_dir,
        summary_json=args.summary_json,
        category_url=args.category_url,
        max_category_pages=args.max_category_pages,
        max_work_pages=args.max_work_pages,
        max_files=args.max_files,
        max_files_per_work=args.max_files_per_work,
        request_delay_seconds=args.request_delay_seconds,
        include_copyright_regex=args.include_copyright_regex,
        exclude_title_regex=args.exclude_title_regex,
        clean=args.clean,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    if not summary.get("records"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
