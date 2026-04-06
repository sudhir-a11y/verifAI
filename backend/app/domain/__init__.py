"""Business (domain) layer for verifAI backend.

This package is intentionally framework-agnostic: no FastAPI, no SQLAlchemy session
management, and no direct HTTP/DB side effects. Keep domain modules focused on
business rules, parsing, validation, and orchestration that can be reused across
API routes and background workflows.
"""

