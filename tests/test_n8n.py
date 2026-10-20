import csv
import io
import json
import re
import shutil
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "n8n"))
import build_workflows  # noqa: E402
from service import server  # noqa: E402
from test_table_mode import LEADS  # noqa: E402

WORKFLOWS = ROOT / "n8n" / "workflows"
HARNESS = ROOT / "tests" / "n8n_harness.js"
ALLOWED_PLACEHOLDERS = {"<SPREADSHEET_ID>", "<TELEGRAM_CHAT_ID>", "<ANTHROPIC_MODEL>", "<BU>", "<PERIOD>"}


def load(name):
    return json.loads((WORKFLOWS / name).read_text(encoding="utf-8"))


def node(workflow, name):
    return next(n for n in workflow["nodes"] if n["name"] == name)


def run_code(code, items=None, nodes=None, compile_only=False):
    spec = {"code": code, "items": items or [], "nodes": nodes or {}, "compileOnly": compile_only}
    result = subprocess.run(["node", str(HARNESS)], input=json.dumps(spec), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def serial(text):
    month, day, year = map(int, text.split("/"))
    return (date(year, month, day) - date(1899, 12, 30)).days


def money(text):
    return float(text.replace("Rp", "").replace(".", "").replace(",", ".").strip())


def sheet_rows(leads):
    """What the Google Sheets node returns with unformatted values and serial dates, headers exactly as in the sheet."""
    dates = {"Inbound Date", "MQL Date", "SQL Date", "Proposal Price Quote Date", "Deal Won Date"}
    values = {" Total Contract SQL", " ARR + OTF (Tanpa PPN) ", " Total Contract Deal Won"}
    rows = []
    for lead in leads:
        row = {}
        for key, value in lead.items():
            if key in dates and value:
                row[key] = serial(value)
            elif key in values and value:
                row[key] = money(value)
            else:
                row[key] = value
        row.update({"PIC Name": "Rahasia", "PIC Phone Number": "0812", "Email": "x@example.com", "Link CRM": "https://crm"})
        rows.append(row)
    return rows


@unittest.skipUnless(shutil.which("node"), "node is required")
class WorkflowStructureTests(unittest.TestCase):
    def test_committed_workflows_match_their_sources(self):
        for name, text in build_workflows.build().items():
            self.assertEqual((WORKFLOWS / name).read_text(encoding="utf-8"), text, f"{name} is stale; run n8n/build_workflows.py")

    def test_graph_is_consistent_and_sanitized(self):
        for path in sorted(WORKFLOWS.glob("*.json")):
            workflow = json.loads(path.read_text(encoding="utf-8"))
            names = [n["name"] for n in workflow["nodes"]]
            self.assertEqual(len(names), len(set(names)), path.name)
            self.assertFalse(workflow["active"], path.name)
            for source, outputs in workflow["connections"].items():
                self.assertIn(source, names)
                for branch in outputs["main"]:
                    for link in branch:
                        self.assertIn(link["node"], names)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn('"credentials"', raw)
            self.assertNotRegex(raw, r"sk-ant|Bearer |password|secret", path.name)
            self.assertEqual(workflow["pinData"], {})
            self.assertEqual(workflow["settings"]["saveDataSuccessExecution"], "none")
            self.assertEqual(workflow["settings"]["timezone"], "Asia/Jakarta")
            found = set(re.findall(r"<[A-Z_]+>", raw))
            self.assertTrue(found <= ALLOWED_PLACEHOLDERS, found - ALLOWED_PLACEHOLDERS)

    def test_each_item_nodes_return_one_object_not_an_array(self):
        for path in sorted(WORKFLOWS.glob("*.json")):
            for n in json.loads(path.read_text(encoding="utf-8"))["nodes"]:
                if n["type"] == "n8n-nodes-base.code" and n["parameters"]["mode"] == "runOnceForEachItem":
                    code = n["parameters"]["jsCode"]
                    self.assertNotRegex(code, r"return\s*\[", f"{path.name}:{n['name']} must return a single { '{ json }' } object")

    def test_every_code_node_compiles(self):
        for path in sorted(WORKFLOWS.glob("*.json")):
            for n in json.loads(path.read_text(encoding="utf-8"))["nodes"]:
                if n["type"] == "n8n-nodes-base.code":
                    self.assertTrue(run_code(n["parameters"]["jsCode"], compile_only=True)["ok"], f"{path.name}:{n['name']}")

    def test_sql_parameters_are_all_supplied(self):
        generate = load("Report_Generate_v1.json")
        query = node(generate, "Save Run")["parameters"]["query"]
        self.assertEqual(max(int(x) for x in re.findall(r"\$(\d+)", query)), 15)
        analysis = load("Report_Analysis_Button_v1.json")
        self.assertEqual(max(int(x) for x in re.findall(r"\$(\d+)", node(analysis, "Save Analysis")["parameters"]["query"])), 6)

    def test_workflows_only_use_tracker_columns_the_generator_needs(self):
        columns, dates, money_columns = build_workflows.tracker_columns()
        for forbidden in ("PIC Name", "PIC Phone Number", "Email", "Link CRM", "Tau McEasy Dari"):
            self.assertNotIn(forbidden, columns)
        self.assertTrue(set(dates) <= set(columns) and set(money_columns) <= set(columns))


@unittest.skipUnless(shutil.which("node"), "node is required")
class CodeNodeTests(unittest.TestCase):
    def plan(self, trigger_json, webhook=False):
        code = node(load("Report_Generate_v1.json"), "Normalize Plan")["parameters"]["jsCode"]
        nodes = {"Webhook Generate": {"executed": webhook}}
        return run_code(code, [trigger_json], nodes)

    def test_manual_parameters_name_the_plans_explicitly(self):
        out = self.plan({"bu": "all", "period": "2026-W39"})
        self.assertEqual(out["result"][0]["json"], {"trigger": "manual", "plans": [{"bu": "bu1", "period": "2026-W39"}, {"bu": "bu2", "period": "2026-W39"}]})
        one = self.plan({"bu": "BU2", "period": " 2026-09 "})
        self.assertEqual(one["result"][0]["json"]["plans"], [{"bu": "bu2", "period": "2026-09"}])

    def test_placeholders_and_malformed_periods_fail_loudly_instead_of_guessing(self):
        for params in ({"bu": "all", "period": "<PERIOD>"}, {"bu": "all"}, {"bu": "all", "period": "minggu ini"},
                       {"bu": "all", "period": "2026-13"}, {"bu": "all", "period": "2026-00"},
                       {"bu": "all", "period": "2026-W00"}, {"bu": "all", "period": "2026-W54"}, {"bu": "bu9", "period": "2026-W39"}):
            out = self.plan(params)
            self.assertFalse(out["ok"], params)
            self.assertTrue(out["error"], params)

    def test_webhook_reads_the_body(self):
        ok = self.plan({"body": {"bu": "BU2", "period": "2026-W39"}, "headers": {}}, webhook=True)
        self.assertEqual(ok["result"][0]["json"], {"trigger": "webhook", "plans": [{"bu": "bu2", "period": "2026-W39"}]})
        both = self.plan({"body": {"period": "2026-09"}}, webhook=True)
        self.assertEqual(len(both["result"][0]["json"]["plans"]), 2)
        self.assertFalse(self.plan({"body": {"bu": "bu1"}}, webhook=True)["ok"])

    def test_no_workflow_runs_on_a_schedule(self):
        for path in sorted(WORKFLOWS.glob("*.json")):
            types = {n["type"] for n in json.loads(path.read_text(encoding="utf-8"))["nodes"]}
            self.assertFalse({t for t in types if "schedule" in t.lower() or "cron" in t.lower()}, path.name)

    def test_manual_runs_start_from_an_editable_parameters_node(self):
        for name in ("Report_Generate_v1.json", "Report_Analysis_Button_v1.json"):
            flow = load(name)
            self.assertIn({"node": "Manual Parameters", "type": "main", "index": 0}, flow["connections"]["Manual Trigger"]["main"][0])
            params = {a["name"]: a["value"] for a in node(flow, "Manual Parameters")["parameters"]["assignments"]["assignments"]}
            self.assertIn("<PERIOD>", params.values())

    def test_validate_request_accepts_manual_fields_and_query_string(self):
        code = node(load("Report_Analysis_Button_v1.json"), "Validate Request")["parameters"]["jsCode"]
        manual = run_code(code, [{"bu": "BU2", "period": "2026-W39", "requested_by": "anggit"}])
        self.assertEqual(manual["result"][0]["json"], {"bu": "bu2", "period": "2026-W39", "requested_by": "anggit"})
        query = run_code(code, [{"query": {"bu": "bu1", "period": "2026-09"}}])
        self.assertEqual(query["result"][0]["json"]["requested_by"], "manual")
        for bad in ({"bu": "<BU>", "period": "2026-W39"}, {"bu": "bu1", "period": "<PERIOD>"}):
            self.assertFalse(run_code(code, [bad])["ok"], bad)

    def format_error(self, item):
        code = node(load("Report_Generate_v1.json"), "Format Generate Error")["parameters"]["jsCode"]
        out = run_code(code, [item], {"Build CSV": {"items": [{"bu": "bu2", "period": "2026-W39", "csv": "SECRET,ROWS\n", "rows": 2}]}})
        self.assertTrue(out["ok"], out)
        self.assertIsInstance(out["result"], dict, "each-item mode needs a single object")
        return out["result"]["json"]["text"]

    def test_generate_error_message_carries_the_service_reason_and_status_but_never_the_csv(self):
        text = self.format_error({"error": {"message": "Unprocessable Entity", "description": '{"error": "kolom wajib SQL tidak ada: SQL Date"}', "httpCode": "422"}, "request": {"body": "SECRET,ROWS"}})
        self.assertIn("Laporan BU2 2026-W39 GAGAL dibuat", text)
        self.assertIn("422", text)
        self.assertIn("kolom wajib SQL tidak ada: SQL Date", text)
        self.assertNotIn("SECRET", text)
        self.assertIn("401", self.format_error({"error": {"message": "Authorization failed", "httpCode": "401"}}))
        self.assertIn("connect ECONNREFUSED", self.format_error({"error": {"message": "The service refused the connection", "cause": {"message": "connect ECONNREFUSED"}}}))
        self.assertIn("plain text failure", self.format_error({"error": "plain text failure"}))
        self.assertIn("penyebab tidak diketahui", self.format_error({"error": {}}))
        self.assertLessEqual(len(self.format_error({"error": {"message": "x" * 5000}})), 1300)

    def build_csv(self, rows, plans=None):
        code = node(load("Report_Generate_v1.json"), "Build CSV")["parameters"]["jsCode"]
        plans = plans or [{"bu": "bu1", "period": "2026-W39"}, {"bu": "bu2", "period": "2026-W39"}]
        return run_code(code, rows, {"Normalize Plan": {"items": [{"plans": plans}], "executed": True}})

    def test_csv_drops_contacts_and_converts_serials_and_money(self):
        out = self.build_csv(sheet_rows(LEADS))
        self.assertTrue(out["ok"], out)
        items = out["result"]
        self.assertEqual([i["json"]["bu"] for i in items], ["bu1", "bu2"])
        text = items[0]["json"]["csv"]
        for secret in ("Rahasia", "0812", "x@example.com", "https://crm"):
            self.assertNotIn(secret, text)
        table = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(table), len(LEADS))
        first = table[0]
        self.assertEqual((first["Inbound Date"], first["MQL Date"], first["Proposal Price Quote Date"]), ("2026-09-21", "2026-09-22", "2026-09-24"))
        self.assertEqual((first["ARR + OTF (Tanpa PPN)"], first["Total Contract SQL"]), ("1000000", "9000000"))

    def test_csv_rounds_float_noise_and_quotes_special_characters(self):
        rows = sheet_rows(LEADS[:1])
        rows[0][" Total Contract SQL"] = 765032431.5500001
        rows[0]["Company"] = 'PT "Maju", Jaya\nTbk'
        table = list(csv.DictReader(io.StringIO(self.build_csv(rows)["result"][0]["json"]["csv"])))
        self.assertEqual(table[0]["Total Contract SQL"], "765032431.55")
        self.assertEqual(table[0]["Company"], 'PT "Maju", Jaya\nTbk')

    def test_implausible_serial_numbers_stay_text_so_the_generator_can_report_them(self):
        rows = sheet_rows(LEADS)
        rows[2]["Inbound Date"] = 20260119  # a BU2 row; BU1 rows are filtered out before validation
        text = self.build_csv(rows)["result"][0]["json"]["csv"]
        self.assertEqual(list(csv.DictReader(io.StringIO(text)))[2]["Inbound Date"], "20260119")
        with self.assertRaises(server.HttpError) as caught:
            server.generate(text.encode(), "bu2", "2026-W39", False)
        self.assertIn("Inbound Date", caught.exception.message)

    def test_empty_cells_may_be_omitted_by_the_sheets_api(self):
        # A column that is empty in EVERY row cannot be told apart from a missing one, so give Remark one value.
        leads = [dict(lead, Remark="Follow Up" if i == 0 else "") for i, lead in enumerate(LEADS)]
        full = self.build_csv(sheet_rows(leads))["result"][0]["json"]["csv"]
        sparse_rows = [{k: v for k, v in row.items() if v not in ("", None)} for row in sheet_rows(leads)]
        sparse = self.build_csv(sparse_rows)
        self.assertTrue(sparse["ok"], sparse)
        self.assertEqual(sparse["result"][0]["json"]["csv"], full)

    def test_first_row_lacking_late_columns_is_not_an_error(self):
        rows = sheet_rows(LEADS)
        for key in ("Proposal Price Quote Date", " ARR + OTF (Tanpa PPN) ", "Deal Won Date", " Total Contract Deal Won"):
            rows[0].pop(key, None)
        self.assertTrue(self.build_csv(rows)["ok"])

    def test_missing_column_message_names_it_and_suggests_a_near_match(self):
        rows = sheet_rows(LEADS)
        for row in rows:
            row["Total contract Deal won"] = row.pop(" Total Contract Deal Won")
        out = self.build_csv(rows)
        self.assertFalse(out["ok"])
        self.assertIn("Total Contract Deal Won", out["error"])
        self.assertIn('header mirip: "Total contract Deal won"', out["error"])
        self.assertIn("tidak ditemukan di satu baris pun", out["error"])

    def test_csv_fails_loudly_on_missing_column_or_empty_sheet(self):
        rows = sheet_rows(LEADS)
        for r in rows:
            del r["SQL Date"]
        out = self.build_csv(rows)
        self.assertFalse(out["ok"])
        self.assertIn("SQL Date", out["error"])
        self.assertFalse(self.build_csv([{"Company": ""}])["ok"])

    def test_js_csv_feeds_the_python_service_and_gives_the_expected_numbers(self):
        items = self.build_csv(sheet_rows(LEADS))["result"]
        by_bu = {i["json"]["bu"]: i["json"]["csv"].encode("utf-8") for i in items}
        bu1 = server.generate(by_bu["bu1"], "bu1", "2026-W39", False)
        self.assertEqual((bu1["audit"]["metrics"]["now"]["SQL"], bu1["audit"]["metrics"]["now"]["SQL Value"]), (1, 1000000))
        bu2 = server.generate(by_bu["bu2"], "bu2", "2026-W39", False)
        self.assertEqual((bu2["audit"]["metrics"]["now"]["SQL"], bu2["audit"]["metrics"]["now"]["SQL Value"]), (2, 8000000))
        # Insert parameters line up with the SQL, and the Telegram text carries aggregates only.
        flow = load("Report_Generate_v1.json")
        prepared = run_code(node(flow, "Prepare Insert")["parameters"]["jsCode"], [bu2])
        params = prepared["result"][0]["json"]["params"]
        self.assertEqual(len(params), 15)
        self.assertEqual(params[0:3], ["bu2", "2026-W39", "week"])
        self.assertEqual(json.loads(params[10])["now"]["SQL Value"], 8000000)
        self.assertEqual(prepared["result"][0]["json"]["lists"]["SQL"][0], {"company": "Co3", "value": 5000000})
        self.assertEqual([e["company"] for e in prepared["result"][0]["json"]["lists"]["SQL"]], ["Co3", "Co5"])

    def compose(self, report_bu="bu2", name_flag=True, lists=None, metrics=None):
        flow = load("Report_Generate_v1.json")
        code = node(flow, "Compose Message")["parameters"]["jsCode"]
        if not name_flag:
            code = code.replace("const INCLUDE_COMPANY_NAMES = true;", "const INCLUDE_COMPANY_NAMES = false;")
        report = server.generate(self.build_csv(sheet_rows(LEADS))["result"][1]["json"]["csv"].encode(), "bu2", "2026-W39", False)
        prepared = run_code(node(flow, "Prepare Insert")["parameters"]["jsCode"], [report])["result"][0]["json"]
        if lists is not None:
            prepared["lists"] = lists
        saved = {"run_id": "12345678-aaaa-bbbb-cccc-1234567890ab", "inserted": True}
        out = run_code(code, [saved], {"Prepare Insert": {"items": [prepared]}})
        self.assertTrue(out["ok"], out)
        return [i["json"] for i in out["result"]]

    def test_chat_summary_has_the_requested_layout(self):
        (message,) = self.compose()
        lines = message["text"].split("\n")
        self.assertEqual(lines[0], "Laporan BU2 2026-W39 tersimpan")
        self.assertEqual(lines[2:8], ["Submission 2", "MQL 1", "SQL 2", "SQL Value Rp 8.000.000", "Deal Won 1", "Deal Won Value Rp 2.500.000"])
        text = message["text"]
        self.assertIn("List SQL + Value (2)\n1. Co3 - Rp 5.000.000\n2. Co5 - Rp 3.000.000", text)
        self.assertIn("List Deal Won + Value (1)\n1. Co5 - Rp 2.500.000", text)
        self.assertIn("Baris di BU: 3 · tanpa BU (tidak dihitung): 0 · Run: 12345678", text)
        self.assertEqual((message["part"], message["parts"]), (1, 1))

    def test_company_names_can_be_switched_off_leaving_only_totals(self):
        (message,) = self.compose(name_flag=False)
        self.assertIn("SQL Value Rp 8.000.000", message["text"])
        self.assertIn("Deal Won Value Rp 2.500.000", message["text"])
        self.assertNotIn("List SQL", message["text"])
        for name in ("Co3", "Co5"):
            self.assertNotIn(name, message["text"])

    def test_empty_lists_and_unusual_names_are_handled(self):
        (message,) = self.compose(lists={"SQL": [], "Deal Won": [{"company": "  PT   Maju\nJaya  " + "x" * 100, "value": 1234.5}]})
        self.assertIn("List SQL + Value (0)\n-", message["text"])
        entry = [l for l in message["text"].split("\n") if l.startswith("1. PT Maju Jaya")][0]
        self.assertLessEqual(len(entry), 80)
        self.assertTrue(entry.endswith("- Rp 1.235"))

    def test_long_lists_are_split_without_losing_or_cutting_lines(self):
        entries = [{"company": f"PT Perusahaan Nomor {i:04d}", "value": 1000000 + i} for i in range(300)]
        messages = self.compose(lists={"SQL": entries, "Deal Won": entries[:3]})
        self.assertGreater(len(messages), 1)
        for m in messages:
            self.assertLessEqual(len(m["text"]), 4000)
            self.assertEqual(m["parts"], len(messages))
        joined = "\n".join(m["text"] for m in messages)
        for i in range(300):
            self.assertEqual(joined.count(f"PT Perusahaan Nomor {i:04d} - "), 1 if i >= 3 else 2, i)
        self.assertIn("List SQL + Value (lanjutan, total 300)", messages[1]["text"])
        self.assertTrue(messages[1]["text"].startswith("List SQL + Value (lanjutan, total 300)\n"))
        self.assertEqual([m["part"] for m in messages], list(range(1, len(messages) + 1)))

    def test_result_has_one_entry_per_report_even_when_the_summary_was_split(self):
        entries = [{"company": f"PT Perusahaan Nomor {i:04d}", "value": 1000000 + i} for i in range(300)]
        composed = self.compose(lists={"SQL": entries, "Deal Won": []})
        self.assertGreater(len(composed), 1)
        code = node(load("Report_Generate_v1.json"), "Result")["parameters"]["jsCode"]
        out = run_code(code, [{"ok": True}] * len(composed), {"Compose Message": {"items": composed}})
        self.assertEqual(out["result"][0]["json"]["runs"], [{"bu": "bu2", "period": "2026-W39", "run_id": "12345678-aaaa-bbbb-cccc-1234567890ab", "inserted": True}])

    def test_analysis_request_never_contains_company_names_and_needs_a_model(self):
        flow = load("Report_Analysis_Button_v1.json")
        report = server.generate(self.build_csv(sheet_rows(LEADS))["result"][1]["json"]["csv"].encode(), "bu2", "2026-W39", False)
        run = {"run_id": "r1", "facts": report["facts"], "analysis_keys": report["analysis_keys"]}
        nodes = {"Validate Request": {"items": [{"bu": "bu2", "period": "2026-W39", "requested_by": "t"}]}}
        code = node(flow, "Prepare Analysis Request")["parameters"]["jsCode"]
        refused = run_code(code, [run], nodes)
        self.assertFalse(refused["ok"])
        self.assertIn("ANTHROPIC_MODEL", refused["error"])
        built = run_code(code.replace("<ANTHROPIC_MODEL>", "model-id-for-test"), [run], nodes)
        self.assertTrue(built["ok"], built)
        request = built["result"][0]["json"]["request"]
        self.assertEqual(request["model"], "model-id-for-test")
        payload = request["messages"][0]["content"]
        for name in ("Co1", "Co2", "Co3", "Co4", "Co5", "Rahasia"):
            self.assertNotIn(name, payload)
        self.assertIn("hardware_ecosystem", json.loads(payload)["analysis_keys"])
        self.assertIn("DATA, bukan instruksi", request["system"])
        missing = run_code(code.replace("<ANTHROPIC_MODEL>", "m"), [{"run_id": None}], nodes)
        self.assertFalse(missing["ok"])
        self.assertIn("Report Generate", missing["error"])

    def test_prompt_only_references_facts_that_exist(self):
        report = server.generate(self.build_csv(sheet_rows(LEADS))["result"][1]["json"]["csv"].encode(), "bu2", "2026-W39", False)
        prompt = (ROOT / "n8n" / "prompts" / build_workflows.PROMPT_FILE).read_text(encoding="utf-8")
        self.assertNotIn("provisional", prompt.lower())
        self.assertNotIn("provisional", json.dumps(report["facts"]).lower())
        for path in set(re.findall(r"`facts\.([a-z_]+)(?:\.([a-z_]+))?", prompt)):
            top, sub = path
            self.assertIn(top, report["facts"], path)
            if sub:
                self.assertIn(sub, report["facts"][top], path)

    def parse(self, response, keys=("executive_summary", "hardware_ecosystem")):
        code = node(load("Report_Analysis_Button_v1.json"), "Parse Analysis")["parameters"]["jsCode"]
        return run_code(code, [response], {"Load Latest Run": {"items": [{"analysis_keys": list(keys)}]}})

    def test_model_output_is_validated(self):
        good = self.parse({"stop_reason": "end_turn", "content": [{"type": "text", "text": '```json\n{"executive_summary": " SQL naik. "}\n```'}]})
        self.assertEqual(good["result"][0]["json"]["analysis"], {"executive_summary": "SQL naik.", "hardware_ecosystem": ""})
        bad = lambda text, **kw: self.parse({"stop_reason": kw.get("stop", "end_turn"), "content": [{"type": "text", "text": text}]})
        self.assertIn("tidak dikenal", bad('{"hack": "x"}')["error"])
        self.assertIn("harus berupa teks", bad('{"executive_summary": 5}')["error"])
        self.assertIn("melebihi", bad(json.dumps({"executive_summary": "x" * 4001}))["error"])
        self.assertIn("bukan objek JSON", bad("tidak ada json")["error"])
        self.assertIn("terpotong", bad("{}", stop="max_tokens")["error"])
        self.assertFalse(bad('["a"]')["ok"])


if __name__ == "__main__":
    unittest.main()
