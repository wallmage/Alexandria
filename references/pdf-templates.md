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

Keep an `[!INSIGHT]` short. The opening section's insight is promoted into the editorial opener's dark panel, and a panel over roughly 420 visual units (about 420 Latin characters or 210 Chinese glyphs) is left in the body flow instead, because it no longer fits the opener and used to push the page's lower grid onto a blank second sheet.

## Colour and contrast

Every template carries five colour roles, not one accent used five ways:

| Token | Role |
|---|---|
| `__ACCENT__` | decorative fills, rules, and diagram strokes. May be bright. Never carries body text. |
| `__ACCENT_TEXT__` | small uppercase labels and citation markers on white. AA on white *and* on the template's pale panel. |
| `__ON_ACCENT__` | text set **on** the accent fill, such as the takeaway band. White where the accent is dark enough to hold it, the template's dark ink where it is not. |
| `__LINK__` | body links on white or pale. A darkened relative of the accent, never the accent itself. |
| `__LINK_ON_DARK__` | links inside the dark insight panel. |

Body links are also underlined, so a link is identifiable in greyscale and to a reader who cannot separate the accent hue from black.

`scripts/pdf_quality.py` proves every pair against WCAG AA for all eleven templates as a pure-data check, with no render. Adding or retuning a template means adding its tokens to `ON_ACCENT`, `LINK_ON_LIGHT`, and `LINK_ON_DARK` in `scripts/pdf_templates.py` and re-running that check; `scripts/pdf_quality.adjust_to_contrast()` computes a passing value for you.

## Imagery

Use subject-relevant imagery when it materially improves the selected template. Prefer the assistant's built-in image generator: ask for a high-resolution, on-topic, positive, visually striking editorial image with professional art direction, clean composition, useful negative space for report typography, and no embedded words, logos, watermarks, or fabricated data. If generation is unavailable, use Google Images first and Bing Images as the fallback; verify the original source, resolution, relevance, and usage rights before downloading anything.

Save the verified raster beside the report Markdown and pass `--cover-image`; the renderer accepts PNG, JPEG, GIF, or WebP inside the report directory and blocks remote or out-of-directory files. Never use a search thumbnail, an unclear license, a negative or alarming image merely for drama, or an image that implies evidence the report does not contain.

Do not delay delivery merely to obtain artwork. Six templates - Maison, Horizon, Terrain, Orbit, Current, and Apricot - ship a licensed photograph in `assets/`, listed in `BUNDLED_TEMPLATE_IMAGES`. The other five draw generated, template-native openers instead.

`apricot-workshop.jpeg` is a workplace interior, which fits Apricot's workplace-culture and employee-experience half but not its care and public-health half. It is kept because it is at least a truthful human-scale workplace scene and no licensed replacement is available; pass `--cover-image` with a subject-appropriate photograph whenever an Apricot report is about care or health.

Blueprint and Sunbeam used to borrow a sibling's photograph: Blueprint printed Orbit's scientific plate in greyscale, and Sunbeam loaded Current's mobility ribbon into every PDF (its stylesheet then hid it, so readers paid the bytes and saw nothing). Neither image had anything to do with its template's subject matter, and no licensed replacement was available. Both now draw a plate in their own visual language - Blueprint an orthographic construction snapped to its own 13mm datum grid, Sunbeam its concentric-arc gradient - which is honest about being a designed mark rather than a photograph of something. A borrowed photo is worse than no photo: it makes a specific and false claim about the subject.

## Apparatus must refer to something

The editorial opener carries a running note and a plate number. These are derived from the section they actually sit on, not decorated: an opener over section 01 says "System note 01 / decision architecture" and "Datum 01A". They previously always said 03, on section 01, which is decoration impersonating structure - the one thing a research document cannot afford.

The same rule applies to cover diagrams. Blueprint's cover nodes carried A/B/C labels with no legend and no referent, and Executive's cover carried a three-step "scale" with terminal measurement nodes and no units. Both are now plainly decorative geometry. If a mark cannot be read, it must not look readable.
