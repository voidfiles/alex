import base64
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from alex.lib.document_sources import copy_file, read_epub_source
from alex.lib.metadata import package_version

DATALAB_CONVERT_API_URL = "https://www.datalab.to/api/v1/convert"
DATALAB_API_KEY_ENV = "DATALAB_API_KEY"


class ToMarkdownConfig(BaseModel):
    source: Path
    output_dir: Path
    name: str
    image_dir: Path = Field(default_factory=lambda: Path("images"))

    @property
    def asset_path(self) -> Path:
        return self.output_dir / f"{self.name}.md"

    @property
    def image_path(self) -> Path:
        return self.output_dir / self.image_dir


class MarkdownOutput(BaseModel):
    config: ToMarkdownConfig
    asset: Path


class DatalabApiError(RuntimeError):
    pass


Markdowner = Callable[[ToMarkdownConfig], MarkdownOutput]


def select_markdowner(
    default_markdowner: Markdowner,
    miner_markdowner: Markdowner,
    datalab_markdowner: Markdowner,
    *,
    use_miner: bool,
    use_datalab: bool,
) -> Markdowner:
    if use_datalab:
        return datalab_markdowner
    if use_miner:
        return miner_markdowner
    return default_markdowner


BOLD_HEADER_PATTERN = re.compile(
    r"^(?P<marker>[ \t]{0,3}#{1,6}[ \t]+)\*\*(?P<text>.*?)\*\*"
    r"(?P<trailing>[ \t]*#*[ \t]*)$",
    re.MULTILINE,
)


class SaveableImage(Protocol):
    def save(self, path: Path, image_format: str) -> None: ...


def pymupdf_to_markdown(source: str, **kwargs: object) -> object:
    # Imported lazily so `alex --help` never pays the PyMuPDF import cost.
    import pymupdf4llm

    return pymupdf4llm.to_markdown(source, **kwargs)


def pymupdf4llm_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    with suppress_stdout():
        markdown = pymupdf_to_markdown(
            str(config.source),
            write_images=True,
            image_path=str(config.image_path),
            image_format="png",
            header=False,
            footer=False,
            show_progress=False,
        )

    if not isinstance(markdown, str):
        raise TypeError("Expected pymupdf4llm to return markdown text.")

    markdown = remove_bold_wrapping_from_headers(markdown)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.asset_path.write_text(markdown, encoding="utf-8")

    return MarkdownOutput(config=config, asset=config.asset_path)


def epub_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    _, markdown = read_epub_source(config.source)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.asset_path.write_text(markdown, encoding="utf-8")

    return MarkdownOutput(config=config, asset=config.asset_path)


def existing_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    copy_file(config.source, config.asset_path)
    return MarkdownOutput(config=config, asset=config.asset_path)


def marker_pdf_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered

    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(str(config.source))
    markdown, output_extension, images = text_from_rendered(rendered)

    if not isinstance(markdown, str) or output_extension != "md":
        raise TypeError("Expected marker-pdf to return markdown text.")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    save_marker_images(config=config, images=images)
    markdown = rewrite_marker_image_paths(
        markdown=markdown,
        image_names=images.keys(),
        image_dir=config.image_dir,
    )
    markdown = remove_bold_wrapping_from_headers(markdown)
    config.asset_path.write_text(markdown, encoding="utf-8")

    return MarkdownOutput(config=config, asset=config.asset_path)


def datalab_pdf_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    api_key = get_datalab_api_key()
    submit_response = submit_datalab_pdf(config.source, api_key)

    if not submit_response.get("success"):
        error = submit_response.get("error", "Unknown error")
        raise RuntimeError(f"Failed to submit PDF to Datalab: {error}")

    check_url = submit_response.get("request_check_url")
    if not isinstance(check_url, str) or not check_url:
        raise TypeError(
            "Expected Datalab submit response to include request_check_url."
        )

    result = poll_datalab_result(check_url, api_key)
    markdown = result.get("markdown")
    if not isinstance(markdown, str):
        raise TypeError("Expected Datalab to return markdown text.")

    images = result.get("images") or {}
    if not isinstance(images, dict):
        raise TypeError("Expected Datalab images to be a mapping.")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    save_datalab_images(config=config, images=images)
    markdown = rewrite_marker_image_paths(
        markdown=markdown,
        image_names=images.keys(),
        image_dir=config.image_dir,
    )
    markdown = remove_bold_wrapping_from_headers(markdown)
    config.asset_path.write_text(markdown, encoding="utf-8")

    return MarkdownOutput(config=config, asset=config.asset_path)


def get_datalab_api_key() -> str:
    api_key = os.environ.get(DATALAB_API_KEY_ENV)
    if not api_key:
        raise OSError(
            f"{DATALAB_API_KEY_ENV} environment variable is not set. "
            "Create an API key at https://www.datalab.to/."
        )
    return api_key


def submit_datalab_pdf(pdf_path: Path, api_key: str) -> dict[str, object]:
    request = build_datalab_submit_request(pdf_path=pdf_path, api_key=api_key)
    return read_datalab_json(request)


def build_datalab_submit_request(
    pdf_path: Path,
    api_key: str,
    *,
    mode: str = "balanced",
    boundary: str | None = None,
) -> Request:
    multipart_boundary = boundary or f"alex-{uuid.uuid4().hex}"
    body = encode_multipart_form(
        fields={
            "output_format": "markdown",
            "mode": mode,
            "paginate": "false",
            "disable_image_extraction": "false",
        },
        file_field="file",
        file_path=pdf_path,
        content_type="application/pdf",
        boundary=multipart_boundary,
    )
    return Request(
        DATALAB_CONVERT_API_URL,
        data=body,
        headers={
            **datalab_request_headers(api_key),
            "Content-Type": f"multipart/form-data; boundary={multipart_boundary}",
        },
        method="POST",
    )


def datalab_request_headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-Key": api_key,
        "User-Agent": f"alex-cli/{package_version()}",
        "Accept": "application/json",
    }


def encode_multipart_form(
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
    content_type: str,
    boundary: str,
) -> bytes:
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    "Content-Disposition: form-data; "
                    f'name="{escape_multipart_header_value(name)}"\r\n\r\n'
                ).encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                "Content-Disposition: form-data; "
                f'name="{escape_multipart_header_value(file_field)}"; '
                f'filename="{escape_multipart_header_value(file_path.name)}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )

    return b"".join(chunks)


def escape_multipart_header_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def read_datalab_json(
    request_or_url: Request | str,
    api_key: str | None = None,
) -> dict[str, object]:
    if isinstance(request_or_url, str):
        if api_key is None:
            raise ValueError("api_key is required when polling a Datalab URL.")
        request = Request(
            request_or_url,
            headers=datalab_request_headers(api_key),
            method="GET",
        )
    else:
        request = request_or_url
    try:
        with urlopen(request) as response:
            payload = response.read()
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace").strip()
        message = f"Datalab API request failed with HTTP {error.code}"
        if body:
            message = f"{message}: {body}"
        raise DatalabApiError(message) from error

    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Expected Datalab API to return a JSON object.")
    return data


def poll_datalab_result(
    check_url: str,
    api_key: str,
    *,
    max_polls: int = 900,
    poll_interval_seconds: float = 2.0,
) -> dict[str, object]:
    for _ in range(max_polls):
        data = read_datalab_json(check_url, api_key)
        status = data.get("status")

        if status == "complete":
            if data.get("success"):
                return data
            error = data.get("error", "Unknown error")
            raise RuntimeError(f"Datalab conversion failed: {error}")

        if status == "failed":
            error = data.get("error", "Unknown error")
            raise RuntimeError(f"Datalab conversion failed: {error}")

        time.sleep(poll_interval_seconds)

    raise TimeoutError(f"Datalab conversion did not complete after {max_polls} polls.")


def save_datalab_images(
    config: ToMarkdownConfig,
    images: dict[object, object],
) -> None:
    if not images:
        return

    config.image_path.mkdir(parents=True, exist_ok=True)
    for image_name, encoded_image in images.items():
        if not isinstance(image_name, str) or not isinstance(encoded_image, str):
            raise TypeError(
                "Expected Datalab images to map filenames to base64 strings."
            )

        image_path = config.image_path / image_name
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(base64.b64decode(encoded_image))


def remove_bold_wrapping_from_headers(markdown: str) -> str:
    return BOLD_HEADER_PATTERN.sub(r"\g<marker>\g<text>\g<trailing>", markdown)


def save_marker_images(
    config: ToMarkdownConfig,
    images: dict[str, SaveableImage],
) -> None:
    if not images:
        return

    config.image_path.mkdir(parents=True, exist_ok=True)
    for image_name, image in images.items():
        image_path = config.image_path / image_name
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_format = image_path.suffix.removeprefix(".").upper()
        image.save(image_path, image_format)


def rewrite_marker_image_paths(
    markdown: str,
    image_names: Iterable[str],
    image_dir: Path,
) -> str:
    rewritten = markdown
    image_dir_path = image_dir.as_posix().rstrip("/")
    for image_name in image_names:
        image_path = f"{image_dir_path}/{image_name}"
        rewritten = rewritten.replace(f"({image_name})", f"({image_path})")
        rewritten = rewritten.replace(f"src='{image_name}'", f"src='{image_path}'")
        rewritten = rewritten.replace(f'src="{image_name}"', f'src="{image_path}"')
    return rewritten


@contextmanager
def suppress_stdout() -> Iterator[None]:
    sys.stdout.flush()
    original_stdout = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)

    try:
        os.dup2(devnull, 1)
        with redirect_stdout(StringIO()):
            yield
    finally:
        sys.stdout.flush()
        os.dup2(original_stdout, 1)
        os.close(original_stdout)
        os.close(devnull)
