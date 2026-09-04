# PRD — The Lenny Growth Assistant

**Owner:** Forward Deployed Engineering
**Status:** v1.0 — Take-Home Submission
**Last Updated:** 2026-09-04

---

## 1. Problem Statement

*Lenny's Podcast* holds hundreds of hours of tactical, hard-won product and growth advice from operators at Airbnb, Notion, Figma, Superhuman, and dozens of other companies. That knowledge is functionally locked away — buried in unsearchable audio and loosely-organized transcripts. A growth PM trying to answer "how did Notion structure their PLG funnel?" has no faster path than scrubbing episode timestamps by hand.

The Lenny Growth Assistant turns that transcript archive into a queryable, cited knowledge base, and adds a second capability on top: turning any grounded answer into a publish-ready essay using the Ship 30 for 30 writing framework — so insight consumption and insight *distribution* live in the same tool.

## 2. Target Persona

**"Priya" — Senior Growth PM, Series B/C startup**
- Owns activation and retention experimentation; reads/listens to Lenny's Podcast for tactics she can apply this quarter.
- Time-constrained: will not listen to a 90-minute episode for one tactic.
- Skeptical of AI tools that hallucinate confidently — trusts an answer only if she can trace it to a specific guest and episode.
- Occasionally needs to turn a good insight into an internal memo or LinkedIn post for her own thought leadership.

## 3. Goals

| # | Goal | Why it matters |
|---|------|-----------------|
| G1 | Grounded, cited Q&A over podcast transcripts | Core trust requirement — no answer without a source |
| G2 | One-click "Ship 30 for 30" essay generation from any answer | Turns retrieval into a content engine, not just a search box |
| G3 | Claude-style sandboxed artifact viewer | Safe rendering of generated Markdown/HTML without XSS risk |
| G4 | Local (Ollama) + cloud (Claude/OpenAI) model parity | Cost control, data locality, and demo-ability without API keys |
| G5 | Single-command deploy (`docker-compose up`) | Forward-deployed reality: this needs to run on a client laptop, not just my machine |

### Non-Goals (v1)
- Multi-podcast / multi-source ingestion (scoped strictly to Lenny's Podcast)
- Multi-tenant auth, roles, or team workspaces
- Fine-tuning or training custom models
- Mobile-native clients

## 4. Success Metrics

| Metric | Target | How it's measured |
|---|---|---|
| Retrieval Citation Accuracy | ≥ 90% | 30-question golden eval set with known correct episode/guest; automated grading script compares cited episode against ground truth |
| Local Inference Latency (first token) | < 4s | P50 latency on the minimum spec (4-core/16GB) running `llama3.1:8b` |
| Artifact Render Safety | 0 XSS vulnerabilities | Manual pentest checklist (script injection, `srcdoc` escape attempts, `postMessage` abuse) run against `SandboxedIframe` |
| Out-of-domain refusal rate | 100% of clearly out-of-scope queries refused, not hallucinated | Adversarial eval set of 15 questions with no transcript coverage |

## 5. Key Trade-offs

- **Local 8B reasoning depth vs. cloud quality.** Small local models synthesize less reliably over long, multi-chunk context, especially for the 1,250-word Ship 30 essay. Mitigation: lower temperature (0.3), a rigid section-by-section prompt template, and a stricter word-count tolerance band rather than relying on the model's own judgment of "done."
- **HNSW recall vs. query speed.** `pgvector`'s HNSW index trades a small amount of recall for sub-100ms query time. Acceptable at this corpus size (~3-6k chunks); would revisit with IVFFlat + exact rerank at 10x scale.
- **Sandbox strictness vs. artifact interactivity.** Omitting `allow-same-origin` on the artifact iframe means generated HTML/JS can't persist to `localStorage` or read parent cookies — a deliberate security ceiling, not an oversight. Any artifact needing persistence uses `postMessage` back to the parent, which the parent explicitly validates and rate-limits.
- **Single-user local deploy vs. production hardening.** This is scoped as a forward-deployed, single-tenant tool running on a client's infrastructure — not a multi-tenant SaaS. Auth, rate limiting, and audit logging are stubbed with clear extension points, not fully built out, to keep the v1 scope honest.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Transcript archive licensing/availability changes | Ingestion pipeline is source-agnostic; point it at any local corpus of Markdown/TXT transcripts |
| Local model download size (4-8GB) on constrained hardware | `docker-compose` Ollama service pulls a 3B model by default; 8B is opt-in via `.env` |
| SSE streaming reliability behind corporate proxies | Fallback to buffered (non-streaming) response mode via `X-Stream-Mode: buffered` header |
| Golden eval set becoming stale as new episodes drop | Eval set is versioned in `backend/tests/fixtures/`, re-run in CI on every ingestion script change |

## 7. Open Questions for Stakeholder Review
- Should the Ship 30 essay be regenerable with user-supplied tone/persona overrides, or fixed to one voice for v1?
- Is a single default cloud provider (Claude) sufficient, or does the client require OpenAI parity on day one?
