# Product scope — PUPIL ZERO

## Product principle
A student teaches an AI classmate. The classmate asks follow-up questions from a misconception-oriented profile. The interaction creates formative evidence for learner reflection and teacher review.

## Implemented in this repository
- FastAPI + SQLite local web application.
- Arabic RTL student experience with text interaction and optional browser speech APIs.
- Three selectable classmates: MILO, NOURA, ZIZO, with distinct local-LLM persona prompts.
- Three original demonstrator learning units: fractions, decimals, introductory ratios.
- Local Ollama and OpenAI-compatible inference adapters.
- Explicit deterministic demo fallback when no model is configured.
- Teacher dashboard at `/teacher`, with session list, transcript detail, and keyword evidence indicators.

## Not yet production-ready
- No teacher/student authentication or role-based authorization.
- No multi-school or class management.
- No verified Egyptian Ministry grade/term mapping or imported official textbook content.
- No validated assessment model; evidence is keyword matching only.
- No expert-reviewed pedagogical evaluation, accessibility audit, or minor-pilot approval.
- Browser voice recognition is not guaranteed offline.

## Required next milestones
1. Add authentication, authorization, school/class boundaries, and secure deployment settings.
2. Add teacher-controlled student identifiers or pseudonyms, consent workflows, retention and deletion controls.
3. Verify each lesson's grade/term mapping against the official current curriculum and record source/version metadata.
4. Expand original lesson content with teacher review and clear learning objectives.
5. Replace keyword-only assessment with expert-annotated evidence spans and evaluate agreement.
6. Run usability, safeguarding, and learning-outcome pilots before making efficacy claims.

## Design constraints
- Local-first operation remains the default.
- Text mode must work without browser speech support.
- Do not store raw audio by default.
- Never infer mental health, intelligence, or diagnosis.
- Do not present a coverage indicator as a formal grade.
- Do not expose the unauthenticated teacher dashboard beyond localhost.
