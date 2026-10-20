#!/usr/bin/env python3
"""Optional second pass: insert reviewed prose after numeric report verification."""
import argparse
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

STATIC_SELECTORS = {
    "executive_summary": ".executive-prose",
    "funnel_analysis": ".funnel .analysis-body",
    "pipeline_insight": ".timing-section .analysis-body",
    "stage_submission": ".breakdown-section .stage-table:nth-child(1) .analysis-body",
    "stage_mql": ".breakdown-section .stage-table:nth-child(2) .analysis-body",
    "stage_sql": ".breakdown-section .stage-table:nth-child(3) .analysis-body",
    "stage_deal_won": ".breakdown-section .stage-table:nth-child(4) .analysis-body",
    "cross_stage_insight": ".cross-stage .analysis-body",
    "hardware_summary": ".hardware-analysis-summary p",
}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def selectors_for(soup):
    """Product slots come from the report itself, so each BU keeps its own product list."""
    selectors = dict(STATIC_SELECTORS)
    for position, block in enumerate(soup.select(".hardware-product-analysis .product-analysis"), 2):
        selectors["hardware_" + slug(block.select_one("strong").get_text())] = f".hardware-product-analysis .product-analysis:nth-of-type({position}) p"
    return selectors


MAX_TEXT_CHARS = 4000


def analysis_keys(report_html: str) -> list[str]:
    return list(selectors_for(BeautifulSoup(report_html, "html.parser")))


def apply_analysis(report_html: str, data: dict) -> str:
    """Insert reviewed prose into a numeric report. Raises ValueError on any mismatch; numbers are never touched."""
    if not isinstance(data, dict):
        raise ValueError("analisis harus berupa objek JSON")
    soup = BeautifulSoup(report_html, "html.parser")
    selectors = selectors_for(soup)
    unknown = set(data) - set(selectors)
    if unknown:
        raise ValueError("Kunci JSON tidak dikenal untuk laporan ini: " + ", ".join(sorted(unknown)))
    for key, selector in selectors.items():
        target = soup.select_one(selector)
        if target is None:
            raise ValueError("Template tidak cocok: " + selector)
        value = data.get(key, "")
        if not isinstance(value, str):
            raise ValueError(key + " harus berupa teks")
        if len(value) > MAX_TEXT_CHARS:
            raise ValueError(f"{key} melebihi {MAX_TEXT_CHARS} karakter")
        target.string = value.strip()  # escaped by BeautifulSoup; no HTML is executed
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
