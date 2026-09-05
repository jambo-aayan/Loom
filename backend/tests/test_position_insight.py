from loom.insight.generator import FakeInsightGenerator


def test_fake_generator_produces_position_commentary_with_no_signal_involved():
    generator = FakeInsightGenerator()

    content = generator.generate_position_commentary("AAPL", "Manual", quantity=10, average_price=150.0)

    assert "AAPL" in content
    assert "Manual" in content
    assert "150.00" in content


def test_fake_generator_answers_a_free_form_question():
    generator = FakeInsightGenerator()

    answer = generator.answer_question("What's the outlook for semiconductor stocks?")

    assert "outlook for semiconductor stocks" in answer


def test_fake_generator_answer_can_be_scoped_to_an_instrument():
    generator = FakeInsightGenerator()

    answer = generator.answer_question("Any recent news?", instrument="NVDA")

    assert "NVDA" in answer
