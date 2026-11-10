"""Document Shield inspection WORKER — runs in a separate, isolated Python process.

    python -I worker.py <input.pdf> <output_dir> <limits-json>

Self-contained on purpose: it imports only the standard library and PyMuPDF, so a malicious PDF that
crashes or hangs the parser cannot reach WAKALA's database, keys or gateway; the parent enforces a
wall-clock timeout and treats any failure as "not inspected" (never as clean).

What it does (read-only on the original bytes):
* per page: every text run from the content stream (``get_texttrace``) with bbox, size, font, colour,
  opacity and render mode; annotations; form-field values; image count
* RENDERING-BASED visibility: the page is rendered twice — as-is, and from an in-memory copy with all text
  removed (``apply_redactions`` text-only). A text run is visible only if removing the text changes pixels
  inside its box. This catches white-on-white, near-background colours, zero opacity, invisible render
  mode and text covered by later shapes or images, while legitimate white text on a dark panel stays visible.
* document metadata, XMP (bounded), embedded-file names/sizes (never extracted), and active-content keys
  (/JavaScript, /JS, /Launch, /OpenAction, /AA, /URI, /SubmitForm, /GoToR, /RichMedia) found in objects
* preview PNGs of each page (rendered from the original; links and actions are never followed)

It never executes document code, never fetches anything over the network and never writes to the input.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ACTIVE_KEYS = ("/JavaScript", "/JS", "/Launch", "/OpenAction", "/AA", "/URI", "/SubmitForm", "/GoToR", "/RichMedia", "/ImportData")


def _hex(color) -> str | None:  # noqa: ANN001
    if not color:
        return None
    c = list(color)
    if len(c) == 1:
        c = c * 3
    if len(c) == 4:  # CMYK → approximate RGB
        k = c[3]
        c = [(1 - min(1.0, x + k)) for x in c[:3]]
    return "#" + "".join(f"{max(0, min(255, round(x * 255))):02x}" for x in c[:3])


def _changed(a, b, bbox, scale, budget):  # noqa: ANN001
    """(changed_pixels, sampled_pixels, cost) for a text box; samples on a grid when the box is large."""
    x0, y0, x1, y1 = (int(bbox[0] * scale), int(bbox[1] * scale), int(bbox[2] * scale) + 1, int(bbox[3] * scale) + 1)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(a.width, x1), min(a.height, y1)
    if x1 <= x0 or y1 <= y0:
        return 0, 0, 0
    area = (x1 - x0) * (y1 - y0)
    step = 1 if area <= 6000 else 2 if area <= 24000 else 3
    sa, sb, st, n = a.samples_mv, b.samples_mv, a.stride, a.n
    changed = sampled = 0
    for y in range(y0, y1, step):
        row = y * st
        for x in range(x0, x1, step):
            i = row + x * n
            sampled += 1
            if max(abs(sa[i] - sb[i]), abs(sa[i + 1] - sb[i + 1]), abs(sa[i + 2] - sb[i + 2])) > 40:
                changed += 1
            if sampled >= budget:
                return changed, sampled, sampled
    return changed, sampled, sampled


def inspect(path: str, out_dir: str, limits: dict) -> dict:  # noqa: C901
    import pymupdf  # imported here so a missing library is reported as an inspection failure

    t0 = time.perf_counter()
    out = Path(out_dir)
    data = Path(path).read_bytes()
    doc = pymupdf.open(stream=data, filetype="pdf")
    if not doc.is_pdf:
        raise ValueError("NOT_A_PDF")
    if doc.needs_pass or doc.is_encrypted:
        raise ValueError("ENCRYPTED_PDF")
    if doc.page_count == 0:
        raise ValueError("NO_PAGES")
    if doc.page_count > limits["max_pages"]:
        raise ValueError("TOO_MANY_PAGES")
    notes: list[str] = []
    stripped = pymupdf.open(stream=data, filetype="pdf")  # in-memory copy used only for the text-removed render
    dpi = limits["render_dpi"]
    scale = dpi / 72
    pages, runs, annotations, widgets = [], [], [], []
    total_chars = 0
    pixel_budget = limits["max_visibility_pixels"]
    for pno in range(doc.page_count):
        page = doc[pno]
        rect = page.rect
        if rect.width * rect.height > limits["max_page_area_pt2"]:
            raise ValueError("PAGE_TOO_LARGE")
        orig = page.get_pixmap(dpi=dpi, alpha=False)
        png = out / f"page-{pno + 1}.png"
        orig.save(str(png))
        sp = stripped[pno]
        sp.add_redact_annot(sp.rect)
        sp.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                            text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        bare = sp.get_pixmap(dpi=dpi, alpha=False)
        traces = page.get_texttrace()
        page_runs = 0
        for t in traces:
            if len(runs) >= limits["max_text_runs"]:
                notes.append("TEXT_RUN_LIMIT_REACHED")
                break
            text = "".join(chr(c[0]) for c in t["chars"] if c[0] >= 0)[: limits["max_run_chars"]]
            if not text.strip():
                continue
            total_chars += len(text)
            if total_chars > limits["max_total_chars"]:
                notes.append("TEXT_CHAR_LIMIT_REACHED")
                break
            bbox = [round(v, 2) for v in t["bbox"]]
            inter = pymupdf.Rect(bbox) & rect
            on_page_frac = (inter.get_area() / pymupdf.Rect(bbox).get_area()) if pymupdf.Rect(bbox).get_area() > 0 and not inter.is_empty else 0.0
            if pixel_budget > 0:
                changed, sampled, cost = _changed(orig, bare, bbox, scale, min(pixel_budget, 40000))
                pixel_budget -= cost
                analysed = True
            else:
                changed = sampled = 0
                analysed = False
                if "VISIBILITY_PIXEL_BUDGET_EXHAUSTED" not in notes:
                    notes.append("VISIBILITY_PIXEL_BUDGET_EXHAUSTED")
            runs.append({
                "page": pno + 1, "seqno": t.get("seqno"), "text": text, "bbox": bbox, "size": round(t["size"], 2),
                "font": str(t.get("font", ""))[:60], "color": _hex(t.get("color")), "opacity": round(float(t.get("opacity", 1.0)), 3),
                "render_mode": int(t.get("type", 0)), "on_page_fraction": round(on_page_frac, 3),
                "render_changed_pixels": changed, "render_sampled_pixels": sampled, "visibility_analysed": analysed,
            })
            page_runs += 1
        for a in page.annots() or []:
            info = a.info or {}
            txt = " ".join(str(info.get(k, "")) for k in ("title", "subject", "content")).strip()
            annotations.append({"page": pno + 1, "type": a.type[1], "bbox": [round(v, 2) for v in a.rect],
                                "text": txt[: limits["max_run_chars"]], "hidden_flag": bool(a.flags & 2)})
        for w in page.widgets() or []:
            widgets.append({"page": pno + 1, "field": str(w.field_name)[:80], "type": w.field_type_string,
                            "value": str(w.field_value or "")[: limits["max_run_chars"]], "bbox": [round(v, 2) for v in w.rect]})
        imgs = page.get_images(full=True)
        pages.append({"page": pno + 1, "width": round(rect.width, 2), "height": round(rect.height, 2), "preview": png.name,
                      "preview_px": [orig.width, orig.height], "text_runs": page_runs, "images": len(imgs),
                      "image_area_fraction": round(min(1.0, sum((pymupdf.Rect(b["bbox"]) & rect).get_area() for b in page.get_image_info())
                                                       / max(1.0, rect.get_area())), 3)})
    active: dict[str, int] = {}
    for xref in range(1, min(doc.xref_length(), limits["max_xrefs"])):
        try:
            obj = doc.xref_object(xref, compressed=True)
        except Exception:  # noqa: BLE001
            continue
        for k in ACTIVE_KEYS:
            if k + " " in obj or k + "<<" in obj or k + "(" in obj or k + "/" in obj or k + "[" in obj or obj.endswith(k):
                active[k] = active.get(k, 0) + 1
    embedded = []
    for name in doc.embfile_names()[:50]:
        try:
            info = doc.embfile_info(name)
            embedded.append({"name": str(name)[:120], "size": info.get("size"), "filename": str(info.get("filename", ""))[:120]})
        except Exception:  # noqa: BLE001
            embedded.append({"name": str(name)[:120], "size": None})
    meta = {k: str(v)[:500] for k, v in (doc.metadata or {}).items() if v}
    xmp = (doc.get_xml_metadata() or "")[: limits["max_xmp_chars"]]
    return {"ok": True, "engine": f"PyMuPDF {pymupdf.__version__}", "page_count": doc.page_count, "pages": pages, "text_runs": runs,
            "annotations": annotations, "widgets": widgets, "metadata": meta, "xmp": xmp, "embedded_files": embedded,
            "active_content": active, "notes": notes, "render_dpi": dpi, "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)}


def main() -> int:
    src, out_dir, limits = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    try:
        result = inspect(src, out_dir, limits)
    except ValueError as e:
        result = {"ok": False, "error": str(e)[:80] if str(e).isupper() or "_" in str(e) else "MALFORMED_PDF"}
    except Exception as e:  # noqa: BLE001 — the parent records this as a failed inspection
        result = {"ok": False, "error": "MALFORMED_PDF", "detail": type(e).__name__}
    Path(out_dir, "inspection.json").write_text(json.dumps(result), encoding="utf-8")
    return 0 if result.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
