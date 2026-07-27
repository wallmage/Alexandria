---
name: rewild
description: Rewrite text that explicitly sounds AI-generated, robotic, or formulaic so it reads more naturally. Use only when the user explicitly wants to humanize or de-AI text with requests like "humanize this", "de-AI this", "remove AI tone", "sounds like ChatGPT", "clean up AI slop", or "rewild this". Do not trigger for generic proofreading, copyediting, grammar fixes, summarization, translation, or routine style polish unless the user clearly says the problem is AI-sounding text.
---

# Rewild

Remove AI-writing tells without turning the text into fiction, parody, or a personality transplant.

## Use / Do Not Use

Use this skill when the user explicitly frames the problem as:
- sounding like AI
- sounding robotic or generic
- needing to be "humanized" or "de-AI'd"

Do not use this skill for:
- normal proofreading or grammar cleanup
- translation
- summarization
- neutral copyediting
- routine tone adjustment when the user does not mention AI-sounding text

## Core Rules

- Preserve meaning. Rewrite style, not substance.
- Never invent facts, names, dates, metrics, quotes, anecdotes, or personal experience.
- Preserve quotes, citations, links, code, legal wording, regulated claims, and technical terms unless the user asks to rewrite them.
- Match the genre. Human does not mean casual.
- If the text already reads naturally, say so and make only the lightest useful pass.
- When the source is vague, make it cleaner and more honest. Do not fake specificity.

## Quick-Reference Checklist

Run this before delivering any rewritten text:

- Three consecutive sentences roughly the same length? Break one up
- Paragraph ends with a tidy one-liner? Vary the exit
- Dash or colon before a dramatic reveal ("The best part: it learns")? Make it a plain sentence
- Explaining a metaphor? Trust the reader
- "Additionally" / "Furthermore" / "Moreover"? Cut or replace with "and" / "but" / nothing
- Rule of three? Make it two or four
- No first person anywhere? Add "I" where the original stance supports it
- No proper nouns? Pull forward real names already in the source
- Every sentence starts Subject-Verb? Reorder one
- No questions asked? Add a rhetorical one if the genre supports it
- Zero sensory language? Add one concrete detail from the source
- No self-correction or uncertainty? Show a mind at work
- Formulaic opener or closer ("In today's...", "In conclusion")? Cut it
- Final line is a "deep" kicker, polished aphorism, or lessons-learned wrap-up? Delete it — do not rewrite it into a better metaphor. End on the clearest concrete sentence already in the draft
- Informal register but zero contractions? Contract where you would when speaking
- Every paragraph roughly the same size? Split or merge one
- Same humanizing move used three times (fragments, self-corrections, rhetorical questions)? Vary or revert one

## Personality and Soul

Avoiding AI patterns is only half the job. Sterile, voiceless writing is just as obvious as slop. Good writing has a human behind it.

Signs of soulless writing (even if technically "clean"):
- Every sentence is the same length and structure
- No opinions, just neutral reporting
- No acknowledgment of uncertainty or mixed feelings
- No first-person perspective when appropriate
- No humor, no edge, no personality
- Reads like a Wikipedia article or press release
- No sensory details, no names, no dates

How to add voice without fabricating:

Have opinions. "I genuinely don't know how to feel about this" is more human than neutrally listing pros and cons.

Vary your rhythm. Short punchy sentences. Then longer ones that take their time. Mix it up.

Acknowledge complexity. "This is impressive but also kind of unsettling" beats "This is impressive."

Use "I" when the original stance supports it. First person is not unprofessional.

Let some mess in. Asides and half-formed thoughts are human. Self-correct mid-thought. But do not add tangents that introduce new topics — mess means texture, not new substance.

Be specific about feelings. Not "this is concerning" but ground it in something real from the source.

Name things. Pull forward real names, places, and details already in the source text. Never invent specifics that are not there.

Think out loud. "Actually, wait — that's not quite right" is more human than a pre-polished paragraph.

Vary your moves. If every text you rewild ends up with the same punchy fragments and staged self-corrections, you have replaced one formula with another. Voice is variance: pick two or three interventions per text and rotate which ones.

CRITICAL CONSTRAINT: every detail you add must already exist in the source text or be obviously inferable from it. Do not invent meetings, anecdotes, statistics, company names, cities, or first-person experiences.


## Workflow

1. Confirm the problem is actually AI tone rather than grammar, structure, or domain accuracy.
2. Mark non-rewrite zones: quotes, citations, links, code, terms of art, precise numbers, and compliance-sensitive language.
3. Identify the reader and the job of the text (inform, persuade, apologize, sell). Cut what serves neither. Note 3-5 voice signals worth preserving — vocabulary, cadence, bluntness, humor, uncertainty — and keep them through every edit.
4. Determine the genre and risk level.
5. Triage each paragraph:
   - Clean or nearly clean: leave it alone, or make one small fix.
   - A few tells: edit in place. Scan at least patterns 1-6 in [references/patterns.md](references/patterns.md); for stubborn tells, go deeper into the relevant category.
   - Dense slop (three or more tells): re-say it instead of editing it. Note the facts worth keeping, look away from the original, and write the paragraph fresh in the same register and genre as the original — business stays business, formal stays formal — the way a skilled human author of that genre would write it, not the way you would say it out loud. Re-saying changes the wording, not the order: keep the source's sequence of points and its paragraph boundaries. Reordering breaks the setups the source built — a lesson billed as "the most important" lands wrong once it has been moved to the end. Then reconcile everything against the source — situations and feelings count as facts too: anything the source does not support gets cut, not just names and numbers. Editing dense slop sentence by sentence preserves its skeleton; re-saying discards it.
   - Exception: press releases, announcements, policy text, and other written-form genres never get fully re-said, however dense the slop. Their written skeleton *is* the register, and re-saying slides into chat tone. Strip and tighten instead: delete the boilerplate sentences outright, compress what remains, keep the announcement's frame. Full re-saying is for essays, posts, and other pieces the voice carries.
6. Run the quick-reference checklist.
7. Second pass: get the rewrite reviewed with fresh eyes. Follow "Second Pass: Review With Fresh Eyes" below.
8. Run the bundled checker on your final text — this step is mandatory, not optional. Save both the original and the rewrite to files and run the script from this skill's own folder, passing both:
   `python3 <skill-dir>/scripts/naturalness-check.py REWRITE --source ORIGINAL --lang en`
   It exits 1 while anything is flagged and 0 when the report is clean.
   Treat the two halves of the report differently. **Style warnings are suggestions** — on text you triaged as already natural, do not edit just to silence a statistic; a justified warning beats an unjustified edit. **Fidelity warnings are defects.** A fidelity warning means the rewrite now says something the source did not, and the fix is always to change the rewrite, never to justify it. The only exception is a figure you derived arithmetically from figures in the source; say so and move on.
   Rerun until it exits 0, or until every remaining style warning has a stated reason and zero fidelity warnings remain. A clean report is not a passing grade; it only means the countable problems are gone.
9. Read it aloud in your head. Any sentence you would not say to a colleague in that register, rewrite plainly.

## Fidelity: The Four Leaks

Check these *after* drafting, not while writing. They are a verification pass, not a brake — write with the voice the section above describes, then come back and confirm you did not drift on any of the four. None of them is a name or a number, which is why the anti-fabrication rule misses them.

- **Attribution.** The source says "observers have cited X"; your rewrite says "X". You have taken someone else's claim as your own. Cutting vague attribution is right — but cut the claim with it, or keep the attribution.
- **Commitments.** The source describes; your rewrite promises. "We'll send another update," "we'll keep refining it" — if the source made no promise, you cannot make one on its author's behalf.
- **Severity.** The source says "impacted"; your rewrite says "nothing worked." Absolutes — nothing, never, always, completely, nobody — are facts about scale. Do not raise them.
- **Causal and diagnostic detail.** The source says a config error caused it; your rewrite adds "not the syntax, which was fine." Ruling things *out* is as invented as ruling them in.

## Second Pass: Review With Fresh Eyes

Never deliver the first draft of a rewrite. Someone with no memory of the original must look at it — you are the worst-placed reviewer of your own output, because you know what it used to say.

Use a subagent to do that blind review. Send it only the rewritten text and the Quick-Reference Checklist above — not the original, not the user's request, not your drafting notes. It reports which checklist items the text trips; it does not rewrite.

Apply the findings yourself, with the catalog open: fix real flags, skip nitpicks that would push the text into pattern 42 territory. Then check the final text against the original once more for invented details or drift.

## Genre Calibration

Informal writing, essays, blog posts:
- You can add warmth, sharper rhythm, and a clearer point of view.
- Use first person, rhetorical questions, and pauses only if the original stance supports them.
- Voice is not performance. The target is "same author, better day" — not a slicker, cooler author.
- A big idea rewritten in plain words is still a big idea. Delete the uplift; end on something concrete.
- "The biggest thing I learned" and "this experience taught me" are kickers too, however casual the tone. End an essay on a specific thing, an image, or a question still open — not on a summary.
- **Run an endings check when you're done.** Write out the last sentence of every paragraph, one per line. If each is short, dry, and lands a beat, that's a metronome, not a voice — at least two should end flat, dull, or mid-thought. Check the same way for: one detail that is mentioned and never picked up again (you want one), numbers rationed one per paragraph (you don't), and filler words spread evenly instead of clustered. This is the last tell to go in first-person writing; see [references/patterns.md](references/patterns.md) 26b.

Business writing:
- Remove hype and vague significance claims.
- Keep the register professional. Do not go breezy in the name of sounding human: the result is still written English — "three main updates," not "three things are new."
- End on the product or the plan ("we'll keep refining it"), not on a shrug.
- Cut unsourced praise ("industry experts believe") together with the claim it carried, and leave the gap. Do not fill it with a modest-sounding substitute ("we won't claim it's perfect") — a humble invention is still an invention.

Technical documentation:
- Prioritize clarity, concrete examples, and precise terms.
- Do not inject personality for its own sake.

Academic writing:
- Remove promotion, vague attribution, and fake ranges.
- Keep the register formal and evidence-aware. Do not force in contractions, exclamations, or conversational asides.

Legal, medical, support, and policy text:
- Be conservative.
- Accuracy, consistency, and traceability matter more than voice.

## Output

Provide:
1. The rewritten text
2. An optional short note naming the main AI-writing patterns removed

Rewilded text is typically shorter than the original because AI writing is padded. Do not add filler to match the original length.

Only score the result if the user asks for scoring.

## Quality Scoring (on request)

Rate the rewritten text on a 1-10 scale across 5 dimensions (total out of 50):

| Dimension | What to measure | Score |
|-----------|----------------|-------|
| Directness | States facts or tells a story around them? 10: cuts straight to it; 1: preamble everywhere | /10 |
| Rhythm | Sentence lengths varied? 10: short/long mix; 1: metronomic uniformity | /10 |
| Trust | Respects the reader's intelligence? 10: concise; 1: over-explains everything | /10 |
| Authenticity | Sounds like a real person? 10: natural, opinionated, specific; 1: robotic, generic | /10 |
| Precision | Uses exact words, names, numbers? 10: no filler; 1: vague abstractions | /10 |
| Total | | /50 |

45-50: Excellent. 35-44: Good, room for more personality. Below 35: Needs another pass.

## Full Worked Example

Before (AI-sounding):
> The new software update serves as a testament to the company's commitment to innovation. Moreover, it introduces batch processing, keyboard shortcuts, and offline mode, providing a seamless, intuitive, and powerful user experience — ensuring that users can accomplish their goals efficiently. It's not just an update, it's a revolution in how we think about productivity. Industry experts believe this will have a lasting impact on the entire sector.

After (rewritten):
> The update adds batch processing, keyboard shortcuts, and offline mode — the three features that matter. Not a revolution. Just a good update that does what people actually asked for.

Changes made:
- Removed "serves as a testament" (inflated symbolism, pattern 1)
- Removed "Moreover" (AI vocabulary, pattern 12)
- Removed "seamless, intuitive, and powerful" (adjective triplet + promotional, patterns 15, 2)
- Removed em-dash-ensuring construction (superficial -ing, pattern 8)
- Removed "It's not just...it's..." (negative parallelism, pattern 14)
- Removed "Industry experts believe" (vague attribution, pattern 3)
- Pulled forward the three concrete features already in the source (fixes pattern 10)

## Reference Files

- [references/patterns.md](references/patterns.md): detailed pattern catalog and rewrite cues

## Sources

The pattern catalog is based on Wikipedia's "Signs of AI writing" guide plus research from Tercon & Dobrovoljc (2025), Reinhart et al. (2024), Herbold et al. (2023), Opara (2025), Alsadhan (2026), and others documented in the references file.
