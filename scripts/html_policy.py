"""Shared positive allowlist for report HTML validation and rendering."""

from urllib.parse import urlparse

SAFE_TAGS = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "br",
        "code",
        "del",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
)

SAFE_ATTRIBUTES = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt", "title"}),
    "h1": frozenset({"id"}),
    "h2": frozenset({"id"}),
    "h3": frozenset({"id"}),
    "h4": frozenset({"id"}),
    "h5": frozenset({"id"}),
    "h6": frozenset({"id"}),
    "code": frozenset({"class"}),
}


def safe_link_destination(value):
    """Return whether a rendered anchor destination is safe."""
    value = str(value or "").strip()
    parsed = urlparse(value)
    return value.startswith("#") or (
        parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)
    )


def safe_image_destination(value):
    """Return whether an image uses a renderer-supported local/data source."""
    value = str(value or "").strip()
    parsed = urlparse(value)
    return (
        not value.startswith("//")
        and not parsed.netloc
        and parsed.scheme.casefold() in {"", "file", "data"}
    )
