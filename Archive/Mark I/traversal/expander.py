"""
LLM query expansion for hybrid retrieval.

Takes a user query and generates multiple parallel search terms/phrases
that can be searched deterministically in the TraversalIndex.

Uses few-shot prompting with examples that can be tuned over iterations.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .model_adapter import (
    ModelAdapter,
    ExpansionModelConfig,
    GenerationResult,
    create_adapter,
    EXPANSION_MODELS,
    DEFAULT_EXPANSION_MODEL,
)
from .intent import Intent, classify_intent


@dataclass
class ExpansionResult:
    """
    Result from query expansion.
    
    Attributes:
        original_query: The original user query
        anchor_terms: List of terms tokenized from the original query (for priority weighting)
        expanded_terms: List of expanded search terms/phrases from LLM
        intent: Classified query intent
        generation_result: Raw generation result with metrics
        parsed_successfully: Whether the LLM output parsed correctly
    """
    original_query: str
    anchor_terms: List[str]  # Tokenized from original query - these get priority weighting
    expanded_terms: List[str]  # LLM-generated expansion terms
    intent: Intent
    generation_result: Optional[GenerationResult] = None
    parsed_successfully: bool = True
    

# Few-shot examples for query expansion
# These are tuned based on the blind evaluation experiments
# IMPORTANT: Include specific game terms (spell names, feat names, ability names)
FEW_SHOT_EXAMPLES = [
    {
        "query": "What does flat-footed do?",
        "intent": "DEFINITION",
        "expansions": [
            "flat-footed",
            "flat-footed condition",
            "off-guard",
            "AC penalty -2",
            "flanking flat-footed",
            "conditions",
            "circumstance penalty",
            "dexterity modifier",
            "caught off guard",
            "surprised"
        ]
    },
    {
        "query": "How does the Gust of Wind spell work?",
        "intent": "DEFINITION",
        "expansions": [
            "gust of wind",
            "gust of wind spell",
            "wind spell",
            "air tradition",
            "push effect",
            "fortitude save",
            "spell 1",
            "concentrate manipulate",
            "move creatures",
            "strong wind"
        ]
    },
    {
        "query": "How can I see through a cloud of gas?",
        "intent": "PROCEDURE",
        "expansions": [
            "concealed",
            "concealment",
            "vision obscured",
            "darkvision",
            "fog cloud",
            "sense through",
            "perception check",
            "hidden",
            "blindsight",
            "obscured terrain"
        ]
    },
    {
        "query": "Suggest some complementary feats for a Level 9 Lashunta Solarian",
        "intent": "COMPARISON",
        "expansions": [
            "solarian feats",
            "solarian class feats",
            "lashunta ancestry feats",
            "lashunta heritage",
            "level 9 feats",
            "photon mode",
            "graviton mode",
            "stellar revelations",
            "solar weapon",
            "charisma feats",
            "damaya korasha"
        ]
    },
    {
        "query": "Can I use Redirect Current to power up a console?",
        "intent": "EXCEPTION",
        "expansions": [
            "redirect current",
            "redirect current feat",
            "power source",
            "console interaction",
            "electricity manipulation",
            "technomancer",
            "tech abilities",
            "electric arc",
            "power device",
            "interact action"
        ]
    },
    {
        "query": "I need help deciding between Covering Fire or I'll Be Back as my 6th level feat",
        "intent": "COMPARISON",
        "expansions": [
            "covering fire",
            "covering fire feat",
            "i'll be back",
            "i'll be back feat",
            "soldier feats",
            "level 6 feats",
            "ranged combat",
            "suppressing fire",
            "reaction feats",
            "recovery feats",
            "regain consciousness"
        ]
    },
    {
        "query": "I don't really understand perception?",
        "intent": "DEFINITION",
        "expansions": [
            "perception",
            "perception skill",
            "perception check",
            "seek action",
            "initiative",
            "senses",
            "hidden detection",
            "stealth vs perception",
            "DC perception",
            "wisdom modifier"
        ]
    },
    {
        "query": "What is the Sidestep reaction?",
        "intent": "DEFINITION",
        "expansions": [
            "sidestep",
            "sidestep feat",
            "sidestep reaction",
            "reaction feat",
            "melee strike miss",
            "step action",
            "soldier feats",
            "level 8 feat",
            "dodge",
            "triggered action"
        ]
    },
    {
        "query": "How does Guarded Thoughts work for Lashunta?",
        "intent": "DEFINITION",
        "expansions": [
            "guarded thoughts",
            "guarded thoughts feat",
            "lashunta feat",
            "mental protection",
            "telepathy defense",
            "ancestry feat",
            "level 9 feat",
            "mind reading",
            "psychic resistance",
            "thought protection"
        ]
    },
    {
        "query": "What feats improve my Solar Weapon as a Solarian?",
        "intent": "COMPARISON",
        "expansions": [
            "solar weapon",
            "solar weapon feats",
            "solarian weapon",
            "weapon manifestation",
            "photon attunement",
            "graviton attunement",
            "stellar rush",
            "blazing orbit",
            "solarian class feats",
            "weapon proficiency"
        ]
    },
]


# Common TTRPG entity patterns for extraction
ENTITY_PATTERNS = [
    # Quoted terms (user explicitly marking important terms)
    r'"([^"]+)"',
    r"'([^']+)'",
    # Capitalized multi-word phrases (likely proper nouns/game terms)
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b',
    # Single capitalized words that aren't sentence starters
    r'(?<!^)(?<!\.\s)\b([A-Z][a-z]{2,})\b',
]

# Common TTRPG term patterns
MECHANIC_KEYWORDS = {
    "spell", "feat", "action", "reaction", "ability", "skill", "trait",
    "condition", "save", "check", "dc", "modifier", "bonus", "penalty",
    "class", "ancestry", "heritage", "level", "damage", "attack", "defense",
}


def _build_system_prompt() -> str:
    """Build the system prompt for query expansion."""
    return """You are a TTRPG rules expert helping with search query expansion.

Your task: Given a user question about game rules, generate 10-12 search terms or phrases 
that would help find relevant rule chunks in a knowledge base.

Requirements:
1. ALWAYS include the exact name of any spell, feat, ability, or game mechanic mentioned
2. Include variations of the name (e.g., "Covering Fire", "covering fire feat", "covering fire action")
3. Include related mechanical terms (conditions, actions, checks, saves)
4. Include the type of content (e.g., "level 6 feat", "spell 1", "ancestry feat")
5. Include class/ancestry names if mentioned
6. Include synonyms and alternative phrasings
7. Include broader category terms that might contain the answer
8. Keep each term/phrase short (1-4 words)

IMPORTANT: Be specific! Include proper game term names, not just generic words.

Format: Output ONLY a JSON array of strings, nothing else.
Example: ["gust of wind", "gust of wind spell", "air spell", "wind push", "fortitude save", "spell 1", "concentrate manipulate", "area wind", "blown away", "strong wind effect"]"""


def _build_user_prompt(query: str, intent: Intent) -> str:
    """Build the user prompt with few-shot examples."""
    # Select 2-3 relevant examples based on intent
    relevant_examples = []
    for ex in FEW_SHOT_EXAMPLES:
        if ex["intent"] == intent.name:
            relevant_examples.append(ex)
        if len(relevant_examples) >= 2:
            break
    
    # If we don't have enough intent-matched examples, add general ones
    if len(relevant_examples) < 2:
        for ex in FEW_SHOT_EXAMPLES:
            if ex not in relevant_examples:
                relevant_examples.append(ex)
                if len(relevant_examples) >= 2:
                    break
    
    # Build examples section
    examples_text = ""
    for ex in relevant_examples:
        examples_text += f"""
Query: "{ex['query']}"
Intent: {ex['intent']}
Expansions: {json.dumps(ex['expansions'])}
"""
    
    return f"""Here are examples of good query expansions:
{examples_text}

Now expand this query:
Query: "{query}"
Intent: {intent.name}
Expansions:"""


def _parse_expansion_response(text: str) -> List[str]:
    """
    Parse the LLM response to extract expansion terms.
    
    Handles various formats:
    - Clean JSON array: ["term1", "term2"]
    - JSON with extra text: Some text ["term1", "term2"] more text
    - Numbered list: 1. term1\n2. term2
    - Bullet list: - term1\n- term2
    """
    text = text.strip()
    
    # Try to extract JSON array
    json_match = re.search(r'\[.*?\]', text, re.DOTALL)
    if json_match:
        try:
            terms = json.loads(json_match.group())
            if isinstance(terms, list):
                return [str(t).strip() for t in terms if t]
        except json.JSONDecodeError:
            pass
    
    # Try numbered list format: 1. term or 1) term
    numbered = re.findall(r'^\d+[\.\)]\s*(.+)$', text, re.MULTILINE)
    if numbered:
        return [t.strip().strip('"\'') for t in numbered]
    
    # Try bullet list format: - term or * term
    bullets = re.findall(r'^[\-\*]\s*(.+)$', text, re.MULTILINE)
    if bullets:
        return [t.strip().strip('"\'') for t in bullets]
    
    # Last resort: split on newlines and filter
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if lines:
        # Filter out lines that look like instructions
        terms = [l for l in lines if len(l) < 50 and not l.startswith('Query:')]
        return terms[:7]  # Cap at 7 terms
    
    return []


def expand_query(
    query: str,
    adapter: ModelAdapter,
    intent: Optional[Intent] = None,
    min_terms: int = 5,
    max_terms: int = 7,
) -> ExpansionResult:
    """
    Expand a query into multiple search terms using LLM.
    
    Args:
        query: The user query to expand
        adapter: ModelAdapter instance to use for generation
        intent: Optional pre-classified intent (will classify if not provided)
        min_terms: Minimum number of terms to generate
        max_terms: Maximum number of terms to return
        
    Returns:
        ExpansionResult with expanded terms and anchor terms from original query
    """
    from .index import tokenize_and_normalize
    
    # Classify intent if not provided
    if intent is None:
        intent = classify_intent(query)
    
    # Extract anchor terms from the original query
    # These are the terms that get priority weighting in scoring
    anchor_terms = tokenize_and_normalize(query)
    
    # Build prompts
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, intent)
    
    # Generate expansion
    result = adapter.generate(user_prompt, system_prompt)
    
    # Parse response
    terms = _parse_expansion_response(result.text)
    parsed_successfully = len(terms) >= min_terms
    
    # If parsing failed or too few terms, add fallback terms from query
    if not parsed_successfully:
        # Extract key terms from original query as fallback
        fallback_terms = anchor_terms.copy()
        terms = list(set(terms + fallback_terms))
    
    # Deduplicate and limit
    seen = set()
    unique_terms = []
    for term in terms:
        term_lower = term.lower().strip()
        if term_lower and term_lower not in seen:
            seen.add(term_lower)
            unique_terms.append(term)
    
    return ExpansionResult(
        original_query=query,
        anchor_terms=anchor_terms,
        expanded_terms=unique_terms[:max_terms],
        intent=intent,
        generation_result=result,
        parsed_successfully=parsed_successfully,
    )


def expand_query_with_model(
    query: str,
    model_name: str = None,  # Uses DEFAULT_EXPANSION_MODEL if None
    intent: Optional[Intent] = None,
) -> ExpansionResult:
    """
    Convenience function to expand query with a named model.
    
    Args:
        query: The user query to expand
        model_name: Name of model from EXPANSION_MODELS (defaults to DEFAULT_EXPANSION_MODEL)
        intent: Optional pre-classified intent
        
    Returns:
        ExpansionResult with expanded terms
    """
    effective_model = model_name if model_name is not None else DEFAULT_EXPANSION_MODEL
    adapter = create_adapter(effective_model)
    return expand_query(query, adapter, intent)


class QueryExpander:
    """
    Reusable query expander with cached adapter.
    
    Usage:
        expander = QueryExpander()  # Uses default model (gpt-5.2)
        result = expander.expand("What does flat-footed do?")
    """
    
    def __init__(
        self,
        model_name_or_config: Union[str, ExpansionModelConfig] = None,  # Uses DEFAULT_EXPANSION_MODEL
        few_shot_examples: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize the query expander.
        
        Args:
            model_name_or_config: Model name or config to use (defaults to DEFAULT_EXPANSION_MODEL)
            few_shot_examples: Optional custom few-shot examples
        """
        effective_model = model_name_or_config if model_name_or_config is not None else DEFAULT_EXPANSION_MODEL
        self.adapter = create_adapter(effective_model)
        self.few_shot_examples = few_shot_examples or FEW_SHOT_EXAMPLES
        self._call_count = 0
        self._total_latency_ms = 0.0
        self._total_tokens = 0
    
    def expand(
        self,
        query: str,
        intent: Optional[Intent] = None,
    ) -> ExpansionResult:
        """
        Expand a query into search terms.
        
        Args:
            query: The user query
            intent: Optional pre-classified intent
            
        Returns:
            ExpansionResult
        """
        result = expand_query(query, self.adapter, intent)
        
        # Track metrics
        self._call_count += 1
        if result.generation_result:
            self._total_latency_ms += result.generation_result.latency_ms
            self._total_tokens += result.generation_result.total_tokens
        
        return result
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics for this expander."""
        return {
            "call_count": self._call_count,
            "total_latency_ms": self._total_latency_ms,
            "avg_latency_ms": self._total_latency_ms / max(1, self._call_count),
            "total_tokens": self._total_tokens,
            "avg_tokens_per_call": self._total_tokens / max(1, self._call_count),
            "model_name": self.adapter.config.name,
            "model_id": self.adapter.config.model_id,
        }
    
    def reset_metrics(self) -> None:
        """Reset accumulated metrics."""
        self._call_count = 0
        self._total_latency_ms = 0.0
        self._total_tokens = 0
    
    def with_model(
        self,
        model_name_or_config: Union[str, ExpansionModelConfig],
    ) -> "QueryExpander":
        """
        Create a new expander with a different model.
        
        Useful for A/B testing different models.
        """
        return QueryExpander(model_name_or_config, self.few_shot_examples)
