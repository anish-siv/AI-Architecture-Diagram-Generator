"""
Mermaid diagram generator — turns detected components into a flowchart.
Accepts optional LLM-provided edges and architecture style.
"""

from typing import Dict, List, Optional

# Visual styles per component category
_SHAPE = {
    "Frontend":               ("[", "]"),
    "Backend":                ("[", "]"),
    "Database":               ("[(", ")]"),
    "Cache/Database":         ("[(", ")]"),
    "Search Engine":          ("[(", ")]"),
    "Authentication":         ("{{", "}}"),
    "Cloud Services":         ("([", "])"),
    "Containerisation":       ("([", "])"),
    "Orchestration":          ("([", "])"),
    "Infrastructure as Code": ("([", "])"),
    "CI/CD":                  ("([", "])"),
    "AI/ML":                  (">", "]"),
    "Task Queue":             ("[[", "]]"),
    "Message Broker":         ("[[", "]]"),
    "API Layer":              ("[/", "/]"),
    "ORM":                    ("[/", "/]"),
    "Payments":               ("{{", "}}"),
    "Email Service":          ("{{", "}}"),
    "Object Storage":         ("[(", ")]"),
    "Reverse Proxy":          ("([", "])"),
}


def _node_id(label: str) -> str:
    return label.replace(" ", "_").replace("/", "_").replace("-", "_")


def _shape(category: str) -> tuple:
    return _SHAPE.get(category, ("[", "]"))


def generate_mermaid(
    components: Dict[str, List[str]],
    edges: Optional[List[Dict[str, str]]] = None,
    architecture_style: str = "",
) -> str:
    """
    Build a Mermaid flowchart TD string.

    If *edges* (from LLM) are provided they are used directly;
    otherwise edges are inferred from the component map.
    """
    if not components:
        return "graph TD\n    empty[No components detected]"

    lines: List[str] = ["graph TD"]
    node_ids: Dict[str, str] = {}

    if architecture_style:
        safe = architecture_style.replace('"', "'")
        lines.append(f'    style_label["{safe}"]')
        lines.append(f"    style style_label fill:none,stroke:none")

    # Create nodes
    for category, techs in sorted(components.items()):
        label = f"{category}\\n({', '.join(techs)})"
        nid = _node_id(category)
        node_ids[category] = nid
        left, right = _shape(category)
        lines.append(f"    {nid}{left}\"{label}\"{right}")

    # Edges: prefer LLM-provided, fall back to rule-based inference
    if edges:
        resolved = _resolve_llm_edges(edges, node_ids)
    else:
        resolved = _infer_edges(components)

    for src, dst, label in resolved:
        src_id = node_ids.get(src)
        dst_id = node_ids.get(dst)
        if src_id and dst_id:
            if label:
                lines.append(f"    {src_id} -->|{label}| {dst_id}")
            else:
                lines.append(f"    {src_id} --> {dst_id}")

    return "\n".join(lines)


def _resolve_llm_edges(
    raw_edges: List[Dict[str, str]],
    node_ids: Dict[str, str],
) -> List[tuple]:
    """Convert LLM-provided edge dicts into (src, dst, label) tuples,
    silently dropping any that reference unknown categories."""
    resolved = []
    for e in raw_edges:
        src = e.get("source", "")
        dst = e.get("target", "")
        label = e.get("label", "")
        if src in node_ids and dst in node_ids:
            resolved.append((src, dst, label))
    return resolved


def _infer_edges(components: Dict[str, List[str]]) -> List[tuple]:
    """
    Return (source_category, dest_category, edge_label) tuples
    representing typical data-flow relationships.
    """
    cats = set(components.keys())
    edges: List[tuple] = []

    _SSR_TECHS = {"thymeleaf", "django", "rails", "jinja2"}

    if "Frontend" in cats and "Backend" in cats:
        backend_techs = set(components.get("Backend", []))
        if backend_techs & _SSR_TECHS:
            edges.append(("Frontend", "Backend", "HTTP requests"))
            edges.append(("Backend", "Frontend", "rendered HTML"))
        else:
            edges.append(("Frontend", "Backend", "API calls"))
    if "Frontend" in cats and "API Layer" in cats:
        edges.append(("Frontend", "API Layer", "queries"))
    if "API Layer" in cats and "Backend" in cats:
        edges.append(("API Layer", "Backend", "resolves"))

    if "Backend" in cats:
        has_orm = "ORM" in cats
        for db in ("Database", "Cache/Database", "Search Engine"):
            if db in cats:
                label = "read/write via ORM" if has_orm and db == "Database" else "read/write"
                edges.append(("Backend", db, label))
        if "Authentication" in cats:
            edges.append(("Backend", "Authentication", "delegates auth"))
        if "AI/ML" in cats:
            edges.append(("Backend", "AI/ML", "invokes"))
        if "Task Queue" in cats:
            edges.append(("Backend", "Task Queue", "enqueues"))
        if "Message Broker" in cats:
            edges.append(("Backend", "Message Broker", "publishes"))
        if "Payments" in cats:
            edges.append(("Backend", "Payments", "charges"))
        if "Email Service" in cats:
            edges.append(("Backend", "Email Service", "sends"))
        if "Object Storage" in cats:
            edges.append(("Backend", "Object Storage", "uploads"))
        if "Cloud Services" in cats:
            edges.append(("Backend", "Cloud Services", "deploys to"))
        if "ORM" in cats:
            edges.append(("ORM", "Database", "maps"))
        if "CI/CD" in cats:
            edges.append(("CI/CD", "Backend", "builds/deploys"))

    if "Task Queue" in cats and "Message Broker" in cats:
        edges.append(("Task Queue", "Message Broker", "consumes"))

    if "Containerisation" in cats and "Orchestration" in cats:
        edges.append(("Orchestration", "Containerisation", "manages"))

    return edges
