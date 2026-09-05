from loom.insight.generator import FakeInsightGenerator


def test_fake_generator_produces_position_commentary_with_no_signal_involved():
    generator = FakeInsightGenerator()

    content = generator.generate_position_commentary("AAPL", "Manual", quantity=10, average_price=150.0)

    assert "AAPL" in content
    assert "Manual" in content
    assert "150.00" in content
