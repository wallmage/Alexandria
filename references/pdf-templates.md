# PDF templates and report intake

Use this reference when acknowledging a new Alexandria assignment and again before rendering.

## Ask once, in one non-blocking batch

Immediately after the user's first Deep Research request, acknowledge the topic and ask all four questions together in a commentary update. Put the template question first and write in the user's language.

1. **What look and feel do you want?**
   - **A — Executive (Default).** A restrained consulting style built from ivory, navy, and teal, with editorial headings, precise rules, and evidence-led page layouts. It suits strategy, companies, finance, policy, organizations, and general business research.
   - **B — Spectrum.** A contemporary system of white, cobalt, violet, electric lime, and black, with flowing bands and bold signal panels. It suits technology, innovation, products, startups, and future-facing subjects.
   - **C — Atlas.** A field-journal style built from white, forest green, sage, quiet typography, and subject-relevant editorial imagery. It suits people, biography, history, culture, art, society, natural science, and geography.
   - **D — Horizon.** A sharp black, white, and cobalt-blue system with panoramic photography, floating observation cards, and strong editorial contrast. It suits infrastructure, climate and energy, geopolitics, supply chains, resilience, cities, and place-based market signals.
2. **Who should appear under “Prepared by”?** Default: Alexandria.
3. **Do you want a client name in the report?** Default: blank; omit the client field entirely.
4. **Do you want confidentiality wording and stamps on the report?** Default: Off. Explain that turning it on adds “Strictly Confidential” and the footer “Controlled copy · Not for external distribution.”

Do not ask these as four separate turns, and do not wait for an answer. Start framing and researching the topic immediately after sending the questions. Treat the questions as optional production preferences, never as permission to begin.

Keep the adaptive/default values active while research continues. If the user replies during the work, apply every supplied answer to the final production and keep the defaults for unanswered items. Resolve the final values immediately before rendering; if an answer arrives after a draft PDF was rendered but before delivery, rerender it. If no answer arrives, finish and deliver with the adaptive/default values.

## Select the template

An explicit template choice always wins. Without one, adapt from the topic:

- **Executive:** business, organizations, finance, policy, law, regulation, competition, industry, investment, leadership, or strategy.
- **Spectrum:** technology, AI, software, digital products, startups, innovation, automation, robotics, cyber, biotech, or future scenarios.
- **Atlas:** people, biography, history, culture, art, society, natural science, or geography.
- **Horizon:** infrastructure, climate risk, energy, geopolitics, supply chains, logistics, resilience, security, cities, transport, water, or place-based market signals.
- **Ambiguous or evenly mixed:** Executive.

Pass `--template auto` when the renderer should make the same deterministic selection. Pass the exact named template when the user chose one.

## Metadata contract

- Date: use the report metadata date when supplied; otherwise use today's date.
- Prepared by: Alexandria unless the user supplies another person or organization.
- Client: omit the label and field when blank.
- Confidentiality: omit all classification language when Off. When On, show “Strictly Confidential” on the cover and controlled-copy wording in the cover and page footer.
- Do not add document-control, engagement, report-to, owner, version, reading-guide, or other administrative fields.

## Visual components in Markdown

Use these portable blockquote markers only when the content earns the emphasis:

```markdown
> [!METRIC]
> **2.4×**
> Higher renewal intent in the reviewed cohort.

> [!INSIGHT]
> The scarce asset is judgment applied early enough to change the decision.

> [!TAKEAWAY]
> Reorganize the offer around the moments where evidence changes the path.
```

The renderer turns them into a metric card, a dark contrast panel, and a full-width takeaway band. Never invent a number to fill a visual component. Prefer one or two strong components per chapter over decorative repetition.

## Imagery

Atlas and Horizon benefit most from a subject-relevant cover image. When image generation or image search is available, create or obtain one useful editorial raster image, verify its relevance and usage rights, save it beside the report Markdown, and pass `--cover-image`. The renderer accepts PNG, JPEG, GIF, or WebP inside the report directory and blocks remote or out-of-directory files.

Do not delay delivery merely to obtain an image. Atlas includes a composed cartographic fallback, while Horizon ships with a bundled panoramic photograph so its cover and opening feature page never collapse into a flat gradient. Executive and Spectrum are designed to work without imagery.
