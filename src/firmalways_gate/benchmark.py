"""Synthetic Thai benchmark for detection quality.

Every value is generated (no real people). Scores are exact span-and-type
matches per entity type, plus "protection recall": the share of personal-data
characters covered by any detection, which is what matters for privacy.

Caveat: the same author wrote the detectors and the templates, so results are
optimistic. Treat them as a regression guard and a format-coverage check, and
add independent, human-labelled samples before quoting numbers externally.
"""

from __future__ import annotations

import random
import re
import string
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from importlib import resources

from .analyzer import ENTITY_TYPES, analyze
from .entities import Entity

FIRST_NAMES = ("สมชาย", "สมศรี", "วิภาวรรณ", "ณัฐพล", "กิตติพงษ์", "ปิยะนุช", "อรุณี", "ธนกฤต", "ศิริพร", "ชยพล", "เอกชัย", "ดวงใจ")
LAST_NAMES = ("ใจดี", "รักไทย", "ศรีสุข", "วงศ์ทอง", "แก้วมณี", "บุญมา", "สุขสวัสดิ์", "ทองคำ")
EN_NAMES = (("John", "Smith"), ("Anna", "Lee"), ("David", "Chen"))
LATIN = ("somchai", "wipa", "natt", "kitti", "orn", "tanakrit")
DOMAINS = ("example.co.th", "example.com", "mail.example.org")
PLACES = (
    ("ตำบลบางพลีใหญ่", "อำเภอบางพลี", "จังหวัดสมุทรปราการ", "10540"),
    ("ตำบลสุเทพ", "อำเภอเมืองเชียงใหม่", "จังหวัดเชียงใหม่", "50200"),
    ("ตำบลในเมือง", "อำเภอเมืองขอนแก่น", "จังหวัดขอนแก่น", "40000"),
)

NEGATIVES = (
    "คุณภาพสินค้าล็อตนี้ดีมาก ช่วยสรุปรีวิวให้หน่อย",
    "นายจ้างต้องจ่ายค่าล่วงเวลาอย่างไร",
    "คุณช่วยสรุปยอดขายเดือนนี้ให้หน่อย",
    "ใบสั่งซื้อเลขที่ 4501234567 จำนวน 120 ชิ้น ราคา 35,900 บาท",
    "ปี 2567 ยอดขายเพิ่มขึ้น 12.5% เทียบกับปี 2566",
    "นางแบบคนนี้ถ่ายโฆษณาให้แบรนด์",
    "เขตพื้นที่การศึกษามีโรงเรียน 25 แห่ง",
    "รหัสสินค้า SKU-X01 เหลือ 5 ชิ้น",
    "คุณสมบัติของผู้สมัครตำแหน่งนี้มีอะไรบ้าง",
    "โทรหาเบอร์ 1112 เพื่อสั่งพิซซ่า",
    "ขอบคุณครับ ทนายความจะส่งเอกสารให้พรุ่งนี้",
    "ราคา 4,990 บาท ส่งฟรีทั่วประเทศ",
    "ประชุมวันที่ 15/11/2026 เวลา 09:15 น.",
)


@dataclass(frozen=True)
class Sample:
    text: str
    spans: tuple[tuple[str, int, int], ...]  # (type, start, end)


def _digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(n))


def thai_id(rng: random.Random) -> str:
    base = str(rng.randint(1, 8)) + _digits(rng, 11)
    total = sum(int(d) * w for d, w in zip(base, range(13, 1, -1)))
    value = base + str((11 - total % 11) % 10)
    style = rng.randrange(3)
    if style == 1:
        return f"{value[0]}-{value[1:5]}-{value[5:10]}-{value[10:12]}-{value[12]}"
    if style == 2:
        return f"{value[0]} {value[1:5]} {value[5:10]} {value[10:12]} {value[12]}"
    return value


def phone(rng: random.Random) -> str:
    style = rng.randrange(4)
    mobile = rng.choice("689") + _digits(rng, 8)
    if style == 0:
        return "0" + mobile
    if style == 1:
        return f"0{mobile[:2]}-{mobile[2:5]}-{mobile[5:]}"
    if style == 2:
        return f"+66 {mobile[:2]} {mobile[2:5]} {mobile[5:]}"
    return f"02-{_digits(rng, 3)}-{_digits(rng, 4)}"


def email(rng: random.Random) -> str:
    return f"{rng.choice(LATIN)}{rng.randint(1, 99)}@{rng.choice(DOMAINS)}"


def bank_formatted(rng: random.Random) -> str:
    return f"{_digits(rng, 3)}-{_digits(rng, 1)}-{_digits(rng, 5)}-{_digits(rng, 1)}"


def card(rng: random.Random) -> str:
    base = "4" + _digits(rng, 14)
    total = 0
    for i, ch in enumerate(reversed(base)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    value = base + str((10 - total % 10) % 10)
    sep = rng.choice(" -")
    return sep.join(value[i : i + 4] for i in range(0, 16, 4))


def address(rng: random.Random) -> str:
    tambon, amphoe, province, postal = rng.choice(PLACES)
    return f"บ้านเลขที่ {rng.randint(1, 999)}/{rng.randint(1, 99)} หมู่ {rng.randint(1, 12)} {tambon} {amphoe} {province} {postal}"


def secret(rng: random.Random) -> str:
    alphabet = string.ascii_letters + string.digits
    kind = rng.randrange(3)
    if kind == 0:
        return "sk-" + "".join(rng.choice(alphabet) for _ in range(32))
    if kind == 1:
        return "AKIA" + "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    return "ghp_" + "".join(rng.choice(alphabet) for _ in range(36))


Part = str | tuple[str, str]


def _compose(parts: list[Part]) -> Sample:
    text, spans = "", []
    for part in parts:
        if isinstance(part, tuple):
            kind, value = part
            spans.append((kind, len(text), len(text) + len(value)))
            text += value
        else:
            text += part
    return Sample(text, tuple(spans))


def _templates(rng: random.Random) -> list[Sample]:
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    full = f"{first} {last}"
    en_first, en_last = rng.choice(EN_NAMES)
    return [
        _compose(["ลูกค้าคุณ", ("PERSON", full), " เลขบัตรประชาชน ", ("THAI_NATIONAL_ID", thai_id(rng)),
                  " ติดต่อ ", ("PHONE", phone(rng))]),
        _compose(["ช่วยร่างอีเมลถึงนาย", ("PERSON", first), " ที่ ", ("EMAIL", email(rng)), " เรื่องค่างวดค้างชำระ"]),
        _compose(["โอนเงินเข้าบัญชี ", ("BANK_ACCOUNT", bank_formatted(rng)), " แล้วแจ้งสลิปที่ ", ("PHONE", phone(rng))]),
        _compose(["เลขบัญชี ", ("BANK_ACCOUNT", _digits(rng, 10)), " ชื่อบัญชีนางสาว", ("PERSON", full)]),
        _compose(["ที่อยู่จัดส่ง ", ("THAI_ADDRESS", address(rng)), " โทร ", ("PHONE", phone(rng))]),
        _compose(["บัตรเครดิต ", ("CREDIT_CARD", card(rng)), " ถูกปฏิเสธ ช่วยเขียนข้อความแจ้งลูกค้า"]),
        _compose(["นี่คือ API key ของระบบ ", ("SECRET", secret(rng)), " ช่วยตรวจโค้ดหน่อย"]),
        _compose([("SENSITIVE_HEALTH", "ผู้ป่วย"), "เลขบัตร", ("THAI_NATIONAL_ID", thai_id(rng).replace(" ", "").replace("-", "")),
                  "โทร", ("PHONE", "0" + rng.choice("689") + _digits(rng, 8))]),
        _compose(["Please email Mr. ", ("PERSON", f"{en_first} {en_last}"), " at ", ("EMAIL", email(rng))]),
        _compose(["พนักงาน นาย", ("PERSON", full), " รหัสผ่าน: ", ("SECRET", "Pa55" + _digits(rng, 4))]),
    ]


def generate(seed: int = 7, repeats: int = 30) -> list[Sample]:
    rng = random.Random(seed)
    samples: list[Sample] = []
    for _ in range(repeats):
        samples.extend(_templates(rng))
    samples.extend(Sample(text, ()) for text in NEGATIVES)
    return samples


def evaluate(samples: list[Sample], detect: Callable[[str], list[Entity]] = analyze) -> dict[str, Any]:
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    gold_chars = covered_chars = 0
    negative_false_positives = 0
    for sample in samples:
        predicted = {(e.type, e.start, e.end) for e in detect(sample.text)}
        gold = set(sample.spans)
        for item in predicted & gold:
            tp[item[0]] += 1
        for item in predicted - gold:
            fp[item[0]] += 1
        for item in gold - predicted:
            fn[item[0]] += 1
        if not gold:
            negative_false_positives += len(predicted)
        covered = set()
        for _, start, end in predicted:
            covered.update(range(start, end))
        for _, start, end in gold:
            gold_chars += end - start
            covered_chars += sum(1 for i in range(start, end) if i in covered)

    def prf(t: int, p: int, n: int) -> dict[str, float]:
        precision = t / (t + p) if t + p else 1.0
        recall = t / (t + n) if t + n else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": t + n}

    per_type = {kind: prf(tp[kind], fp[kind], fn[kind]) for kind in ENTITY_TYPES}
    return {
        "samples": len(samples),
        "per_type": per_type,
        "overall": prf(sum(tp.values()), sum(fp.values()), sum(fn.values())),
        "protection_recall": round(covered_chars / gold_chars, 4) if gold_chars else 1.0,
        "negative_false_positives": negative_false_positives,
    }


_MARK = re.compile(r"\[\[([A-Z_]+):(.*?)\]\]")


def parse_marked(line: str) -> Sample:
    """Turn ``"โทร [[PHONE:0812345678]]"`` into text plus gold spans."""
    parts: list[Part] = []
    pos = 0
    for m in _MARK.finditer(line):
        parts.append(line[pos : m.start()])
        parts.append((m.group(1), m.group(2)))
        pos = m.end()
    parts.append(line[pos:])
    return _compose(parts)


def load_curated() -> list[Sample]:
    text = resources.files("firmalways_gate").joinpath("data/curated_th.txt").read_text(encoding="utf-8")
    return [parse_marked(line) for line in text.splitlines() if line.strip() and not line.startswith("#")]


def evaluate_any_type(samples: list[Sample], detect: Callable[[str], list[tuple[int, int]]]) -> dict[str, Any]:
    """Type-agnostic comparison: a gold value counts as found if any detection overlaps it.

    ``detect`` returns ``(start, end)`` spans, so tools with different type
    names (for example Microsoft Presidio) can be compared fairly.
    """
    found_by_type: Counter[str] = Counter()
    total_by_type: Counter[str] = Counter()
    false_positives = 0
    predictions = 0
    gold_chars = covered_chars = 0
    for sample in samples:
        predicted = detect(sample.text)
        predictions += len(predicted)
        for start, end in predicted:
            if not any(start < g_end and g_start < end for _, g_start, g_end in sample.spans):
                false_positives += 1
        covered = set()
        for start, end in predicted:
            covered.update(range(start, end))
        for kind, start, end in sample.spans:
            total_by_type[kind] += 1
            if any(start < p_end and p_start < end for p_start, p_end in predicted):
                found_by_type[kind] += 1
            gold_chars += end - start
            covered_chars += sum(1 for i in range(start, end) if i in covered)
    found = sum(found_by_type.values())
    total = sum(total_by_type.values())
    return {
        "samples": len(samples),
        "values": total,
        "recall": round(found / total, 4) if total else 1.0,
        "precision": round((predictions - false_positives) / predictions, 4) if predictions else 1.0,
        "protection_recall": round(covered_chars / gold_chars, 4) if gold_chars else 1.0,
        "false_positives": false_positives,
        "recall_by_type": {k: round(found_by_type[k] / total_by_type[k], 4) for k in sorted(total_by_type)},
    }


def run(seed: int = 7, repeats: int = 30, dataset: str = "synthetic") -> dict[str, Any]:
    if dataset == "curated":
        samples = load_curated()
        report = evaluate(samples)
        report["any_type"] = evaluate_any_type(samples, lambda text: [(e.start, e.end) for e in analyze(text)])
        report["dataset"] = "curated"
        return report
    report = evaluate(generate(seed, repeats))
    report["dataset"] = "synthetic"
    return report


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"FirmAlways Gate {report.get('dataset', 'synthetic')} Thai benchmark — {report['samples']} samples",
        f"{'type':<17} {'precision':>9} {'recall':>7} {'f1':>6} {'support':>8}",
    ]
    for kind, m in report["per_type"].items():
        lines.append(f"{kind:<17} {m['precision']:>9.3f} {m['recall']:>7.3f} {m['f1']:>6.3f} {m['support']:>8}")
    o = report["overall"]
    lines.append(f"{'OVERALL':<17} {o['precision']:>9.3f} {o['recall']:>7.3f} {o['f1']:>6.3f} {o['support']:>8}")
    lines.append(f"protection recall (characters covered): {report['protection_recall']:.3f}")
    lines.append(f"false positives on negative samples: {report['negative_false_positives']}")
    if report.get("dataset") == "curated":
        a = report["any_type"]
        lines.append(f"any-type recall {a['recall']:.3f}, precision {a['precision']:.3f}, false positives {a['false_positives']}")
        lines.append("Curated v0: hand-written by maintainers, not externally annotated.")
    else:
        lines.append("Synthetic and written by the detector authors: optimistic, use as a regression guard.")
    return "\n".join(lines)
