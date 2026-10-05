"""Google Search grounding: tool config, metadata extraction and source formatting.

Nothing here invents data. Sources come only from url_citation annotations the
API returned on the answer text; queries come only from google_search_call
steps; the search-suggestions widget is the HTML Google returned.
"""

from _future_ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .helpers import (
    display_domain,
    is_http_url,
    iter_text_blocks,
    md_escape,
    read_field,
    truncate,
    type_of,
)

MAX_SNIPPETS_PER_SOURCE = 2
SNIPPET_CHARS = 160


@dataclass
class Source:
    title: str
    domain: str
    url: str
    snippets: list[str] = field(default_factory=list)  # text this source supports


@dataclass
class SearchInfo:
    used: bool = False
    queries: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    suggestions_html: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def google_search_tools() -> list[dict[str, str]]:
    """The built-in Google Search tool for the Interactions API."""
    return [{"type": "google_search"}]


def _snippet(text: str, start: Any, end: Any) -> str:
    """The span of answer text a citation supports (clamped to valid bounds)."""
    if not isinstance(start, int) or not isinstance(end, int) or not text:
        return ""
    start = max(start, 0)
    end = min(end, len(text))
    if start >= end:
        return ""
    return truncate(text[start:end], SNIPPET_CHARS)


def extract_search_info(interaction: Any) -> SearchInfo:
    """Collect search queries, cited sources and suggestions from a response."""
    info = SearchInfo()
    called = False
    by_url: dict[str, Source] = {}

    for step in read_field(interaction, "steps", []) or []:
        kind = type_of(step)
        if kind == "google_search_call":
            called = True
            arguments = read_field(step, "arguments")
            for query in read_field(arguments, "queries", []) or []:
                if isinstance(query, str) and query.strip() and query not in info.queries:
                    info.queries.append(query.strip())
        elif kind == "google_search_result":
            for item in read_field(step, "result", []) or []:
                html = read_field(item, "search_suggestions")
                if isinstance(html, str) and html.strip():
                    info.suggestions_html = html

    for block in iter_text_blocks(interaction):
        text = read_field(block, "text", "") or ""
        for annotation in read_field(block, "annotations", []) or []:
            if type_of(annotation) != "url_citation":
                continue
            url = read_field(annotation, "url")
            if not is_http_url(url):
                continue
            title = str(read_field(annotation, "title", "") or "")
            source = by_url.get(url)
            if source is None:
                domain = display_domain(title, url)
                source = Source(title=title or domain, domain=domain, url=url)
                by_url[url] = source
            snippet = _snippet(
                text,
                read_field(annotation, "start_index"),
                read_field(annotation, "end_index"),
            )
            if (
                snippet
                and snippet not in source.snippets
                and len(source.snippets) < MAX_SNIPPETS_PER_SOURCE
            ):
                source.snippets.append(snippet)

    info.sources = list(by_url.values())
    info.used = called or bool(info.sources)
    return info


def why_search_text(mode: str, queries: list[str] | None = None) -> str:
    """Plain-language product explanation (not model reasoning)."""
    if (mode or "").lower() == "search":
        text = (
            "You asked Nexa to research this answer, so it looked up current "
            "information on the web."
        )
    else:
        text = (
            "Nexa searched for current information because this question may "
            "depend on facts that change over time."
        )
    if queries:
        shown = "; ".join(f"“{md_escape(q)}”" for q in queries[:5])
        text += f"\n\nSearches run: {shown}"
    return text


def format_sources_markdown(sources: list[dict[str, Any]] | list[Source]) -> str:
    """Render sources as a numbered Markdown list with what each one supports."""
    lines: list[str] = []
    for index, raw in enumerate(sources, start=1):
        src = raw if isinstance(raw, dict) else asdict(raw)
        url = str(src.get("url", "")).replace(" ", "%20").replace(")", "%29")
        domain = str(src.get("domain", ""))
        title = str(src.get("title", "")) or domain
        label = md_escape(truncate(title, 90))
        suffix = f" — {md_escape(domain)}" if domain and domain != title else ""
        lines.append(f"{index}. [{label}]({url}){suffix}")
        for snippet in src.get("snippets", []) or []:
            lines.append(f"    - Supports: “{md_escape(snippet)}”")
    return "\n".join(lines)
