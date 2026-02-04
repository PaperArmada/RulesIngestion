"""
Query intent classification.

Hybrid approach: rules first, LLM fallback for ambiguous cases.
"""

from __future__ import annotations

import re
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

from .policy import Intent


# Regex patterns for intent classification
DEFINITION_PATTERNS = [
    r"^what\s+(?:is|are|does)\s+",
    r"^define\s+",
    r"^explain\s+",
    r"^describe\s+",
    r"^what\s+.*\s+(?:mean|do)\??$",
    r"condition\s+(?:is|does)",
    r"^how\s+does\s+\w+\s+work",
]

PROCEDURE_PATTERNS = [
    r"^how\s+(?:do|can|to)\s+",
    r"^steps?\s+(?:for|to)\s+",
    r"^process\s+(?:for|to)\s+",
    r"^how\s+(?:do\s+)?(?:i|you|we)\s+",
    r"^(?:can|could)\s+(?:i|you|we)\s+",
]

EXCEPTION_PATTERNS = [
    r"^does\s+.*\s+apply\s+",
    r"^when\s+.*\s+(?:not|doesn't|don't)\s+",
    r"^(?:is|are)\s+.*\s+exception",
    r"^(?:can|does)\s+.*\s+override",
    r"unless",
    r"except\s+when",
    r"instead\s+of",
]

COMPARISON_PATTERNS = [
    r"\s+vs\.?\s+",
    r"\s+versus\s+",
    r"difference\s+between",
    r"compare\s+",
    r"comparison\s+",
    r"which\s+is\s+better",
    r"should\s+i\s+use\s+.*\s+or\s+",
]

LOOKUP_PATTERNS = [
    r"^what(?:'s| is)\s+the\s+(?:dc|check|modifier|bonus)",
    r"^(?:list|table)\s+of\s+",
    r"^(?:show|give)\s+(?:me\s+)?the\s+table",
    r"how\s+(?:much|many)",
    r"what\s+(?:level|rank|tier)",
    r"range\s+of\s+",
    r"cost\s+of\s+",
]


def classify_intent_rules(query: str) -> Optional[Intent]:
    """
    Rule-based intent classification using regex patterns.
    
    Returns None if no pattern matches (ambiguous).
    """
    query_lower = query.lower().strip()
    
    # Check patterns in order of specificity
    
    # Comparison (most specific patterns)
    for pattern in COMPARISON_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return Intent.COMPARISON
    
    # Exception
    for pattern in EXCEPTION_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return Intent.EXCEPTION
    
    # Lookup
    for pattern in LOOKUP_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return Intent.LOOKUP
    
    # Procedure
    for pattern in PROCEDURE_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return Intent.PROCEDURE
    
    # Definition (most general)
    for pattern in DEFINITION_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return Intent.DEFINITION
    
    # No match
    return None


def classify_intent_llm(query: str, client: OpenAI) -> Intent:
    """
    LLM-based intent classification for ambiguous cases.
    
    Uses the OpenAI Responses API with gpt-5.2.
    See: Docs/architecture/OpenAI_Responses_API.md
    """
    if client is None:
        return Intent.UNKNOWN
    
    instructions = """You are a TTRPG rules question classifier. 
Classify questions into exactly one category and respond with ONLY the category name."""

    prompt = f"""Classify the following TTRPG rules question into exactly one category.

Categories:
- DEFINITION: "What is X?", "What does X do?", explaining a concept
- PROCEDURE: "How do I X?", "Steps for X", describing a process
- EXCEPTION: "Does X apply when Y?", handling edge cases or overrides
- COMPARISON: "X vs Y", "Difference between X and Y", comparing options
- LOOKUP: "What's the DC for X?", "Table of X", finding specific values

Question: {query}

Respond with only the category name (DEFINITION, PROCEDURE, EXCEPTION, COMPARISON, or LOOKUP)."""

    try:
        # Use Responses API (recommended for all new projects)
        response = client.responses.create(
            model="gpt-5.2",
            instructions=instructions,
            input=prompt,
            max_output_tokens=20,
            temperature=0,
        )
        
        result = response.output_text.strip().upper()
        
        # Map to Intent enum
        intent_map = {
            "DEFINITION": Intent.DEFINITION,
            "PROCEDURE": Intent.PROCEDURE,
            "EXCEPTION": Intent.EXCEPTION,
            "COMPARISON": Intent.COMPARISON,
            "LOOKUP": Intent.LOOKUP,
        }
        
        return intent_map.get(result, Intent.UNKNOWN)
    
    except Exception:
        return Intent.UNKNOWN


def classify_intent(
    query: str,
    client: Optional[OpenAI] = None,
) -> Intent:
    """
    Hybrid intent classification: rules first, LLM fallback.
    
    Args:
        query: The query string
        client: Optional OpenAI client for LLM fallback
        
    Returns:
        Classified Intent
    """
    # Try rules first
    intent = classify_intent_rules(query)
    if intent is not None:
        return intent
    
    # LLM fallback if client provided
    if client is not None:
        return classify_intent_llm(query, client)
    
    # Default to DEFINITION (most common for rules questions)
    return Intent.DEFINITION
