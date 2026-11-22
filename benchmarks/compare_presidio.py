"""Compare FirmAlways Gate with Microsoft Presidio on the curated Thai test set.

Type-agnostic: a value counts as found if any detection overlaps it, so the
tools' different type names do not matter. Presidio runs with its default
recognizers and spaCy's small English model, because Presidio ships no Thai
NLP model; that is the setup most teams would start from.

    uv run --python 3.12 --with presidio-analyzer \
      --with https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl \
      python benchmarks/compare_presidio.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from firmalways_gate.analyzer import analyze  # noqa: E402
from firmalways_gate.benchmark import evaluate_any_type, load_curated  # noqa: E402


def presidio_detector():
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    nlp = NlpEngineProvider(
        nlp_configuration={"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]}
    ).create_engine()
    engine = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
    # Dates, URLs and nationalities are not personal data in this test set's sense; ignore them.
    ignored = {"DATE_TIME", "URL", "NRP"}

    def detect(text: str) -> list[tuple[int, int]]:
        return [(r.start, r.end) for r in engine.analyze(text=text, language="en") if r.entity_type not in ignored]

    return detect


def main() -> None:
    samples = load_curated()
    results = {
        "FirmAlways Gate": evaluate_any_type(samples, lambda text: [(e.start, e.end) for e in analyze(text)]),
        "Presidio (default, en_core_web_sm)": evaluate_any_type(samples, presidio_detector()),
    }
    kinds = sorted({k for r in results.values() for k in r["recall_by_type"]})
    names = list(results)
    print(f"Curated Thai set: {len(samples)} prompts, {results[names[0]]['values']} labelled values\n")
    print("| Metric | " + " | ".join(names) + " |")
    print("|---|" + "---:|" * len(names))
    for metric in ("recall", "precision", "protection_recall", "false_positives"):
        print(f"| {metric} | " + " | ".join(str(results[n][metric]) for n in names) + " |")
    for kind in kinds:
        print(f"| recall: {kind} | " + " | ".join(f"{results[n]['recall_by_type'].get(kind, 0):.2f}" for n in names) + " |")


if __name__ == "__main__":
    main()
