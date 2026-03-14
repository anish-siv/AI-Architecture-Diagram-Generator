"""
LLM analyser — sends curated repo context to an LLM and returns
structured architecture insights.  Supports OpenAI and Anthropic
via a provider-agnostic abstraction.
"""

import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import Config

# ── result dataclass ────────────────────────────────────────────────────────


@dataclass
class AnalysisResult:
    technologies: List[str] = field(default_factory=list)
    components: Dict[str, List[str]] = field(default_factory=dict)
    edges: List[Dict[str, str]] = field(default_factory=list)
    architecture_style: str = ""
    summary: str = ""


# ── system prompt ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior software architect.  You will receive:
1. A curated snapshot of a code repository (directory tree + key files).
2. A JSON object of technologies already detected by a rule-based scanner.

Your job is to analyse the repository and return a SINGLE JSON object with
exactly these keys (no markdown fences, no extra text):

{
  "additional_technologies": ["tech1", "tech2"],
  "architecture_style": "e.g. MVC Monolith, Microservices, Serverless, JAMStack",
  "components": {
    "Category Name": ["tech1", "tech2"]
  },
  "edges": [
    {"source": "Category A", "target": "Category B", "label": "description"}
  ],
  "summary": "A 2-4 sentence architectural summary of the project."
}

Guidelines:
- "components" should be the COMPLETE component map (merge your findings with
  the rule-based results — do not drop anything the scanner found).
- "edges" describe data-flow or dependency relationships between component
  categories (not individual technologies).  Arrows must reflect how HTTP
  actually works: browsers/clients INITIATE requests to backends, backends
  RESPOND.  For server-rendered apps, show both directions.
- "additional_technologies" lists ONLY technologies the rule-based scanner
  missed.  Do not repeat what was already found.
- Keep the summary concise and specific to THIS project.
- Return raw JSON only — no markdown code fences, no commentary.

Component classification rules:
- Group technologies by WHERE they run, not what they do.
- Server-side template engines (Thymeleaf, Jinja2, EJS, Pug, ERB) belong in
  "Backend" — they run on the server, not in the browser.
- Embedded auth middleware (Spring Security, Passport.js, Django auth, bcrypt,
  JWT libraries) belongs in "Backend" — it runs inside the backend process.
- Only EXTERNAL auth services (Auth0, Firebase Auth, Okta, AWS Cognito) should
  be a separate "Authentication" component.
- "Frontend" should only contain what runs CLIENT-SIDE in the browser (React,
  Vue, Angular, Bootstrap CSS, Font Awesome, client-side JS).
"""


def _build_user_prompt(context: str, rule_results: dict) -> str:
    sanitised = {
        "technologies": sorted(rule_results.get("technologies", [])),
        "components": rule_results.get("components", {}),
        "files_scanned": rule_results.get("files_scanned", []),
    }
    return (
        f"=== RULE-BASED SCAN RESULTS ===\n"
        f"{json.dumps(sanitised, indent=2)}\n\n"
        f"=== REPOSITORY SNAPSHOT ===\n"
        f"{context}"
    )


# ── provider abstraction ────────────────────────────────────────────────────


class LLMProvider(ABC):
    @abstractmethod
    def call(self, system: str, user: str, model: str) -> str:
        """Send a chat completion and return the assistant message text."""


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        try:
            import openai  # noqa: F811
        except ImportError:
            _die("openai package not installed. Run: pip install openai")
        self._client = openai.OpenAI(api_key=api_key)

    def call(self, system: str, user: str, model: str) -> str:
        resp = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        try:
            import anthropic  # noqa: F811
        except ImportError:
            _die("anthropic package not installed. Run: pip install anthropic")
        self._client = anthropic.Anthropic(api_key=api_key)

    def call(self, system: str, user: str, model: str) -> str:
        resp = self._client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=0.2,
        )
        return resp.content[0].text if resp.content else ""


_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}

# ── public API ──────────────────────────────────────────────────────────────


def analyze(
    context: str,
    rule_results: dict,
    config: Config,
) -> Optional[AnalysisResult]:
    """
    Call the configured LLM provider and parse the response.
    Returns None on failure (caller should fall back to rule-based output).
    """
    if not config.ai_enabled:
        return None

    provider_cls = _PROVIDERS.get(config.provider)
    if not provider_cls:
        print(f"Warning: unknown provider '{config.provider}', skipping AI pass.",
              file=sys.stderr)
        return None

    try:
        provider = provider_cls(config.api_key)
    except Exception as exc:
        print(f"Warning: failed to initialise {config.provider} client: {exc}",
              file=sys.stderr)
        return None

    user_prompt = _build_user_prompt(context, rule_results)

    try:
        raw = provider.call(_SYSTEM_PROMPT, user_prompt, config.model)
    except Exception as exc:
        print(f"Warning: LLM call failed: {exc}", file=sys.stderr)
        return None

    return _parse_response(raw)


# ── response parsing ────────────────────────────────────────────────────────


def _parse_response(raw: str) -> Optional[AnalysisResult]:
    """Parse the raw LLM JSON response into an AnalysisResult."""
    text = raw.strip()
    # Strip markdown fences if the model added them despite instructions
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        data: Dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        print("Warning: LLM returned invalid JSON, falling back to rules.",
              file=sys.stderr)
        return None

    return AnalysisResult(
        technologies=data.get("additional_technologies", []),
        components=data.get("components", {}),
        edges=data.get("edges", []),
        architecture_style=data.get("architecture_style", ""),
        summary=data.get("summary", ""),
    )


def _die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)
