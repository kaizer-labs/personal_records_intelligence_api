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


def score_text(query: str, candidate_text: str) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0

    candidate_lower = candidate_text.lower()
    token_counts = Counter(tokenize(candidate_text))
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

    return score


def build_excerpt(text: str, query: str, max_chars: int = 240) -> str:
    candidate_text = " ".join(text.split())
    if len(candidate_text) <= max_chars:
        return candidate_text

    lower_text = candidate_text.lower()

    for token in tokenize(query):
        position = lower_text.find(token)
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
