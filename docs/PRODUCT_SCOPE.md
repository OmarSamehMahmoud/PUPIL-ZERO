# Product scope — PUPIL ZERO MVP

## Product principle
A student teaches an AI classmate. The classmate uses a controlled misconception profile to ask follow-up questions. The product turns the interaction into formative evidence for the learner and teacher.

## First demonstrator
- Audience: Egyptian preparatory-school learners.
- Subject: Mathematics.
- Topic: fractions (original sample prompts).
- Interaction: Arabic text and browser-native speech input/output.
- Persona: MILO, initially.
- Teacher output: transcript plus conservative evidence indicators.

## What this MVP is — and is not
This repository currently implements a local web prototype and a deterministic conversation/assessment scaffold. It does **not** yet call an LLM, provide human-like free-form dialogue, or provide validated educational measurement. Do not describe the current version as a fully autonomous AI tutor.

Next engineering milestones:
1. Replace canned turn responses with a provider-neutral dialogue interface.
2. Add curriculum-grounded retrieval and strict source metadata.
3. Add persona state machine and misconception-specific follow-up paths.
4. Add teacher report with transcript evidence spans.
5. Validate assessment against expert-created annotations before reporting accuracy.
6. Add school/guardian consent and retention controls before any real minor pilot.

## Design constraints
- No dedicated hardware.
- Text mode must remain available if browser speech APIs are unsupported.
- No raw audio storage by default.
- Never infer a student's mental health, intelligence, or diagnosis.
- Do not expose a numeric score as a formal grade.
