# /// script
# requires-python = ">=3.12"
# dependencies = ["beautifulsoup4==4.14.3", "httpx==0.28.1"]
# ///
"""Bounded discovery of Quotebacks publishers, not a new evaluation corpus."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

AGENT = "AlexQuotebacksDiscovery/1.0"
SOCIAL = {
    "x.com",
    "twitter.com",
    "youtube.com",
    "youtu.be",
    "mastodon.social",
    "bsky.app",
}
SKIP = {
    "cdn.jsdelivr.net",
    "unpkg.com",
    "raw.githubusercontent.com",
    "user-images.githubusercontent.com",
    "chrome.google.com",
    "schema.org",
    "w3.org",
    "gatsbyjs.com",
    "quotebacks.net",
    "github.com",
    "gist.github.com",
    "chromewebstore.google.com",
    "books.google.com",
    "getquoteback.com",
    "quoteback.app",
    "quote-back.com",
    "examone.com",
    "epic.org",
    "archive.epic.org",
    "pdf4pro.com",
    "uspto.gov",
    "training.citizensfla.com",
    "flatfeecorp.com",
    "mib.org.uk",
    "en.touchelivros.com.br",
    "help.micro.blog",
    "book.micro.blog",
    "api.hypothes.is",
    "anagora.org",
    "superpath.co",
    "unboundsummits.com",
    "thelitforum.com",
    "links.l3m.in",
}
PLATFORMS = (
    SKIP
    | SOCIAL
    | {
        "wikipedia.org",
        "en.wikipedia.org",
        "amazon.com",
        "amzn.to",
        "nytimes.com",
        "theguardian.com",
        "bbc.com",
        "bbc.co.uk",
        "linkedin.com",
        "facebook.com",
        "reddit.com",
        "news.ycombinator.com",
        "medium.com",
        "arxiv.org",
        "doi.org",
        "google.com",
        "support.mozilla.org",
        "indieweb.org",
        "scalingsynthesis.com",
    }
)


def host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").removeprefix("www.").lower()
    except ValueError:
        return ""


def url_clean(url: str) -> str:
    return urldefrag(url.strip())[0]


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text)


def dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


class Fetcher:
    def __init__(self, client: httpx.AsyncClient, cache: Path):
        self.client = client
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.locks: dict[str, asyncio.Lock] = {}
        self.robots: dict[str, RobotFileParser | None] = {}
        self.requests = 0
        self.cache_hits = 0

    async def raw(self, url: str) -> dict[str, Any]:
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / f"{key}.json"
        if path.exists():
            self.cache_hits += 1
            return json.loads(path.read_text())
        async with self.locks.setdefault(host(url), asyncio.Lock()):
            result: dict[str, Any] = {
                "url": url,
                "fetched_at": datetime.now(UTC).isoformat(),
            }
            try:
                response = await self.client.get(url)
                self.requests += 1
                result.update(
                    status=response.status_code,
                    resolved_url=str(response.url),
                    content_type=response.headers.get("content-type", ""),
                    text=response.text[:3_000_000],
                )
            except (httpx.HTTPError, httpx.InvalidURL) as error:
                result.update(
                    status=0, resolved_url=url, text="", error=type(error).__name__
                )
            dump(path, result)
            await asyncio.sleep(0.25)
            return result

    async def get(self, url: str) -> dict[str, Any]:
        origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
        if origin not in self.robots:
            result = await self.raw(origin + "/robots.txt")
            parser = RobotFileParser()
            if result["status"] == 200 and "user-agent" in result["text"].lower():
                parser.parse(result["text"].splitlines())
                self.robots[origin] = parser
            elif result["status"] in {401, 403}:
                parser.disallow_all = True
                self.robots[origin] = parser
            else:
                self.robots[origin] = None
        parser = self.robots[origin]
        if parser is not None and not parser.can_fetch(AGENT, url):
            return {
                "url": url,
                "resolved_url": url,
                "status": 0,
                "text": "",
                "error": "robots_disallowed",
            }
        return await self.raw(url)


def extract_quotes(soup: BeautifulSoup, page_url: str) -> list[dict[str, Any]]:
    quotes = []
    seen = set()
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
        text = clean.get_text(" ", strip=True)
        identity = (source, text)
        if not text or identity in seen:
            continue
        seen.add(identity)
        quotes.append(
            {
                "quote_page_url": page_url,
                "source_url": source,
                "source_title": str(
                    block.get("data-title") or block.get("title") or ""
                ),
                "source_author": str(
                    block.get("data-author") or block.get("author") or ""
                ),
                "quote_word_count": len(words(text)),
                "quote_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "quote_preview": " ".join(text.split()[:12])
                + (" …" if len(text.split()) > 12 else ""),
                "external_source": host(source) != host(page_url),
                "source_kind": "social_or_video"
                if host(source) in SOCIAL
                else "web_text",
                "embed_marker": "quoteback-component"
                if block.name == "quoteback-component"
                else "blockquote.quoteback"
                if "quoteback" in block.get("class", [])
                else "blockquote[data-author][cite]",
            }
        )
    return quotes


def deduplicate_quotes(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for quote in examples:
        key = (url_clean(quote["source_url"]), quote["quote_sha256"])
        if key not in unique:
            unique[key] = {**quote, "observed_on_pages": []}
        if quote["quote_page_url"] not in unique[key]["observed_on_pages"]:
            unique[key]["observed_on_pages"].append(quote["quote_page_url"])
    return list(unique.values())


def page_score(url: str) -> int:
    value = url.lower()
    score = 0
    if "quoteback" in value:
        score += 100
    if any(
        word in value
        for word in (
            "quote",
            "conversation",
            "reply",
            "notes",
            "link",
            "week",
            "reading",
            "blogroll",
        )
    ):
        score += 20
    if re.search(r"/20\d\d/", value):
        score += 5
    if any(
        word in value
        for word in (
            "about",
            "privacy",
            "contact",
            "login",
            "subscribe",
            "tag/",
            "category/",
            "search",
        )
    ):
        score -= 20
    return score


def internal_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    links = []
    for a in soup.find_all("a", href=True):
        url = url_clean(urljoin(page_url, str(a["href"])))
        if (
            host(url) == host(page_url)
            and url.startswith(("http://", "https://"))
            and not re.search(r"\.(?:jpg|png|svg|pdf|zip|css|js|mp3|xml)$", url, re.I)
        ):
            links.append(url)
    return list(dict.fromkeys(links))


def xml_links(text: str) -> list[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    links = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "loc" and node.text:
            links.append(node.text.strip())
        elif tag == "link":
            value = node.get("href") or (node.text or "").strip()
            if value.startswith(("http://", "https://")):
                links.append(value)
    return list(dict.fromkeys(links))


async def probe_site(
    site: dict[str, Any], fetcher: Fetcher, max_pages: int
) -> dict[str, Any]:
    domain = site["domain"]
    pages = list(dict.fromkeys(site["urls"] + [site["site_url"]]))
    seen = set()
    checked = []
    examples = []
    mentions = []
    scripts = []
    redirects = []
    canonicals = []
    discovered = []
    title = ""
    maps_done = False
    for _iteration in range(max_pages):
        if not pages:
            break
        url = pages.pop(0)
        if url in seen:
            continue
        seen.add(url)
        result = await fetcher.get(url)
        checked.append(
            {
                k: result[k]
                for k in ("url", "resolved_url", "status", "error", "fetched_at")
                if k in result
            }
        )
        if result["status"] != 200:
            continue
        page_url = result["resolved_url"]
        if host(page_url) != domain:
            redirects.append({"requested_url": url, "resolved_url": page_url})
            continue
        if (
            result.get("content_type", "").startswith(("application/", "image/"))
            or "xml" in result.get("content_type", "")
            or result["text"].lstrip().startswith("<?xml")
        ):
            continue
        soup = BeautifulSoup(result["text"], "html.parser")
        canonical = soup.select_one('link[rel="canonical"][href]')
        if canonical:
            canonical_url = urljoin(page_url, str(canonical["href"]))
            if host(canonical_url) != domain:
                canonicals.append(canonical_url)
        if not title and soup.title:
            title = soup.title.get_text(" ", strip=True)
        page_quotes = extract_quotes(soup, page_url)
        examples.extend(page_quotes)
        for quote in page_quotes:
            if quote["external_source"] and quote["quote_word_count"] >= 25:
                source = quote["source_url"]
                if host(source) not in PLATFORMS:
                    discovered.append(source)
        for script in soup.find_all("script", src=True):
            src = urljoin(page_url, str(script["src"]))
            if re.search(r"quotebacks?[^/]*\.js", src, re.I):
                scripts.append({"page_url": page_url, "script_url": src})
        readable = soup.get_text(" ", strip=True)
        if re.search(r"\bquotebacks?\b", readable, re.I):
            mentions.append(page_url)
        good = [
            q
            for q in deduplicate_quotes(examples)
            if q["external_source"]
            and q["source_kind"] == "web_text"
            and 30 <= q["quote_word_count"] <= 500
        ]
        ordinary = [
            q
            for q in good
            if "quoteback" not in urlsplit(q["quote_page_url"]).path.lower()
        ]
        if len({q["source_url"] for q in ordinary}) >= 2 and len(good) >= 3:
            break
        fresh = [
            link
            for link in internal_links(soup, page_url)
            if link not in seen and link not in pages
        ]
        fresh.sort(key=page_score, reverse=True)
        pages.extend(fresh[:30])
        if not maps_done:
            maps_done = True
            origin = site["site_url"].rstrip("/")
            sitemap = await fetcher.get(origin + "/sitemap.xml")
            checked.append(
                {
                    k: sitemap[k]
                    for k in ("url", "resolved_url", "status", "error")
                    if k in sitemap
                }
            )
            mapped = xml_links(sitemap["text"]) if sitemap["status"] == 200 else []
            child_maps = [
                x
                for x in mapped
                if urlsplit(x).path.endswith(".xml") and host(x) == domain
            ]
            for child in child_maps[:2]:
                response = await fetcher.get(child)
                if response["status"] == 200:
                    mapped.extend(xml_links(response["text"]))
            mapped = [
                x
                for x in mapped
                if host(x) == domain and not urlsplit(x).path.endswith(".xml")
            ]
            feeds = [
                urljoin(page_url, str(x.get("href")))
                for x in soup.select('link[rel="alternate"][type*="xml"][href]')
            ]
            if not feeds:
                feeds = [origin + "/feed/", origin + "/feed.xml"]
            for feed in feeds[:2]:
                response = await fetcher.get(feed)
                if response["status"] == 200:
                    mapped.extend(xml_links(response["text"]))
            mapped = list(
                dict.fromkeys(x for x in mapped if host(x) == domain and x not in seen)
            )
            mapped.sort(key=page_score, reverse=True)
            pages = list(
                dict.fromkeys(
                    pages[: len(site["urls"])]
                    + mapped[:40]
                    + pages[len(site["urls"]) :]
                )
            )
    unique = deduplicate_quotes(examples)
    good = [
        q
        for q in unique
        if q["external_source"]
        and q["source_kind"] == "web_text"
        and 30 <= q["quote_word_count"] <= 500
    ]
    ordinary = [
        q for q in good if "quoteback" not in urlsplit(q["quote_page_url"]).path.lower()
    ]
    if unique:
        status = "confirmed_embeds"
    elif scripts:
        status = "script_only"
    elif mentions:
        status = "mention_only"
    elif redirects:
        status = "redirected_elsewhere"
    elif not any(p["status"] == 200 for p in checked):
        status = "unreachable_or_blocked"
    else:
        status = "no_embed_observed"
    priority = (
        "high"
        if len(good) >= 3 and len({q["source_url"] for q in ordinary}) >= 2
        else "medium"
        if good
        else "low"
    )
    return {
        "domain": domain,
        "site_url": site["site_url"],
        "site_title": title or domain,
        "status": status,
        "priority": priority,
        "discovered_via": site["discovered_via"],
        "discovery_urls": site["urls"],
        "checked_at": datetime.now(UTC).isoformat(),
        "pages_checked": checked,
        "embed_count_observed": len(unique),
        "external_text_quotes_30_plus": len(good),
        "quote_post_count_observed": len({q["quote_page_url"] for q in unique}),
        "original_source_domains": sorted({host(q["source_url"]) for q in good}),
        "examples": sorted(
            unique,
            key=lambda q: (q not in good, q not in ordinary, -q["quote_word_count"]),
        )[:5],
        "script_evidence": list({s["script_url"]: s for s in scripts}.values()),
        "redirects_to_other_sites": redirects,
        "external_canonical_urls": list(dict.fromkeys(canonicals)),
        "mention_pages": list(dict.fromkeys(mentions))[:5],
        "new_leads": list(dict.fromkeys(discovered))[:8],
        "quality_note": (
            "Heuristic priority based on substantial, externally attributed text "
            "excerpts and distinct source URLs; source pages and editorial quality "
            "require review before dataset inclusion."
        ),
    }


def save(output: Path, records: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    records = sorted(
        records,
        key=lambda r: ({"high": 0, "medium": 1, "low": 2}[r["priority"]], r["domain"]),
    )
    for filename, selected in [
        ("all_checked_sites.jsonl", records),
        (
            "potential_sources.jsonl",
            [r for r in records if r["status"] != "no_embed_observed"],
        ),
    ]:
        (output / filename).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected)
        )
    stats["sites_checked"] = len(records)
    stats["status_counts"] = dict(Counter(r["status"] for r in records))
    stats["priority_counts"] = dict(Counter(r["priority"] for r in records))
    dump(output / "crawl_report.json", stats)


async def main(args: argparse.Namespace) -> None:
    data = json.loads(args.seeds.read_text())
    sites: dict[str, dict[str, Any]] = {}

    def add(url: str, via: str) -> None:
        domain = host(url)
        if (
            not domain
            or domain in SKIP
            or domain in SOCIAL
            or re.search(r"\.(?:pdf|opml|svg|png|jpg|jpeg|gif|js|css|zip)$", url, re.I)
        ):
            return
        site = sites.setdefault(
            domain,
            {
                "domain": domain,
                "site_url": f"https://{urlsplit(url).netloc}/",
                "urls": [],
                "discovered_via": [],
            },
        )
        if url not in site["urls"]:
            site["urls"].append(url)
        if via not in site["discovered_via"]:
            site["discovered_via"].append(via)

    for url in data["seed_urls"]:
        add(url, "user_examples_or_project_blogroll")
    for batch in data["search_evidence"]:
        for entry in batch["results"]:
            add(entry["url"], "web_search:" + batch["batch"])
    records = []
    stats = {
        "started_at": datetime.now(UTC).isoformat(),
        "user_agent": AGENT,
        "max_sites": args.max_sites,
        "max_pages_per_site": args.max_pages,
        "robots_policy": (
            "Check robots rules; skip explicit disallows. Missing/unavailable "
            "rules are treated as unknown, not evidence of permission."
        ),
        "source_validation": (
            "Quote text is observed in publishers' HTML. Original source links "
            "are recorded; full original-source matching is deferred."
        ),
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15), follow_redirects=True, headers={"User-Agent": AGENT}
    ) as client:
        fetcher = Fetcher(client, args.cache)
        opml = await fetcher.get("https://quotebacks.net/quotebacks-blogroll.opml")
        if opml["status"] == 200:
            for node in ET.fromstring(opml["text"]).iter("outline"):
                if node.get("htmlUrl"):
                    add(node.get("htmlUrl", ""), "official_quotebacks_opml")
        # Public discovery exposes candidate publishers, not private timelines.
        disco = await fetcher.get("https://micro.blog/posts/discover")
        if disco["status"] == 200:
            try:
                for item in json.loads(disco["text"]).get("items", []):
                    if item.get("url"):
                        add(item["url"], "public_microblog_discovery")
            except (json.JSONDecodeError, AttributeError):
                pass
        done = set()
        while len(done) < min(args.max_sites, len(sites)):
            batch = [s for domain, s in sites.items() if domain not in done][
                : min(args.workers, args.max_sites - len(done))
            ]
            if not batch:
                break
            results = await asyncio.gather(
                *(
                    probe_site(
                        s,
                        fetcher,
                        args.max_pages
                        if any(
                            not via.startswith(
                                ("cited_by_quoteback:", "public_microblog")
                            )
                            for via in s["discovered_via"]
                        )
                        else min(args.max_pages, 8),
                    )
                    for s in batch
                ),
                return_exceptions=True,
            )
            for site, result in zip(batch, results, strict=True):
                done.add(site["domain"])
                if isinstance(result, BaseException):
                    print(site["domain"], type(result).__name__, flush=True)
                    records.append(
                        {
                            **site,
                            "site_title": site["domain"],
                            "status": "unreachable_or_blocked",
                            "priority": "low",
                            "error": str(result),
                            "examples": [],
                            "pages_checked": [],
                        }
                    )
                else:
                    records.append(result)
                    print(
                        site["domain"],
                        result["status"],
                        result["embed_count_observed"],
                        result["priority"],
                        flush=True,
                    )
                    for lead in result["new_leads"]:
                        if len(sites) < args.max_sites and host(lead) not in PLATFORMS:
                            add(lead, "cited_by_quoteback:" + result["domain"])
            stats.update(
                requests=fetcher.requests,
                cache_hits=fetcher.cache_hits,
                discovered_sites=len(sites),
                completed_at=datetime.now(UTC).isoformat(),
            )
            save(args.output, records, stats)
        stats["unvisited_sites"] = [
            s for domain, s in sites.items() if domain not in done
        ]
        save(args.output, records, stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    root = Path(__file__).parent
    parser.add_argument("--seeds", type=Path, default=root / "discovery_seeds.json")
    parser.add_argument("--output", type=Path, default=root)
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache/alex/quotebacks-discovery"
    )
    parser.add_argument("--max-sites", type=int, default=120)
    parser.add_argument("--max-pages", type=int, default=18)
    parser.add_argument("--workers", type=int, default=10)
    asyncio.run(main(parser.parse_args()))
