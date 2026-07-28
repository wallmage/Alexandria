# PDF templates and report intake

Use this reference when acknowledging a new Alexandria assignment and again before rendering.

## Ask once, in one non-blocking batch

Immediately after the user's first Deep Research request, acknowledge the topic and ask all four questions together in a commentary update. Put the template question first and write in the user's language.

1. **What look and feel do you want?**
   - **A — Executive (Default).** Restrained ivory, navy, and teal consulting pages with editorial hierarchy and precise evidence layouts, best for strategy, finance, policy, companies, and general business research.
   - **B — Spectrum.** White, cobalt, violet, lime, and black form a bold contemporary signal system, best for digital products, media, consumer technology, startups, and future-facing subjects.
   - **C — Atlas.** Forest green, sage, quiet serif typography, and field-journal imagery create an editorial record, best for people, history, culture, art, society, and geography.
   - **D — Horizon.** Black, white, cobalt blue, panoramic photography, and floating observation cards create a decisive field-note aesthetic, best for infrastructure, energy, geopolitics, supply chains, resilience, and cities.
   - **E — Maison.** Warm ivory, monumental serif typography, refined photography, and generous editorial space create a premium magazine feel, best for luxury, hospitality, retail, travel, real estate, food, and consumer brands.
   - **F — Blueprint.** Black, white, and technical cyan combine with grids, datums, nodes, and process maps, best for operating models, organization design, engineering, governance, implementation, and transformation.
   - **G — Terrain.** Forest green, cream, aerial imagery, contour lines, and cartographic notation create a place-based field atlas, best for ecology, conservation, agriculture, water, land use, and natural resources.
   - **H — Orbit.** Electric cobalt, black, white, orbital geometry, scientific imagery, and measured typography create a precision research system, best for AI, semiconductors, robotics, advanced science, and deep technology.
   - **I — Sunbeam.** Ink black, tangerine, sunflower yellow, oversized serif type, and playful circular signals create an upbeat editorial system, best for entrepreneurship, education, youth, civic participation, social impact, and community initiatives.
   - **J — Current.** Warm white, flowing orange ribbons, friendly sans-serif typography, and route-like diagrams create an optimistic sense of motion, best for mobility, customer journeys, innovation programs, service operations, the future of work, and organizational change.
   - **K — Apricot.** Warm ivory, apricot accents, human-scale photography, and generous serif layouts create a calm, welcoming report, best for workplace culture, care, public health, learning, people strategy, and community wellbeing.
2. **Who should appear under “Prepared by”?** Default: Alexandria.
3. **Do you want a client name in the report?** Default: blank; omit the client field entirely.
4. **Do you want confidentiality wording and stamps on the report?** Default: Off. Explain that turning it on adds “Strictly Confidential” and the footer “Controlled copy · Not for external distribution.”

Do not ask these as four separate turns, and do not wait for an answer. Start framing and researching the topic immediately after sending the questions. Treat the questions as optional production preferences, never as permission to begin.

Keep the adaptive/default values active while research continues. If the user replies during the work, apply every supplied answer to the final production and keep the defaults for unanswered items. Resolve the final values immediately before rendering; if an answer arrives after a draft PDF was rendered but before delivery, rerender it. If no answer arrives, finish and deliver two PDFs containing the same report content: Executive as the default version and one topic-adaptive companion.

## Select the template

An explicit template choice always wins. Without one, adapt from the topic:

- **Executive:** business, organizations, finance, policy, law, regulation, competition, industry, investment, leadership, or strategy.
- **Spectrum:** digital products, media, entertainment, consumer technology, platforms, startups, creator businesses, gaming, or future scenarios.
- **Atlas:** people, biography, history, culture, art, society, natural science, or geography.
- **Horizon:** infrastructure, climate risk, energy, geopolitics, supply chains, logistics, resilience, security, cities, transport, water, or place-based market signals.
- **Maison:** luxury, hospitality, retail, travel, service design, premium consumer brands, food, wellness, or real estate.
- **Blueprint:** operating models, organization design, operations, process, governance, implementation, engineering, workflow, or enterprise transformation.
- **Terrain:** ecology, conservation, agriculture, biodiversity, land use, forestry, watersheds, wetlands, oceans, or natural resources.
- **Orbit:** AI, machine learning, semiconductors, robotics, automation, cyber, data science, biotech, aerospace, quantum, or deep technology.
- **Sunbeam:** entrepreneurship, education, youth development, civic participation, public engagement, the creative economy, social impact, or community initiatives.
- **Current:** mobility, customer journeys, service innovation, innovation programs, the future of work, work redesign, organizational change, or the circular economy.
- **Apricot:** workplace culture, employee experience, care, mental health, public or community health, lifelong learning, people and culture, or community wellbeing.
- **Ambiguous or evenly mixed:** use a stable topic hash to distribute the adaptive version across the portfolio instead of repeatedly choosing the same design.

An explicit template choice produces one PDF and always wins. Without a choice, render Executive plus the deterministic non-Executive companion selected for the topic; both use the already-approved Markdown, sources, citations, and Rewild receipt, so the second version adds no research or writing tokens and only one additional local rendering pass. If that second pass actually exceeds five minutes or cannot complete within the available runtime, deliver Executive alone and say so.

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

Use subject-relevant imagery when it materially improves the selected template. Prefer the assistant's built-in image generator: ask for a high-resolution, on-topic, positive, visually striking editorial image with professional art direction, clean composition, useful negative space for report typography, and no embedded words, logos, watermarks, or fabricated data. If generation is unavailable, use Google Images first and Bing Images as the fallback; verify the original source, resolution, relevance, and usage rights before downloading anything.

Save the verified raster beside the report Markdown and pass `--cover-image`; the renderer accepts PNG, JPEG, GIF, or WebP inside the report directory and blocks remote or out-of-directory files. Never use a search thumbnail, an unclear license, a negative or alarming image merely for drama, or an image that implies evidence the report does not contain. Do not delay delivery merely to obtain artwork: Maison, Horizon, Terrain, Orbit, Current, and Apricot include high-definition fallbacks, while Executive, Spectrum, Atlas, Blueprint, and Sunbeam remain complete without one.
