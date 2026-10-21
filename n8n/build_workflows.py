#!/usr/bin/env python3
"""Assemble the importable n8n workflows from n8n/code, n8n/sql and n8n/prompts.

The JSON under n8n/workflows is generated; edit the sources and rerun this script. A test fails when they drift.
Workflows are sanitized on purpose: no credential ids, spreadsheet ids, chat ids, tokens or customer data.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import generate_report  # noqa: E402

PROMPT_FILE = "analysis_v1.md"
SETTINGS = {
    "executionOrder": "v1",
    "timezone": "Asia/Jakarta",
    # Executions of these workflows handle customer rows; do not keep their data unless debugging.
    "saveDataSuccessExecution": "none",
    "saveDataErrorExecution": "none",
    "saveManualExecutions": False,
}
SERVICE_URL = "http://report-service:8080"


def sheet_header(canonical: str, aliases: dict[str, list[str]]) -> str:
    """The Tracker header is the name that is not the stage-CSV style 'SUM of ...' spelling."""
    candidates = [canonical, *aliases.get(canonical, [])]
    return next(name for name in candidates if not name.startswith("SUM of "))


def tracker_columns() -> tuple[list[str], list[str], list[str]]:
    columns: list[str] = []
    dates: list[str] = []
    money: list[str] = []
    for path in sorted(generate_report.PROFILE_DIR.glob("*.json")):
        profile = json.loads(path.read_text(encoding="utf-8"))
        aliases = profile.get("value_column_aliases", {})
        for stage, names in generate_report.required_columns(profile).items():
            for name in names:
                header = sheet_header(name, aliases)
                if header not in columns:
                    columns.append(header)
        for header in (profile["bu_column"], profile.get("record_key_column")):
            if header and header not in columns:
                columns.append(header)
        for column in profile["stage_date_columns"].values():
            if column not in dates:
                dates.append(column)
        for column in (profile["sql_value_column"], profile["won_value_column"]):
            header = sheet_header(column, aliases)
            if header not in money:
                money.append(header)
    return columns, dates, money


def code(name: str, **replacements: str) -> str:
    source = (HERE / "code" / name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        assert f"__{key}__" in source, (name, key)
        source = source.replace(f"__{key}__", value)
    return source


def sql(name: str) -> str:
    return (HERE / "sql" / name).read_text(encoding="utf-8").strip() + "\n"


def node_id(workflow: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"inbound-marketing/{workflow}/{name}"))


class Flow:
    def __init__(self, name: str):
        self.name = name
        self.nodes: list[dict] = []
        self.connections: dict[str, dict] = {}

    def add(self, name, type_, version, parameters, position, **extra):
        self.nodes.append({"parameters": parameters, "id": node_id(self.name, name), "name": name, "type": type_, "typeVersion": version, "position": list(position), **extra})

    def connect(self, source, target, output=0):
        outputs = self.connections.setdefault(source, {"main": []})["main"]
        while len(outputs) <= output:
            outputs.append([])
        outputs[output].append({"node": target, "type": "main", "index": 0})

    def export(self):
        return {"name": self.name, "nodes": self.nodes, "connections": self.connections, "active": False, "settings": SETTINGS, "pinData": {}, "meta": {"templateCredsSetupCompleted": False}}


def code_node(flow, name, file, position, mode="runOnceForAllItems", **replacements):
    flow.add(name, "n8n-nodes-base.code", 2, {"mode": mode, "language": "javaScript", "jsCode": code(file, **replacements)}, position)


def postgres_node(flow, name, query_file, position, **extra):
    flow.add(name, "n8n-nodes-base.postgres", 2.5, {"operation": "executeQuery", "query": sql(query_file), "options": {"queryReplacement": "={{ $json.params }}"}}, position, **extra)


def telegram_node(flow, name, text_expression, position):
    flow.add(name, "n8n-nodes-base.telegram", 1.2, {"resource": "message", "operation": "sendMessage", "chatId": "<TELEGRAM_CHAT_ID>", "text": text_expression, "additionalFields": {"appendAttribution": False}}, position)


def manual_parameters(flow, position, fields):
    """Editable values for a manual run. The placeholders make the node fail loudly until they are filled in."""
    assignments = [{"id": node_id(flow.name, f"Manual Parameters/{name}"), "name": name, "value": value, "type": "string"} for name, value in fields]
    flow.add("Manual Parameters", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": assignments}, "options": {}}, position)


def header_auth_webhook(flow, name, path, method, position, response_mode="lastNode", authentication="headerAuth"):
    flow.add(name, "n8n-nodes-base.webhook", 2, {"httpMethod": method, "path": path, "authentication": authentication, "responseMode": response_mode, "options": {}}, position, webhookId=node_id(flow.name, name + "/webhook"))


def generate_flow() -> Flow:
    columns, dates, money = tracker_columns()
    flow = Flow("Report Generate v1")
    header_auth_webhook(flow, "Webhook Generate", "report-generate", "POST", (0, 160))
    flow.add("Manual Trigger", "n8n-nodes-base.manualTrigger", 1, {}, (0, 0))
    manual_parameters(flow, (240, 0), [("bu", "all"), ("period", "<PERIOD>")])
    code_node(flow, "Normalize Plan", "normalize_plan.js", (260, 240))
    flow.add("Read Tracker", "n8n-nodes-base.googleSheets", 4.7, {
        "resource": "sheet", "operation": "read",
        "documentId": {"__rl": True, "mode": "id", "value": "<SPREADSHEET_ID>"},
        "sheetName": {"__rl": True, "mode": "name", "value": "NEW Customers List"},
        "options": {
            "dataLocationOnSheet": {"values": {"rangeDefinition": "specifyRangeA1", "range": "A:DR"}},
            "outputFormatting": {"values": {"general": "UNFORMATTED_VALUE", "date": "SERIAL_NUMBER"}},
        },
    }, (500, 240))
    code_node(flow, "Build CSV", "build_csv.js", (740, 240), COLUMNS=json.dumps(columns), DATE_COLUMNS=json.dumps(dates), MONEY_COLUMNS=json.dumps(money))
    flow.add("Generate Report", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"{SERVICE_URL}/v1/reports",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendQuery": True, "queryParameters": {"parameters": [{"name": "bu", "value": "={{ $json.bu }}"}, {"name": "period", "value": "={{ $json.period }}"}]},
        "sendBody": True, "contentType": "raw", "rawContentType": "text/csv", "body": "={{ $json.csv }}",
        "options": {"timeout": 300000},
    }, (980, 240), onError="continueErrorOutput")
    code_node(flow, "Prepare Insert", "prepare_insert.js", (1220, 160))
    postgres_node(flow, "Save Run", "insert_run.sql", (1460, 160))
    code_node(flow, "Compose Message", "compose_message.js", (1700, 160))
    telegram_node(flow, "Notify", "={{ $json.text }}", (1940, 160))
    code_node(flow, "Result", "result_generate.js", (2180, 160))
    code_node(flow, "Format Generate Error", "format_generate_error.js", (1220, 400), mode="runOnceForEachItem")
    telegram_node(flow, "Notify Error", "={{ $json.text }}", (1460, 400))
    for trigger in ("Manual Parameters", "Webhook Generate"):
        flow.connect(trigger, "Normalize Plan")
    flow.connect("Manual Trigger", "Manual Parameters")
    for a, b in (("Normalize Plan", "Read Tracker"), ("Read Tracker", "Build CSV"), ("Build CSV", "Generate Report"), ("Prepare Insert", "Save Run"), ("Save Run", "Compose Message"), ("Compose Message", "Notify"), ("Notify", "Result"), ("Format Generate Error", "Notify Error")):
        flow.connect(a, b)
    flow.connect("Generate Report", "Prepare Insert", 0)
    flow.connect("Generate Report", "Format Generate Error", 1)
    return flow


def performa_flow() -> Flow:
    """Manual only: reads the Tracker and stores aggregated daily and cohort numbers for the Performa page. No webhook, no Telegram."""
    columns, dates, money = tracker_columns()
    flow = Flow("Performa Generate v1")
    flow.add("Manual Trigger", "n8n-nodes-base.manualTrigger", 1, {}, (0, 0))
    manual_parameters(flow, (240, 0), [("bu", "all")])
    code_node(flow, "Normalize Plan", "normalize_performa_plan.js", (480, 0))
    flow.add("Read Tracker", "n8n-nodes-base.googleSheets", 4.7, {
        "resource": "sheet", "operation": "read",
        "documentId": {"__rl": True, "mode": "id", "value": "<SPREADSHEET_ID>"},
        "sheetName": {"__rl": True, "mode": "name", "value": "NEW Customers List"},
        "options": {
            "dataLocationOnSheet": {"values": {"rangeDefinition": "specifyRangeA1", "range": "A:DR"}},
            "outputFormatting": {"values": {"general": "UNFORMATTED_VALUE", "date": "SERIAL_NUMBER"}},
        },
    }, (720, 0))
    code_node(flow, "Build CSV", "build_csv.js", (960, 0), COLUMNS=json.dumps(columns), DATE_COLUMNS=json.dumps(dates), MONEY_COLUMNS=json.dumps(money))
    flow.add("Compute Performa", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"{SERVICE_URL}/v1/performa",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendQuery": True, "queryParameters": {"parameters": [{"name": "bu", "value": "={{ $json.bu }}"}]},
        "sendBody": True, "contentType": "raw", "rawContentType": "text/csv", "body": "={{ $json.csv }}",
        "options": {"timeout": 300000},
    }, (1200, 0), onError="continueErrorOutput")
    code_node(flow, "Prepare Insert", "prepare_performa_insert.js", (1440, -80))
    postgres_node(flow, "Save Snapshot", "insert_performance.sql", (1680, -80))
    code_node(flow, "Result", "result_performa.js", (1920, -80))
    code_node(flow, "Format Error", "format_performa_error.js", (1440, 160), mode="runOnceForEachItem")
    flow.connect("Manual Trigger", "Manual Parameters")
    for a, b in (("Manual Parameters", "Normalize Plan"), ("Normalize Plan", "Read Tracker"), ("Read Tracker", "Build CSV"), ("Build CSV", "Compute Performa"), ("Prepare Insert", "Save Snapshot"), ("Save Snapshot", "Result")):
        flow.connect(a, b)
    flow.connect("Compute Performa", "Prepare Insert", 0)
    flow.connect("Compute Performa", "Format Error", 1)
    return flow


def analysis_flow() -> Flow:
    prompt = (HERE / "prompts" / PROMPT_FILE).read_text(encoding="utf-8").strip()
    flow = Flow("Report Analysis Button v1")
    header_auth_webhook(flow, "Webhook Analysis", "report-analysis", "POST", (0, 160))
    flow.add("Manual Trigger", "n8n-nodes-base.manualTrigger", 1, {}, (0, 0))
    manual_parameters(flow, (240, 0), [("bu", "<BU>"), ("period", "<PERIOD>"), ("requested_by", "manual")])
    code_node(flow, "Validate Request", "validate_request.js", (480, 80))
    flow.add("Load Latest Run", "n8n-nodes-base.postgres", 2.5, {"operation": "executeQuery", "query": sql("select_latest_run.sql"), "options": {"queryReplacement": "={{ [$json.bu, $json.period] }}"}}, (480, 0), alwaysOutputData=True)
    code_node(flow, "Prepare Analysis Request", "prepare_analysis_request.js", (720, 0), SYSTEM_PROMPT=json.dumps(prompt, ensure_ascii=False), PROMPT_VERSION=json.dumps(PROMPT_FILE.removesuffix(".md")))
    flow.add("Ask Model", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": "={{ $json.url }}",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True, "specifyHeaders": "json", "jsonHeaders": "={{ JSON.stringify($json.headers) }}",
        "sendBody": True, "contentType": "json", "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}",
        "options": {"timeout": 300000},
    }, (960, 0))
    code_node(flow, "Parse Analysis", "parse_analysis.js", (1200, 0))
    flow.add("Apply Analysis", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"{SERVICE_URL}/v1/analysis/apply",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "contentType": "json", "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ report_html: $('Load Latest Run').first().json.numeric_html, analysis: $json.analysis }) }}",
        "options": {"timeout": 120000},
    }, (1440, 0))
    code_node(flow, "Prepare Save", "prepare_save_analysis.js", (1680, 0))
    postgres_node(flow, "Save Analysis", "insert_analysis.sql", (1920, 0))
    flow.add("Notify", "n8n-nodes-base.telegram", 1.2, {"resource": "message", "operation": "sendMessage", "chatId": "<TELEGRAM_CHAT_ID>", "text": "=Analisis {{ $('Validate Request').first().json.bu.toUpperCase() }} {{ $('Validate Request').first().json.period }} tersimpan", "additionalFields": {"appendAttribution": False}}, (2160, 0))
    code_node(flow, "Result", "result_analysis.js", (2400, 0))
    flow.connect("Manual Trigger", "Manual Parameters")
    flow.connect("Manual Parameters", "Validate Request")
    for a, b in (("Webhook Analysis", "Validate Request"), ("Validate Request", "Load Latest Run"), ("Load Latest Run", "Prepare Analysis Request"), ("Prepare Analysis Request", "Ask Model"), ("Ask Model", "Parse Analysis"), ("Parse Analysis", "Apply Analysis"), ("Apply Analysis", "Prepare Save"), ("Prepare Save", "Save Analysis"), ("Save Analysis", "Notify"), ("Notify", "Result")):
        flow.connect(a, b)
    return flow


def view_flow() -> Flow:
    flow = Flow("Report View v1")
    header_auth_webhook(flow, "Webhook View", "report", "GET", (0, 0), response_mode="responseNode", authentication="basicAuth")
    code_node(flow, "Validate Request", "validate_request.js", (240, 0))
    flow.add("Load Report", "n8n-nodes-base.postgres", 2.5, {"operation": "executeQuery", "query": sql("select_latest_report.sql"), "options": {"queryReplacement": "={{ [$json.bu, $json.period] }}"}}, (480, 0), alwaysOutputData=True)
    code_node(flow, "Render", "render_report.js", (720, 0))
    flow.add("Respond", "n8n-nodes-base.respondToWebhook", 1.1, {
        "respondWith": "text", "responseBody": "={{ $json.html }}",
        "options": {"responseCode": "={{ $json.status }}", "responseHeaders": {"entries": [
            {"name": "Content-Type", "value": "text/html; charset=utf-8"},
            {"name": "Cache-Control", "value": "no-store"},
            {"name": "X-Content-Type-Options", "value": "nosniff"},
            {"name": "Content-Security-Policy", "value": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"},
        ]}},
    }, (960, 0))
    for a, b in (("Webhook View", "Validate Request"), ("Validate Request", "Load Report"), ("Load Report", "Render"), ("Render", "Respond")):
        flow.connect(a, b)
    return flow


FLOWS = {
    "Report_Generate_v1.json": generate_flow,
    "Performa_Generate_v1.json": performa_flow,
    "Report_Analysis_Button_v1.json": analysis_flow,
    "Report_View_v1.json": view_flow,
}


def slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")


def build() -> dict[str, str]:
    """Workflow JSON plus, for each Code node, the rendered script. The scripts let you fix a node in a running n8n
    by pasting new code, without re-importing the workflow and losing its credentials and placeholders."""
    files = {}
    for name, factory in FLOWS.items():
        flow = factory()
        files[name] = json.dumps(flow.export(), ensure_ascii=False, indent=2) + "\n"
        for n in flow.nodes:
            if n["type"] == "n8n-nodes-base.code":
                files[f"code/{name.removesuffix('.json')}__{slug(n['name'])}.js"] = n["parameters"]["jsCode"]
    return files


if __name__ == "__main__":
    out = HERE / "workflows"
    out.mkdir(exist_ok=True)
    for name, text in build().items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print("wrote", target)
