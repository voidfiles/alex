import os
import sys
import zipfile
from base64 import b64encode
from collections.abc import Iterator
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.error import HTTPError

import pytest

from alex.lib.converters import to_markdown as converter_module
from alex.lib.converters.to_markdown import (
    DatalabApiError,
    ToMarkdownConfig,
    build_datalab_submit_request,
    datalab_pdf_markdowner,
    epub_markdowner,
    existing_markdowner,
    marker_pdf_markdowner,
    poll_datalab_result,
    pymupdf4llm_markdowner,
    read_datalab_json,
)


def test_pymupdf4llm_markdowner_writes_markdown_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_to_markdown(source_path: str, **kwargs: Any) -> str:
        calls.append((source_path, kwargs))
        return "# Paper\n"

    monkeypatch.setattr(converter_module, "pymupdf_to_markdown", fake_to_markdown)

    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="paper")

    result = pymupdf4llm_markdowner(config)

    assert result.config == config
    assert result.asset == tmp_path / "out" / "paper.md"
    assert result.asset.read_text(encoding="utf-8") == "# Paper\n"
    assert calls == [
        (
            str(source),
            {
                "write_images": True,
                "image_path": str(tmp_path / "out" / "images"),
                "image_format": "png",
                "header": False,
                "footer": False,
                "show_progress": False,
            },
        )
    ]


def test_pymupdf4llm_markdowner_rejects_non_string_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    def fake_to_markdown(source_path: str, **kwargs: Any) -> list[str]:
        return ["# Paper\n"]

    monkeypatch.setattr(converter_module, "pymupdf_to_markdown", fake_to_markdown)

    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="paper")

    with pytest.raises(TypeError, match="Expected pymupdf4llm to return markdown text"):
        pymupdf4llm_markdowner(config)


def test_pymupdf4llm_markdowner_suppresses_library_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    def fake_to_markdown(source_path: str, **kwargs: Any) -> str:
        print("=== noisy parser output ===")
        os.write(1, b"=== noisy fd parser output ===\n")
        return "# Paper\n"

    monkeypatch.setattr(converter_module, "pymupdf_to_markdown", fake_to_markdown)

    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="paper")

    pymupdf4llm_markdowner(config)

    captured = capfd.readouterr()
    assert captured.out == ""


def test_pymupdf4llm_markdowner_removes_bold_wrapping_from_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    def fake_to_markdown(source_path: str, **kwargs: Any) -> str:
        return "## **Paper Title**\n\nBody with **bold** text.\n"

    monkeypatch.setattr(converter_module, "pymupdf_to_markdown", fake_to_markdown)

    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="paper")

    result = pymupdf4llm_markdowner(config)

    assert (
        result.asset.read_text(encoding="utf-8")
        == "## Paper Title\n\nBody with **bold** text.\n"
    )


def test_epub_markdowner_writes_local_markdown_asset(tmp_path: Path) -> None:
    source = tmp_path / "sample.epub"
    write_minimal_epub(source)
    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="book")

    result = epub_markdowner(config)

    assert result.config == config
    assert result.asset == tmp_path / "out" / "book.md"
    assert result.asset.read_text(encoding="utf-8") == (
        "# Example Book\n\n"
        "By Jane Writer\n\n"
        "# Opening\n\n"
        "The first paragraph.\n\n"
        "The second paragraph.\n"
    )


def test_existing_markdowner_copies_markdown_asset(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\nBody.\n", encoding="utf-8")
    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="asset")

    result = existing_markdowner(config)

    assert result.config == config
    assert result.asset == tmp_path / "out" / "asset.md"
    assert result.asset.read_text(encoding="utf-8") == "# Notes\n\nBody.\n"
    assert source.read_text(encoding="utf-8") == "# Notes\n\nBody.\n"


def test_marker_pdf_markdowner_writes_markdown_asset_and_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    calls: list[tuple[Any, ...]] = []
    rendered = object()

    class FakeImage:
        def save(self, path: Path, image_format: str) -> None:
            calls.append(("save_image", path, image_format))
            path.write_text("fake image", encoding="utf-8")

    class FakePdfConverter:
        def __init__(self, artifact_dict: dict[str, str]) -> None:
            calls.append(("init_converter", artifact_dict))

        def __call__(self, source_path: str) -> object:
            calls.append(("convert", source_path))
            return rendered

    def fake_create_model_dict() -> dict[str, str]:
        calls.append(("create_models", None))
        return {"layout_model": "fake"}

    def fake_text_from_rendered(
        rendered: object,
    ) -> tuple[str, str, dict[str, FakeImage]]:
        calls.append(("render_text", rendered))
        return (
            "![Figure](figure.jpeg)\n\n## **Paper**\n",
            "md",
            {"figure.jpeg": FakeImage()},
        )

    install_fake_marker_modules(
        monkeypatch=monkeypatch,
        pdf_converter=FakePdfConverter,
        create_model_dict=fake_create_model_dict,
        text_from_rendered=fake_text_from_rendered,
    )

    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="paper")

    result = marker_pdf_markdowner(config)

    assert result.config == config
    assert result.asset == tmp_path / "out" / "paper.md"
    assert (
        result.asset.read_text(encoding="utf-8")
        == "![Figure](images/figure.jpeg)\n\n## Paper\n"
    )
    assert (tmp_path / "out" / "images" / "figure.jpeg").read_text(
        encoding="utf-8"
    ) == "fake image"
    assert calls == [
        ("create_models", None),
        ("init_converter", {"layout_model": "fake"}),
        ("convert", str(source)),
        ("render_text", rendered),
        ("save_image", tmp_path / "out" / "images" / "figure.jpeg", "JPEG"),
    ]


def test_marker_pdf_markdowner_rejects_non_markdown_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    class FakePdfConverter:
        def __init__(self, artifact_dict: dict[str, str]) -> None:
            pass

        def __call__(self, source_path: str) -> object:
            return object()

    def fake_text_from_rendered(rendered: object) -> tuple[str, str, dict[str, object]]:
        return "{}", "json", {}

    install_fake_marker_modules(
        monkeypatch=monkeypatch,
        pdf_converter=FakePdfConverter,
        create_model_dict=lambda: {"layout_model": "fake"},
        text_from_rendered=fake_text_from_rendered,
    )

    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="paper")

    with pytest.raises(TypeError, match="Expected marker-pdf to return markdown text"):
        marker_pdf_markdowner(config)


def test_build_datalab_submit_request_uses_convert_api_multipart_form(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    request = build_datalab_submit_request(
        pdf_path=source,
        api_key="test-datalab-key",
        boundary="test-boundary",
    )
    body = request.data

    assert request.full_url == "https://www.datalab.to/api/v1/convert"
    assert request.get_method() == "POST"
    assert request.get_header("X-api-key") == "test-datalab-key"
    assert request.get_header("User-agent") == "alex-cli/0.1.0"
    assert request.get_header("Accept") == "application/json"
    assert (
        request.get_header("Content-type")
        == "multipart/form-data; boundary=test-boundary"
    )
    assert isinstance(body, bytes)
    assert b'name="output_format"\r\n\r\nmarkdown' in body
    assert b'name="mode"\r\n\r\nbalanced' in body
    assert b'name="disable_image_extraction"\r\n\r\nfalse' in body
    assert b'name="file"; filename="paper.pdf"' in body
    assert b"Content-Type: application/pdf\r\n\r\n%PDF-1.7\n" in body


def test_read_datalab_json_uses_datalab_friendly_headers_for_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_requests: list[Any] = []

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"status": "processing"}'

    def fake_urlopen(request: Any) -> FakeResponse:
        captured_requests.append(request)
        return FakeResponse()

    monkeypatch.setattr(converter_module, "urlopen", fake_urlopen)

    result = read_datalab_json(
        "https://www.datalab.to/api/v1/convert/request-123",
        "test-datalab-key",
    )

    assert result == {"status": "processing"}
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.get_header("X-api-key") == "test-datalab-key"
    assert request.get_header("User-agent") == "alex-cli/0.1.0"
    assert request.get_header("Accept") == "application/json"


def test_read_datalab_json_raises_readable_error_for_http_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any) -> object:
        raise HTTPError(
            url=request.full_url,
            code=403,
            msg="Forbidden",
            hdrs=Message(),
            fp=BytesIO(b"error code: 1010"),
        )

    monkeypatch.setattr(converter_module, "urlopen", fake_urlopen)

    with pytest.raises(
        DatalabApiError,
        match="Datalab API request failed with HTTP 403: error code: 1010",
    ):
        read_datalab_json(
            "https://www.datalab.to/api/v1/convert/request-123",
            "test-datalab-key",
        )


def test_poll_datalab_result_polls_until_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: Iterator[dict[str, object]] = iter(
        [
            {"status": "processing"},
            {"status": "complete", "success": True, "markdown": "# Paper\n"},
        ]
    )
    calls: list[tuple[str, str]] = []

    def fake_read_datalab_json(url: str, api_key: str) -> dict[str, object]:
        calls.append((url, api_key))
        return next(responses)

    monkeypatch.setattr(
        converter_module,
        "read_datalab_json",
        fake_read_datalab_json,
    )

    result = poll_datalab_result(
        check_url="https://www.datalab.to/api/v1/convert/request-123",
        api_key="test-datalab-key",
        max_polls=2,
        poll_interval_seconds=0,
    )

    assert result == {"status": "complete", "success": True, "markdown": "# Paper\n"}
    assert calls == [
        ("https://www.datalab.to/api/v1/convert/request-123", "test-datalab-key"),
        ("https://www.datalab.to/api/v1/convert/request-123", "test-datalab-key"),
    ]


def test_poll_datalab_result_raises_when_conversion_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_read_datalab_json(url: str, api_key: str) -> dict[str, object]:
        return {"status": "failed", "success": False, "error": "parse failed"}

    monkeypatch.setattr(
        converter_module,
        "read_datalab_json",
        fake_read_datalab_json,
    )

    with pytest.raises(RuntimeError, match="Datalab conversion failed: parse failed"):
        poll_datalab_result(
            check_url="https://www.datalab.to/api/v1/convert/request-123",
            api_key="test-datalab-key",
            max_polls=1,
            poll_interval_seconds=0,
        )


def test_datalab_pdf_markdowner_writes_markdown_asset_and_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    calls: list[tuple[Any, ...]] = []

    def fake_submit_datalab_pdf(
        pdf_path: Path,
        api_key: str,
    ) -> dict[str, object]:
        calls.append(("submit", pdf_path, api_key))
        return {
            "success": True,
            "request_id": "request-123",
            "request_check_url": "https://www.datalab.to/api/v1/convert/request-123",
        }

    def fake_poll_datalab_result(check_url: str, api_key: str) -> dict[str, object]:
        calls.append(("poll", check_url, api_key))
        return {
            "status": "complete",
            "success": True,
            "markdown": "![Figure](figure.png)\n\n## **Paper**\n",
            "images": {"figure.png": b64encode(b"fake image").decode("ascii")},
        }

    monkeypatch.setenv("DATALAB_API_KEY", "test-datalab-key")
    monkeypatch.setattr(
        converter_module,
        "submit_datalab_pdf",
        fake_submit_datalab_pdf,
    )
    monkeypatch.setattr(
        converter_module,
        "poll_datalab_result",
        fake_poll_datalab_result,
    )

    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="paper")

    result = datalab_pdf_markdowner(config)

    assert result.config == config
    assert result.asset == tmp_path / "out" / "paper.md"
    assert (
        result.asset.read_text(encoding="utf-8")
        == "![Figure](images/figure.png)\n\n## Paper\n"
    )
    assert (tmp_path / "out" / "images" / "figure.png").read_bytes() == b"fake image"
    assert calls == [
        ("submit", source, "test-datalab-key"),
        (
            "poll",
            "https://www.datalab.to/api/v1/convert/request-123",
            "test-datalab-key",
        ),
    ]


def test_datalab_pdf_markdowner_requires_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    monkeypatch.delenv("DATALAB_API_KEY", raising=False)
    config = ToMarkdownConfig(source=source, output_dir=tmp_path / "out", name="paper")

    with pytest.raises(EnvironmentError, match="DATALAB_API_KEY"):
        datalab_pdf_markdowner(config)


def install_fake_marker_modules(
    monkeypatch: pytest.MonkeyPatch,
    pdf_converter: type,
    create_model_dict: object,
    text_from_rendered: object,
) -> None:
    marker_module = ModuleType("marker")
    converters_module = ModuleType("marker.converters")
    pdf_module: Any = ModuleType("marker.converters.pdf")
    models_module: Any = ModuleType("marker.models")
    output_module: Any = ModuleType("marker.output")

    pdf_module.PdfConverter = pdf_converter
    models_module.create_model_dict = create_model_dict
    output_module.text_from_rendered = text_from_rendered

    monkeypatch.setitem(sys.modules, "marker", marker_module)
    monkeypatch.setitem(sys.modules, "marker.converters", converters_module)
    monkeypatch.setitem(sys.modules, "marker.converters.pdf", pdf_module)
    monkeypatch.setitem(sys.modules, "marker.models", models_module)
    monkeypatch.setitem(sys.modules, "marker.output", output_module)


def write_minimal_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Example Book</dc:title>
    <dc:creator>Jane Writer</dc:creator>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter"/>
  </spine>
</package>
""",
        )
        archive.writestr(
            "OEBPS/chapter.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>Opening</h1>
    <p>The first paragraph.</p>
    <p>The second paragraph.</p>
  </body>
</html>
""",
        )
