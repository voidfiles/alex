from __future__ import annotations

import argparse
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from alex.lib.asset_folders import DEFAULT_VAULT_ASSET_ROOT


DEFAULT_SAMPLE_FILE = Path("pdf_test/sample.txt")
DEFAULT_ASSET_ROOT = DEFAULT_VAULT_ASSET_ROOT
DEFAULT_OUTPUT_ROOT = Path("pdf_test")
DEFAULT_LIMIT = 10

type CommandRunner = Callable[[Sequence[str]], None]


@dataclass(frozen=True, slots=True)
class PdfMarkdownSampleResult:
    sample: str
    directory: Path
    default_markdown: Path
    miner_markdown: Path


def run_checked_command(command: Sequence[str]) -> None:
    subprocess.run(command, check=True)


def run_pdf_markdown_samples(
    *,
    sample_file: Path = DEFAULT_SAMPLE_FILE,
    asset_root: Path = DEFAULT_ASSET_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    alex_command: str = "alex",
    limit: int = DEFAULT_LIMIT,
    run_command: CommandRunner = run_checked_command,
) -> list[PdfMarkdownSampleResult]:
    results: list[PdfMarkdownSampleResult] = []

    for sample in read_samples(sample_file=sample_file, limit=limit):
        sample_dir = output_root / sample
        sample_dir.mkdir(parents=True, exist_ok=True)

        original_pdf = sample_dir / "o.pdf"
        original_markdown = sample_dir / "o.md"
        default_source = sample_dir / "alex-default.pdf"
        miner_source = sample_dir / "alex-miner.pdf"
        default_asset_root = sample_dir / "default-assets"
        miner_asset_root = sample_dir / "miner-assets"
        default_markdown = (
            default_asset_root / default_source.stem / f"{default_source.stem}.md"
        )
        miner_markdown = (
            miner_asset_root / miner_source.stem / f"{miner_source.stem}.md"
        )

        asset_dir = asset_root / sample
        shutil.copy2(asset_dir / f"{sample}.pdf", original_pdf)
        shutil.copy2(original_pdf, default_source)
        shutil.copy2(original_pdf, miner_source)
        shutil.copy2(asset_dir / f"{sample}.md", original_markdown)

        for command in (
            (
                alex_command,
                "to-asset",
                str(default_source),
                "--asset-root",
                str(default_asset_root),
            ),
            (
                alex_command,
                "to-asset",
                str(miner_source),
                "--miner",
                "--asset-root",
                str(miner_asset_root),
            ),
        ):
            run_command(command)

        results.append(
            PdfMarkdownSampleResult(
                sample=sample,
                directory=sample_dir,
                default_markdown=default_markdown,
                miner_markdown=miner_markdown,
            )
        )

    return results


def read_samples(*, sample_file: Path, limit: int) -> list[str]:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    samples: list[str] = []
    for line in sample_file.read_text(encoding="utf-8").splitlines():
        sample = line.strip()
        if sample == "":
            continue

        samples.append(sample)
        if len(samples) == limit:
            break

    return samples


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy PDF markdown test samples and run alex to-asset.",
    )
    parser.add_argument(
        "--sample-file",
        type=Path,
        default=DEFAULT_SAMPLE_FILE,
        help=f"File containing sample names, one per line. Defaults to {DEFAULT_SAMPLE_FILE}.",
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=DEFAULT_ASSET_ROOT,
        help=f"Root Obsidian asset directory. Defaults to {DEFAULT_ASSET_ROOT}.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Directory where sample test folders are written. Defaults to {DEFAULT_OUTPUT_ROOT}.",
    )
    parser.add_argument(
        "--alex",
        default="alex",
        help="Command used to invoke the alex CLI. Defaults to alex.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Maximum number of samples to process. Defaults to {DEFAULT_LIMIT}.",
    )
    args = parser.parse_args(argv)

    results = run_pdf_markdown_samples(
        sample_file=args.sample_file,
        asset_root=args.asset_root,
        output_root=args.output_root,
        alex_command=args.alex,
        limit=args.limit,
    )

    for result in results:
        print(f"Wrote {result.default_markdown} and {result.miner_markdown}")

    return 0
