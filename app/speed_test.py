"""Find out why the LLM call is slow.   Run from the project folder:
    python app/speed_test.py
It sends the same tiny request per model and thinking level (default, low, medium) and prints
the time and how many "thinking tokens" were used. Each call gives up after 90 seconds, and the
SDK is told not to retry silently, so what you see is what the server really did.
To compare several models:   $env:SPEED_MODELS = "model-a,model-b"
To choose levels:            $env:SPEED_LEVELS = "default,low"
"""
import os
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from google import genai
from google.genai import types

models = [m.strip() for m in os.environ.get("SPEED_MODELS", os.environ.get("LLM_MODEL", "")).split(",") if m.strip()]
if not models:
    raise SystemExit("Set LLM_MODEL (or SPEED_MODELS) first.")

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(timeout=90_000, retry_options=types.HttpRetryOptions(attempts=1)))
PROMPT = "Write one SQLite query that counts rows in table blocks where category = 'Safe'. Output only the SQL."

levels = [None if x == "default" else x.upper()
          for x in os.environ.get("SPEED_LEVELS", "default,low,medium").lower().split(",") if x.strip()]

for model in models:
    for level in levels:
        cfg = types.GenerateContentConfig(temperature=0)
        if level:
            cfg.thinking_config = types.ThinkingConfig(thinking_level=level)
        label = f"{model} | thinking={level or 'model default'}"
        t = time.time()
        try:
            r = client.models.generate_content(model=model, contents=PROMPT, config=cfg)
            u = r.usage_metadata
            print(f"{label}: {time.time() - t:.1f}s | thinking tokens: {u.thoughts_token_count} "
                  f"| output tokens: {u.candidates_token_count}")
        except Exception as e:
            print(f"{label}: FAILED after {time.time() - t:.1f}s -> {type(e).__name__}: {str(e)[:200]}")
