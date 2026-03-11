# PROMPTS.md — Reusable Claude + LLM Prompts for SkillPointe Match

## Purpose

This file contains:

1. **Reusable Claude build prompts** for repo development
2. **Reusable Claude review/debug prompts** for iteration
3. **Base LLM prompts** for extraction, verification, explanation, and planning chat

Use this file together with:

- `CLAUDE.md`
- `DECISIONS.md`
- `SCORING_CONFIG.yaml`
- `BUILD_PLAN.md`

---

# Part 1 — How to Start Any Claude Build Session

At the start of a Claude build session, first paste:

- `CLAUDE.md`
- `DECISIONS.md`
- `SCORING_CONFIG.yaml`
- `BUILD_PLAN.md`
- optionally this `PROMPTS.md`

Then use this session header:

```text
Before doing any work, read and follow:
- CLAUDE.md
- DECISIONS.md
- SCORING_CONFIG.yaml
- BUILD_PLAN.md
- PROMPTS.md

At the start of your response, always state:
- Current Phase
- Current Step
- Depends On
- What exists already
- What this task will change
- What must be tested after this task
- Next Step

Do not add batch matching or deferred acceptance to MVP.
Do not make LLMs the sole ranking engine.
Do not skip geography, admin review, RBAC, or auditability.
Keep deterministic fit estimation separate from policy reranking and LLM-assisted interpretation.
```
