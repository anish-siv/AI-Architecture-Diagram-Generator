"""
Streamlit web UI for the AI Architecture Diagram Generator.

Launch with:
    streamlit run app.py
"""

import os
from pathlib import Path

import streamlit as st

from config import Config, DEFAULT_MODELS, resolve_config
from collector import collect
from detector import detect
from diagram import generate_mermaid
from llm_analyzer import AnalysisResult, analyze
from main import merge_results, build_output
from summarizer import generate_summary

# ── page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Architecture Diagram Generator",
    page_icon="🏗️",
    layout="wide",
)

# ── mermaid renderer ─────────────────────────────────────────────────────────


def render_mermaid(mermaid_code: str, height: int = 500) -> None:
    """Render a Mermaid diagram using mermaid.js embedded in an iframe."""
    escaped = mermaid_code.replace("`", "\\`").replace("${", "\\${")
    html = f"""
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
        <style>
            body {{
                background: transparent;
                display: flex;
                justify-content: center;
                padding: 1rem 0;
                margin: 0;
            }}
            #diagram {{
                width: 100%;
            }}
            .mermaid svg {{
                max-width: 100%;
                height: auto;
            }}
        </style>
    </head>
    <body>
        <div id="diagram" class="mermaid">
{mermaid_code}
        </div>
        <script>
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'neutral',
                flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: 'basis' }},
                securityLevel: 'loose',
            }});
        </script>
    </body>
    </html>
    """
    st.components.v1.html(html, height=height, scrolling=True)


# ── analysis pipeline ────────────────────────────────────────────────────────


def run_analysis(
    repo_path: str,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    no_ai: bool,
) -> dict:
    """Run the full detection + optional LLM analysis pipeline.
    Returns a dict with mermaid, summary, output_md, and metadata."""

    if api_key:
        env_var = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider, "")
        if env_var:
            os.environ[env_var] = api_key

    config = resolve_config(
        cli_provider=provider if not no_ai else None,
        cli_model=model if not no_ai else None,
        no_ai=no_ai,
    )

    rule_results = detect(repo_path)

    llm_result = None
    if config.ai_enabled:
        context = collect(repo_path)
        llm_result = analyze(context, rule_results, config)

    merged = merge_results(rule_results, llm_result)

    mermaid = generate_mermaid(
        merged["components"],
        edges=merged.get("edges"),
        architecture_style=merged.get("architecture_style", ""),
    )
    summary = generate_summary(
        merged["components"],
        merged["files_scanned"],
        llm_summary=merged.get("llm_summary", ""),
        architecture_style=merged.get("architecture_style", ""),
    )
    output_md = build_output(merged, mermaid, summary)

    return {
        "mermaid": mermaid,
        "summary": summary,
        "output_md": output_md,
        "technologies": sorted(merged.get("technologies", set())),
        "components": merged.get("components", {}),
        "files_scanned": merged.get("files_scanned", []),
        "architecture_style": merged.get("architecture_style", ""),
        "ai_used": config.ai_enabled and llm_result is not None,
    }


# ── sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Configuration")

    repo_path = st.text_input(
        "Repository path",
        placeholder="/path/to/your/repo",
        help="Absolute path to the local repository to analyse.",
    )

    st.divider()

    analysis_mode = st.radio(
        "Analysis mode",
        options=["AI-Enhanced", "Rules Only"],
        index=0,
        help="AI-Enhanced uses an LLM for deeper analysis. Rules Only runs offline with no API calls.",
    )
    no_ai = analysis_mode == "Rules Only"

    provider = None
    model = None
    api_key = None

    if not no_ai:
        provider = st.selectbox(
            "LLM Provider",
            options=["openai", "anthropic"],
            format_func=lambda x: {"openai": "OpenAI", "anthropic": "Anthropic"}[x],
        )

        default_model = DEFAULT_MODELS.get(provider, "")
        model = st.text_input(
            "Model",
            value=default_model,
            help=f"Default: {default_model}",
        )

        env_key_name = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider, "")
        has_env_key = bool(os.environ.get(env_key_name))

        if has_env_key:
            st.success(f"✓ `{env_key_name}` found in environment")
        else:
            api_key = st.text_input(
                "API Key",
                type="password",
                placeholder=f"Enter your {env_key_name}",
                help="Your key is never stored — it's only used for this session.",
            )

    st.divider()
    analyze_btn = st.button("🔍 Analyze Repository", use_container_width=True, type="primary")

# ── main content ─────────────────────────────────────────────────────────────

st.title("Architecture Diagram Generator")
st.markdown("Scan a local repository and generate an interactive architecture diagram.")

if analyze_btn:
    if not repo_path or not repo_path.strip():
        st.error("Please enter a repository path.")
    elif not Path(repo_path.strip()).is_dir():
        st.error(f"**{repo_path}** is not a valid directory.")
    else:
        repo = str(Path(repo_path.strip()).resolve())
        effective_no_ai = no_ai
        if not no_ai and not api_key and not os.environ.get(
            {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider or "", ""), ""
        ):
            effective_no_ai = True
            st.warning("No API key provided — falling back to rules-only mode.")

        with st.spinner("Analysing repository…"):
            try:
                result = run_analysis(repo, provider, model, api_key, effective_no_ai)
                st.session_state["result"] = result
                st.session_state["repo"] = repo
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")

if "result" in st.session_state:
    result = st.session_state["result"]
    repo = st.session_state["repo"]

    mode_label = "AI-Enhanced" if result["ai_used"] else "Rules Only"
    col1, col2, col3 = st.columns(3)
    col1.metric("Technologies", len(result["technologies"]))
    col2.metric("Components", len(result["components"]))
    col3.metric("Mode", mode_label)

    st.divider()

    # Diagram
    st.subheader("Architecture Diagram")
    render_mermaid(result["mermaid"], height=520)

    with st.expander("View Mermaid source"):
        st.code(result["mermaid"], language="text")

    st.divider()

    # Summary
    st.subheader("Architecture Summary")
    st.markdown(result["summary"])

    st.divider()

    # Details
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Detected Technologies")
        for tech in result["technologies"]:
            st.markdown(f"- `{tech}`")

    with col_right:
        st.subheader("Files Scanned")
        for f in result["files_scanned"]:
            st.markdown(f"- `{f}`")

    st.divider()

    # Download
    st.download_button(
        label="📥 Download Markdown",
        data=result["output_md"],
        file_name="architecture_output.md",
        mime="text/markdown",
        use_container_width=True,
    )
