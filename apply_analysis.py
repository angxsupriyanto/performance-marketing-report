#!/usr/bin/env python3
"""Optional second pass: insert reviewed prose into a numeric report. Numbers are never touched."""
import argparse
import json
from pathlib import Path
from bs4 import BeautifulSoup

import report_view

MAX_TEXT_CHARS = 4000


def selectors_for(soup):
    """Slots come from the report itself (`data-analysis` elements), so each BU keeps its own panels."""
    return {el["data-analysis"]: f'[data-analysis="{el["data-analysis"]}"]' for el in soup.select("[data-analysis]")}


def analysis_keys(report_html: str) -> list[str]:
    return list(selectors_for(BeautifulSoup(report_html, "html.parser")))


def apply_analysis(report_html: str, data: dict) -> str:
    """Insert reviewed prose into a numeric report. Raises ValueError on any mismatch."""
    if not isinstance(data, dict):
        raise ValueError("analisis harus berupa objek JSON")
    soup = BeautifulSoup(report_html, "html.parser")
    selectors = selectors_for(soup)
    unknown = set(data) - set(selectors)
    if unknown:
        raise ValueError("Kunci JSON tidak dikenal untuk laporan ini: " + ", ".join(sorted(unknown)))
    for key, selector in selectors.items():
        target = soup.select_one(selector)
        value = data.get(key, "")
        if not isinstance(value, str):
            raise ValueError(key + " harus berupa teks")
        if len(value) > MAX_TEXT_CHARS:
            raise ValueError(f"{key} melebihi {MAX_TEXT_CHARS} karakter")
        value = value.strip()
        target.string = value or report_view.EMPTY_ANALYSIS  # escaped by BeautifulSoup; no HTML is executed
        if value:
            target.attrs.pop("style", None)
        else:
            target["style"] = f"color: {report_view.MUTED}"
    return str(soup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path,required=True,help="HTML numerik yang sudah diverifikasi")
    parser.add_argument("--analysis",type=Path,required=True,help="JSON teks hasil review terpisah")
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    if args.report.resolve()==args.output.resolve():
        parser.error("--output harus berbeda dari --report agar laporan numerik tetap utuh")
    try:
        html = apply_analysis(args.report.read_text(encoding="utf-8"), json.loads(args.analysis.read_text(encoding="utf-8")))
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(html,encoding="utf-8")
    print("OK: "+str(args.output))


if __name__=="__main__":main()
