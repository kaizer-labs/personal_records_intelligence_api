from __future__ import annotations

from app.services import text_processing as tp


def test_normalize_and_chunk_text() -> None:
    normalized = tp.normalize_text(" First   line \nsecond line\n\n\n third   paragraph ")
    assert normalized == "First line second line\n\nthird paragraph"

    chunks = tp.chunk_text(normalized, max_chars=25)
    assert chunks == ["First line second line", "third paragraph"]

    split_chunks = tp.chunk_text("Intro\n\n" + ("x" * 25), max_chars=10)
    assert split_chunks == ["Intro", "xxxxxxxxxx", "xxxxxxxxxx", "xxxxx"]
    assert tp.chunk_text("") == []


def test_token_expansion_and_hint_helpers() -> None:
    assert tp.tokenize("Tell me the monthly subscription amount") == [
        "monthly",
        "subscription",
        "amount",
    ]

    expanded = tp.expand_query_terms("subscription pay")
    assert "renewal" in expanded
    assert "salary" in expanded

    hints = tp.query_hint_phrases("income date amount")
    assert "federal income tax withheld" in hints
    assert "statement period" in hints
    assert "ending balance" in hints


def test_query_intent_and_request_detectors() -> None:
    intents = tp.detect_query_intents(
        "What dates, amounts, and commitments matter for my monthly subscription?"
    )
    assert {"dates", "amounts", "commitments", "subscriptions", "priorities"} & intents
    assert tp.is_explicitly_off_topic("Tell me a joke about taxes.") is True
    assert tp.is_explicitly_off_topic("What is the balance due?") is False
    assert tp.looks_like_document_request("Summarize the important documents in this folder.")
    assert tp.has_contextual_follow_up_reference("What about this one?") is True
    assert tp.has_contextual_follow_up_reference("Explain the renewal charge.") is False


def test_value_counting_penalties_and_scoring() -> None:
    candidate = (
        "Monthly subscription statement. Monthly charge $12.00. "
        "Renewal date January 15, 2026. Payment due 01/20/2026."
    )
    boilerplate = (
        "For informational purposes only. Should not be relied upon. "
        "Displayed are estimates."
    )

    assert tp.count_currency_values("USD 9.99 and $12.00 and 100.50") == 3
    assert tp.count_date_values("01/20/2026, 2026-04-12, January 15, 2026") >= 3
    assert tp.boilerplate_penalty("nothing to see here") == 0.0
    assert tp.boilerplate_penalty(boilerplate) >= 2.5
    assert tp.subscription_signal_score("monthly recurring membership auto-pay") > 0
    assert tp.subscription_signal_score("flight itinerary hotel check-in") < 0

    relevant_score = tp.score_text(
        "What is the monthly subscription amount and renewal date?",
        candidate,
    )
    boilerplate_score = tp.score_text(
        "What is the monthly subscription amount and renewal date?",
        boilerplate,
    )

    assert relevant_score > boilerplate_score
    assert relevant_score > 10


def test_excerpt_and_similarity_helpers() -> None:
    long_text = (
        "Opening summary. " * 20
        + "The ending balance is $5,432.10 after the transfer cleared. "
        + "Closing notes. " * 10
    )
    excerpt_by_token = tp.build_excerpt(
        long_text,
        "What is the balance?",
        max_chars=90,
    )
    assert "balance" in excerpt_by_token.lower()
    assert excerpt_by_token.startswith("...")

    excerpt_by_hint = tp.build_excerpt(
        long_text,
        "Show amount details",
        max_chars=90,
    )
    assert "ending balance" in excerpt_by_hint.lower()

    fallback = tp.build_excerpt("x" * 300, "unrelated", max_chars=30)
    assert fallback.endswith("...")
    assert len(fallback) <= 33

    assert tp.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert tp.cosine_similarity([1.0], [1.0, 2.0]) == 0.0
    assert tp.cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
