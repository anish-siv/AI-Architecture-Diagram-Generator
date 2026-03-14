"""
Architecture summarizer — produces a human-readable summary from
detected components, optionally enhanced by LLM output.
"""

from typing import Dict, List


def generate_summary(
    components: Dict[str, List[str]],
    files_scanned: List[str],
    llm_summary: str = "",
    architecture_style: str = "",
) -> str:
    """
    Return a Markdown-formatted architecture summary.

    When *llm_summary* is provided (from the AI pass), it is used as the
    primary narrative.  The structured bullet list is always appended.
    """
    if not components:
        return (
            "No technologies were detected. "
            "Make sure the repository contains recognisable config files "
            "(package.json, requirements.txt, Dockerfile, etc.)."
        )

    sections: List[str] = []
    sections.append("## Architecture Summary\n")

    if architecture_style:
        sections.append(f"**Architecture style:** {architecture_style}\n")

    sections.append(f"**Config files analysed:** {', '.join(files_scanned)}\n")

    for category in sorted(components):
        techs = components[category]
        sections.append(f"- **{category}:** {', '.join(techs)}")

    sections.append("")

    if llm_summary:
        sections.append(llm_summary)
    else:
        sections.append(_narrative(components))

    return "\n".join(sections)


def _narrative(components: Dict[str, List[str]]) -> str:
    """Build a plain-English paragraph describing the architecture."""
    parts: List[str] = []

    frontend = components.get("Frontend")
    backend = components.get("Backend")
    database = components.get("Database")
    cache = components.get("Cache/Database")
    auth = components.get("Authentication")
    cloud = components.get("Cloud Services")
    ai = components.get("AI/ML")
    queue = components.get("Task Queue")
    broker = components.get("Message Broker")
    container = components.get("Containerisation")
    cicd = components.get("CI/CD")

    if frontend:
        parts.append(
            f"The front-end is built with **{_join(frontend)}**."
        )
    if backend:
        parts.append(
            f"The back-end uses **{_join(backend)}**."
        )
    if database:
        parts.append(
            f"Data is persisted in **{_join(database)}**."
        )
    if cache:
        parts.append(
            f"**{_join(cache)}** is used for caching or as an in-memory store."
        )
    if auth:
        parts.append(
            f"Authentication is handled via **{_join(auth)}**."
        )
    if ai:
        parts.append(
            f"AI/ML capabilities are provided by **{_join(ai)}**."
        )
    if queue or broker:
        names = (queue or []) + (broker or [])
        parts.append(
            f"Asynchronous processing relies on **{_join(names)}**."
        )
    if cloud:
        parts.append(
            f"The project targets **{_join(cloud)}** for cloud infrastructure."
        )
    if container:
        parts.append(
            f"The application is containerised with **{_join(container)}**."
        )
    if cicd:
        parts.append(
            f"CI/CD is managed with **{_join(cicd)}**."
        )

    if not parts:
        parts.append("The detected technologies suggest a custom or minimal stack.")

    return " ".join(parts)


def _join(items: List[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
