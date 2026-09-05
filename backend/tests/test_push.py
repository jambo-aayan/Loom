from loom.notifications.push import FakePushSender, PushTarget, build_signal_push_payload


def test_fake_push_sender_records_sends():
    sender = FakePushSender()
    target = PushTarget(endpoint="https://push.example/abc", p256dh="key", auth="secret")
    payload = build_signal_push_payload("sig-1", "VUSA.L", "buy", 0.9)

    sender.send(target, payload)

    assert len(sender.sent) == 1
    sent_target, sent_payload = sender.sent[0]
    assert sent_target.endpoint == target.endpoint
    assert sent_payload["signal_id"] == "sig-1"


def test_payload_carries_approve_and_reject_actions():
    payload = build_signal_push_payload("sig-1", "VUSA.L", "buy", 0.9)

    action_names = {a["action"] for a in payload["actions"]}

    assert action_names == {"approve", "reject"}
