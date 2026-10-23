# foxlead/llm.py
# Claude se baat karne ka ek hi rasta. Har call ka token hisaab usage table mein
# jaata hai, taake admin panel mein kharcha dikh sake.

import anthropic

from . import config, db


class LLMError(Exception):
    """Claude se jawab nahi mila - message user ko dikhane layak hai."""


_client = None


def client():
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise LLMError("ANTHROPIC_API_KEY is not set on the server.")
        # max_retries: 429 / server error par SDK khud dobara try karta hai
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=4)
    return _client


def ask(prompt, *, user_id, kind, effort="low", max_tokens=2000, system=None):
    """Claude se text jawab lo. kind = score / comments / draft / chat (hisaab ke liye).
    prompt ek string ho sakta hai, ya poori baatcheet (messages list)."""
    messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
    extra = {"system": system} if system else {}
    try:
        resp = client().messages.create(
            model=config.MODEL_NAME,
            max_tokens=max_tokens,                  # thinking + jawab dono isi mein
            output_config={"effort": effort},
            messages=messages,
            **extra,
        )
    except anthropic.AuthenticationError as e:
        raise LLMError("The server's Claude API key is wrong.") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Claude is busy right now — please try again in a minute.") from e
    except anthropic.BadRequestError as e:
        raise LLMError(f"Claude rejected the request: {e.message[:200]}") from e
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        raise LLMError("Could not reach Claude — please try again.") from e

    with db.connect() as conn:
        db.record_usage(conn, user_id, kind, resp.usage)
    if resp.stop_reason == "refusal":
        raise LLMError("Claude declined this one.")
    # jawab mein thinking + text blocks hote hain - sirf text chahiye
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise LLMError("Claude sent back an empty answer — please try again.")
    return text
