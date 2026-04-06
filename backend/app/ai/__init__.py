"""AI integration layer.

Contains external AI client calls (LLM/OCR/grammar/etc.) plus prompt building and
response normalization. This layer must not access the database directly.
"""

# Shared clients
from app.ai.openai_chat import OpenAIChatError, chat_completions, extract_message_text
from app.ai.openai_responses import OpenAIResponsesError, extract_responses_text, responses_create

# Subpackages
from app.ai.audit import run_openai_merged_medical_audit
from app.ai.extraction import ExtractionConfigError, ExtractionProcessingError, run_extraction
from app.ai.grammar import GrammarCheckError, grammar_check_report_html
from app.ai.structuring import (
    ClaimStructuredDataNotFoundError,
    ClaimStructuringError,
    generate_claim_structured_data,
    get_claim_structured_data,
    sync_clean_provider_registry_for_claim,
)
from app.ai.claims_conclusion import generate_ai_medico_legal_conclusion

__all__ = [
    # Shared clients
    "chat_completions",
    "extract_message_text",
    "OpenAIChatError",
    "responses_create",
    "extract_responses_text",
    "OpenAIResponsesError",
    # Grammar
    "grammar_check_report_html",
    "GrammarCheckError",
    # Extraction
    "run_extraction",
    "ExtractionConfigError",
    "ExtractionProcessingError",
    # Structuring
    "generate_claim_structured_data",
    "get_claim_structured_data",
    "sync_clean_provider_registry_for_claim",
    "ClaimStructuringError",
    "ClaimStructuredDataNotFoundError",
    # Audit
    "run_openai_merged_medical_audit",
    # Conclusion
    "generate_ai_medico_legal_conclusion",
]
