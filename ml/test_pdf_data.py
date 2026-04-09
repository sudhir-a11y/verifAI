from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _bootstrap_backend_imports() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


def _find_latest_nb_artifact(artifact_dir: Path) -> Path | None:
    import re

    candidates = list(artifact_dir.glob("claim_recommendation_nb_*.json"))
    if not candidates:
        return None

    def _key(path: Path) -> tuple[int, float]:
        # Prefer parsing the embedded UTC timestamp in versions like: nb-v2-YYYYMMDDhhmmss
        m = re.search(r"nb-v\d+-(\d{14})", path.name)
        if m:
            try:
                return (int(m.group(1)), path.stat().st_mtime)
            except Exception:
                pass
        return (0, path.stat().st_mtime)

    return max(candidates, key=_key)


def _load_json(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return body


def _extract_pdf_text_pypdf(pdf_path: Path) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = list(reader.pages)
    text = "\n".join((page.extract_text() or "") for page in pages).strip()
    return text, len(pages)


def _extract_pdf_text_ocr(pdf_path: Path, *, max_pages: int | None) -> str:
    from app.ai.pdf_splitter import split_pdf
    from app.ai.page_classifier import BlankPageError, classify_page
    from app.ai.ocr_engine import OCRConfigError, OCRProcessingError, run_hybrid_ocr

    images = split_pdf(str(pdf_path), page_range=(0, max_pages) if max_pages else None)
    parts: list[str] = []
    for image in images:
        try:
            classification = classify_page(image)
        except BlankPageError:
            continue
        page_type = classification.get("page_type")
        try:
            result = run_hybrid_ocr(image, page_type=page_type)
        except (OCRConfigError, OCRProcessingError):
            continue
        if result.text.strip():
            parts.append(result.text.strip())
    return "\n".join(parts).strip()


def main() -> int:
    _bootstrap_backend_imports()

    from app.ml.models.naive_bayes import predict  # noqa: E402

    parser = argparse.ArgumentParser(description="Run claim-recommendation ML model on PDFs in a directory.")
    parser.add_argument(
        "--pdf-dir",
        type=str,
        default="backend/tests/pdfs",
        help="Directory containing PDF files",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="Path to a Naive Bayes artifact JSON (defaults to latest in artifacts/ml)",
    )
    parser.add_argument(
        "--min-text-chars",
        type=int,
        default=200,
        help="If PDF-extracted text is shorter than this, try OCR fallback",
    )
    parser.add_argument(
        "--max-ocr-pages",
        type=int,
        default=10,
        help="Max pages to OCR per PDF (only used when OCR fallback triggers)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Optional output JSONL path (one row per PDF)",
    )
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        print(f"PDF dir not found: {pdf_dir}", file=sys.stderr)
        return 2

    model_path = Path(args.model) if str(args.model).strip() else _find_latest_nb_artifact(Path("artifacts") / "ml")
    if model_path is None or not model_path.exists():
        print("No model artifact found. Pass --model or ensure artifacts/ml contains claim_recommendation_nb_*.json.")
        return 2
    model = _load_json(model_path)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found under {pdf_dir}")
        return 2

    out_path = Path(args.out) if str(args.out).strip() else None
    out_f = out_path.open("w", encoding="utf-8") if out_path else None
    try:
        label_counts: Counter[str] = Counter()
        rows: list[dict[str, Any]] = []

        for pdf_path in pdfs:
            try:
                text, page_count = _extract_pdf_text_pypdf(pdf_path)
            except Exception as exc:
                row = {
                    "pdf": str(pdf_path),
                    "error": f"pypdf_failed:{exc.__class__.__name__}",
                }
                rows.append(row)
                if out_f:
                    out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                continue

            used_ocr = False
            if len(text) < int(args.min_text_chars or 0):
                try:
                    ocr_text = _extract_pdf_text_ocr(
                        pdf_path,
                        max_pages=(int(args.max_ocr_pages) if args.max_ocr_pages else None),
                    )
                except Exception:
                    ocr_text = ""
                if len(ocr_text) > len(text):
                    text = ocr_text
                    used_ocr = True

            pred = predict(model, text_value=text)
            label = str(pred.label or "unknown")
            label_counts[label] += 1

            row = {
                "pdf": str(pdf_path),
                "pages": int(page_count),
                "text_chars": int(len(text)),
                "used_ocr": bool(used_ocr),
                "available": bool(pred.available),
                "label": pred.label,
                "confidence": float(pred.confidence or 0.0),
                "top_signals": pred.top_signals or [],
                "model_version": pred.model_version or str(model.get("version") or ""),
                "training_examples": int(pred.training_examples or model.get("num_examples") or 0),
            }
            rows.append(row)
            if out_f:
                out_f.write(json.dumps(row, ensure_ascii=False) + "\n")

        summary = {
            "model_path": str(model_path),
            "pdf_dir": str(pdf_dir),
            "pdf_count": len(pdfs),
            "label_counts": dict(label_counts),
        }
        print(json.dumps({"summary": summary, "results": rows}, ensure_ascii=False, indent=2))
        return 0
    finally:
        if out_f:
            out_f.close()


if __name__ == "__main__":
    raise SystemExit(main())
