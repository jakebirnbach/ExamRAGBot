---
name: course-materials
description: Use when you need to know what is in data/raw - the student's Health & Wellness coaching course materials - e.g. writing eval or quiz questions, writing prompts that reference the course, debugging why a fact isn't retrieved, deciding topic/module mappings, or handling transcript quirks. Covers the corpus inventory, module structure and names, document types and their shapes, duplicates/exclusions, speech-to-text errors in transcripts, and where key concepts live. Triggers - "what's in the materials", "which module covers", "write questions", "quiz", "why can't it find", "transcript typo", "study guide", "slide deck".
---

# Course materials (data/raw/)

The materials belong to the student: the user's mom, a master's student in Health & Wellness,
in a health & wellness coaching course (handouts are headed "Health and Wellness Coach Certification"; it references NBHWC board certification). They are private: gitignored and never to
be redistributed. Never publish their text or commit files from `data/raw/`.

## Inventory (225 PDFs, about 2,170 pages, about 3.9M characters)

| Group | Files | Pages | Shape |
|---|---|---|---|
| `Module N Video Transcripts/M{n} L{l} Video {v} - Title.pdf` | 144 | 707 | Speech-to-text prose, about 3k chars/page. The core lecture content. |
| `Video Slides Handout - *.pdf` (top level) | 35 | 241 | 3 slides per page in scrambled reading order, sparse bullets, slide numbers inline. |
| `(NEW) Live Class Combined Slide Deck (4.21 to 6.25).pdf` | 1 | 713 | Very sparse slides (about 250 chars/page): live-class exercises, OARS/MI practice, scenarios. |
| `Health and Wellness Coaching - Study Guide (Full 138pp).pdf` | 1 | 138 | Dense, well-structured summary of all 6 modules with key terms bolded. Often the best single source. |
| Articles, reference sheets, checklists (top level) | 37 | 145 | e.g. lab test ranges, macro/micronutrient table, session checklists, sleep, burnout, nature. |
| `MyPlate Resources/` | 6 | 175 | Mostly `Dietary_Guidelines_for_Americans_2020-2025.pdf` (164 pages). |

Not indexed: `Health and Wellness Coaching - Study Guide.pdf` (the 48-page edition, via
`data/ingest_exclude.txt`); exact duplicates ending in ` (1)`; `Module 2 Video Transcripts.zip`
(the same 39 PDFs as the folder); `HEP.png` and a poster-images zip; and two image-only PDFs:
`The Latest Physical Activity Guidelines for Maximum Health Benefits.pdf` and `The Disordered
Eating-Eating Disorder Continuum.pdf` (an infographic; OCR could recover them later).
Note the real file name `Heatlh and Wellness Reference Guide.pdf` (sic).

## Modules (topic labels: `M{n} · {name}`)

1. Foundations of Health Coaching: what coaches do, credentials (NBHWC, 2012/2016), scope of practice, coaching vs education vs psychotherapy.
2. Setting Up & Conducting Sessions: coaching agreement, intake, rapport, active listening, presence, empathy, initial session, wellness vision, SMART goals, wellness wheel, follow-ups, ending agreements.
3. Health Behavior Change Theory: TTM (stages, processes, decisional balance, self-efficacy), SDT, theory of planned behavior, social cognitive theory, self-efficacy, social ecological model, appreciative inquiry, patient activation (PAM), neuroplasticity and habits.
4. Motivational Interviewing & Coaching Strategies: MI spirit (partnership, acceptance, compassion, evocation), the four processes (engaging, focusing, evoking, planning), OARS, change vs sustain talk, rolling with resistance, ambivalence, scaling questions, brainstorming, self-compassion.
5. Professional Practice, Ethics & Self-Care: ongoing development, self-care, scope, multiple roles, code of ethics, legal (confidentiality and data).
6. Health Promotion, Fitness, Nutrition & Wellness: prevention levels, Travis continuum, social determinants, physical activity guidelines (150 min), fitness components, digestion, macro/micronutrients, hydration (about 60% body water), processing (NOVA), diets, 8 wellness dimensions (physical, emotional, occupational, social, environmental, intellectual, spiritual, cultural; a separate article covers the "seven dimensions" model), chronic disease (CVD, diabetes, stroke, obesity, metabolic syndrome, autoimmune), substances, sleep, stress, breathwork, ACEs.

Lessons that exist in **both M2 and M4** (Follow-Up Session 1–3, Final Closing Session,
Coach and Client Debrief): files matched to these by title fall back to `General / Reference`.

## Transcript quirks (they matter for regexes, keyword search, and prompts)

Transcripts are automatic speech-to-text exports:
- Spaces before hyphens, **pervasive** in every module: `pre -contemplation`, `client -centered`, `check -in`, `time -bound`, `trans -theoretical`, `action -oriented`, `c -reactive`. Patterns should use `[\s-]*` between word parts.
- Misheard names and terms: `Protesta and DiClemente` (Prochaska), `Ryan and Desi` (Deci),
  `Self -Ethicacy`, `two -catted`, `[BLANK _AUDIO]`, `Sprit`/`Spritual` (also in file names).
- Filler and dialogue: two-presenter conversations (`Hi Stephanie. Hi Shanna.`) and role-play
  sessions (`Coach John Client Shana`), so not every chunk is expository.

Answers should rely on the study guide or handouts for correct spellings of names when the
transcript garbles them.

## Where concepts are duplicated

Most concepts appear in 3–5 places: the transcript, the slide handout, a study-guide section, the
live deck, and sometimes an article. Retrieval and evals should accept any of them (the eval uses
`also_accept`), and the per-source cap (2 chunks per file) keeps the top 5 varied.
