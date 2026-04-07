from __future__ import annotations

from collections import Counter
import math
import re


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "do",
    "much",
    "me",
    "my",
    "tell",
    "please",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}


TERM_EXPANSIONS = {
    "subscription": {
        "subscription",
        "subscriptions",
        "renewal",
        "renewals",
        "monthly",
        "recurring",
        "membership",
        "memberships",
        "plan",
        "plans",
        "premium",
        "premiums",
        "charge",
        "charges",
        "billing",
        "autopay",
        "auto-pay",
    },
    "subscriptions": {
        "subscription",
        "subscriptions",
        "renewal",
        "renewals",
        "monthly",
        "recurring",
        "membership",
        "memberships",
        "plan",
        "plans",
        "premium",
        "premiums",
        "charge",
        "charges",
        "billing",
        "autopay",
        "auto-pay",
    },
    "earn": {
        "earn",
        "earned",
        "earning",
        "earnings",
        "income",
        "salary",
        "pay",
        "paid",
        "wage",
        "wages",
        "compensation",
        "gross",
    },
    "earnings": {
        "earn",
        "earning",
        "earnings",
        "income",
        "salary",
        "pay",
        "wages",
        "compensation",
        "gross",
    },
    "income": {
        "income",
        "earn",
        "earnings",
        "salary",
        "pay",
        "wage",
        "wages",
        "compensation",
        "gross",
    },
    "salary": {
        "salary",
        "pay",
        "income",
        "earnings",
        "compensation",
        "gross",
        "wages",
    },
    "pay": {
        "pay",
        "paid",
        "salary",
        "income",
        "earnings",
        "compensation",
        "gross",
        "wages",
    },
    "wage": {
        "wage",
        "wages",
        "salary",
        "income",
        "earnings",
        "compensation",
        "gross",
    },
    "wages": {
        "wage",
        "wages",
        "salary",
        "income",
        "earnings",
        "compensation",
        "gross",
    },
    "compensation": {
        "compensation",
        "income",
        "earnings",
        "salary",
        "pay",
        "wages",
        "gross",
    },
    "w2": {
        "w2",
        "wages",
        "compensation",
        "withheld",
        "salary",
        "income",
    },
}


QUERY_HINT_PHRASES = {
    "earn": [
        "wages, tips, other compensation",
        "wages tips other compensation",
        "medicare wages and tips",
        "social security wages",
        "gross pay",
        "base salary",
        "annual salary",
        "other compensation",
    ],
    "earnings": [
        "wages, tips, other compensation",
        "medicare wages and tips",
        "social security wages",
        "gross pay",
        "base salary",
        "annual salary",
    ],
    "income": [
        "federal income tax withheld",
        "wages, tips, other compensation",
        "gross pay",
        "annual salary",
    ],
    "salary": ["base salary", "annual salary", "gross pay"],
    "pay": ["gross pay", "net pay", "take home pay"],
    "wage": [
        "wages, tips, other compensation",
        "medicare wages and tips",
        "social security wages",
    ],
    "wages": [
        "wages, tips, other compensation",
        "medicare wages and tips",
        "social security wages",
    ],
    "amount": [
        "ending balance",
        "beginning balance",
        "net deposits",
        "net withdrawals",
        "dividends received",
        "interest earned",
        "market value",
        "account value",
    ],
    "amounts": [
        "ending balance",
        "beginning balance",
        "net deposits",
        "net withdrawals",
        "dividends received",
        "interest earned",
        "market value",
        "account value",
    ],
    "date": [
        "statement period",
        "as of",
        "through",
        "year to date",
    ],
    "dates": [
        "statement period",
        "as of",
        "through",
        "year to date",
    ],
    "commitment": [
        "you agree",
        "payment due",
        "due date",
        "renewal",
        "required by",
        "must pay",
    ],
    "commitments": [
        "you agree",
        "payment due",
        "due date",
        "renewal",
        "required by",
        "must pay",
    ],
    "subscription": [
        "monthly amount",
        "renewal date",
        "month-to-month",
        "annual renewal",
        "monthly premium",
        "monthly charge",
        "auto-pay",
        "recurring charge",
    ],
    "subscriptions": [
        "monthly amount",
        "renewal date",
        "month-to-month",
        "annual renewal",
        "monthly premium",
        "monthly charge",
        "auto-pay",
        "recurring charge",
    ],
}


QUERY_INTENT_KEYWORDS = {
    "priorities": {
        "pay attention",
        "important",
        "importance",
        "need to know",
        "what matters",
        "priorities",
        "priority",
        "focus on",
        "attention",
        "action items",
        "next steps",
        "what should i do",
    },
    "dates": {
        "date",
        "dates",
        "deadline",
        "deadlines",
        "when",
        "due",
        "period",
        "timeline",
    },
    "amounts": {
        "amount",
        "amounts",
        "cost",
        "costs",
        "price",
        "prices",
        "value",
        "values",
        "balance",
        "balances",
        "total",
        "totals",
        "how much",
    },
    "commitments": {
        "commitment",
        "commitments",
        "obligation",
        "obligations",
        "agree",
        "agreed",
        "owed",
        "owe",
        "required",
        "responsibility",
        "responsibilities",
        "must",
    },
    "subscriptions": {
        "subscription",
        "subscriptions",
        "membership",
        "memberships",
        "renewal",
        "renewals",
        "monthly",
        "recurring",
        "premium",
        "premiums",
        "billing",
        "charge",
        "charges",
        "autopay",
        "auto-pay",
        "plan",
        "plans",
    },
    "earnings": {
        "earn",
        "earned",
        "earning",
        "earnings",
        "income",
        "salary",
        "wage",
        "wages",
        "compensation",
        "pay",
        "dividend",
        "dividends",
        "interest",
        "cash flow",
        "cash flows",
        "distribution",
        "distributions",
    },
}


BOILERPLATE_PHRASES = (
    "for informational purposes only",
    "should not be relied upon",
    "no guarantee of actual receipt",
    "third-party vendors believed to be reliable",
    "cash flows are estimates",
    "displayed are estimates",
)

SUBSCRIPTION_POSITIVE_TERMS = (
    "subscription",
    "subscriptions",
    "monthly amount",
    "renewal date",
    "month-to-month",
    "annual renewal",
    "monthly premium",
    "monthly charge",
    "billing",
    "auto-pay",
    "autopay",
    "premium",
    "recurring",
    "service",
    "membership",
)

SUBSCRIPTION_NEGATIVE_TERMS = (
    "itinerary",
    "flight",
    "hotel check-in",
    "hotel check-out",
    "traveler",
    "event date",
    "booking deposit",
    "guest count",
    "late checkout",
    "catering",
)

OFF_TOPIC_PATTERNS = (
    r"\bjoke\b",
    r"\bjokes\b",
    r"\bpoem\b",
    r"\briddle\b",
    r"\bstory\b",
    r"\bknock knock\b",
    r"\blyrics?\b",
    r"\broast me\b",
    r"\bmake me laugh\b",
)

DOCUMENT_ANALYSIS_HINTS = (
    "summary",
    "summarize",
    "important",
    "pay attention",
    "need to know",
    "key points",
    "compare",
    "mention",
    "mentioned",
    "list",
    "extract",
    "show",
    "find",
    "documents",
    "document",
    "records",
    "record",
    "files",
    "file",
    "folder",
    "folders",
    "trip",
    "stay",
    "travel",
    "agreement",
    "contract",
    "invoice",
    "statement",
    "deadline",
    "amount",
    "amounts",
    "commitment",
    "commitments",
    "subscription",
    "subscriptions",
    "renewal",
    "monthly",
)

CONTEXTUAL_FOLLOW_UP_HINTS = (
    "this",
    "that",
    "these",
    "those",
    "it",
    "they",
    "them",
    "my stay",
    "my trip",
    "the stay",
    "the trip",
    "those documents",
    "these documents",
    "those files",
    "these files",
)


MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


def normalize_text(raw_text: str) -> str:
    normalized_lines: list[str] = []

    for raw_line in raw_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        normalized_lines.append(line)

    paragraphs: list[str] = []
    current_paragraph: list[str] = []

    for line in normalized_lines:
        if not line:
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph).strip())
                current_paragraph = []
            continue

        current_paragraph.append(line)

    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph).strip())

    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def chunk_text(text: str, max_chars: int = 900) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if len(paragraph) <= max_chars:
            current = paragraph
            continue

        start = 0
        while start < len(paragraph):
            end = min(len(paragraph), start + max_chars)
            chunks.append(paragraph[start:end].strip())
            start = end

        current = ""

    if current:
        chunks.append(current)

    return chunks


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]{2,}", text.lower())
        if token not in STOPWORDS
    ]


def expand_query_terms(query: str) -> list[str]:
    tokens = tokenize(query)
    expanded_terms: set[str] = set(tokens)

    for token in tokens:
        expanded_terms.update(TERM_EXPANSIONS.get(token, {token}))

    return sorted(expanded_terms)


def query_hint_phrases(query: str) -> list[str]:
    hints: set[str] = set()
    for token in tokenize(query):
        hints.update(QUERY_HINT_PHRASES.get(token, []))
    return sorted(hints)


def detect_query_intents(query: str) -> set[str]:
    query_lower = query.lower()
    tokens = set(tokenize(query))
    intents: set[str] = set()

    for intent, keywords in QUERY_INTENT_KEYWORDS.items():
        if any(keyword in query_lower for keyword in keywords):
            intents.add(intent)
            continue
        if tokens.intersection(keywords):
            intents.add(intent)

    return intents


def is_explicitly_off_topic(query: str) -> bool:
    query_lower = query.lower()
    return any(re.search(pattern, query_lower) for pattern in OFF_TOPIC_PATTERNS)


def looks_like_document_request(query: str) -> bool:
    query_lower = re.sub(r"\s+", " ", query.lower()).strip()
    if detect_query_intents(query):
        return True

    return any(hint in query_lower for hint in DOCUMENT_ANALYSIS_HINTS)


def has_contextual_follow_up_reference(query: str) -> bool:
    query_lower = re.sub(r"\s+", " ", query.lower()).strip()
    return any(hint in query_lower for hint in CONTEXTUAL_FOLLOW_UP_HINTS)


def count_currency_values(text: str) -> int:
    return len(re.findall(r"(?:\$|usd\s*)?\d[\d,]*(?:\.\d{2})", text.lower()))


def count_date_values(text: str) -> int:
    lower_text = text.lower()
    slash_dates = len(re.findall(r"\b\d{1,2}/\d{1,2}/(?:\d{2}|\d{4})\b", lower_text))
    iso_dates = len(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", lower_text))
    month_dates = sum(lower_text.count(month) for month in MONTH_NAMES)
    return slash_dates + iso_dates + month_dates


def boilerplate_penalty(text: str) -> float:
    lower_text = text.lower()
    hits = sum(1 for phrase in BOILERPLATE_PHRASES if phrase in lower_text)
    if hits == 0:
        return 0.0

    return min(4.0, hits * 1.25)


def subscription_signal_score(text: str) -> float:
    lower_text = text.lower()
    positive_hits = sum(1 for term in SUBSCRIPTION_POSITIVE_TERMS if term in lower_text)
    negative_hits = sum(1 for term in SUBSCRIPTION_NEGATIVE_TERMS if term in lower_text)
    return float(positive_hits) - (negative_hits * 1.5)


def score_text(query: str, candidate_text: str) -> float:
    query_tokens = expand_query_terms(query)
    if not query_tokens:
        return 0.0

    candidate_lower = candidate_text.lower()
    token_counts = Counter(tokenize(candidate_text))
    intents = detect_query_intents(query)
    score = 0.0

    for token in query_tokens:
        score += float(token_counts.get(token, 0))

    collapsed_query = re.sub(r"\s+", " ", query.lower()).strip()
    if collapsed_query and collapsed_query in candidate_lower:
        score += 8.0

    bigrams = [
        f"{query_tokens[index]} {query_tokens[index + 1]}"
        for index in range(len(query_tokens) - 1)
    ]
    score += sum(2.5 for bigram in bigrams if bigram in candidate_lower)
    score += sum(3.5 for hint in query_hint_phrases(query) if hint in candidate_lower)

    if "dates" in intents:
        score += min(8.0, count_date_values(candidate_text) * 1.5)
    if "amounts" in intents or "earnings" in intents:
        score += min(10.0, count_currency_values(candidate_text) * 1.25)

    if "commitments" in intents:
        commitment_terms = (
            "due",
            "required",
            "must",
            "agree",
            "agreed",
            "obligation",
            "responsibility",
            "renewal",
            "payment",
            "commitment",
        )
        score += sum(1.5 for term in commitment_terms if term in candidate_lower)

    if "subscriptions" in intents:
        subscription_score = subscription_signal_score(candidate_text)
        score += subscription_score * 3.0
        if subscription_score <= 0:
            score -= 6.0

    penalty = boilerplate_penalty(candidate_text)
    if penalty and count_currency_values(candidate_text) == 0 and count_date_values(candidate_text) == 0:
        score -= penalty

    return score


def build_excerpt(text: str, query: str, max_chars: int = 240) -> str:
    candidate_text = " ".join(text.split())
    if len(candidate_text) <= max_chars:
        return candidate_text

    lower_text = candidate_text.lower()

    for token in expand_query_terms(query):
        position = lower_text.find(token)
        if position >= 0:
            start = max(0, position - max_chars // 3)
            end = min(len(candidate_text), start + max_chars)
            excerpt = candidate_text[start:end].strip()
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(candidate_text) else ""
            return f"{prefix}{excerpt}{suffix}"

    for hint in query_hint_phrases(query):
        position = lower_text.find(hint)
        if position >= 0:
            start = max(0, position - max_chars // 3)
            end = min(len(candidate_text), start + max_chars)
            excerpt = candidate_text[start:end].strip()
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(candidate_text) else ""
            return f"{prefix}{excerpt}{suffix}"

    return f"{candidate_text[:max_chars].strip()}..."


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    numerator = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_magnitude = math.sqrt(sum(value * value for value in left))
    right_magnitude = math.sqrt(sum(value * value for value in right))

    if left_magnitude == 0.0 or right_magnitude == 0.0:
        return 0.0

    return numerator / (left_magnitude * right_magnitude)
