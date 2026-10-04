"""Apply explicit review annotations to the bounded Quotebacks discovery crawl."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).parent


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def link(label: str, url: str) -> str:
    return f"[{cell(label)}](<{url}>)"


def example_links(record: dict[str, Any]) -> str:
    examples = record.get("examples", [])
    if not examples:
        return link("Evidence / lead", record["review_evidence_url"])
    quote = examples[0]
    # Prefer the individual post when an archive repeats the same embed.
    pages = quote.get("observed_on_pages", [quote["quote_page_url"]])

    def archive_score(url: str) -> tuple[bool, int, int]:
        path = urlsplit(url).path
        archive = (
            path == "/"
            or bool(re.fullmatch(r"/\d{4}(?:/\d{1,2})?/?", path))
            or any(part in url for part in ("/category/", "/page2/", "?query="))
        )
        return archive, -path.count("/"), len(url)

    page = min(pages, key=archive_score)
    return (
        link("Example page", page)
        + " · "
        + link("Cited source", quote["source_url"])
        + f" ({quote['quote_word_count']} words)"
    )


def table(records: list[dict[str, Any]], confirmed: bool) -> list[str]:
    count_label = "Unique embeds observed" if confirmed else "Crawl status"
    lines = [
        f"| Website | Topics | {count_label} | Evidence | Review notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        count = str(record["embed_count_observed"]) if confirmed else record["status"]
        name = link(record["publisher_name"], record["site_url"])
        name += f" — {record['review_priority']} priority"
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    cell(record["topics"]),
                    count,
                    example_links(record),
                    cell(record["review_note"]),
                ]
            )
            + " |"
        )
    return lines


def main() -> None:
    reviewed = json.loads((ROOT / "review_annotations.json").read_text())
    report = json.loads((ROOT / "crawl_report.json").read_text())
    base = read_jsonl(ROOT / "all_checked_sites.jsonl")
    supplemental = read_jsonl(ROOT / "redirect_target_probes.jsonl")
    records = {row["domain"]: row for row in base + supplemental}
    selected = []
    for domain, annotation in reviewed["confirmed"].items():
        row = records[domain].copy()
        assert row["status"] == "confirmed_embeds", domain
        name, group, priority, topics, note = annotation
        row.update(
            publisher_name=name,
            catalog_group=group,
            heuristic_priority=row["priority"],
            priority=priority,
            review_priority=priority,
            topics=topics,
            review_note=note,
            quality_note=note,
            verified_quotebacks_embed=True,
        )
        selected.append(row)
    for domain, annotation in reviewed["unverified"].items():
        row = records[domain].copy()
        assert row["status"] != "confirmed_embeds", domain
        name, priority, topics, note, evidence = annotation
        row.update(
            publisher_name=name,
            catalog_group="unverified",
            heuristic_priority=row["priority"],
            priority=priority,
            review_priority=priority,
            topics=topics,
            review_note=note,
            quality_note=note,
            review_evidence_url=evidence,
            verified_quotebacks_embed=False,
        )
        selected.append(row)
    groups = {
        group: [r for r in selected if r["catalog_group"] == group]
        for group in ("recommended", "limited", "unverified")
    }
    assert len({r["domain"] for r in selected}) == len(selected)
    assert not set(reviewed["excluded"]) & {r["domain"] for r in selected}
    for record in selected:
        for quote in record.get("examples", []):
            assert quote["quote_sha256"]
            domain = (urlsplit(quote["quote_page_url"]).hostname or "").removeprefix(
                "www."
            )
            assert domain == record["domain"], (domain, record["domain"])
    (ROOT / "potential_sources.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected)
    )
    summary = {
        "crawl_completed_at": report["completed_at"],
        "base_sites_checked": len(base),
        "supplemental_sites_checked": len(supplemental),
        "distinct_sites_checked": len(records),
        "raw_status_counts": dict(Counter(r["status"] for r in records.values())),
        "catalog_counts": {k: len(v) for k, v in groups.items()},
        "confirmed_independent_publishers": sum(
            r["verified_quotebacks_embed"] for r in selected
        ),
        "observed_unique_embeds_on_confirmed_publishers": sum(
            r["embed_count_observed"]
            for r in selected
            if r["verified_quotebacks_embed"]
        ),
        "excluded": reviewed["excluded"],
        "aliases": reviewed["aliases"],
    }
    (ROOT / "catalog_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    confirmed = summary["confirmed_independent_publishers"]
    recommended = len(groups["recommended"])
    limited = len(groups["limited"])
    unverified = len(groups["unverified"])
    lines = [
        "# Potential Quotebacks sources for quote-extraction evaluation",
        "",
        "Discovered and checked on **2026-10-04 (UTC)**.",
        "",
        f"Checked **{len(records)} distinct websites**: {len(base)} in the main "
        f"crawl and {len(supplemental)} redirect targets separately. Found "
        f"**{confirmed} independent publishers with genuine Quotebacks embeds**: "
        f"{recommended} promising sources for further sampling and {limited} "
        f"with limited evidence, demos, or same-author citations. Also retained "
        f"**{unverified} explicitly unverified leads**. These leads are not "
        "counted as Quotebacks users.",
        "",
        "Start with **Tom Critchlow, Jay Springett, Matt Webb, Toby Shorin, "
        "Aaron Z. Lewis, and Brendan Langen**. Priorities are editorial "
        "triage based on sampled excerpts and attribution, not a measured "
        "quality score. An embed on an older post confirms historical use; "
        "it does not establish current or regular use.",
        "",
        "## Promising sources",
        "",
        "Each count is a lower bound on distinct selections observed during "
        "this bounded crawl, not a whole-site inventory. An example's word "
        "count describes its rendered excerpt. Multiple excerpts from one "
        "source can be valid independent selections.",
        "",
        *table(groups["recommended"], True),
        "",
        "## Confirmed embeds with limited evaluation value or evidence",
        "",
        "These sites do use the embed format, but the sampled evidence "
        "does not establish an extensive independent quote collection.",
        "",
        *table(groups["limited"], True),
        "",
        "## Unverified leads",
        "",
        "Mentions, integration articles, and search-indexed pages help "
        "discovery, but do not prove published use. The status is the result "
        "of this crawl only; unavailable or blocked pages were not bypassed.",
        "",
        *table(groups["unverified"], False),
        "",
        "## Original examples and exclusions",
        "",
        "From the supplied examples, **Interconnected and Tom Critchlow** "
        "have confirmed embeds. No embed was observed in the sampled pages "
        "of Douglas Creager, Daring Fireball, Austin Kleon, or The Marginalian. "
        "Alan Jacobs's site was unavailable or blocked to this crawl. These "
        "may still be useful quote-curation sources; their Quotebacks use "
        "has not been established here.",
        "",
        "- **sepiabrown.github.io** is excluded as an independent curator: "
        "the sampled LinkedIn Learning post shares 45 of 46 paragraphs "
        "longer than 80 characters with Tom Critchlow's corresponding post. "
        "See the two "
        "URLs and comparison counts in `review_annotations.json`.",
        "- **amyhuang.work** redirects to **mirhuang.com**, which was "
        "checked separately and has confirmed excerpts. It is counted once.",
        "- **bix.blog** redirects to **slow.dog**. No embed was observed "
        "in the separately checked target; the old site remains a lead.",
        "- Tool documentation, platforms, copied code snippets, and unrelated "
        "insurance products also named QuoteBack are excluded from the "
        "publisher catalog.",
        "",
        "## Discovery and verification",
        "",
        "Discovery used the [official Quotebacks users list]"
        "(https://quotebacks.net/) and [OPML blogroll]"
        "(https://quotebacks.net/quotebacks-blogroll.opml), targeted web "
        "searches, public GitHub issue participants' websites, public "
        "Micro.blog discovery, and original-source links from confirmed "
        "embeds. Sitemap and feed URLs supplied additional post candidates.",
        "",
        "The crawler checks robots rules, pauses between uncached requests "
        "per host, and caches responses. It checks at most 18 queued page "
        "candidates per directly discovered site, or 8 for weak network "
        "leads; it may stop early once several substantive external excerpts "
        "are found. Sitemap/feed/robots requests are additional. Script-only "
        "and text-mention evidence are recorded separately.",
        "",
        "Confirmation requires rendered `blockquote.quoteback`, "
        "`quoteback-component`, or compatible attributed `blockquote` markup "
        "with a source URL. Detection excludes code samples. Quotes repeated "
        "on posts and archives are deduplicated by defragmented source URL "
        "plus rendered-text SHA-256. Redirected pages are attributed to "
        "their actual publisher, not the old host.",
        "",
        "**Before adding any pair to the evaluation**, fetch its original "
        "source as Markdown, verify the quote against that text, and review "
        "its context, completeness, attribution, and accessibility. This "
        "catalog records source links and short previews; it is not yet a "
        "source-grounded evaluation dataset. No LLM judge was used to "
        "assign the priorities.",
        "",
        "## Local artifacts and reproduction",
        "",
        "- [potential_sources.jsonl](potential_sources.jsonl): the curated "
        "catalog, with verification flags, groups, priorities, examples, "
        "source URLs, quote hashes, and crawl evidence.",
        "- [all_checked_sites.jsonl](all_checked_sites.jsonl): all main-crawl "
        "results, including unsuccessful probes.",
        "- [redirect_target_probes.jsonl](redirect_target_probes.jsonl): "
        "the two separately checked redirect targets.",
        "- [catalog_report.json](catalog_report.json) and "
        "[crawl_report.json](crawl_report.json): counts and crawl settings.",
        "- [verification_report.json](verification_report.json): all 77 "
        "saved example/source/hash pairs matched the cached publisher HTML.",
        "- [review_annotations.json](review_annotations.json): explicit "
        "editorial notes, inclusion decisions, aliases, and exclusions.",
        "- [discovery_seeds.json](discovery_seeds.json): search queries, "
        "results, and seed URLs; GitHub lead files preserve additional "
        "discovery provenance.",
        "",
        "From the repository root:",
        "",
        "```bash",
        "uv run --script evals/quote_extraction/quotebacks/discover_sources.py "
        "--max-sites 220 --max-pages 18 --workers 12",
        "uv run python evals/quote_extraction/quotebacks/build_catalog.py",
        "```",
        "",
        "Rerunning discovery overwrites its generated files; running "
        "`build_catalog.py` reapplies the saved annotations to regenerate "
        "the curated catalog. Supplemental probes are stored separately. "
        "Cached HTTP responses live in "
        "`~/.cache/alex/quotebacks-discovery/`; remove that task-specific "
        "cache only when a fresh network crawl is desired. Site content "
        "and availability can change.",
    ]
    (ROOT / "potential_sources.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
