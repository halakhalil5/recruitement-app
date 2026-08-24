"""The one chat model every LLM call in this package goes through.

Routed at the iHQ LiteLLM proxy (OpenAI-compatible), not a direct Anthropic
key - see the team's LiteLLM connection docs. One place to change if the
endpoint, model, or key ever change.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()  # other modules build a model at import time - .env must be loaded before that happens

MODEL = "anthropic/claude-haiku-4-5"
BASE_URL = "https://litellm.i-hq.tech/v1"


def get_model(temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        api_key=os.environ["LITELLM_API_KEY"],
        base_url=BASE_URL,
        temperature=temperature,
        # structured-output calls (evaluate_candidate especially) return one
        # object per requirement; with no cap the proxy's default can cut a
        # long resume's response off mid-field, which pydantic then reports
        # as a "missing" field rather than a truncation error.
        max_tokens=32000,
    )
