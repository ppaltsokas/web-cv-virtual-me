import os

from fastapi import HTTPException


MAX_OUTPUT_TOKENS = 1536


def paid_ai_enabled():
    return os.getenv("PAID_AI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def online_evaluation_enabled():
    return paid_ai_enabled() and os.getenv("ONLINE_EVALUATION_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def require_paid_ai():
    if not paid_ai_enabled():
        raise HTTPException(status_code=503, detail="Chat is temporarily disabled. Please try again later.")


def output_token_limit(variable):
    limit = int(os.getenv(variable, str(MAX_OUTPUT_TOKENS)))
    if not 1 <= limit <= MAX_OUTPUT_TOKENS:
        raise ValueError(f"{variable} must be between 1 and {MAX_OUTPUT_TOKENS}")
    return limit
