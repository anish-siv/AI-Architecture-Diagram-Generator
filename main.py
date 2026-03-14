#!/usr/bin/env python3
"""
AI Architecture Diagram Generator

Usage:
    python main.py /path/to/repo
    python main.py /path/to/repo --provider openai
    python main.py /path/to/repo --provider anthropic --model claude-3-5-sonnet-latest
    python main.py /path/to/repo --no-ai
    python main.py /path/to/repo -o custom_output.md
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from config import resolve_config
from collector import collect
from detector import detect
from diagram import generate_mermaid
from llm_analyzer import AnalysisResult, analyze
from summarizer import generate_summary

DEFAULT_OUTPUT = "architecture_output.md"

# ── merge logic ─────────────────────────────────────────────────────────────


def _merge_results(
    rule_results: dict,
    llm_result: Optional[AnalysisResult],
) -> dict:
    """
    Combine rule-based detection with LLM analysis.
    LLM components take priority; rule-based fills gaps.
    """
    if llm_result is None:
        return rule_results

    # Technologies: union of both
    all_techs = set(rule_results.get("technologies", set()))
    all_techs.update(llm_result.technologies)

    # Components: prefer the LLM map (it was asked to include everything),
    # then merge in any rule-based categories the LLM missed.
    merged_components: Dict[str, List[str]] = {}
    for cat, techs in llm_result.components.items():
        merged_components[cat] = list(techs)

    for cat, techs in rule_results.get("components", {}).items():
        if cat not in merged_components:
            merged_components[cat] = list(techs)
        else:
            existing = set(merged_components[cat])
            for t in techs:
                if t not in existing:
                    merged_components[cat].append(t)

    return {
        "technologies": all_techs,
        "components": merged_components,
        "files_scanned": rule_results.get("files_scanned", []),
        "edges": llm_result.edges,
        "architecture_style": llm_result.architecture_style,
        "llm_summary": llm_result.summary,
    }


# ── output builder ──────────────────────────────────────────────────────────


def build_output(result: dict, mermaid: str, summary: str) -> str:
    lines = [
        "# Architecture Diagram\n",
        "```mermaid",
        mermaid,
        "```\n",
        summary,
        "",
    ]
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan a repository and generate an architecture diagram.",
    )
    parser.add_argument(
        "repo",
        help="Path to the local repository to analyse.",
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output Markdown file (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic"],
        default=None,
        help="Force a specific LLM provider.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the default model for the chosen provider.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Run in rules-only mode (no LLM calls).",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not repo_path.is_dir():
        print(f"Error: '{repo_path}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    # Resolve AI configuration
    try:
        config = resolve_config(
            cli_provider=args.provider,
            cli_model=args.model,
            no_ai=args.no_ai,
        )
    except (ValueError, EnvironmentError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Pass 1: rule-based detection (always) ───────────────────────────
    print(f"Scanning repository: {repo_path}")
    rule_results = detect(str(repo_path))

    if not rule_results["technologies"]:
        print("Warning: no technologies detected by rule-based scanner.")

    print(f"Files scanned : {', '.join(rule_results['files_scanned']) or 'none'}")
    print(f"Technologies  : {', '.join(sorted(rule_results['technologies'])) or 'none'}")
    print(f"Components    : {', '.join(sorted(rule_results['components'])) or 'none'}")

    # ── Pass 2: LLM analysis (if configured) ────────────────────────────
    llm_result = None
    if config.ai_enabled:
        print(f"\nRunning AI analysis ({config.provider} / {config.model})...")
        context = collect(str(repo_path))
        llm_result = analyze(context, rule_results, config)
        if llm_result:
            print("AI analysis complete.")
            if llm_result.architecture_style:
                print(f"Architecture  : {llm_result.architecture_style}")
            if llm_result.technologies:
                print(f"AI found extra: {', '.join(llm_result.technologies)}")
        else:
            print("AI analysis returned no results, using rules only.")
    else:
        if not args.no_ai:
            print("\nNo API key found — running in rules-only mode.")
            print("Set OPENAI_API_KEY or ANTHROPIC_API_KEY for AI-enhanced output.")

    # ── Merge & generate output ─────────────────────────────────────────
    merged = _merge_results(rule_results, llm_result)

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
    output_text = build_output(merged, mermaid, summary)

    out_path = Path(args.output)
    out_path.write_text(output_text, encoding="utf-8")
    print(f"\nOutput saved to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
