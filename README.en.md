# Alexandria

Alexandria takes its name from the Library of Alexandria and its ambition to gather all the world's knowledge. I built this project with the same aspiration: any subject, in any era or corner of the universe, should be open to serious inquiry.

**Give Alexandria a subject, and it puts a research desk to work. For a complex question, that team can investigate hundreds of sources, trace claims to the original evidence, assess their credibility, and cross-check independent accounts. An editor then turns the findings into a long-form report that explains how things work, why they happened, and what supports each major conclusion.**

Ancient history, modern technology, a person's life, a school of philosophy: each calls for different questions. Alexandria selects a research framework and runs successive rounds of searches. The material has to survive scrutiny before it earns a place in the report. Researchers look for evidence that could overturn their conclusions as well as evidence that supports them. Ten websites repeating one article count as one source. Official claims are distinguished from independent findings; unresolved disagreements stay visible, along with their implications.

Before drafting, the team organizes the evidence and works through the reasoning, and important citations receive priority in a final spot-check against the original pages. The finished report explains mechanisms, causes, and trade-offs, gives serious objections their due, and includes citations you can follow to check the argument yourself. You receive a typeset PDF and an editable Markdown manuscript, with a design chosen to suit the subject.

[简体中文](README.md) · [English](README.en.md) · [繁體中文（香港）](README.zh-HK.md)

Alexandria can research anything: there are no fixed subject limits. Delivery uses `alx`: init → fetch → find/claims → draft → check --fix → render. You receive a professionally produced PDF with citations beside the claims.

## A framework for any subject

Ming fiscal policy, a chipmaker, and a philosophical idea demand different lines of inquiry. Alexandria has six research frameworks. It selects the one that fits the subject and combines relevant dimensions when a question crosses fields.

| Subject | What the framework asks |
|---|---|
| **People** | How did their background shape their choices? Which decisions changed the course of their life? How do achievements, controversies, and historical circumstances connect? |
| **Organizations** | How did the organization begin and evolve? How does it operate? What makes it competitive? How are power and interests distributed? |
| **Products, technologies, and creative works** | What makes it work? How has it changed? How well does it perform in practice? What are its strengths and limits compared with alternatives? |
| **Events** | Which conditions made the event possible? What triggered it? What did each party do? How do its consequences persist? |
| **Concepts, theories, and methods** | What problem was it meant to solve? What is its underlying logic? How has it developed? Which criticisms and counterexamples are hardest to answer? |
| **Industries, institutions, and systems** | How do the rules work? Where do money, information, and power flow? Who benefits, who pays, and what drives change? |

From there, Alexandria builds a set of specific questions, identifies the evidence needed, and defines what would count as a sufficient answer. Questions that could change the conclusion take priority.

The framework catches omissions; the subject determines the chapters. A history report might follow decisive turning points. A technology report might move from first principles to practical limits.

## An editor and a team of researchers

The AI you give the assignment to is the **main agent**, which acts as editor. It can delegate specific investigations to other AI assistants called **sub-agents**, which act as researchers. Each researcher searches for material, checks evidence, and returns its findings to the editor.

The editor first decides what the report needs to answer, then divides the work. One researcher might examine the history and original records, another check current data and real-world performance, and another investigate disputes, failures, and contrary evidence. Each has a defined assignment. The editor keeps track of the whole argument and decides where the evidence is sufficient and where more work is needed.

You supply the subject; Alexandria handles the assignments and brings the results together. In an environment that supports multiple agents, investigations can run in parallel. Otherwise, it works through the same research plan sequentially.

Searches start with names, aliases, and specialist terms, then pursue original material such as papers, archives, financial filings, and public data. Researchers also examine independent reporting and participants' accounts, including later corrections or retractions. Where necessary, they search in the sources' original language.

Researchers return evidence, citations, contradictions, open questions, and preliminary analysis. The editor combines the findings, removes duplicates, checks which results corroborate one another, and takes responsibility for the final argument.

How much research is enough depends on the question. Major questions need supporting evidence; unresolved ones need a record of the disagreements and gaps. Before stopping, the team checks that further searching is no longer changing its judgment. There is no fixed source quota.

## Assess the sources. Test the conclusions.

### Credibility depends on provenance and evidence

Alexandria distinguishes five source categories according to their relationship to the subject:

| Source category | What gets checked |
|---|---|
| **Primary and independent** | Does the source have direct access to the evidence? Are its research or recording methods sound? |
| **Primary with a vested interest** | What do official documents, vendor data, or participants' statements actually establish? Which parts remain their own claims? |
| **Secondary and independent** | Did the source investigate independently? Can its account be traced to original evidence? |
| **Secondary and dependent on other reporting** | Is it repeating existing material, or has it verified anything further? |
| **Anonymous, unverifiable, or republished** | Where did it originate? Can it be checked? Is it useful only as a lead for further investigation? |

It also distinguishes financial disclosures, peer-reviewed research, preprints, official documentation, independent tests, interviews, opinion, and marketing material. Confidence is assessed as high, medium, or low for the individual claim.

Authority and independence are separate questions. A financial filing can substantiate reported revenue; it cannot establish that a product is better. A company announcement establishes that a plan was announced, not that the plan will work. A familiar masthead adds no independent evidence to an article that merely repeats another source.

### Ten articles may still be one source

Ten websites republishing an article share a single origin. Multiple pages from one institution, or several studies using the same dataset, do not automatically amount to independent corroboration either.

Alexandria groups sources with a common origin. Adequate corroboration of a major claim requires at least two independent source families, with at least one independent of the subject being studied. If the evidence falls short, the report lowers its confidence and explains the limitation.

When accounts conflict, researchers compare dates, definitions, samples, and interests before looking for original records and subsequent corrections. If the conflict can be resolved, the report explains which account it accepts and why. If it cannot, the disagreement and its effect on the conclusion remain in the report.

### Look for evidence that could prove the argument wrong

Before accepting a central conclusion, Alexandria formulates the strongest competing explanation and searches for evidence that would distinguish between them. Failures, negative results, limits, and objections from people involved are part of the assignment.

A claim that a technology leads its field, for example, needs more than favorable benchmarks. Researchers examine test conditions, failure cases, and alternatives. The final judgment has to stand up to that contrary evidence.

### Build the evidence record before writing

Important claims have an evidence record: an excerpt or location in the original, its source and date, confidence, relevant contradictions, and the reasoning that connects the evidence to the conclusion. Facts, participants' claims, estimates, and analysis are recorded separately.

Before drafting, Alexandria checks quotations, consolidates duplicate sources, addresses disputes, and records gaps. Before delivery, it spot-checks the online originals, prioritizing citations that support major conclusions, to confirm the recorded evidence is actually on the cited page. Time-sensitive information also gets a freshness check.

## History should read differently from a technology analysis

Alexandria has six writing modes, available in both Chinese and English. The editor chooses a main mode for the subject, then decides where the story begins, which material deserves space, and how to explain the evidence.

You can describe the approach through a writer whose work you know. For Chinese history, that might mean drawing on Ray Huang's way of understanding personal choices through institutions and historical conditions. For an English biography, it might mean drawing on Walter Isaacson's use of consequential decisions to organize a life. These are references for the craft of writing; the agents write the report from verified material.

| Mode | A suitable subject | How the writing works |
|---|---|---|
| **Historical** | Chinese history, such as Ming fiscal policy | Begin with a concrete issue such as silver, then examine how taxation, trade, and local government affected one another. Place personal choices in their historical setting, follow turning points, and distinguish what people understood at the time from later interpretations. |
| **Investigative** | Geopolitics, conflict, and contested events | Use a war correspondent's verification discipline. Separate what each party says from what the records establish and what independent sources confirm. Explain events through interests and actions, preserve uncertainties, and source any details of conditions on the ground. |
| **Narrative** | An English biography or a study of a founder | Organize the account around decisions that changed a life: the circumstances, available choices, and consequences. Build the portrait from documented experiences, statements, and turning points, then connect it to the wider historical setting. |
| **Analytical** | Business or technology research in either language, such as NVIDIA | Use the approach of long-form business and technology journalism. State the central argument, then examine hardware, the software ecosystem, and customer dependence. Compare advantages, costs, and alternatives, and explain what could weaken the company's position and when the argument would cease to hold. |
| **Explanatory** | Technical principles or philosophical ideas, such as existentialism | Start with a concrete problem and work through the concepts and logic, as a good science writer would. Explain terms when they first appear. Use disagreements, counterexamples, and limits to test the understanding the reader has just built. |
| **Critical** | Evaluating a product, creative work, or body of thought | Describe the subject accurately before setting out the criteria for judgment and comparing credible alternatives. Explain the verdict, reasonable objections to it, and what evidence could change it. |

These choices shape the whole report. In history, the circumstances of the period deserve space; in biography, so do the experiences that shaped a life. A technology analysis must explain both principles and practical constraints. Individual sections can develop differently while the report retains a consistent main mode.

Chinese and English have their own editing rules. Simplified Chinese uses natural Chinese phrasing; Hong Kong Traditional Chinese follows local vocabulary and written usage. English editing attends to diction, sentence rhythm, and the connections in an argument. Figures, quotations, and necessary qualifications must remain faithful to the evidence in every mode.

## A finished report you can read, check, and reuse

Alexandria includes **11 visual templates** for business reports, history and the humanities, technology, ecology, and other subjects. By default, you receive two PDFs with identical content: one in Executive and another in a style selected for the subject. You can also request a particular template.

Reports include a cover, contents page, chapters, and clickable citations. After generation, the PDF is reopened to check text, links, fonts, pagination, and overflow. Page images are inspected for clipping, blank pages, and other layout problems, which are then corrected. See the [template guide](references/pdf-templates.md) for design options.

You receive:

- **A full-length report:** 5,000–10,000 non-whitespace characters in Chinese, or 7,500–15,000 words in English. The report reaches that length through additional evidence and deeper analysis.
- **Checked PDFs:** produced with a target of roughly ten pages or more; actual length depends on language and layout.
- **The Markdown manuscript:** ready to search, quote, edit, or build on.
- **Citations beside the claims they support:** so you can verify the evidence and continue reading the original sources.

## Why can a run take half an hour?

A complete research assignment follows this sequence:

**Define the questions → Assign the searches → Assess the sources → Cross-check and seek contrary evidence → Consolidate the findings → Draft the report → Produce and visually check the PDFs**

Some steps need another pass. Conflicting sources can send researchers back to the original records. An argument that looks under-supported in the draft calls for more research. An edit that affects a conclusion requires another evidence check.

Complex subjects may take half an hour or longer. Actual time depends on the question, the availability of material, the model, and the environment it runs in.

## Start your first report

Give the repository link or ZIP to an agent that supports skills, web research, and local execution, and ask:

> Install this skill for me.

The agent follows [INSTALL.md](INSTALL.md) to set up the environment and verify PDF generation. Once installed, give it a subject:

> Use Alexandria to research why Ming fiscal policy remained so dependent on silver. Explain the roles of institutions, trade, and local government. Write the report in Chinese.

> Use Alexandria to investigate NVIDIA's competitive advantages. Examine hardware, its software ecosystem, and customer dependence, then test the factors most likely to weaken its position.

> Use Alexandria to explain existentialism: the problems it addresses, its main disagreements, and how it influences everyday choices.

Include an angle, intended audience, or period if you have one. A subject alone is enough to begin.
