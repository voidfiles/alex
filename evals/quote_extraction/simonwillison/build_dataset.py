# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "beautifulsoup4==4.14.3",
#   "httpx==0.28.1",
#   "Markdown==3.9",
#   "markdownify==1.2.2",
#   "trafilatura==2.1.0",
# ]
# ///
"""Collect source-grounded quote examples; run with uv run --script this_file."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import markdown
import trafilatura
from bs4 import BeautifulSoup
from markdownify import markdownify

BASE = "https://simonwillison.net"
ARCHIVE = f"{BASE}/quotations/"
USER_AGENT = "AlexQuoteDataset/1.0"
SEEDS = [
    f"{BASE}/2026/Oct/1/matthew-green/",
    f"{BASE}/2026/Sep/29/anthropic-frontier-red-team/",
    f"{BASE}/2026/Sep/28/joedaroo/",
]
SOCIAL_HOSTS = {
    "twitter.com",
    "x.com",
    "threads.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "bsky.app",
}
EDITORIAL = re.compile(r"\[([^\]]+)\]|\.{3}|…")


def dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def dump_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
    )


def normalized(text: str) -> str:
    """Compare words, ignoring whitespace, case, typography and punctuation."""
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def markdown_text(text: str) -> str:
    html = markdown.markdown(text, extensions=["tables", "fenced_code", "def_list"])
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def quote_segments(quote: str) -> list[str]:
    # Bracketed text is Simon's editorial insertion/replacement, not source text.
    return [part.strip() for part in EDITORIAL.split(quote)[::2] if normalized(part)]


def align_quote(quote: str, source: str) -> list[dict[str, Any]]:
    """Require every non-editorial segment to occur in source order."""
    source_normalized = normalized(markdown_text(source))
    cursor = 0
    alignments = []
    for segment in quote_segments(quote):
        needle = normalized(segment)
        match = re.search(
            r"(?<!\w)" + re.escape(needle) + r"(?!\w)",
            source_normalized[cursor:],
        )
        if match is None:
            raise ValueError(f"quote segment absent from source: {segment[:100]!r}")
        start = cursor + match.start()
        end = cursor + match.end()
        alignments.append(
            {
                "quote_segment": segment,
                "normalized_segment": needle,
                "normalized_source_start": start,
                "normalized_source_end": end,
            }
        )
        cursor = end
    if not alignments:
        raise ValueError("quote contains no source-grounded segments")
    return alignments


class Fetcher:
    """Bounded, cached HTTP requests with per-host pacing and robots checks."""

    def __init__(self, client: httpx.AsyncClient, cache: Path, refresh: bool):
        self.client = client
        self.cache = cache
        self.refresh = refresh
        self.semaphore = asyncio.Semaphore(4)
        self.locks: dict[str, asyncio.Lock] = {}
        self.robots: dict[str, RobotFileParser | None] = {}
        cache.mkdir(parents=True, exist_ok=True)

    async def request(self, url: str) -> dict[str, Any]:
        key = hashlib.sha256(url.encode()).hexdigest()
        cache_path = self.cache / f"{key}.json"
        if cache_path.exists() and not self.refresh:
            return json.loads(cache_path.read_text())
        host = urlparse(url).netloc
        lock = self.locks.setdefault(host, asyncio.Lock())
        async with lock, self.semaphore:
            response = await self.client.get(url)
            result = {
                "url": url,
                "resolved_url": str(response.url),
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "fetched_at": datetime.now(UTC).isoformat(),
                "html": response.text,
            }
            dump_json(cache_path, result)
            await asyncio.sleep(0.5)
        return result

    async def fetch(self, url: str) -> dict[str, Any]:
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        if origin not in self.robots:
            try:
                response = await self.request(f"{origin}/robots.txt")
                parser = RobotFileParser()
                if response["status"] == 200 and "<html" not in response["html"]:
                    parser.parse(response["html"].splitlines())
                    self.robots[origin] = parser
                else:
                    self.robots[origin] = None
            except httpx.HTTPError:
                self.robots[origin] = None
        parser = self.robots[origin]
        if parser is not None and not parser.can_fetch(USER_AGENT, url):
            raise ValueError("disallowed by source robots.txt")
        result = await self.request(url)
        if result["status"] != 200:
            raise ValueError(f"HTTP {result['status']}")
        if "html" not in result["content_type"]:
            raise ValueError(f"unsupported content type: {result['content_type']}")
        return result


def parse_candidate(element: Any, archive_url: str) -> dict[str, Any]:
    block = element.select_one("blockquote[cite]")
    bookmark = element.select_one('a[rel="bookmark"]')
    attribution = element.select_one(".cite a")
    if block is None or bookmark is None or attribution is None:
        raise ValueError("quotation is missing a source, bookmark, or attribution")
    post_url = urljoin(BASE, bookmark["href"])
    date = (
        datetime.strptime("/".join(urlparse(post_url).path.split("/")[1:4]), "%Y/%b/%d")
        .date()
        .isoformat()
    )
    context = element.select_one(".context")
    return {
        "id": f"{date}-{urlparse(post_url).path.rstrip('/').split('/')[-1]}",
        "post_url": post_url,
        "post_date": date,
        "source_url": urljoin(BASE, block["cite"]),
        "attribution": attribution.get_text(" ", strip=True),
        "context": context.get_text(" ", strip=True) if context else "",
        "tags": [a.get_text(strip=True) for a in element.select('a[href^="/tags/"]')],
        "reference_quote": block.get_text(" ", strip=True),
        "reference_quote_markdown": markdownify(
            block.decode_contents(), heading_style="ATX"
        ).strip(),
        "discovered_on": archive_url,
    }


def extract_source(html: str, url: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(url).hostname or ""
    if host == "github.com" and "/commit/" in urlparse(url).path:
        for script in soup.select('script[type="application/json"]'):
            data = json.loads(script.string or "{}")
            commit = data.get("payload", {}).get("commitRoute", {}).get("commit")
            if commit:
                title = BeautifulSoup(
                    commit["shortMessageMarkdown"], "html.parser"
                ).get_text(" ", strip=True)
                body = BeautifulSoup(
                    commit["bodyMessageHtml"], "html.parser"
                ).get_text()
                return title, f"# {title}\n\n{body}\n", "github-commit-message"
        raise ValueError("GitHub page is missing the original commit message")
    if host == "news.ycombinator.com":
        item_id = urlparse(url).fragment
        item = soup.find(id=item_id) if item_id else None
        comment = item.select_one(".commtext") if item else None
        if comment is None:
            raise ValueError(
                "forum link does not identify an individual source comment"
            )
        author = item.select_one(".hnuser")
        title = f"Hacker News comment by {author.get_text() if author else item_id}"
        body = markdownify(str(comment), heading_style="ATX").strip()
        return title, f"# {title}\n\n{body}\n", "hacker-news-linked-comment"
    heading = soup.select_one("h1")
    og_title = soup.select_one('meta[property="og:title"]')
    title = og_title.get("content", "") if og_title else ""
    if not title and heading:
        title = heading.get_text(" ", strip=True)
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    # Known article containers preserve all paragraphs, including footnotes.
    selectors = (
        ".entry-content, .post-content, .e-content, .body.markup, "
        "#post-content, #article-body"
    )
    if host == "daringfireball.net":
        selectors = "#Main > .article, #Main > .linkedlist"
    elif host == "www.anthropic.com":
        selectors = "main article article"
    container = soup.select_one(selectors)
    if container is not None:
        for junk in container.select(
            "script, style, nav, form, .sharedaddy, .prevnext, .dateline, "
            "[class*='newsletter'], [class*='share-button'], [class*='social-share']"
        ):
            junk.decompose()
        if host == "daringfireball.net":
            # Daring Fireball uses a definition list for a linked post. Flatten
            # that layout so its prose does not become an indented code block.
            for term in container.select("dt"):
                term.name = "h1"
            for definition in container.select("dd"):
                definition.unwrap()
            for definition_list in container.select("dl"):
                definition_list.name = "div"
        content_html = str(container)
        method = "article-container+markdownify"
    else:
        content_html = trafilatura.extract(
            html,
            url=url,
            output_format="html",
            include_links=True,
            include_tables=True,
            include_comments=False,
            include_formatting=True,
            favor_recall=True,
        )
        if not content_html:
            raise ValueError("main article extraction returned no content")
        method = "trafilatura-html+markdownify"
    body = markdownify(content_html, heading_style="ATX", bullets="-").strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    if title and normalized(title) not in normalized(markdown_text(body[:500])):
        body = f"# {title}\n\n{body}"
    return title, body + "\n", method


async def collect_one(
    fetcher: Fetcher, candidate: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        host = urlparse(candidate["source_url"]).hostname or ""
        if host == "github.com" and urlparse(candidate["source_url"]).path.endswith(
            ".json"
        ):
            raise ValueError("configuration/code file excluded from prose benchmark")
        if (
            host.removeprefix("www.") in SOCIAL_HOSTS
            and candidate["post_url"] not in SEEDS
        ):
            raise ValueError(
                "social/video source excluded from article-selection benchmark"
            )
        response = await fetcher.fetch(candidate["source_url"])
        title, source, method = extract_source(
            response["html"], response["resolved_url"]
        )
        source_words = len(normalized(markdown_text(source)).split())
        quote_words = len(normalized(candidate["reference_quote"]).split())
        if source_words < 150 or source_words < quote_words + 80:
            raise ValueError(
                f"insufficient source context ({source_words} source words)"
            )
        alignments = align_quote(candidate["reference_quote"], source)
        record = {
            "schema_version": 1,
            **candidate,
            "resolved_source_url": response["resolved_url"],
            "source_title": title,
            "source_fetched_at": response["fetched_at"],
            "extraction_method": method,
            "source_markdown_path": f"cases/{candidate['id']}/source.md",
            "quote_markdown_path": f"cases/{candidate['id']}/quote.md",
            "source_markdown": source,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "source_word_count": source_words,
            "quote_word_count": quote_words,
            "validation": {
                "status": "verified",
                "method": "ordered-normalized-source-segments",
                "editorial_markers": [
                    m.group() for m in EDITORIAL.finditer(candidate["reference_quote"])
                ],
                "segments": alignments,
            },
        }
        return record, None
    except (ValueError, httpx.HTTPError) as error:
        return None, {
            **candidate,
            "reason": str(error),
            "attempted_at": datetime.now(UTC).isoformat(),
        }


def validate(output: Path, expected_count: int | None = None) -> None:
    records = [
        json.loads(line)
        for line in (output / "examples.jsonl").read_text().splitlines()
    ]
    if expected_count is not None and len(records) != expected_count:
        raise ValueError(f"expected {expected_count} examples, got {len(records)}")
    for field in ("id", "post_url", "resolved_source_url", "source_sha256"):
        if len({record[field] for record in records}) != len(records):
            raise ValueError(f"duplicate {field}")
    splits = json.loads((output / "splits.json").read_text())
    for split in ("dev", "test"):
        if splits[split] != [r["id"] for r in records if r["split"] == split]:
            raise ValueError(f"split manifest differs from JSONL: {split}")
    if set(splits["dev"]) & set(splits["test"]):
        raise ValueError("development and test splits overlap")
    for record in records:
        if record["schema_version"] != 1:
            raise ValueError(f"unsupported schema: {record['id']}")
        if normalized(markdown_text(record["reference_quote_markdown"])) != normalized(
            record["reference_quote"]
        ):
            raise ValueError(f"plain-text quote differs from Markdown: {record['id']}")
        source = (output / record["source_markdown_path"]).read_text()
        if source != record["source_markdown"]:
            raise ValueError(f"source file differs from JSONL: {record['id']}")
        if hashlib.sha256(source.encode()).hexdigest() != record["source_sha256"]:
            raise ValueError(f"source checksum differs: {record['id']}")
        if (
            align_quote(record["reference_quote"], source)
            != record["validation"]["segments"]
        ):
            raise ValueError(f"quote alignment differs: {record['id']}")
        quote = (output / record["quote_markdown_path"]).read_text()
        if record["reference_quote_markdown"] not in quote:
            raise ValueError(f"quote file differs from JSONL: {record['id']}")
    print(
        f"Validated {len(records)} unique source/quote pairs, checksums and alignments."
    )


async def build(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    discovered: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    seen_posts: set[str] = set()
    seen_sources: set[str] = set()
    seen_hashes: set[str] = set()
    started_at = datetime.now(UTC).isoformat()
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(30, connect=10),
    ) as client:
        fetcher = Fetcher(client, args.cache_dir, args.refresh)
        archive_url = ARCHIVE
        for _ in range(args.max_pages):
            response = await fetcher.fetch(archive_url)
            soup = BeautifulSoup(response["html"], "html.parser")
            candidates = []
            for element in soup.select(".quote.segment"):
                candidate = parse_candidate(element, archive_url)
                if candidate["post_url"] not in seen_posts:
                    seen_posts.add(candidate["post_url"])
                    candidates.append(candidate)
            discovered.extend(candidates)
            pages.append(
                {
                    "url": archive_url,
                    "fetched_at": response["fetched_at"],
                    "quote_count": len(candidates),
                }
            )
            print(
                f"Discovered {len(candidates)} quotation posts on {archive_url}",
                flush=True,
            )
            offset = 0
            while offset < len(candidates):
                batch = candidates[
                    offset : offset + min(4, args.target - len(accepted))
                ]
                offset += len(batch)
                results = await asyncio.gather(
                    *(collect_one(fetcher, c) for c in batch)
                )
                for record, failure in results:
                    if failure:
                        rejected.append(failure)
                        print(
                            f"  SKIP {failure['id']}: {failure['reason']}", flush=True
                        )
                        continue
                    assert record is not None
                    if (
                        record["resolved_source_url"] in seen_sources
                        or record["source_sha256"] in seen_hashes
                    ):
                        rejected.append(
                            {**record, "reason": "duplicate original source"}
                        )
                        continue
                    seen_sources.add(record["resolved_source_url"])
                    seen_hashes.add(record["source_sha256"])
                    accepted.append(record)
                    print(
                        f"  ACCEPT {len(accepted):02d} {record['id']} "
                        f"({record['source_word_count']} words)",
                        flush=True,
                    )
                if len(accepted) >= args.target:
                    break
            if len(accepted) >= args.target:
                break
            next_link = next(
                (
                    a
                    for a in soup.select(".pagination a")
                    if a.get_text(strip=True).startswith("next")
                ),
                None,
            )
            if next_link is None:
                break
            archive_url = urljoin(archive_url, next_link["href"])
    # Stable held-out split for this snapshot; source URLs/hashes are unique.
    dev_ids = {
        r["id"]
        for r in sorted(
            accepted, key=lambda r: hashlib.sha256(r["id"].encode()).hexdigest()
        )[: max(1, args.target // 5)]
    }
    for record in accepted:
        record["split"] = "dev" if record["id"] in dev_ids else "test"
        case_dir = output / "cases" / record["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "source.md").write_text(record["source_markdown"])
        (case_dir / "quote.md").write_text(
            record["reference_quote_markdown"] + "\n\n"
            f"— {record['attribution']}\n\n"
            f"Source: {record['source_url']}\n\n"
            f"Selected by Simon Willison: {record['post_url']}\n"
        )
    dump_jsonl(output / "examples.jsonl", accepted)
    dump_jsonl(output / "rejected.jsonl", rejected)
    dump_jsonl(output / "candidates.jsonl", discovered)
    dump_json(
        output / "splits.json",
        {
            split: [r["id"] for r in accepted if r["split"] == split]
            for split in ("dev", "test")
        },
    )
    index = [
        "# Source / quote pairs\n",
        "Each source is the model input; each quote is the reference selection.\n",
        "| Date | Attribution | Source | Words | Reference | Split |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for record in accepted:
        title = record["source_title"].replace("|", "\\|").replace("\n", " ")
        index.append(
            f"| {record['post_date']} | {record['attribution']} | "
            f"[{title}]({record['source_markdown_path']}) | "
            f"{record['source_word_count']:,} | "
            f"[Quote]({record['quote_markdown_path']}) | {record['split']} |"
        )
    (output / "INDEX.md").write_text("\n".join(index) + "\n")
    report = {
        "schema_version": 1,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "target_count": args.target,
        "accepted_count": len(accepted),
        "discovered_count": len(discovered),
        "attempted_count": len(accepted) + len(rejected),
        "rejected_count": len(rejected),
        "source_word_counts": {
            "min": min(r["source_word_count"] for r in accepted),
            "median": median(r["source_word_count"] for r in accepted),
            "max": max(r["source_word_count"] for r in accepted),
            "total": sum(r["source_word_count"] for r in accepted),
        }
        if accepted
        else {},
        "selection": "newest-first eligible source items, without duplicate sources",
        "split_counts": dict(Counter(r["split"] for r in accepted)),
        "archive_pages": pages,
        "source_hosts": dict(
            Counter(urlparse(r["resolved_source_url"]).netloc for r in accepted)
        ),
        "seed_status": {
            url: "included"
            if any(r["post_url"] == url for r in accepted)
            else next(
                (r["reason"] for r in rejected if r["post_url"] == url),
                "not discovered",
            )
            for url in SEEDS
        },
    }
    dump_json(output / "crawl_report.json", report)
    validate(output, args.target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    parser.add_argument("--target", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument(
        "--cache-dir", type=Path, default=Path.home() / ".cache/alex/quote-dataset"
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.target < 1 or args.max_pages < 1:
        parser.error("--target and --max-pages must be positive")
    if args.validate_only:
        validate(args.output, args.target)
    else:
        asyncio.run(build(args))


if __name__ == "__main__":
    main()
