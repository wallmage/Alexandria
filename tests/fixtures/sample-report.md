# R&D Systems: A Render Check

> July 2026

## Executive summary

This compact fixture checks typography, navigation, citations, and special characters. Its only factual purpose is to exercise the report pipeline.

## Key process

The pipeline converts Markdown into a styled PDF, builds a contents page, and keeps [a source link](https://example.com/research/a-very-long-but-valid-path-that-must-wrap-inside-the-page-instead-of-running-through-the-margin) clickable.

| Stage | Expected result |
|---|---|
| Parse | Safe HTML |
| Render | A4 PDF |
| Reopen | Extractable text |

```text
Long code lines should wrap safely instead of leaving the page.
```

## Outlook

The renderer should remain readable when headings, tables, code, and long links appear together.

## Sources

- [Example source](https://example.com/research/a-very-long-but-valid-path-that-must-wrap-inside-the-page-instead-of-running-through-the-margin)
