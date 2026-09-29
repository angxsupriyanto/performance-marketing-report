#!/usr/bin/env python3
"""Deterministic BU1 weekly dashboard generator. No AI, no network calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

STAGES = {
    "Submission": "Inbound Date",
    "MQL": "MQL Date",
    "SQL": "Proposal Price Quote Date",
    "Deal Won": "Deal Won Date",
}
SQL_VALUE = "SUM of ARR + OTF (Tanpa PPN)"
WON_VALUE = "SUM of Total Contract Deal Won"
PRODUCTS = ("Dashcam", "GPS Tracker", "Fuel", "MDVR", "OBD")
REQUIRED = {
    "Submission": ("Company", "Channel", "Source", "Campaign", "Campaign Hardware", "Industry", "Remark", "Inbound Date", "MQL Date"),
    "MQL": ("Company", "Channel", "Source", "Campaign", "Campaign Hardware", "Industry", "Inbound Date", "MQL Date"),
    "SQL": ("Company", "Channel", "Source", "Campaign", "Campaign Hardware", "Industry", "Inbound Date", "Proposal Price Quote Date", SQL_VALUE),
    "Deal Won": ("Company", "Channel", "Source", "Campaign", "Campaign Hardware", "Industry", "Inbound Date", "Deal Won Date", WON_VALUE),
}


def parse_date(value: str, context: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"{context}: tanggal tidak valid {value!r}; gunakan M/D/YYYY atau YYYY-MM-DD")


def parse_money(value: str, context: str) -> int:
    value = (value or "").strip().replace("Rp", "").replace("rp", "").strip()
    if value in ("", "-"):
        return 0
    compact = value.replace(" ", "")
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:[.,][0-9]{3})+)", compact):
        raise ValueError(f"{context}: nilai uang tidak valid {value!r}; gunakan bilangan bulat Rupiah")
    return int(re.sub(r"[.,]", "", compact))


def normalize_header(name: str) -> str:
    return " ".join((name or "").strip().split())


def read_stage(path: Path, stage: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: CSV kosong")
        fields = [normalize_header(x) for x in reader.fieldnames]
        if len(fields) != len(set(fields)):
            raise ValueError(f"{path}: header duplikat setelah normalisasi")
        missing = set(REQUIRED[stage]) - set(fields)
        if missing:
            raise ValueError(f"{path}: kolom wajib {stage} tidak ada: {', '.join(sorted(missing))}")
        rows = []
        for number, row in enumerate(reader, 2):
            clean = {normalize_header(k): (v or "").strip() for k, v in row.items() if k is not None}
            if not any(clean.values()) or (clean.get("Company", "").casefold()=="grand total" and not clean.get(STAGES[stage], "")):
                continue
            for column in ("Inbound Date", STAGES[stage]):
                if column in clean:
                    parse_date(clean[column], f"{path.name} baris {number} kolom {column}")
            if not parse_date(clean[STAGES[stage]], f"{path.name} baris {number}"):
                raise ValueError(f"{path.name} baris {number}: {STAGES[stage]} wajib terisi")
            if stage in ("SQL", "Deal Won"):
                parse_money(clean[SQL_VALUE if stage == "SQL" else WON_VALUE], f"{path.name} baris {number}")
            rows.append(clean)
    return rows


def product(row: dict[str, str]) -> str:
    raw = row.get("Campaign Hardware", "").strip()
    if raw == "GPS":
        return "GPS Tracker"
    if raw == "OND" and "OBD" in row.get("Campaign", "").upper():
        return "OBD"
    return raw if raw in PRODUCTS else ""


def source(row: dict[str, str]) -> str:
    return row.get("Source", "").strip() or "Unknown"


def campaign(row: dict[str, str]) -> str:
    return row.get("Campaign", "").strip() or "Unknown"


def stage_value(row: dict[str, str], stage: str) -> int:
    key = SQL_VALUE if stage == "SQL" else WON_VALUE
    return parse_money(row.get(key, ""), key)


def period_rows(rows: list[dict[str, str]], stage: str, monday: date) -> list[dict[str, str]]:
    return [r for r in rows if monday <= parse_date(r[STAGES[stage]], STAGES[stage]) <= monday + timedelta(days=6)]


def inbound_in_week(row: dict[str, str], monday: date) -> bool:
    inbound = parse_date(row.get("Inbound Date", ""), "Inbound Date")
    return bool(inbound and monday <= inbound <= monday + timedelta(days=6))


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def money(n: int) -> str:
    return "Rp " + fmt(n)


def pct(n: float) -> str:
    return f"{n:.1f}".replace(".", ",") + "%"


def rate(a: int, b: int) -> float | None:
    return 100 * a / b if b else None


def rate_text(a: int, b: int) -> str:
    x = rate(a, b)
    return pct(x) if x is not None else "N/A"


def change(a: int | float, b: int | float, pp: bool = False) -> tuple[str, str]:
    if b == 0 and not pp:
        return ("→ 0,0%", "flat") if a == 0 else ("N/A", "flat")
    diff = (a - b) if pp else (100 * (a / b - 1))
    mark = "▲" if diff > 0 else "▼" if diff < 0 else "→"
    return f"{mark} {f'{abs(diff):.1f}'.replace('.', ',') + ' pp' if pp else pct(abs(diff))}", "up" if diff > 0 else "down" if diff < 0 else "flat"


def text(tag, value) -> None:
    tag.clear()
    tag.string = str(value)


def node(soup, tag: str, value: str, **attrs):
    el = soup.new_tag(tag, attrs=attrs)
    el.string = str(value)
    return el


def add_cells(soup, parent, values, numeric_from=1):
    row = soup.new_tag("tr")
    for i, value in enumerate(values):
        cell = node(soup, "td", value)
        if i >= numeric_from:
            cell["class"] = ["num"]
        row.append(cell)
    parent.append(row)
    return row


def pair(soup, current, previous, currency=False):
    td = soup.new_tag("td", attrs={"class": "num detail-pair"})
    td.append(node(soup, "strong", money(current) if currency else current))
    td.append(node(soup, "small", "W" + str(PREV_WEEK_NUMBER) + " " + str(money(previous) if currency else previous)))
    return td


def set_period_copy(soup, current: date, previous: date):
    global PREV_WEEK_NUMBER
    PREV_WEEK_NUMBER = previous.isocalendar().week
    week = current.isocalendar().week
    year = current.isocalendar().year
    def date_label(monday):
        end = monday + timedelta(days=6)
        return f"{monday.day}–{end.day} {monday.strftime('%b')} {monday.year}"
    soup.title.string = f"BU1 Performance Marketing Report — Week {week} vs Week {PREV_WEEK_NUMBER}"
    text(soup.select_one(".header .sub"), f"Week {week} ({date_label(current)}) vs Week {PREV_WEEK_NUMBER} ({date_label(previous)})")
    text(soup.select_one(".header .tag"), "BU1 · DATA AKTUAL")
    text(soup.select_one(".sql-list h2"), f"Daftar SQL · Week {week}")
    text(soup.select_one(".hardware-section > .section-head .note"), f"Angka utama W{week} · pembanding W{PREV_WEEK_NUMBER}")
    text(soup.select_one(".campaign-detail .detail-head .note"), f"Angka utama Week {week} · pembanding kecil Week {PREV_WEEK_NUMBER}")
    for span, monday in zip(soup.select(".funnel .legend span")[:2], (current, previous)):
        dot = span.select_one(".dot")
        span.clear()
        if dot:span.append(dot)
        span.append(f"Week {monday.isocalendar().week} ({monday.day}–{(monday+timedelta(days=6)).day} {monday.strftime('%b')})")
    for label in soup.select(".funnel .week-label"):
        text(label, "W" + str(week if "current" in label.parent.select_one(".fill").get("class", []) else PREV_WEEK_NUMBER))
    for panel in soup.select(".stage-table"):
        headers = panel.select("thead th")
        for index in (1,4):
            if index < len(headers):text(headers[index],headers[index].get_text().replace("W—",f"W{week}"))
        for index in (2,5):
            if index < len(headers):text(headers[index],headers[index].get_text().replace("W—",f"W{PREV_WEEK_NUMBER}"))
    for note in soup.select(".table-note,.formula,.footer"):
        for child in list(note.find_all(string=True)):
            value = str(child).replace("Week —", f"Week {week}").replace("W—", f"W{week}")
            if value != str(child):child.replace_with(value)
    text(soup.select_one(".footer"), f"Sumber: empat CSV BU1 Campaign Tracker. Week {week}: {date_label(current)}; Week {PREV_WEEK_NUMBER}: {date_label(previous)}. Stage memakai tanggal event. SQL Value = ARR + OTF tanpa PPN; Deal Value = Total Contract Deal Won.")


def populate(soup, data: dict[str, list[dict[str, str]]], current: date, previous: date):
    set_period_copy(soup, current, previous)
    weeks = {w: {stage: period_rows(rows, stage, monday) for stage, rows in data.items()} for w, monday in (("now", current), ("prev", previous))}
    metrics = {}
    for w in ("now", "prev"):
        r = weeks[w]
        metrics[w] = {
            "Submission": len(r["Submission"]), "MQL": len(r["MQL"]), "SQL": len(r["SQL"]),
            "SQL Value": sum(stage_value(x, "SQL") for x in r["SQL"]),
            "Deal Won": len(r["Deal Won"]), "Deal Won Value": sum(stage_value(x, "Deal Won") for x in r["Deal Won"]),
        }
    stage_names = ("Submission", "MQL", "SQL", "SQL Value", "Deal Won", "Deal Won Value")
    for card, name in zip(soup.select(".summary > .card"), stage_names):
        a, b = metrics["now"][name], metrics["prev"][name]
        currency = "Value" in name
        text(card.select_one(".value"), money(a) if currency else fmt(a))
        text(card.select_one(".compare"), f"Week {PREV_WEEK_NUMBER}  {money(b) if currency else fmt(b)}")
        delta, kind = change(a,b)
        badge = card.select_one(".delta");text(badge, delta);badge["class"] = ["delta",kind]
        rate_el = card.select_one(".rate")
        if rate_el:
            numerator = name
            denom = {"MQL":"Submission", "SQL":"MQL", "Deal Won":"SQL"}[name]
            ra = rate(a, metrics["now"][denom]);rb = rate(b, metrics["prev"][denom])
            delta_rate = change(ra,rb,True)[0] if ra is not None and rb is not None else "N/A"
            text(rate_el, f"{name} Rate {pct(ra) if ra is not None else 'N/A'} vs {pct(rb) if rb is not None else 'N/A'} · {delta_rate}")
            rate_el["class"] = ["rate", "uptext" if ra is not None and rb is not None and ra>rb else "downtext" if ra is not None and rb is not None and ra<rb else ""]
    # Cohort events from stage-specific exports: inbound and stage event occur in the same week.
    same = {}
    for w,monday in (("now",current),("prev",previous)):
        mql = [r for r in weeks[w]["MQL"] if inbound_in_week(r,monday)]
        sql = [r for r in weeks[w]["SQL"] if inbound_in_week(r,monday)]
        same[w] = (len(mql),len(sql),sum(stage_value(r,"SQL") for r in sql))
    for i,card in enumerate(soup.select(".same .card")):
        a,b=same["now"][i],same["prev"][i]
        total=metrics["now"]["MQL" if i==0 else "SQL" if i==1 else "SQL Value"]
        currency=i==2
        text(card.select_one(".value"),money(a) if currency else fmt(a))
        text(card.select_one(".compare"),f"Week {PREV_WEEK_NUMBER}  {money(b) if currency else fmt(b)} · {change(a,b)[0]}")
        card.select_one(".compare")["class"] = ["compare", "uptext" if a>b else "downtext" if a<b else ""]
        text(card.select_one(".share"),f"{rate_text(a,total)} dari total {money(total) if currency else fmt(total)} {'SQL Value' if currency else 'MQL' if i==0 else 'SQL'} Week {current.isocalendar().week}")
    # All prose panels remain deliberately blank.
    for el in soup.select(".executive-prose,.analysis-body,.hardware-analysis-summary p,.product-analysis p"):
        el.clear()
    # Deterministic highlight selection from numeric rankings.
    sql_by_campaign=defaultdict(lambda:[0,0])
    for r in weeks["now"]["SQL"]:
        x=sql_by_campaign[campaign(r)];x[0]+=1;x[1]+=stage_value(r,"SQL")
    sub_by_campaign=Counter(campaign(r) for r in weeks["now"]["Submission"])
    junk_by_campaign=Counter(campaign(r) for r in weeks["now"]["Submission"] if r.get("Remark","").casefold()=="junk leads")
    best=max(sql_by_campaign, key=lambda x:(sql_by_campaign[x][1],x),default=None)
    weak=max((x for x in sub_by_campaign if sql_by_campaign[x][0]==0),key=lambda x:(sub_by_campaign[x],x),default=None)
    junk=max(junk_by_campaign,key=lambda x:(junk_by_campaign[x],x),default=None)
    highlights=[
        (best,money(sql_by_campaign[best][1]) if best else "—",f"{sql_by_campaign[best][0]} SQL · {sub_by_campaign[best]} submission" if best else ""),
        (weak,f"{sub_by_campaign[weak]} submission" if weak else "—",f"0 SQL" if weak else ""),
        (junk,f"{junk_by_campaign[junk]} junk / {sub_by_campaign[junk]} submission" if junk else "—",f"{sql_by_campaign[junk][0]} SQL" if junk else ""),
    ]
    for card,(title,value,small) in zip(soup.select(".highlight"),highlights):
        text(card.select_one("h3"),title or "—");text(card.select_one("strong"),value);text(card.select_one("small"),small)
    for card,stage in zip(soup.select(".contributors .card"),("SQL","Deal Won")):
        value=lambda r:stage_value(r,stage)
        top=max(weeks["now"][stage],key=lambda r:(value(r),r.get("Company","")),default=None)
        fields=card.select(".details b")
        if top:
            text(card.select_one("h3"),top.get("Company") or "Unknown")
            text(card.select_one(".amount"),money(value(top)))
            inbound=parse_date(top.get("Inbound Date",""),"Inbound Date")
            event=parse_date(top[STAGES[stage]],STAGES[stage])
            for el,v in zip(fields,(top.get("Industry") or "—",source(top),campaign(top),f"{(event-inbound).days} hari" if inbound else "—")):text(el,v)
        else:
            text(card.select_one("h3"),"—");text(card.select_one(".amount"),"—")
            for el in fields:text(el,"—")
    tbody=soup.select_one(".sql-list tbody");tbody.clear()
    for r in sorted(weeks["now"]["SQL"],key=lambda r:(-stage_value(r,"SQL"),r.get("Company",""))):
        inbound=parse_date(r.get("Inbound Date",""),"Inbound Date")
        event=parse_date(r[STAGES["SQL"]],"SQL date")
        timing=f"{(event-inbound).days} hari · {'Same-week' if inbound_in_week(r,current) else 'Backlog'}" if inbound else "—"
        add_cells(soup,tbody,[r.get("Company") or "Unknown",r.get("Industry") or "—",campaign(r),money(stage_value(r,"SQL")),timing],numeric_from=3)
    footer=soup.select_one(".sql-list tfoot tr");footer.clear()
    td=node(soup,"td",f"TOTAL · {len(weeks['now']['SQL'])} SQL",colspan="3");footer.append(td)
    footer.append(node(soup,"td",money(metrics["now"]["SQL Value"]),**{"class":"num"}))
    footer.append(node(soup,"td",""))
    text(soup.select_one(".sql-list .table-note"),f"Diurutkan menurut SQL Value. SQL dihitung dari Proposal Price Quote Date pada Week {current.isocalendar().week}; Same-week berarti Inbound Date juga pada minggu tersebut.")
    # Funnel: each pair of bars is normalized within its own metric.
    funnel_labels=[("Submission",""),("MQL","Submission → MQL"),("SQL","MQL → SQL"),("Deal Won","SQL → Deal Won"),("SQL Value",""),("Deal Won Value","")]
    for row,(name,conversion) in zip(soup.select(".funnel .metric-row"),funnel_labels):
        a,b=metrics["now"][name],metrics["prev"][name]
        mark,kind=change(a,b);badge=row.select_one(".delta");text(badge,mark);badge["class"]=["delta",kind]
        maximum=max(a,b,1)
        for line,value in zip(row.select(".pair-line"),(a,b)):
            text(line.select_one("b"),money(value) if "Value" in name else fmt(value))
            line.select_one(".fill")["style"]=f"width:{value/maximum*100:.1f}%"
        conv=row.select_one(".conversion")
        if conv:
            denom={"MQL":"Submission","SQL":"MQL","Deal Won":"SQL"}[name]
            text(conv,f"{conversion}: {rate_text(a,metrics['now'][denom])} vs {rate_text(b,metrics['prev'][denom])}")
    for row,stage in zip(soup.select(".timing-row"),("MQL","SQL","Deal Won")):
        fresh=sum(inbound_in_week(r,current) for r in weeks["now"][stage]);total=len(weeks["now"][stage]);old=total-fresh
        row.select_one(".timing-current")["style"]=f"width:{fresh/total*100 if total else 0:.1f}%"
        row.select_one(".timing-prior")["style"]=f"width:{old/total*100 if total else 0:.1f}%"
        text(row.select_one("span"),f"{fresh} same-week · {old} backlog")
    # Four event-week source breakdown tables.
    for panel,stage in zip(soup.select(".stage-table"),STAGES):
        body=panel.select_one("tbody");foot=panel.select_one("tfoot");body.clear();foot.clear()
        sources=sorted(set(source(r) for w in weeks for r in weeks[w][stage]),key=lambda x:(-sum(source(r)==x for r in weeks["now"][stage]),x))
        for name in sources+["TOTAL"]:
            sets=[weeks[w][stage] if name=="TOTAL" else [r for r in weeks[w][stage] if source(r)==name] for w in ("now","prev")]
            a,b=map(len,sets)
            values=[name,fmt(a),fmt(b),change(a,b)[0]]
            if stage in ("SQL","Deal Won"):
                values += [money(sum(stage_value(r,stage) for r in group)) for group in sets]
            add_cells(soup,foot if name=="TOTAL" else body,values)
    # Cross-stage table: MQL cohort uses Submission rows; later stages use event dates.
    cross=soup.select_one(".cross-stage");body=cross.select_one("tbody");foot=cross.select_one("tfoot");body.clear();foot.clear()
    sources=sorted(set(source(r) for stage in STAGES for r in weeks["now"][stage]))
    for name in sources+["TOTAL"]:
        selection=lambda stage:weeks["now"][stage] if name=="TOTAL" else [r for r in weeks["now"][stage] if source(r)==name]
        sub=selection("Submission");sql=selection("SQL");won=selection("Deal Won")
        mql=sum(bool(parse_date(r.get("MQL Date",""),"MQL Date") and current<=parse_date(r.get("MQL Date",""),"MQL Date")<=current+timedelta(days=6)) for r in sub)
        add_cells(soup,foot if name=="TOTAL" else body,[name,len(sub),mql,rate_text(mql,len(sub)),len(sql),money(sum(stage_value(r,"SQL") for r in sql)),len(won),money(sum(stage_value(r,"Deal Won") for r in won))])
    text(cross.select_one(".table-note"),f"MQL dan MQL Rate memakai submission Week {current.isocalendar().week} yang mencapai MQL dalam minggu yang sama. SQL dan Deal Won memakai tanggal event Week {current.isocalendar().week}, termasuk backlog; kolom-kolom bukan satu cohort.")
    # Product aggregate, restricted to five tagged hardware categories.
    hardware=soup.select_one(".hardware-section");table=hardware.select_one(":scope > .table-wrap table")
    body=table.select_one("tbody");foot=table.select_one("tfoot");body.clear();foot.clear()
    aggregate={w:[0]*7 for w in ("now","prev")}
    def product_metrics(name,w,monday):
        sets={stage:[r for r in weeks[w][stage] if product(r)==name] for stage in STAGES}
        return [len(sets["Submission"]),len(sets["MQL"]),len(sets["SQL"]),sum(stage_value(r,"SQL") for r in sets["SQL"]),len(sets["Deal Won"]),sum(stage_value(r,"Deal Won") for r in sets["Deal Won"]),sum(r.get("Remark","").casefold()=="junk leads" for r in sets["Submission"])]
    def product_row(label, now, prev, target):
        tr=soup.new_tag("tr");tr.append(node(soup,"td",label))
        for i,(a,b) in enumerate(zip(now,prev)):
            td=soup.new_tag("td",attrs={"class":"num"});td.append(node(soup,"strong",money(a) if i in (3,5) else fmt(a)))
            td.append(node(soup,"small",f"W{PREV_WEEK_NUMBER} "+(money(b) if i in (3,5) else fmt(b))))
            tr.append(td)
        target.append(tr)
    for name in PRODUCTS:
        a=product_metrics(name,"now",current);b=product_metrics(name,"prev",previous)
        aggregate["now"]=[x+y for x,y in zip(aggregate["now"],a)]
        aggregate["prev"]=[x+y for x,y in zip(aggregate["prev"],b)]
        product_row(name,a,b,body)
    product_row("TOTAL 5 PRODUK",aggregate["now"],aggregate["prev"],foot)
    # Active current-week campaigns in the selected hardware categories.
    detail=hardware.select_one(".campaign-detail");body=detail.select_one("tbody");foot=detail.select_one("tfoot");body.clear();foot.clear()
    active=Counter((product(r),campaign(r)) for r in weeks["now"]["Submission"] if product(r) in PRODUCTS)
    ordered=sorted(active,key=lambda x:(-active[x],x[0],x[1]))
    totals={w:{"sub":0,"mql":0,"junk":0,"sql":0,"value":0} for w in ("now","prev")}
    def campaign_metrics(h,c,w):
        sub=[r for r in weeks[w]["Submission"] if product(r)==h and campaign(r)==c]
        sql=[r for r in weeks[w]["SQL"] if product(r)==h and campaign(r)==c]
        return {"sub":len(sub),"mql":sum(bool(parse_date(r.get("MQL Date",""),"MQL Date")) for r in sub),"junk":sum(r.get("Remark","").casefold()=="junk leads" for r in sub),"sql":len(sql),"value":sum(stage_value(r,"SQL") for r in sql)}
    for h,c in ordered:
        values={w:campaign_metrics(h,c,w) for w in ("now","prev")}
        for w in values:
            for key in totals[w]:totals[w][key]+=values[w][key]
        tr=soup.new_tag("tr",attrs={"data-hardware":h});tr.append(node(soup,"td",h));tr.append(node(soup,"td",c))
        tr.append(pair(soup,values["now"]["sub"],values["prev"]["sub"]))
        tr.append(pair(soup,rate_text(values["now"]["mql"],values["now"]["sub"]),rate_text(values["prev"]["mql"],values["prev"]["sub"])))
        for key in ("junk","sql"):tr.append(pair(soup,values["now"][key],values["prev"][key]))
        tr.append(pair(soup,values["now"]["value"],values["prev"]["value"],True));body.append(tr)
    tr=soup.new_tag("tr");tr.append(node(soup,"td","TOTAL CAMPAIGN AKTIF",colspan="2"))
    tr.append(pair(soup,totals["now"]["sub"],totals["prev"]["sub"]))
    tr.append(pair(soup,rate_text(totals["now"]["mql"],totals["now"]["sub"]),rate_text(totals["prev"]["mql"],totals["prev"]["sub"])))
    for key in ("junk","sql"):tr.append(pair(soup,totals["now"][key],totals["prev"][key]))
    tr.append(pair(soup,totals["now"]["value"],totals["prev"]["value"],True));foot.append(tr)
    text(detail.select_one(".table-note"),"MQL Rate campaign = submission pada minggu tersebut yang sudah memiliki MQL Date pada snapshot CSV ÷ submission campaign. SQL Value mengikuti Proposal Price Quote Date masing-masing minggu; cohort dan SQL event dapat berbeda.")
    return metrics, same


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission",type=Path,required=True)
    parser.add_argument("--mql",type=Path,required=True)
    parser.add_argument("--sql",type=Path,required=True)
    parser.add_argument("--won",type=Path,required=True)
    parser.add_argument("--week",required=True,help="ISO week eksplisit, contoh 2026-W39")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    match=re.fullmatch(r"(\d{4})-W(\d{2})",args.week)
    if not match:parser.error("--week harus YYYY-Www, contoh 2026-W39")
    try:
        current=date.fromisocalendar(int(match.group(1)),int(match.group(2)),1)
        previous=current-timedelta(days=7)
        paths={"Submission":args.submission,"MQL":args.mql,"SQL":args.sql,"Deal Won":args.won}
        data={stage:read_stage(path,stage) for stage,path in paths.items()}
        template=Path(__file__).with_name("dashboard_template.html")
        soup=BeautifulSoup(template.read_text(encoding="utf-8"),"html.parser")
        if not period_rows(data["Submission"], "Submission", current):
            raise ValueError(f"tidak ada Submission pada {args.week}; periksa minggu dan file input")
        metrics,same=populate(soup,data,current,previous)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(str(soup),encoding="utf-8")
        audit = {
            "week": args.week,
            "period_start": current.isoformat(),
            "period_end": (current + timedelta(days=6)).isoformat(),
            "comparison_start": previous.isoformat(),
            "inputs": {stage: {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows_excluding_totals": len(data[stage])} for stage,path in paths.items()},
            "metrics": metrics,
            "same_week": {"MQL": same["now"][0], "SQL": same["now"][1], "SQL Value": same["now"][2]},
            "descriptive_analysis": "blank",
        }
        args.output.with_suffix(".audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    except (ValueError,OSError) as exc:
        parser.exit(2,f"Gagal: {exc}\n")
    print(f"OK: {args.output} (audit: {args.output.with_suffix('.audit.json')})")
    print(f"Week {current.isocalendar().week}: Submission {metrics['now']['Submission']}, MQL {metrics['now']['MQL']}, SQL {metrics['now']['SQL']}, SQL Value {money(metrics['now']['SQL Value'])}, Deal Won {metrics['now']['Deal Won']}")
    print("Bagian analisis deskriptif tetap kosong.")


if __name__=="__main__":
    main()
