"""One function, llm(system, prompt) -> text, with two interchangeable providers.

Choose with environment variables (PowerShell examples):
    $env:LLM_PROVIDER = "gemini"            # or "anthropic"
    $env:LLM_MODEL    = "<model id>"        # copy the ID from AI Studio / the Anthropic docs
    $env:GEMINI_API_KEY = "..."             # or ANTHROPIC_API_KEY
Optional backup model, used if the main one stays overloaded:
    $env:LLM_FALLBACK_MODEL = "<another model id>"
Optional, Gemini only: less "thinking" = faster answers (minimal | low | medium | high):
    $env:LLM_THINKING = "minimal"
Never paste keys into code or commit them to Git.
"""
import os
import time

try:                                   # reads settings from the .env file in the project folder
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
MODEL = os.environ.get("LLM_MODEL", "")
FALLBACK = os.environ.get("LLM_FALLBACK_MODEL", "")
THINKING = os.environ.get("LLM_THINKING", "").strip().lower()   # empty = model default
RETRY_CODES = {429, 500, 502, 503, 504}     # busy / rate-limited / temporary server errors
WAITS = [2, 5, 10, 20]                      # seconds to wait between attempts


def _gemini(model, system, prompt):
    from google import genai                      # pip install google-genai
    from google.genai import errors, types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    use_thinking = bool(THINKING)
    for attempt in range(len(WAITS) + 2):
        cfg = types.GenerateContentConfig(system_instruction=system, temperature=0)
        if use_thinking:
            cfg.thinking_config = types.ThinkingConfig(thinking_level=THINKING.upper())
        try:
            return client.models.generate_content(model=model, contents=prompt, config=cfg).text
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if code == 400 and use_thinking and "think" in str(e).lower():
                print("  (this model rejected the thinking setting; continuing without it)")
                use_thinking = False
                continue
            if code in RETRY_CODES and attempt < len(WAITS):
                print(f"  (Gemini busy, error {code}; retrying in {WAITS[attempt]}s...)")
                time.sleep(WAITS[attempt])
                continue
            raise


def _anthropic(model, system, prompt):
    import anthropic                              # pip install anthropic
    client = anthropic.Anthropic()                # reads ANTHROPIC_API_KEY; retries built in
    msg = client.messages.create(
        model=model, max_tokens=600, temperature=0, system=system,
        messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text


def llm(system, prompt):
    if not MODEL:
        raise RuntimeError("Set the LLM_MODEL environment variable to a model ID.")
    call = {"gemini": _gemini, "anthropic": _anthropic}.get(PROVIDER)
    if call is None:
        raise RuntimeError(f"Unknown LLM_PROVIDER '{PROVIDER}'")
    try:
        return call(MODEL, system, prompt)
    except Exception as e:
        if FALLBACK:
            print(f"  (main model failed: {type(e).__name__}; trying fallback model)")
            return call(FALLBACK, system, prompt)
        raise
