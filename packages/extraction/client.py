"""
client.py — OpenAI client wrapper with retry and JSON parsing.
"""
from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAI, RateLimitError, APIError, APIConnectionError


def get_openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def call_llm_json(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Call LLM expecting a JSON response. Retries on transient errors."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=60,
            )
            raw = response.choices[0].message.content or "{}"
            return json.loads(raw)
        except (RateLimitError, APIConnectionError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
        except APIError as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except json.JSONDecodeError as e:
            last_error = e
            if attempt < max_retries - 1:
                continue
            raise
    raise last_error or RuntimeError("call_llm_json failed after retries")


def generate_embedding(
    client: OpenAI,
    text: str,
    model: str = "text-embedding-3-small",
) -> list[float]:
    """Generate a 1536-dim embedding vector. Truncates input to ~8000 chars."""
    text = text.strip()[:8000]
    if not text:
        return [0.0] * 1536
    response = client.embeddings.create(input=text, model=model)
    return response.data[0].embedding
