#!/usr/bin/env python3
"""Render cv/web/data.yaml through cv/web/template.html.j2 and print to PDF.

Usage: scripts/generate-cv-web.py [output-pdf]
  output-pdf   default: cv/current/cv.pdf
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cvweb


def main() -> None:
    out_pdf = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else cvweb.REPO_ROOT / "cv" / "current" / "cv.pdf"
    )
    cvweb.export_pdf(out_pdf)
    print(f"Generated: {out_pdf}")


if __name__ == "__main__":
    main()
