import smtplib

from loom.notifications.email import SmtpEmailSender


def test_smtp_failure_is_swallowed_not_raised(monkeypatch):
    """A transient SMTP outage must not turn a successful trading pass/approval/kill-switch
    action into a 500 — mirrors WebPushSender's per-target isolation (code review finding)."""

    class _BoomSMTP:
        def __init__(self, *args, **kwargs):
            raise smtplib.SMTPConnectError(421, "connection refused")

    monkeypatch.setattr(smtplib, "SMTP", _BoomSMTP)
    sender = SmtpEmailSender("smtp.example.com", 587, "", "", "loom@example.com")

    sender.send("user@example.com", "subject", "<p>body</p>")  # must not raise
