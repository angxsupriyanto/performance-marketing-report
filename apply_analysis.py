#!/usr/bin/env python3
"""Optional second pass: insert reviewed prose after numeric report verification."""
import argparse
import json
from pathlib import Path
from bs4 import BeautifulSoup

SELECTORS = {
    "executive_summary": ".executive-prose",
    "funnel_analysis": ".funnel .analysis-body",
    "pipeline_insight": ".timing-section .analysis-body",
    "stage_submission": ".breakdown-section .stage-table:nth-child(1) .analysis-body",
    "stage_mql": ".breakdown-section .stage-table:nth-child(2) .analysis-body",
    "stage_sql": ".breakdown-section .stage-table:nth-child(3) .analysis-body",
    "stage_deal_won": ".breakdown-section .stage-table:nth-child(4) .analysis-body",
    "cross_stage_insight": ".cross-stage .analysis-body",
    "hardware_summary": ".hardware-analysis-summary p",
    "hardware_dashcam": ".hardware-product-analysis .product-analysis:nth-of-type(2) p",
    "hardware_gps_tracker": ".hardware-product-analysis .product-analysis:nth-of-type(3) p",
    "hardware_fuel": ".hardware-product-analysis .product-analysis:nth-of-type(4) p",
    "hardware_mdvr": ".hardware-product-analysis .product-analysis:nth-of-type(5) p",
    "hardware_obd": ".hardware-product-analysis .product-analysis:nth-of-type(6) p",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path,required=True,help="HTML numerik yang sudah diverifikasi")
    parser.add_argument("--analysis",type=Path,required=True,help="JSON teks hasil review terpisah")
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    if args.report.resolve()==args.output.resolve():
        parser.error("--output harus berbeda dari --report agar laporan numerik tetap utuh")
    data=json.loads(args.analysis.read_text(encoding="utf-8"))
    unknown=set(data)-set(SELECTORS)
    if unknown:parser.error("Kunci JSON tidak dikenal: "+", ".join(sorted(unknown)))
    soup=BeautifulSoup(args.report.read_text(encoding="utf-8"),"html.parser")
    for key,selector in SELECTORS.items():
        target=soup.select_one(selector)
        if target is None:parser.error("Template tidak cocok: "+selector)
        value=data.get(key,"")
        if not isinstance(value,str):parser.error(key+" harus berupa teks")
        target.string=value.strip()  # escaped by BeautifulSoup; no HTML is executed
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(str(soup),encoding="utf-8")
    print("OK: "+str(args.output))


if __name__=="__main__":main()
