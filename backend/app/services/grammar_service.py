"""Compatibility shim — all symbols now live in app.ai.grammar."""

from app.ai.grammar import GrammarCheckError, grammar_check_report_html

__all__ = ["GrammarCheckError", "grammar_check_report_html"]
