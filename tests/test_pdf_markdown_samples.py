from collections.abc import Sequence
from pathlib import Path

from alex.lib.pdf_markdown_samples import run_pdf_markdown_samples


def test_run_pdf_markdown_samples_copies_first_ten_samples_and_runs_both_converters(
    tmp_path: Path,
) -> None:
    sample_file = tmp_path / "sample.txt"
    samples = [f"sample_{index}" for index in range(12)]
    sample_file.write_text("\n".join(["", *samples, ""]) + "\n", encoding="utf-8")
    asset_root = tmp_path / "assets"
    output_root = tmp_path / "pdf_test"
    commands: list[tuple[str, ...]] = []

    for sample in samples:
        sample_asset_dir = asset_root / sample
        sample_asset_dir.mkdir(parents=True)
        (sample_asset_dir / f"{sample}.pdf").write_bytes(f"{sample} pdf".encode())
        (sample_asset_dir / f"{sample}.md").write_text(f"{sample} md", encoding="utf-8")

    def fake_run(command: Sequence[str]) -> None:
        commands.append(tuple(command))

    results = run_pdf_markdown_samples(
        sample_file=sample_file,
        asset_root=asset_root,
        output_root=output_root,
        alex_command="alex",
        limit=10,
        run_command=fake_run,
    )

    copied_samples = samples[:10]
    assert [result.sample for result in results] == copied_samples

    for sample in copied_samples:
        sample_dir = output_root / sample
        assert (sample_dir / "o.pdf").read_bytes() == f"{sample} pdf".encode()
        assert (sample_dir / "o.md").read_text(encoding="utf-8") == f"{sample} md"
        assert (sample_dir / "alex-default.pdf").read_bytes() == (
            f"{sample} pdf".encode()
        )
        assert (sample_dir / "alex-miner.pdf").read_bytes() == f"{sample} pdf".encode()

    assert commands == [
        command
        for sample in copied_samples
        for command in [
            (
                "alex",
                "to-asset",
                str(output_root / sample / "alex-default.pdf"),
                "--asset-root",
                str(output_root / sample / "default-assets"),
            ),
            (
                "alex",
                "to-asset",
                str(output_root / sample / "alex-miner.pdf"),
                "--miner",
                "--asset-root",
                str(output_root / sample / "miner-assets"),
            ),
        ]
    ]

    assert [result.default_markdown for result in results] == [
        output_root / sample / "default-assets" / "alex-default" / "alex-default.md"
        for sample in copied_samples
    ]
    assert [result.miner_markdown for result in results] == [
        output_root / sample / "miner-assets" / "alex-miner" / "alex-miner.md"
        for sample in copied_samples
    ]
