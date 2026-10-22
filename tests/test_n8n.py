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
ALLOWED_PLACEHOLDERS = {"<SPREADSHEET_ID>", "<TELEGRAM_CHAT_ID>", "<BU>", "<PERIOD>"}


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
        self.assertEqual(manual["result"][0]["json"], {"bu": "bu2", "period": "2026-W39", "requested_by": "anggit", "targets": None, "actions": [], "budget": None})
        query = run_code(code, [{"query": {"bu": "bu1", "period": "2026-09"}}])
        self.assertEqual(query["result"][0]["json"]["requested_by"], "manual")
        for bad in ({"bu": "<BU>", "period": "2026-W39"}, {"bu": "bu1", "period": "<PERIOD>"}):
            self.assertFalse(run_code(code, [bad])["ok"], bad)

    def test_actions_and_budget_are_cleaned_and_reach_the_model_request_with_the_kpi_knowledge_kept_in_the_prompt_only(self):
        flow = load("Report_Analysis_Button_v1.json")
        validate = node(flow, "Validate Request")["parameters"]["jsCode"]
        body = {"bu": "bu1", "period": "2026-W39", "actions": [{"action": "  Naikkan\nbid  ", "campaign": "Camp A", "note": 5}, {"action": ""}, "x", {"action": "Ganti materi", "campaign": "", "note": "mulai Selasa"}] + [{"action": "a"}] * 40,
                "budget": {"state": "ok", "total": 15000000, "campaigns": [{"name": "Camp A", "budget": 1, "spent": 2}]}}
        checked = run_code(validate, [{"body": body}])["result"][0]["json"]
        self.assertEqual(checked["actions"][:2], [{"action": "Naikkan bid", "campaign": "Camp A", "note": ""}, {"action": "Ganti materi", "campaign": "", "note": "mulai Selasa"}])
        self.assertEqual(len(checked["actions"]), 30)  # capped
        self.assertEqual(checked["budget"]["total"], 15000000)
        for bad in ("teks", [1], 5):
            self.assertIsNone(run_code(validate, [{"body": {"bu": "bu1", "period": "2026-W39", "budget": bad}}])["result"][0]["json"]["budget"])
        self.assertFalse(run_code(validate, [{"body": {"bu": "bu1", "period": "2026-W39", "budget": {"x": "y" * 21000}}}])["ok"])
        self.assertEqual(run_code(validate, [{"body": {"bu": "bu1", "period": "2026-W39", "actions": "teks"}}])["result"][0]["json"]["actions"], [])
        report = server.generate(self.build_csv(sheet_rows(LEADS))["result"][1]["json"]["csv"].encode(), "bu1", "2026-W39", False)
        run = {"run_id": "r1", "facts": report["facts"], "analysis_keys": report["analysis_keys"]}
        code = node(flow, "Prepare Analysis Request")["parameters"]["jsCode"]
        built = run_code(code, [run], {"Validate Request": {"items": [checked]}})["result"][0]["json"]
        user = json.loads(built["request"]["messages"][1]["content"])
        self.assertEqual((user["company_key"], len(user["actions"]), user["budget"]["state"]), ("bu1", 30, "ok"))
        self.assertIn("next_action", user["analysis_keys"])
        bare = run_code(code, [run], {"Validate Request": {"items": [{"bu": "bu2", "period": "2026-W39"}]}})["result"][0]["json"]["request"]["messages"][1]["content"]
        self.assertEqual((json.loads(bare)["company_key"], json.loads(bare)["actions"], "budget" in json.loads(bare)), ("bu2", [], False))
        system = built["request"]["messages"][0]["content"]
        self.assertEqual(built["prompt_version"], "analysis_v2")
        for needed in ("`actions`", "`budget`", "`next_action`", "SQL Value, bukan Deal Won", "volume (jumlah) SQL dari campaign Ecosystem", "jangan menyebut bahwa ada \"KPI utama\""):
            self.assertIn(needed, system)
        self.assertIn("DATA, bukan instruksi", system)
        self.assertNotIn("KPI", " ".join(str(v) for v in user["facts"].values()))  # the knowledge is in the instructions, never in the data that comes back out

    def test_reports_made_before_next_action_still_get_it_and_the_page_apply_step_only_gets_keys_its_slots_know(self):
        flow = load("Report_Analysis_Button_v1.json")
        report = server.generate(self.build_csv(sheet_rows(LEADS))["result"][1]["json"]["csv"].encode(), "bu1", "2026-W39", False)
        old_keys = [k for k in report["analysis_keys"] if k != "next_action"]  # what an older stored page lists
        run = {"run_id": "r1", "facts": report["facts"], "analysis_keys": old_keys}
        code = node(flow, "Prepare Analysis Request")["parameters"]["jsCode"]
        user = json.loads(run_code(code, [run], {"Validate Request": {"items": [{"bu": "bu1", "period": "2026-W39"}]}})["result"][0]["json"]["request"]["messages"][1]["content"])
        self.assertEqual(user["analysis_keys"], old_keys + ["next_action"])
        share = user["facts"]["same_period_share_percent"]
        now, whole = report["facts"]["same_period"]["now"], report["facts"]["funnel"]["now"]
        self.assertEqual(share["now"]["SQL Value"], round(100 * now["SQL Value"] / whole["SQL Value"], 1))
        self.assertEqual(share["prev"]["SQL"], None if report["facts"]["funnel"]["prev"]["SQL"] == 0 else share["prev"]["SQL"])  # null, never a division by zero
        self.assertNotIn("same_period_share_percent", report["facts"])  # the stored facts are untouched
        parsed = self.parse({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"executive_summary": "a", "next_action": "b"})}}]}, keys=old_keys)
        self.assertEqual(parsed["result"][0]["json"]["analysis"]["next_action"], "b")
        apply_body = node(flow, "Apply Analysis")["parameters"]["jsonBody"]
        self.assertIn(".analysis_keys.includes(key)", apply_body)  # next_action is saved with the analysis but not pushed into a page that has no slot for it

    def test_the_prompt_asks_for_juta_and_miliar_and_forbids_field_names_and_the_two_caveats(self):
        prompt = (ROOT / "n8n" / "prompts" / build_workflows.PROMPT_FILE).read_text(encoding="utf-8")
        for needed in ("`Rp 256,3 juta`", "`Rp 10,23 miliar`", "Rp di bawah satu juta", "Jangan menulis nama kunci atau jalur JSON", "Same-week", "same_period_share_percent",
                       "Jangan menyebut `facts.data_quality`", "Jangan menuliskan catatan tentang hal ini"):
            self.assertIn(needed.replace("Rp di bawah", "Rupiah di bawah"), prompt)
        self.assertNotIn("sebut sekali di `executive_summary` sebagai keterbatasan data", prompt)

    def test_viewer_targets_reach_the_model_request_as_numbers_only(self):
        flow = load("Report_Analysis_Button_v1.json")
        validate = node(flow, "Validate Request")["parameters"]["jsCode"]
        targets = {"unit": "idr", "semester": {"label": "Semester 2 2026", "actual": 1000000, "target": 12000000, "progress_percent": 8.3}}
        checked = run_code(validate, [{"body": {"bu": "bu1", "period": "2026-W39", "requested_by": "viewer", "targets": targets}}])["result"][0]["json"]
        self.assertEqual((checked["requested_by"], checked["targets"]), ("viewer", targets))
        for bad in ("teks", [1, 2], 5):
            self.assertIsNone(run_code(validate, [{"body": {"bu": "bu1", "period": "2026-W39", "targets": bad}}])["result"][0]["json"]["targets"])
        self.assertFalse(run_code(validate, [{"body": {"bu": "bu1", "period": "2026-W39", "targets": {"x": "y" * 21000}}}])["ok"])
        report = server.generate(self.build_csv(sheet_rows(LEADS))["result"][1]["json"]["csv"].encode(), "bu1", "2026-W39", False)
        run = {"run_id": "r1", "facts": report["facts"], "analysis_keys": report["analysis_keys"]}
        code = node(flow, "Prepare Analysis Request")["parameters"]["jsCode"]
        with_targets = run_code(code, [run], {"Validate Request": {"items": [checked]}})["result"][0]["json"]["request"]["messages"][1]["content"]
        without = run_code(code, [run], {"Validate Request": {"items": [{"bu": "bu1", "period": "2026-W39", "targets": None}]}})["result"][0]["json"]["request"]["messages"][1]["content"]
        self.assertEqual(json.loads(with_targets)["targets"], targets)
        self.assertNotIn("targets", json.loads(without))
        self.assertIn("hardware_gps_tracker", json.loads(with_targets)["analysis_keys"])
        prompt = node(flow, "Prepare Analysis Request")["parameters"]["jsCode"]
        self.assertIn("targets", prompt)

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

    def test_a_missing_or_renamed_node_is_named_instead_of_n8ns_bare_message(self):
        helper = (ROOT / "n8n" / "code" / "_ref.js").read_text(encoding="utf-8")
        gone = {"Normalize Plan": {"missing": True}}
        out = run_code(helper + "\nreturn ref('Normalize Plan').first();", [], gone)
        self.assertFalse(out["ok"])
        self.assertIn('Node "Normalize Plan" tidak ditemukan', out["error"])
        self.assertIn("Referenced node doesn't exist", out["error"])  # n8n's own text stays visible
        self.assertIn('"Normalize Plan1"', out["error"])  # the usual cause: a number added on import
        for access in ("all()", "last()", "item"):
            self.assertFalse(run_code(helper + f"\nreturn ref('Normalize Plan').{access};", [], gone)["ok"], access)
        present = run_code(helper + "\nreturn ref('Normalize Plan').first().json.plans;", [], {"Normalize Plan": {"items": [{"plans": [1]}]}})
        self.assertEqual(present["result"], [1])
        built = self.build_csv(sheet_rows(LEADS))
        self.assertTrue(built["ok"], built)
        code = node(load("Report_Generate_v1.json"), "Build CSV")["parameters"]["jsCode"]
        missing = run_code(code, sheet_rows(LEADS), {"Normalize Plan": {"missing": True}})
        self.assertFalse(missing["ok"])
        self.assertIn('Node "Normalize Plan" tidak ditemukan', missing["error"])

    def test_every_node_lookup_goes_through_the_helper(self):
        for path in (ROOT / "n8n" / "code").glob("*.js"):
            if path.name in ("_ref.js", "normalize_plan.js", "normalize_performa_plan.js"):
                continue  # the two Normalize nodes only ask whether the webhook ran, and say so themselves
            self.assertNotIn("$('", path.read_text(encoding="utf-8"), path.name)
        for name in ("Report_Generate_v1.json", "Performa_Generate_v1.json", "Report_Analysis_Button_v1.json"):
            for n in load(name)["nodes"]:
                code = n["parameters"].get("jsCode", "")
                if "ref('" in code:
                    self.assertTrue(code.startswith("// Reads another node of this workflow"), (name, n["name"]))

    def test_a_skipped_read_tracker_is_named_as_the_cause(self):
        skipped = self.build_csv([{"trigger": "manual", "plans": [{"bu": "bu1", "period": "2026-W39"}]}])  # what a disabled node passes through
        self.assertFalse(skipped["ok"])
        self.assertIn("keluaran node Normalize Plan, bukan baris sheet", skipped["error"])
        self.assertIn("Read Tracker sedang dinonaktifkan", skipped["error"])

    def test_an_empty_or_unreadable_sheet_explains_which_node_and_what_to_check(self):
        none = self.build_csv([])
        self.assertFalse(none["ok"])
        self.assertIn("Read Tracker tidak mengembalikan satu baris pun", none["error"])
        self.assertIn("ID spreadsheet", none["error"])
        wrong = self.build_csv([{"Kolom Lain": "x", "Satu Lagi": "y"}])
        self.assertFalse(wrong["ok"])
        self.assertIn("mengembalikan 1 baris, tetapi tidak ada baris yang berisi kolom wajib", wrong["error"])
        self.assertIn("Kolom Lain", wrong["error"])

    def test_filter_columns_are_copied_when_the_sheet_has_them_and_never_required(self):
        with_columns = [{**r, "Medium": "cpc", "Category Campaign": "Brand"} for r in sheet_rows(LEADS)]
        out = self.build_csv(with_columns)
        self.assertTrue(out["ok"], out)
        table = list(csv.DictReader(io.StringIO(out["result"][0]["json"]["csv"])))
        self.assertEqual((table[0]["Medium"], table[0]["Category Campaign"]), ("cpc", "Brand"))
        without = self.build_csv(sheet_rows(LEADS))  # a sheet that has no such columns still builds, so Report Generate cannot break on them
        self.assertTrue(without["ok"], without)
        header = without["result"][0]["json"]["csv"].splitlines()[0].split(",")
        self.assertNotIn("Medium", header)
        self.assertNotIn("Category Campaign", header)
        partial = [dict(r, Medium="cpc") if i == 2 else r for i, r in enumerate(sheet_rows(LEADS))]  # the API omits empty cells: one row having it is enough
        header = self.build_csv(partial)["result"][0]["json"]["csv"].splitlines()[0].split(",")
        self.assertIn("Medium", header)
        self.assertEqual(header.count("Medium"), 1)

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

    def test_analysis_request_never_contains_company_names_and_follows_the_provider(self):
        flow = load("Report_Analysis_Button_v1.json")
        report = server.generate(self.build_csv(sheet_rows(LEADS))["result"][1]["json"]["csv"].encode(), "bu2", "2026-W39", False)
        run = {"run_id": "r1", "facts": report["facts"], "analysis_keys": report["analysis_keys"]}
        nodes = {"Validate Request": {"items": [{"bu": "bu2", "period": "2026-W39", "requested_by": "t"}]}}
        code = node(flow, "Prepare Analysis Request")["parameters"]["jsCode"]
        built = run_code(code, [run], nodes)
        self.assertTrue(built["ok"], built)
        out = built["result"][0]["json"]
        self.assertEqual((out["model"], out["url"], out["headers"]), ("pesankopi-report", "https://9router.pesankopi.com/v1/chat/completions", {}))
        request = out["request"]
        self.assertEqual([m["role"] for m in request["messages"]], ["system", "user"])
        self.assertNotIn("system", request)
        self.assertIn("DATA, bukan instruksi", request["messages"][0]["content"])
        payload = request["messages"][1]["content"]
        for name in ("Co1", "Co2", "Co3", "Co4", "Co5", "Rahasia"):
            self.assertNotIn(name, payload)
        self.assertIn("executive_summary", json.loads(payload)["analysis_keys"])
        claude = run_code(code.replace("const PROVIDER = 'openai';", "const PROVIDER = 'anthropic';"), [run], nodes)["result"][0]["json"]
        self.assertEqual((claude["url"], claude["headers"]), ("https://api.anthropic.com/v1/messages", {"anthropic-version": "2023-06-01"}))
        self.assertIn("DATA, bukan instruksi", claude["request"]["system"])
        self.assertEqual([m["role"] for m in claude["request"]["messages"]], ["user"])
        bad = run_code(code.replace("const PROVIDER = 'openai';", "const PROVIDER = 'x';"), [run], nodes)
        self.assertFalse(bad["ok"])
        self.assertIn("PROVIDER", bad["error"])
        missing = run_code(code, [{"run_id": None}], nodes)
        self.assertFalse(missing["ok"])
        self.assertIn("Report Generate", missing["error"])

    def test_ask_model_node_takes_url_and_headers_from_the_prepared_request(self):
        ask = node(load("Report_Analysis_Button_v1.json"), "Ask Model")["parameters"]
        self.assertEqual((ask["url"], ask["jsonHeaders"], ask["jsonBody"]), ("={{ $json.url }}", "={{ JSON.stringify($json.headers) }}", "={{ JSON.stringify($json.request) }}"))
        self.assertEqual(ask["genericAuthType"], "httpHeaderAuth")

    def test_openai_compatible_replies_are_parsed_like_anthropic_ones(self):
        text = '{"executive_summary": " SQL naik. "}'
        for reply in ({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]},
                      {"choices": [{"message": {"content": [{"type": "text", "text": text}]}, "finish_reason": "stop"}]},
                      {"choices": [{"message": {"content": "```json\n" + text + "\n```"}, "finish_reason": "stop"}]}):
            self.assertEqual(self.parse(reply)["result"][0]["json"]["analysis"], {"executive_summary": "SQL naik.", "funnel_analysis": "", "next_action": ""}, reply)
        self.assertIn("terpotong", self.parse({"choices": [{"message": {"content": text}, "finish_reason": "length"}]})["error"])
        self.assertIn("kosong", self.parse({"choices": [{"message": {"content": None}, "finish_reason": "stop"}]})["error"])
        self.assertIn("kosong", self.parse({"choices": []})["error"])
        self.assertIn("tidak dikenal", self.parse({"choices": [{"message": {"content": '{"hack": "x"}'}, "finish_reason": "stop"}]})["error"])

    def test_prompt_only_references_facts_that_exist(self):
        csv_bytes = self.build_csv(sheet_rows(LEADS))["result"][1]["json"]["csv"].encode()
        reports = [server.generate(csv_bytes, bu, "2026-W39", False) for bu in ("bu1", "bu2")]
        prompt = (ROOT / "n8n" / "prompts" / build_workflows.PROMPT_FILE).read_text(encoding="utf-8")
        self.assertNotIn("provisional", prompt.lower())
        for report in reports:
            self.assertNotIn("provisional", json.dumps(report["facts"]).lower())
        added_by_the_request_node = {"same_period_share_percent"}  # computed in Prepare Analysis Request so the model never divides
        for top, sub in set(re.findall(r"`facts\.([a-z_]+)(?:\.([a-z_]+))?", prompt)):
            if top in added_by_the_request_node:
                self.assertIn(top, node(load("Report_Analysis_Button_v1.json"), "Prepare Analysis Request")["parameters"]["jsCode"])
                continue
            owners = [r["facts"] for r in reports if top in r["facts"]]
            self.assertTrue(owners, f"facts.{top} tidak ada di laporan BU mana pun")
            if sub:
                self.assertTrue(any(sub in facts[top] for facts in owners), f"facts.{top}.{sub}")

    def parse(self, response, keys=("executive_summary", "funnel_analysis")):
        code = node(load("Report_Analysis_Button_v1.json"), "Parse Analysis")["parameters"]["jsCode"]
        return run_code(code, [response], {"Load Latest Run": {"items": [{"analysis_keys": list(keys)}]}})

    def test_model_output_is_validated(self):
        good = self.parse({"stop_reason": "end_turn", "content": [{"type": "text", "text": '```json\n{"executive_summary": " SQL naik. "}\n```'}]})
        self.assertEqual(good["result"][0]["json"]["analysis"], {"executive_summary": "SQL naik.", "funnel_analysis": "", "next_action": ""})
        bad = lambda text, **kw: self.parse({"stop_reason": kw.get("stop", "end_turn"), "content": [{"type": "text", "text": text}]})
        self.assertIn("tidak dikenal", bad('{"hack": "x"}')["error"])
        self.assertIn("harus berupa teks", bad('{"executive_summary": 5}')["error"])
        self.assertIn("melebihi", bad(json.dumps({"executive_summary": "x" * 4001}))["error"])
        self.assertIn("bukan objek JSON", bad("tidak ada json")["error"])
        self.assertIn("terpotong", bad("{}", stop="max_tokens")["error"])
        self.assertFalse(bad('["a"]')["ok"])

    def test_the_model_that_actually_answered_is_recorded_not_the_combo_name(self):
        text = '{"executive_summary": "ok"}'
        reply = lambda **kw: {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], **kw}
        self.assertEqual(self.parse(reply(model="gemini-2.5-pro"))["result"][0]["json"]["model"], "gemini-2.5-pro")
        self.assertEqual(self.parse(reply(model="  weird\nname "))["result"][0]["json"]["model"], "weirdname")
        self.assertEqual(len(self.parse(reply(model="m" * 300))["result"][0]["json"]["model"]), 120)
        self.assertEqual(self.parse(reply())["result"][0]["json"]["model"], "")  # none reported: Prepare Save falls back to the requested name
        self.assertEqual(self.parse(reply(model=5))["result"][0]["json"]["model"], "")
        prep = node(load("Report_Analysis_Button_v1.json"), "Prepare Save")["parameters"]["jsCode"]
        nodes = lambda model: {"Prepare Analysis Request": {"items": [{"run_id": "r1", "model": "pesankopi-report", "prompt_version": "v1"}]},
                               "Validate Request": {"items": [{"bu": "bu1", "period": "2026-W39", "requested_by": "viewer"}]},
                               "Parse Analysis": {"items": [{"analysis": {"executive_summary": "ok"}, "model": model}]}}
        for answered, stored in (("gemini-2.5-pro", "gemini-2.5-pro"), ("", "pesankopi-report")):
            out = run_code(prep, [{"html": "<p>x</p>"}], nodes(answered))
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["result"][0]["json"]["params"][2], stored)

    def test_performa_workflow_is_manual_only_and_stores_aggregates_through_the_writer_query(self):
        flow = load("Performa_Generate_v1.json")
        types = {n["name"]: n["type"] for n in flow["nodes"]}
        self.assertNotIn("n8n-nodes-base.webhook", types.values())  # started by hand, like the user wants
        self.assertNotIn("n8n-nodes-base.telegram", types.values())
        self.assertEqual(flow["active"], False)
        self.assertEqual(node(flow, "Manual Parameters")["parameters"]["assignments"]["assignments"][0]["value"], "all")
        http = node(flow, "Compute Performa")["parameters"]
        self.assertEqual((http["url"], http["genericAuthType"]), ("http://report-service:8080/v1/performa", "httpHeaderAuth"))
        self.assertEqual(node(flow, "Compute Performa")["onError"], "continueErrorOutput")
        query = node(flow, "Save Snapshot")["parameters"]["query"]
        self.assertIn("ON CONFLICT (bu, as_of, source_sha256, generator_version) DO NOTHING", query)
        self.assertIn("reports.performance_snapshots", query)
        self.assertEqual(max(int(n) for n in re.findall(r"\$(\d+)", query)), 5)
        csv_code = node(flow, "Build CSV")["parameters"]["jsCode"]
        self.assertEqual(csv_code, node(load("Report_Generate_v1.json"), "Build CSV")["parameters"]["jsCode"])  # same column whitelist: no PIC, phone or email
        declared = json.loads(re.search(r"const COLUMNS = (\[.*?\]);", csv_code).group(1)) + json.loads(re.search(r"const OPTIONAL_COLUMNS = (\[.*?\]);", csv_code).group(1))
        for column in ("Channel", "Source", "Medium", "Campaign", "Category Campaign", "Campaign Hardware"):  # the six Performa filters
            self.assertIn(column, declared)
        for private in ("Phone", "Email", "PIC", "Contact", "CRM", "Link"):
            self.assertFalse([c for c in declared if private.lower() in c.lower()], private)

    def test_performa_code_nodes(self):
        flow = load("Performa_Generate_v1.json")
        plan = run_code(node(flow, "Normalize Plan")["parameters"]["jsCode"], [{"bu": "all"}])
        self.assertEqual([p["bu"] for p in plan["result"][0]["json"]["plans"]], ["bu1", "bu2"])
        one = run_code(node(flow, "Normalize Plan")["parameters"]["jsCode"], [{"bu": "BU2"}])
        self.assertEqual([p["bu"] for p in one["result"][0]["json"]["plans"]], ["bu2"])
        self.assertFalse(run_code(node(flow, "Normalize Plan")["parameters"]["jsCode"], [{"bu": "bu9"}])["ok"])
        response = {"bu": "bu1", "as_of": "2026-10-21", "source_sha256": "a" * 64, "generator_version": "dev+abc", "leads": 3, "rows_in_bu": 9, "data": {"v": 2, "dims": {}, "leads": []}}
        prepared = run_code(node(flow, "Prepare Insert")["parameters"]["jsCode"], [{**response}])
        params = prepared["result"][0]["json"]["params"]
        self.assertEqual(params[:4], ["bu1", "2026-10-21", "a" * 64, "dev+abc"])
        self.assertEqual(json.loads(params[4]), response["data"])
        result = run_code(node(flow, "Result")["parameters"]["jsCode"], [{"snapshot_id": "s1", "inserted": True}], {"Prepare Insert": {"items": [r["json"] for r in prepared["result"]]}})
        self.assertEqual(result["result"][0]["json"]["snapshots"], [{"bu": "bu1", "as_of": "2026-10-21", "leads": 3, "snapshot_id": "s1", "inserted": True}])
        failed = run_code(node(flow, "Format Error")["parameters"]["jsCode"], [{"error": {"message": "x" * 3000, "httpCode": "422"}}], {"Build CSV": {"items": [{"bu": "bu2", "csv": "SECRET,ROW\nsecret,row"}]}}, )
        text = failed["result"]["json"]["text"] if isinstance(failed["result"], dict) else failed["result"][0]["json"]["text"]
        self.assertTrue(text.startswith("Performa BU2 GAGAL dihitung: 422"))
        self.assertNotIn("SECRET", text)
        self.assertLessEqual(len(text), 1300)


if __name__ == "__main__":
    unittest.main()
