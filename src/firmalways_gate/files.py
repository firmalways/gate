"""Extract text from attached files so Gate can inspect them.

Supported: plain text (txt, csv, md, json, tsv, log), DOCX (standard library
only) and PDF (needs the optional ``pypdf`` package: ``pip install
"firmalways-gate[pdf]"``). Images are not supported: Gate has no OCR.

DOCX is read with regular expressions over ``word/document.xml`` instead of an
XML parser, which avoids XML entity attacks, and archive sizes are capped to
avoid zip bombs.
"""

from __future__ import annotations

import base64
import binascii
import html
import io
import re
import zipfile

MAX_UNCOMPRESSED = 20_000_000

TEXT_EXTENSIONS = (".txt", ".csv", ".tsv", ".md", ".json", ".log", ".xml", ".html", ".htm")
TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml")
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_DATA_URL = re.compile(r"^data:(?P<mime>[\w.+/-]*)(?:;[\w=.-]+)*;base64,(?P<data>.*)$", re.DOTALL)
_PARAGRAPH = re.compile(r"<w:p[ >].*?</w:p>|<w:p/>", re.DOTALL)
_TEXT_RUN = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>|<w:tab/>|<w:br/>", re.DOTALL)


class FileNotSupported(ValueError):
    """The file cannot be inspected, so policy requires refusing it."""


def decode_data_url(value: str) -> tuple[str, bytes]:
    match = _DATA_URL.match(value or "")
    if not match:
        raise FileNotSupported("file_data must be a base64 data URL")
    try:
        return match.group("mime").lower(), base64.b64decode(match.group("data"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FileNotSupported("file_data is not valid base64") from exc


def extract_text(filename: str, mime: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".docx") or mime == DOCX_MIME:
        return _docx_text(data)
    if name.endswith(".pdf") or mime == "application/pdf":
        return _pdf_text(data)
    if name.endswith(TEXT_EXTENSIONS) or mime.startswith(TEXT_MIME_PREFIXES):
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FileNotSupported(f"{filename or 'file'} is not UTF-8 text") from exc
    raise FileNotSupported(f"cannot inspect files of type {mime or name or 'unknown'}")


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_UNCOMPRESSED:
                raise FileNotSupported("DOCX document is too large to inspect")
            xml = archive.read(info).decode("utf-8")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise FileNotSupported("not a readable DOCX file") from exc
    paragraphs = []
    for paragraph in _PARAGRAPH.findall(xml):
        pieces = []
        for m in _TEXT_RUN.finditer(paragraph):
            token = m.group(0)
            pieces.append("\t" if token == "<w:tab/>" else "\n" if token == "<w:br/>" else html.unescape(m.group(1)))
        paragraphs.append("".join(pieces))
    return "\n".join(paragraphs)


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise FileNotSupported('PDF inspection needs pypdf: pip install "firmalways-gate[pdf]"') from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise FileNotSupported("encrypted PDFs cannot be inspected")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except FileNotSupported:
        raise
    except Exception as exc:  # noqa: BLE001 - any parser failure means "cannot inspect"
        raise FileNotSupported("not a readable PDF file") from exc
