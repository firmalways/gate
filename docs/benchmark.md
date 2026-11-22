# Benchmarks

Two datasets ship with Gate. Neither is externally annotated yet, so treat the numbers as indicative.

| Dataset | Command | What it is |
|---|---|---|
| Synthetic | `firmalways-gate benchmark` | 313 generated prompts from templates plus hard negatives. Same authors as the detectors: a regression guard, not a quality claim. |
| Curated v0 | `firmalways-gate benchmark --dataset curated` | 50 hand-written prompts ([`curated_th.txt`](../src/firmalways_gate/data/curated_th.txt)), independent of the templates, including known misses (untitled names, unusual titles). |

## Gate vs Microsoft Presidio (curated v0, 22 November 2026)

Type-agnostic: a labelled value counts as found if any detection overlaps it. Presidio ran with its default recognizers and spaCy `en_core_web_sm`, because it ships no Thai model. That is a typical starting setup, not Presidio's best possible configuration: custom Thai recognizers would raise its numbers.

| Metric | FirmAlways Gate 0.1 | Presidio (default) |
|---|---:|---:|
| Recall (values found) | 0.944 | 0.537 |
| Precision | 1.000 | 0.741 |
| Protection recall (characters covered) | 0.984 | 0.533 |
| False positives | 0 | 14 |
| Recall: Thai national ID | 1.00 | 0.00 |
| Recall: person names | 0.83 | 0.28 |
| Recall: PDPA s.26 health | 1.00 | 0.33 |
| Recall: secrets | 1.00 | 0.00 |
| Recall: LINE ID / licence plate | 1.00 / 1.00 | 0.00 / 0.00 |
| Recall: phone, email, card, bank, IP, passport | 1.00 | 1.00 |

Reproduce:

```bash
uv run --python 3.12 --with presidio-analyzer \
  --with https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl \
  python benchmarks/compare_presidio.py
```

## Gate on curated v0 by type (exact span and type)

Person names: precision 0.93, recall 0.78. The misses are by design of the current rules: a name without a title (`ส่งรายงานให้สมชาย`), the title `พี่`, a name starting with a stop word (`คุณมีนา`), and a following word taken as a surname (`นางสาวปิยะนุช เริ่มงาน`). The optional Thai NER extra targets the first case.

## Help wanted

Externally annotated Thai prompts (with invented data) are the most valuable contribution: add lines to `curated_th.txt` using `[[TYPE:value]]` marks.
