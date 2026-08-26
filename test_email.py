"""Email delivery tests - recipient validation, precedence, and the SMTP path
exercised with a fake transport (no real credentials, no network).
Run: python test_email.py
"""
import io
import os
import sys
from email import message_from_string
from unittest import mock

os.environ["TRACE_DELAY_MS"] = "0"
os.environ["PLANNER"] = "mock"
os.environ["STORE"] = "memory"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from agent.tools import notify
from core.store import MemoryStore

# ---- 1. recipient validation ------------------------------------------
assert notify.parse_recipients("a@b.co") == ["a@b.co"]
assert notify.parse_recipients(" a@b.co , c@d.org ") == ["a@b.co", "c@d.org"]
assert notify.parse_recipients("a@b.co; c@d.org") == ["a@b.co", "c@d.org"]
assert notify.parse_recipients("a@b.co,") == ["a@b.co"], "a trailing comma is harmless"
for bad in ["", "   ", "nope", "a@b", "a b@c.co", "a@@b.co", "@b.co", "a@.co", "a@b.c"]:
    try:
        notify.parse_recipients(bad)
        raise AssertionError(f"should have rejected {bad!r}")
    except ValueError:
        pass
try:
    notify.parse_recipients(",".join(f"u{i}@x.co" for i in range(6)))
    raise AssertionError("should cap recipients")
except ValueError:
    pass
print("recipient validation: OK")

# ---- 2. precedence: override > dashboard setting > env -----------------
os.environ["EMAIL_TO"] = "env@port.az"
assert notify.resolve_recipients({}, None) == ["env@port.az"]
assert notify.resolve_recipients({"email_to": "meta@port.az"}, None) == ["meta@port.az"]
assert notify.resolve_recipients({"email_to": "meta@port.az"}, "call@port.az") == ["call@port.az"]
assert notify.resolve_recipients({"email_to": "garbage"}, None) == ["env@port.az"], \
    "a corrupt stored value must fall through, not crash"
del os.environ["EMAIL_TO"]
assert notify.resolve_recipients({}, None) == []
print("recipient precedence: OK")

# ---- 3. build a real plan to email -------------------------------------
from data.seed import build_state
from agent.pipeline import execute_run
from datetime import datetime

store = MemoryStore()
store.reset(build_state())
rid = "run-email-test"
store.upsert("runs", {"id": rid, "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                      "finished_at": None, "status": "running", "trigger": "manual",
                      "scenario": None, "steps": [], "plan_id": None, "planner": None})
execute_run(store, rid, "manual")
plan = store.get("plans", store.get("runs", rid)["plan_id"])
assert plan and plan["assignments"], "no plan to email"

# with no SMTP and no recipient: rendered, never raises
rec = notify.send_dispatch_email(plan, {}, store)
assert rec["delivered"] is False and rec["error"] == "no recipient set"
assert rec["html"] and rec["attachment"], "email must still render + attach"
print("no-recipient path: OK (rendered, not sent, no crash)")

# ---- 4. SMTP path with a fake transport --------------------------------
sent = {}


class FakeSMTP:
    def __init__(self, host, port, timeout=None):
        sent["host"], sent["port"] = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        sent["starttls"] = True

    def login(self, user, password):
        sent["user"], sent["password"] = user, password

    def send_message(self, msg):
        sent["msg"] = msg


os.environ.update(SMTP_HOST="smtp.gmail.com", SMTP_PORT="465",
                  SMTP_USER="agent@gmail.com", SMTP_PASS="app-password")
assert notify.smtp_configured() is True

with mock.patch.object(notify.smtplib, "SMTP_SSL", FakeSMTP):
    rec = notify.send_dispatch_email(plan, {"email_to": "ops@port.az"}, store)
assert rec["delivered"] is True, rec
assert rec["error"] is None
assert sent["host"] == "smtp.gmail.com" and sent["port"] == 465
assert sent["user"] == "agent@gmail.com" and sent["password"] == "app-password"
msg = sent["msg"]
assert msg["To"] == "ops@port.az" and msg["From"] == "agent@gmail.com"
assert "Dispatch Plan" in msg["Subject"]
parts = msg.get_payload()
assert any(p.get_content_type() == "text/html" for p in parts), "html body missing"
assert any("attachment" in str(p.get("Content-Disposition", "")) for p in parts), "xlsx missing"
print(f"SSL send path: OK (to={msg['To']}, {len(parts)} parts incl. XLSX)")

# multiple recipients, one-off override wins over the stored setting
with mock.patch.object(notify.smtplib, "SMTP_SSL", FakeSMTP):
    rec = notify.send_dispatch_email(plan, {"email_to": "ops@port.az"}, store,
                                     recipient="a@x.co, b@y.co")
assert rec["delivered"] and sent["msg"]["To"] == "a@x.co, b@y.co", sent["msg"]["To"]
assert rec["recipients"] == ["a@x.co", "b@y.co"]
print("override + multi-recipient: OK")

# port 587 must use STARTTLS instead of implicit SSL
sent.clear()
os.environ["SMTP_PORT"] = "587"
with mock.patch.object(notify.smtplib, "SMTP", FakeSMTP):
    rec = notify.send_dispatch_email(plan, {"email_to": "ops@port.az"}, store)
assert rec["delivered"] and sent.get("starttls") is True and sent["port"] == 587
print("STARTTLS (587) path: OK")

# ---- 5. failures are contained -----------------------------------------
os.environ["SMTP_PORT"] = "465"


class ExplodingSMTP(FakeSMTP):
    def login(self, user, password):
        raise OSError("535 authentication failed")


with mock.patch.object(notify.smtplib, "SMTP_SSL", ExplodingSMTP):
    rec = notify.send_dispatch_email(plan, {"email_to": "ops@port.az"}, store)
assert rec["delivered"] is False
assert "authentication failed" in rec["error"], rec["error"]
assert rec["html"], "the plan must still be rendered when sending fails"
stored = store.get("emails", rec["id"])
assert stored and stored["delivered"] is False, "failure must be recorded for the dashboard"
print("SMTP failure path: OK (contained, recorded, run survives)")

for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"):
    os.environ.pop(k, None)

print("\nALL EMAIL TESTS PASSED")
