# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "beautifulsoup4==4.14.3",
#   "httpx==0.28.1",
#   "Markdown==3.9",
#   "markdown-it-py==4.2.0",
#   "markdownify==1.2.2",
#   "trafilatura==2.1.0",
# ]
# ///
"""Collect additional, independently source-verified Quotebacks eval cases."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from markdownify import markdownify

ROOT = Path(__file__).parent
PARENT = ROOT.parent


def module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


discovery = module("quote_discovery", PARENT / "quotebacks/discover_sources.py")
original = module("original_quote_dataset", PARENT / "simonwillison/build_dataset.py")
SOCIAL = discovery.SOCIAL | original.SOCIAL_HOSTS | {"micro.blog"}
OMISSIONS = re.compile(r"\[(?:\.{3}|…)\]|\.{3}|…")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def url_key(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_")
        and k not in {"fbclid", "gclid", "r", "showWelcomeOnShare", "publication_id"}
    ]
    # Fragments locate passages, not distinct source documents.
    return urlunsplit(
        ("", discovery.host(url), parts.path.rstrip("/"), urlencode(sorted(query)), "")
    )


def markdown_text(source: str) -> str:
    """CommonMark word boundaries compatible with alex's extraction renderer."""
    soup = BeautifulSoup(
        MarkdownIt("commonmark").enable("table").render(source), "html.parser"
    )
    for tag in soup.select("script, style"):
        tag.decompose()
    for image in soup.find_all("img"):
        image.replace_with(str(image.get("alt") or ""))
    for tag in soup.find_all(
        ["p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"]
    ):
        tag.insert_before("\n\n")
        if tag.name != "br":
            tag.insert_after("\n\n")
    for tag in soup.find_all(["td", "th"]):
        tag.insert_before("\t")
    return soup.get_text()


def align(quote: str, source: str) -> tuple[list[dict[str, Any]], str]:
    """Match all words; only explicit ellipses can omit intervening source text."""
    normalized = original.normalized
    haystack = normalized(markdown_text(source))
    complete = normalized(quote)
    if re.search(r"(?<!\w)" + re.escape(complete) + r"(?!\w)", haystack):
        parts = [quote]
        method = "complete-normalized-quote"
    else:
        parts = [p.strip() for p in OMISSIONS.split(quote) if normalized(p)]
        method = "ordered-normalized-ellipsis-segments"
    cursor = 0
    matches = []
    for part in parts:
        needle = normalized(part)
        found = re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack[cursor:])
        if found is None:
            raise ValueError("quote words absent from independently fetched source")
        start, end = cursor + found.start(), cursor + found.end()
        matches.append(
            {
                "quote_segment": part,
                "normalized_segment": needle,
                "normalized_source_start": start,
                "normalized_source_end": end,
            }
        )
        cursor = end
    if not matches:
        raise ValueError("empty source alignment")
    return matches, method


def extract_source(html: str, url: str) -> tuple[str, str, str]:
    """Remove reader contributions before extracting the original article body."""
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.select(
        ".webmentions, .u-comment, #comments, .comments, .comment-list, "
        ".comment-section, #disqus_thread, .utterances, .giscus, "
        "[class*='webmention'], .related-posts, .related-articles"
    ):
        junk.decompose()
    for anchor in soup.select("a[href]"):
        anchor["href"] = urljoin(url, str(anchor["href"]))
    return original.extract_source(str(soup), url)


class Fetcher(discovery.Fetcher):
    """Reuse existing exact-URL snapshots; bound concurrent new requests."""

    def __init__(self, client: httpx.AsyncClient, cache: Path):
        super().__init__(client, cache)
        self.network = asyncio.Semaphore(8)
        self.prior_caches = [
            Path.home() / ".cache/alex/quotebacks-discovery",
            Path.home() / ".cache/alex/quote-dataset",
        ]

    async def raw(self, url: str) -> dict[str, Any]:
        key = sha(url) + ".json"
        for cache in [self.cache, *self.prior_caches]:
            path = cache / key
            if path.exists():
                self.cache_hits += 1
                result = json.loads(path.read_text())
                if "html" in result:
                    result["text"] = result.pop("html")
                return result
        async with self.network:
            return await super().raw(url)


def candidate_quotes(
    html: str, page_url: str, publisher: dict[str, Any], fetched_at: str
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for block in soup.select(
        "blockquote.quoteback, quoteback-component, blockquote[data-author][cite]"
    ):
        if block.find_parent(["pre", "code", "textarea", "script", "template"]):
            continue
        source = block.get("cite") or block.get("data-url") or block.get("url")
        if not source:
            footer = block.find("footer")
            anchor = footer.find("a", href=True) if footer else None
            source = anchor.get("href") if anchor else None
        if not source:
            continue
        source = urljoin(page_url, str(source))
        if not source.startswith(("http://", "https://")):
            continue
        clean = BeautifulSoup(str(block), "html.parser")
        for tag in clean.select("footer, script, style"):
            tag.decompose()
        quote = clean.get_text(" ", strip=True)
        count = len(original.normalized(quote).split())
        if not 30 <= count <= 500:
            continue
        identity = sha(url_key(source) + "\n" + original.normalized(quote))
        result.append(
            {
                "id": "qb-"
                + publisher["domain"].replace(".", "-")
                + "-"
                + identity[:12],
                "publisher_domain": publisher["domain"],
                "publisher_name": publisher["publisher_name"],
                "post_url": page_url,
                "post_fetched_at": fetched_at,
                "publisher_html_sha256": sha(html),
                "source_url": source,
                "attribution": unquote(str(block.get("data-author") or "")),
                "cited_source_title": unquote(str(block.get("data-title") or "")),
                "reference_quote": quote,
                "reference_quote_markdown": markdownify(
                    clean.decode_contents(), heading_style="ATX", bullets="-"
                ).strip(),
                "reference_quote_sha256": sha(quote),
                "quote_word_count": count,
                "context": "",
                "tags": [],
            }
        )
    return result


def queue_score(url: str) -> int:
    path = urlsplit(url).path.lower()
    score = 15 if re.search(r"/20\d\d/", path) else 0
    score += 12 * any(x in path for x in ("week", "notes", "reading", "links"))
    score += 30 * ("quoteback" in path)
    score -= 30 * any(x in path for x in ("about", "contact", "privacy", "login"))
    return score


async def crawl_publisher(
    publisher: dict[str, Any], state: dict[str, Any], limit: int, fetcher: Fetcher
) -> list[dict[str, Any]]:
    found = []
    while state["queue"] and len(state["seen"]) < limit:
        url = state["queue"].pop(0)
        if url in state["seen"]:
            continue
        state["seen"].add(url)
        acquisition_url = "https:" + url[5:] if url.startswith("http:") else url
        response = await fetcher.get(acquisition_url)
        state["checked"].append(
            {
                k: response[k]
                for k in ("url", "resolved_url", "status", "error")
                if k in response
            }
        )
        if response["status"] != 200:
            continue
        page = response["resolved_url"]
        if discovery.host(page) != publisher["domain"]:
            continue
        if "html" not in response.get("content_type", ""):
            continue
        html = response["text"]
        found.extend(candidate_quotes(html, page, publisher, response["fetched_at"]))
        soup = BeautifulSoup(html, "html.parser")
        fresh = discovery.internal_links(soup, page)
        if not state["mapped"]:
            state["mapped"] = True
            origin = publisher["site_url"].rstrip("/")
            maps = [origin + "/sitemap.xml"]
            for _ in range(5):
                if not maps:
                    break
                sitemap = await fetcher.get(maps.pop(0))
                if sitemap["status"] != 200:
                    continue
                for link in discovery.xml_links(sitemap["text"]):
                    if discovery.host(link) != publisher["domain"]:
                        continue
                    if urlsplit(link).path.endswith(".xml"):
                        maps.append(link)
                    else:
                        fresh.append(link)
            feeds = [
                urljoin(page, str(x["href"]))
                for x in soup.select('link[rel="alternate"][type*="xml"][href]')
            ]
            for feed in feeds[:2]:
                response = await fetcher.get(feed)
                if response["status"] == 200:
                    fresh.extend(discovery.xml_links(response["text"]))
        fresh = [
            u
            for u in dict.fromkeys(fresh)
            if discovery.host(u) == publisher["domain"]
            and u not in state["seen"]
            and u not in state["queue"]
            and not urlsplit(u).query
            and not re.search(r"\.(?:xml|mp3|pdf|png|jpg|zip)$", u, re.I)
        ]
        fresh.sort(key=lambda u: (-queue_score(u), sha(u)))
        state["queue"].extend(fresh[:500])
    return found


async def collect_source(
    candidates: list[dict[str, Any]], fetcher: Fetcher, old_urls: set[str]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    failures = []
    first = candidates[0]
    try:
        url = first["source_url"]
        if discovery.host(url) in SOCIAL:
            raise ValueError("social/video/timeline source excluded")
        if discovery.host(url).startswith("forum."):
            raise ValueError("forum thread without an individual source item excluded")
        if url_key(url) in old_urls:
            raise ValueError("source already appears in the Simon dataset")
        acquisition_url = "https:" + url[5:] if url.startswith("http:") else url
        response = await fetcher.get(acquisition_url)
        if response["status"] != 200:
            raise ValueError(f"HTTP {response['status']}: {response.get('error', '')}")
        if "html" not in response.get("content_type", ""):
            raise ValueError("unsupported source content type")
        if len(response["text"]) >= 2_999_000:
            raise ValueError("response exceeds complete-snapshot limit")
        if url_key(response["resolved_url"]) in old_urls:
            raise ValueError("resolved source already appears in the Simon dataset")
        title, source, extraction = extract_source(
            response["text"], response["resolved_url"]
        )
        source_count = len(original.normalized(markdown_text(source)).split())
        if not 150 <= source_count <= 15000:
            raise ValueError(f"source length outside 150-15000 words: {source_count}")
        for candidate in candidates:
            try:
                if source_count < candidate["quote_word_count"] + 80:
                    raise ValueError("source has fewer than 80 words beyond the quote")
                segments, method = align(candidate["reference_quote"], source)
                if original.normalized(
                    markdown_text(candidate["reference_quote_markdown"])
                ) != original.normalized(candidate["reference_quote"]):
                    raise ValueError("quote Markdown changes published word boundaries")
                record = {
                    "schema_version": 1,
                    **candidate,
                    "resolved_source_url": response["resolved_url"],
                    "acquisition_url": acquisition_url,
                    "source_title": title,
                    "source_fetched_at": response["fetched_at"],
                    "source_html_sha256": sha(response["text"]),
                    "extraction_method": extraction,
                    "source_markdown": source,
                    "source_sha256": sha(source),
                    "source_word_count": source_count,
                    "same_publisher_source": (
                        discovery.host(response["resolved_url"])
                        == candidate["publisher_domain"]
                        or discovery.host(response["resolved_url"]).endswith(
                            "." + candidate["publisher_domain"]
                        )
                    ),
                    "source_markdown_path": f"cases/{candidate['id']}/source.md",
                    "quote_markdown_path": f"cases/{candidate['id']}/quote.md",
                    "validation": {
                        "status": "verified",
                        "method": method,
                        "editorial_markers": OMISSIONS.findall(
                            candidate["reference_quote"]
                        ),
                        "segments": segments,
                    },
                }
                return record, failures
            except ValueError as error:
                failures.append({**candidate, "reason": str(error)})
        return None, failures
    except (ValueError, httpx.HTTPError) as error:
        return None, [{**candidate, "reason": str(error)} for candidate in candidates]


def save_dataset(
    output: Path,
    accepted: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    stats: dict[str, Any],
    old: list[dict[str, Any]],
) -> None:
    ordered = sorted(accepted, key=lambda r: (r["publisher_domain"], r["id"]))
    by_publisher: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in ordered:
        by_publisher[record["publisher_domain"]].append(record)
    dev_ids = set()
    for group in by_publisher.values():
        ranked = sorted(group, key=lambda r: sha(r["id"]))
        count = max(1, round(len(group) * 0.2)) if len(group) >= 3 else 0
        dev_ids.update(r["id"] for r in ranked[:count])
    for record in ordered:
        record["split"] = "dev" if record["id"] in dev_ids else "test"
        folder = output / "cases" / record["id"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "source.md").write_text(record["source_markdown"])
        (folder / "quote.md").write_text(
            record["reference_quote_markdown"]
            + f"\n\nSelected by {record['publisher_name']}.\n\n"
            + f"Source: {record['source_url']}\n\n"
            + f"Selection page: {record['post_url']}\n"
        )
    jsonl(output / "examples.jsonl", ordered)
    jsonl(output / "candidates.jsonl", candidates)
    jsonl(output / "rejected.jsonl", rejected)
    dump(
        output / "splits.json",
        {s: [r["id"] for r in ordered if r["split"] == s] for s in ("dev", "test")},
    )
    combined = []
    for record in old:
        copy = record.copy()
        for key in ("source_markdown_path", "quote_markdown_path"):
            copy[key] = os.path.relpath(PARENT / "simonwillison" / copy[key], output)
        combined.append(copy)
    combined.extend(ordered)
    jsonl(output / "combined_examples.jsonl", combined)
    stats.update(
        updated_at=datetime.now(UTC).isoformat(),
        accepted_count=len(ordered),
        combined_count=len(combined),
        candidate_count=len(candidates),
        rejected_pairing_count=len(rejected),
        publishers=dict(Counter(r["publisher_domain"] for r in ordered)),
        source_hosts=dict(
            Counter(discovery.host(r["resolved_source_url"]) for r in ordered)
        ),
        rejection_reasons=dict(Counter(r["reason"] for r in rejected)),
        publisher_pages_checked={
            domain: state["checked"] for domain, state in states.items()
        },
    )
    if ordered:
        stats["source_words"] = {
            "min": min(r["source_word_count"] for r in ordered),
            "median": median(r["source_word_count"] for r in ordered),
            "max": max(r["source_word_count"] for r in ordered),
        }
    dump(output / "crawl_report.json", stats)
    index = [
        "# Additional Quotebacks source / quote pairs",
        "",
        f"{len(ordered)} new cases; {len(combined)} cases when combined "
        "with the unchanged Simon dataset.",
        "",
        "| Publisher | Original source | Quote | Split |",
        "| --- | --- | --- | --- |",
    ]
    for record in ordered:
        title = record["source_title"].replace("|", "\\|").replace("\n", " ")
        index.append(
            f"| {record['publisher_name']} | "
            f"[{title}]({record['source_markdown_path']}) | "
            f"[Quote]({record['quote_markdown_path']}) | {record['split']} |"
        )
    (output / "INDEX.md").write_text("\n".join(index) + "\n")


def audit_saved(output: Path, cache: Path) -> None:
    """Re-extract saved inputs from their original snapshots, without requests."""
    report = json.loads((output / "crawl_report.json").read_text())
    accepted = []
    rejected = rows(output / "rejected.jsonl")
    caches = [
        cache,
        Path.home() / ".cache/alex/quotebacks-discovery",
        Path.home() / ".cache/alex/quote-dataset",
    ]
    for record in rows(output / "examples.jsonl"):
        try:
            snapshot = None
            for url in dict.fromkeys(
                [
                    record.get("acquisition_url", record["source_url"]),
                    record["source_url"],
                    record["resolved_source_url"],
                ]
            ):
                for folder in caches:
                    path = folder / (sha(url) + ".json")
                    if path.exists():
                        data = json.loads(path.read_text())
                        html = data.get("html", data.get("text", ""))
                        if sha(html) == record["source_html_sha256"]:
                            snapshot = html
                            break
                if snapshot is not None:
                    break
            if snapshot is None:
                raise ValueError("original independently fetched snapshot absent")
            title, source, extraction = extract_source(
                snapshot, record["resolved_source_url"]
            )
            count = len(original.normalized(markdown_text(source)).split())
            if not 150 <= count <= 15000 or count < record["quote_word_count"] + 80:
                raise ValueError("insufficient original body after removing comments")
            segments, method = align(record["reference_quote"], source)
            if original.normalized(
                markdown_text(record["reference_quote_markdown"])
            ) != original.normalized(record["reference_quote"]):
                raise ValueError("quote Markdown changes published word boundaries")
            record.update(
                source_title=title,
                source_markdown=source,
                source_sha256=sha(source),
                source_word_count=count,
                extraction_method=extraction,
            )
            record["validation"].update(segments=segments, method=method)
            accepted.append(record)
        except ValueError as error:
            rejected.append(
                {
                    **record,
                    "source_markdown": None,
                    "reason": "Snapshot audit: " + str(error),
                }
            )
    old = rows(PARENT / "simonwillison/examples.jsonl")
    states = {
        domain: {"checked": pages}
        for domain, pages in report["publisher_pages_checked"].items()
    }
    save_dataset(
        output,
        accepted,
        rows(output / "candidates.jsonl"),
        rejected,
        states,
        report,
        old,
    )
    selected = {r["id"] for r in accepted}
    for folder in (output / "cases").iterdir():
        if folder.name not in selected and {p.name for p in folder.iterdir()} == {
            "source.md",
            "quote.md",
        }:
            for path in folder.iterdir():
                path.unlink()
            folder.rmdir()
    print(f"Snapshot audit retained {len(accepted)} source-grounded cases.")
    validate(output)


def validate(output: Path) -> dict[str, Any]:
    examples = rows(output / "examples.jsonl")
    old = rows(PARENT / "simonwillison/examples.jsonl")
    combined = rows(output / "combined_examples.jsonl")
    assert len(combined) == len(old) + len(examples)
    for field in ("id", "source_sha256"):
        assert len({r[field] for r in combined}) == len(combined), field
    keys = [url_key(r["resolved_source_url"]) for r in combined]
    assert len(set(keys)) == len(keys), "duplicate source URL"
    for record in examples:
        source = (output / record["source_markdown_path"]).read_text()
        assert source == record["source_markdown"]
        assert sha(source) == record["source_sha256"]
        assert (
            align(record["reference_quote"], source)[0]
            == record["validation"]["segments"]
        )
        assert original.normalized(
            original.markdown_text(record["reference_quote_markdown"])
        ) == original.normalized(record["reference_quote"])
        assert (
            record["reference_quote_markdown"]
            in (output / record["quote_markdown_path"]).read_text()
        )
    splits = json.loads((output / "splits.json").read_text())
    assert not set(splits["dev"]) & set(splits["test"])
    for split in ("dev", "test"):
        assert splits[split] == [r["id"] for r in examples if r["split"] == split]
    fixture = (
        "# Fixture\n\nThe cost is 42 dollars. Apples taste sweet. "
        "Oranges smell fresh.\n"
    )
    align("The cost is 42 dollars.", fixture)
    align("The cost is 42 dollars. [...] Oranges smell fresh.", fixture)
    invalid_quotes = [
        "The cost is 43 dollars.",
        "Oranges smell fresh. Apples taste sweet.",
        "The cost is [approximately] 42 dollars.",
        "The cost is 42 unicorns.",
    ]
    for invalid_quote in invalid_quotes:
        try:
            align(invalid_quote, fixture)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid quote accepted: {invalid_quote}")
    # Keep every original case and its split byte-for-byte equivalent except paths.
    for original_row, combined_row in zip(old, combined[: len(old)], strict=True):
        for key in original_row:
            if key not in {"source_markdown_path", "quote_markdown_path"}:
                assert original_row[key] == combined_row[key]
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "new_cases": len(examples),
        "combined_cases": len(combined),
        "status": "passed",
        "checks": [
            "unique source documents and IDs, including the original 50 cases",
            "independently fetched source hashes and file/JSONL agreement",
            "all published quote words matched in source order; "
            "only explicit ellipses omit text",
            "reference Markdown agrees with the plain reference",
            "dev/test manifest agreement and no source leakage",
            "original 50 cases and splits preserved",
            "negative checks reject changed numbers, reordered passages, "
            "inserted bracketed words and fabricated wording",
        ],
    }
    dump(output / "validation_report.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return report


async def build(args: argparse.Namespace) -> None:
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    old = rows(PARENT / "simonwillison/examples.jsonl")
    old_urls = {
        url_key(r[k]) for r in old for k in ("source_url", "resolved_source_url")
    }
    source_hashes = {r["source_sha256"] for r in old}
    publishers = [r for r in rows(args.catalog) if r["catalog_group"] == "recommended"]
    states = {}
    for publisher in publishers:
        seed = [q["quote_page_url"] for q in publisher["examples"]]
        seed.extend(
            p["url"]
            for p in publisher["pages_checked"]
            if p["status"] == 200 and not p["url"].endswith(".xml")
        )
        seed.extend(publisher["discovery_urls"] + [publisher["site_url"]])
        states[publisher["domain"]] = {
            "queue": list(dict.fromkeys(seed)),
            "seen": set(),
            "checked": [],
            "mapped": False,
        }
    accepted = []
    rejected = []
    candidates = []
    seen_quotes = set()
    attempted = set()
    source_urls = set(old_urls)
    stats = {
        "started_at": datetime.now(UTC).isoformat(),
        "target": args.target,
        "max_pages_per_publisher": args.max_pages,
        "catalog": str(args.catalog),
        "selection": (
            "One human-selected quote per distinct original source; "
            "sources overlapping the original corpus excluded."
        ),
        "matching": (
            "All quote words must occur in source order. Case, whitespace, "
            "punctuation and Unicode typography are normalized. "
            "Only explicit ellipses allow omitted intervening text."
        ),
    }
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers={"User-Agent": discovery.AGENT}
    ) as client:
        fetcher = Fetcher(client, args.cache)
        for limit in sorted(
            {min(n, args.max_pages) for n in (8, 20, 40, 80, args.max_pages)}
        ):
            results = await asyncio.gather(
                *(
                    crawl_publisher(p, states[p["domain"]], limit, fetcher)
                    for p in publishers
                ),
                return_exceptions=True,
            )
            for publisher, result in zip(publishers, results, strict=True):
                if isinstance(result, BaseException):
                    print(
                        "Publisher error",
                        publisher["domain"],
                        type(result).__name__,
                        flush=True,
                    )
                    continue
                for candidate in result:
                    key = (
                        url_key(candidate["source_url"]),
                        candidate["reference_quote_sha256"],
                    )
                    if key not in seen_quotes:
                        seen_quotes.add(key)
                        candidates.append(candidate)
            groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for candidate in candidates:
                key = url_key(candidate["source_url"])
                if key not in attempted and key not in source_urls:
                    groups[key].append(candidate)
            # Interleave publishers so a large library does not crowd out others.
            per_publisher: dict[str, list[list[dict[str, Any]]]] = defaultdict(list)
            for key, group in sorted(groups.items(), key=lambda item: sha(item[0])):
                attempted.add(key)
                per_publisher[group[0]["publisher_domain"]].append(group)
            queue = []
            while any(per_publisher.values()):
                for domain in per_publisher:
                    if per_publisher[domain]:
                        queue.append(per_publisher[domain].pop(0))
            print(
                f"Publisher depth {limit}: {len(candidates)} quote candidates, "
                f"{len(queue)} new source documents to check",
                flush=True,
            )
            for start in range(0, len(queue), 8):
                results = await asyncio.gather(
                    *(
                        collect_source(group, fetcher, old_urls)
                        for group in queue[start : start + 8]
                    )
                )
                for record, failures in results:
                    rejected.extend(failures)
                    if record:
                        if (
                            record["source_sha256"] in source_hashes
                            or url_key(record["resolved_source_url"]) in source_urls
                        ):
                            rejected.append(
                                {
                                    **record,
                                    "source_markdown": None,
                                    "reason": (
                                        "duplicate source document or resolved URL"
                                    ),
                                }
                            )
                            continue
                        source_hashes.add(record["source_sha256"])
                        source_urls.add(url_key(record["resolved_source_url"]))
                        accepted.append(record)
                        print(
                            f"Accepted {len(accepted)}: "
                            f"{record['publisher_domain']} - "
                            f"{record['source_title'][:70]}",
                            flush=True,
                        )
                stats.update(
                    network_requests=fetcher.requests, cache_hits=fetcher.cache_hits
                )
                save_dataset(output, accepted, candidates, rejected, states, stats, old)
                if len(accepted) >= args.target:
                    break
            if len(accepted) >= args.target:
                break
        save_dataset(output, accepted, candidates, rejected, states, stats, old)
    validate(output)
    if len(accepted) < args.target:
        print(
            f"Bounded crawl reached {len(accepted)} / {args.target} cases; "
            "see rejections for inaccessible or unmatched sources.",
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=120)
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument(
        "--catalog", type=Path, default=PARENT / "quotebacks/potential_sources.jsonl"
    )
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache/alex/quotebacks-dataset"
    )
    parser.add_argument("--output", type=Path, default=ROOT)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--audit-saved", action="store_true")
    args = parser.parse_args()
    if args.target < 1 or args.max_pages < 1:
        parser.error("target and max-pages must be positive")
    if args.audit_saved:
        audit_saved(args.output, args.cache)
    elif args.validate_only:
        validate(args.output)
    else:
        asyncio.run(build(args))
