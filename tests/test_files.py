import base64
import importlib.util
import io
import unittest
import zipfile

from firmalways_gate.engine import ContentNotAllowed, Gate
from firmalways_gate.files import FileNotSupported, decode_data_url, extract_text
from firmalways_gate.policy import Policy
from firmalways_gate.pseudonymize import Pseudonymizer

ID = "1101700203611"


def make_docx(paragraphs):
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{p}</w:t></w:r></w:p>' for p in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def make_pdf(text):
    """A minimal one-page PDF with Helvetica text (ASCII only)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def data_url(mime, data):
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def file_part(filename, mime, data):
    return {"type": "file", "file": {"filename": filename, "file_data": data_url(mime, data)}}


class ExtractTest(unittest.TestCase):
    def test_docx(self):
        data = make_docx(["สัญญาจ้าง", f"นายสมชาย ใจดี บัตร {ID}", "A &amp; B"])
        self.assertEqual(extract_text("contract.docx", "", data), f"สัญญาจ้าง\nนายสมชาย ใจดี บัตร {ID}\nA & B")

    def test_text_and_csv(self):
        self.assertEqual(extract_text("a.csv", "", "ชื่อ,โทร\nสมชาย,0812345678".encode()), "ชื่อ,โทร\nสมชาย,0812345678")
        self.assertEqual(extract_text("note", "text/plain", "hi".encode()), "hi")

    def test_unsupported_and_broken(self):
        with self.assertRaises(FileNotSupported):
            extract_text("photo.png", "image/png", b"\x89PNG")
        with self.assertRaises(FileNotSupported):
            extract_text("bad.docx", "", b"not a zip")
        with self.assertRaises(FileNotSupported):
            extract_text("bad.txt", "", b"\xff\xfe\xfa")

    def test_data_url(self):
        self.assertEqual(decode_data_url(data_url("text/plain", b"x")), ("text/plain", b"x"))
        for value in ("hello", "data:text/plain;base64,@@@"):
            with self.assertRaises(FileNotSupported):
                decode_data_url(value)

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf not installed")
    def test_pdf(self):
        text = extract_text("a.pdf", "application/pdf", make_pdf(f"Customer ID {ID} phone 0812345678"))
        self.assertIn(ID, text)

    @unittest.skipIf(importlib.util.find_spec("pypdf"), "pypdf installed")
    def test_pdf_without_pypdf_is_refused(self):
        with self.assertRaises(FileNotSupported) as ctx:
            extract_text("a.pdf", "application/pdf", make_pdf("x"))
        self.assertIn("pypdf", str(ctx.exception))


class GateFileTest(unittest.TestCase):
    def test_docx_part_becomes_masked_text(self):
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "สรุปสัญญานี้"},
            file_part("contract.docx", "", make_docx([f"ผู้ว่าจ้าง นายสมชาย ใจดี บัตร {ID}"])),
        ]}]
        out, protection = Gate().protect_messages(messages, Pseudonymizer())
        part = out[0]["content"][1]
        self.assertEqual(part, {"type": "text", "text": "[ไฟล์แนบ: contract.docx]\nผู้ว่าจ้าง นาย«PERSON_1» บัตร «THAI_NATIONAL_ID_1»"})
        self.assertEqual(protection.file_parts, 1)

    def test_secret_in_file_blocks(self):
        messages = [{"role": "user", "content": [file_part("env.txt", "text/plain", b"password: hunter22")]}]
        _, protection = Gate().protect_messages(messages, Pseudonymizer())
        self.assertEqual(protection.blocked_types, {"SECRET"})

    def test_file_id_and_images_refused(self):
        for part in ({"type": "file", "file": {"file_id": "file-abc"}},
                     {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                     file_part("x.png", "image/png", b"\x89PNG")):
            with self.assertRaises(ContentNotAllowed):
                Gate().protect_messages([{"role": "user", "content": [part]}], Pseudonymizer())

    def test_files_block_policy(self):
        gate = Gate(Policy.from_dict({"content": {"files": "block"}}))
        with self.assertRaises(ContentNotAllowed):
            gate.protect_messages([{"role": "user", "content": [file_part("a.txt", "text/plain", b"x")]}], Pseudonymizer())


if __name__ == "__main__":
    unittest.main()
