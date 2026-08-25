"""Dispatcher notification: HTML email + XLSX attachment.

Sends over SMTP when configured (SMTP_HOST/SMTP_USER/SMTP_PASS/EMAIL_TO,
e.g. Gmail app password with the password in Secret Manager on Cloud Run).
Always records the rendered email in the store so the dashboard can show
the deliverable even without SMTP.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from core.clock import hhmm

PRIORITY_LABEL = {1: "P1 - URGENT", 2: "P2 - LOAD ASAP", 3: "P3 - TODAY"}
PRIORITY_COLOR = {1: "#d64545", 2: "#d69a2e", 3: "#3a7bd5"}


def build_email_html(plan: dict, meta: dict) -> str:
    rows = []
    for a in sorted(plan["assignments"], key=lambda x: (x["priority"], x["load_start"])):
        chip = (f"<span style='background:{PRIORITY_COLOR[a['priority']]};color:#fff;"
                f"padding:2px 8px;border-radius:10px;font-size:11px'>{PRIORITY_LABEL[a['priority']]}</span>")
        rows.append(
            "<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #e3e8ee'>{chip}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e3e8ee'><b>{a['shipment_id']}</b></td>"
            f"<td style='padding:8px;border-bottom:1px solid #e3e8ee'>{a['wagon_id']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e3e8ee'>{a['team_id']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e3e8ee'>{hhmm(a['load_start'])}&ndash;{hhmm(a['load_end'])}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e3e8ee'>{a['target_ship']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e3e8ee'>{a['confidence']}%</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e3e8ee;color:#5b6b77'>{a['reason']}</td>"
            "</tr>")

    holds = "".join(
        f"<li><b>{h['shipment_id']}</b>: {h['action']} &mdash; <i>{h['reason']}</i></li>"
        for h in plan.get("holds", []))

    s = plan.get("summary", {})
    version_note = "" if plan["version"] == 1 else (
        f"<p style='background:#fdf1e7;border-left:4px solid #c85a10;padding:10px 14px'>"
        f"<b>Updated plan v{plan['version']}</b> &mdash; disruption response. "
        f"Changes vs previous plan are listed in the dashboard.</p>")

    return f"""
<div style="font-family:Arial,Helvetica,sans-serif;color:#1b2733;max-width:860px">
  <h2 style="margin:0 0 4px">Daily Dispatch Plan &mdash; {plan['plan_date']}</h2>
  <p style="margin:0 0 12px;color:#5b6b77">Generated {plan['generated_at'].replace('T', ' ')}
     by {plan['planner']} &middot; {meta.get('port_name', 'Port Terminal')}</p>
  {version_note}
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <tr style="background:#16324a;color:#fff;text-align:left">
      <th style="padding:8px">Priority</th><th style="padding:8px">Shipment</th>
      <th style="padding:8px">Wagon</th><th style="padding:8px">Dock team</th>
      <th style="padding:8px">Load window</th><th style="padding:8px">Ship</th>
      <th style="padding:8px">Conf.</th><th style="padding:8px">Reason</th>
    </tr>
    {''.join(rows)}
  </table>
  {f"<h3 style='margin:16px 0 6px'>On hold</h3><ul>{holds}</ul>" if holds else ""}
  <h3 style="margin:16px 0 6px">Summary</h3>
  <p style="margin:0;color:#334">
    {s.get('planned', 0)} loads scheduled &middot; {s.get('holds', 0)} on hold &middot;
    SLA compliance {s.get('sla_met_pct', '-')}% &middot;
    peak dock utilization {s.get('peak_util_pct', '-')}% &middot;
    planned in {s.get('planning_seconds', '-')}s (manual baseline {meta.get('manual_baseline_min', 45)} min)
  </p>
  <p style="color:#5b6b77;margin-top:14px">Reply to this email or use the dashboard to approve / override.</p>
</div>"""


def build_xlsx(plan: dict, path: str) -> str | None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        return None
    wb = Workbook()
    ws = wb.active
    ws.title = "Dispatch Plan"
    ws.append([f"DISPATCH PLAN {plan['plan_date']} v{plan['version']}"])
    ws["A1"].font = Font(size=13, bold=True)
    headers = ["Priority", "Shipment", "Wagon", "Dock team", "Load start", "Load end",
               "Ship", "Confidence", "Reason"]
    ws.append(headers)
    for cell in ws[2]:
        cell.fill = PatternFill(start_color="16324A", end_color="16324A", fill_type="solid")
        cell.font = Font(color="FFFFFF", bold=True)
    for a in sorted(plan["assignments"], key=lambda x: (x["priority"], x["load_start"])):
        ws.append([a["priority"], a["shipment_id"], a["wagon_id"], a["team_id"],
                   hhmm(a["load_start"]), hhmm(a["load_end"]), a["target_ship"],
                   f"{a['confidence']}%", a["reason"]])
    for h in plan.get("holds", []):
        ws.append(["HOLD", h["shipment_id"], "-", "-", "-", "-",
                   h.get("rebook_ship") or "-", f"{h['confidence']}%", h["reason"]])
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 60)
    wb.save(path)
    return path


def send_dispatch_email(plan: dict, meta: dict, store, out_dir: str = "out") -> dict:
    subject = (f"{'UPDATED ' if plan['version'] > 1 else ''}Dispatch Plan {plan['plan_date']} "
               f"v{plan['version']} | {len(plan['assignments'])} loads, "
               f"{len(plan.get('holds', []))} on hold")
    html = build_email_html(plan, meta)

    os.makedirs(out_dir, exist_ok=True)
    xlsx_path = build_xlsx(plan, os.path.join(out_dir, f"dispatch_plan_{plan['id']}.xlsx"))

    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASS")
    to = os.environ.get("EMAIL_TO")
    delivered = False
    if host and user and pwd and to:
        try:
            msg = MIMEMultipart()
            msg["Subject"], msg["From"], msg["To"] = subject, user, to
            msg.attach(MIMEText(html, "html"))
            if xlsx_path:
                with open(xlsx_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f"attachment; filename={os.path.basename(xlsx_path)}")
                msg.attach(part)
            with smtplib.SMTP_SSL(host, int(os.environ.get("SMTP_PORT", "465"))) as smtp:
                smtp.login(user, pwd)
                smtp.send_message(msg)
            delivered = True
        except Exception as exc:  # demo must never die on mail problems
            print(f"[notify] SMTP send failed: {exc}")

    record = {
        "id": f"email-{plan['id']}",
        "plan_id": plan["id"],
        "subject": subject,
        "html": html,
        "attachment": os.path.basename(xlsx_path) if xlsx_path else None,
        "to": to or "dispatcher (SMTP not configured - logged only)",
        "delivered": delivered,
        "created_at": plan["generated_at"],
    }
    store.upsert("emails", record)
    return record
