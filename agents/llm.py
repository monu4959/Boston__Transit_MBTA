import os
import sys
from getpass import getpass
from dotenv import load_dotenv

load_dotenv()

PROVIDER = "anthropic"   # change to "openai" if your key is an OpenAI key
_key = None


def _get_key():
    global _key
    if not _key:
        key = (os.getenv("LLM_API_KEY") or "").strip()
        if not key:
            if not (sys.stdin and sys.stdin.isatty()):   # a server: never wait for typed input
                raise RuntimeError("LLM_API_KEY is not set")
            key = getpass(f"{PROVIDER} API key: ")
        _key = key
    return _key


def ask_llm(prompt):
    if PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=_get_key())
        msg = client.messages.create(
            model="claude-haiku-5-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if block.type == "text")
        if not text:
            text = f"(No answer text returned. stop_reason: {msg.stop_reason})"
        return text
    else:
        from openai import OpenAI
        client = OpenAI(api_key=_get_key())
        resp = client.chat.completions.create(
            model="gpt-4o-mini",   # check your OpenAI dashboard for current small models
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content