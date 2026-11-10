"""Build PDF versions of the WAKALA submission documents.

Markdown (submission/0*.md) -> HTML with wakala-print.css -> PDF via headless Microsoft Edge.
Usage:  python submission/source/build_docs.py
"""
import pathlib
import subprocess
import tempfile

import markdown

SRC = pathlib.Path(__file__).resolve().parent
SUB = SRC.parent
OUT = SUB / "pdf"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CSS = (SRC / "wakala-print.css").read_text(encoding="utf-8")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="wakala-docs-"))
    for md in sorted(SUB.glob("0*.md")):
        body = markdown.markdown(md.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "md_in_html"])
        title = md.stem.replace("_", " ")
        footer = "" if "class=\"footer\"" in body else (
            "<p class='footer'>WAKALA · UAE Hackathon 2026 · Challenge #27 · Working prototype on synthetic data — "
            "not a production government system.</p>")
        html = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>WAKALA — {title}</title>"
                f"<style>{CSS}</style></head><body>{body}{footer}</body></html>")
        page = tmp / (md.stem + ".html")
        page.write_text(html, encoding="utf-8")
        pdf = OUT / (md.stem + ".pdf")
        subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", page.as_uri()], check=True, capture_output=True, timeout=120)
        print("wrote", pdf.relative_to(SUB.parent), pdf.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
