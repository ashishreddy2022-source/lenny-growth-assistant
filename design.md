# Design Spec — The Lenny Growth Assistant

## 1. Layout: Dual-Pane Interface

```
┌───────────────────────────────┬─────────────────────────────────┐
│  LEFT PANE (Chat) — 55%        │  RIGHT PANE (Artifact) — 45%     │
│                                 │  collapsible, closed by default  │
│  ┌───────────────────────────┐ │                                   │
│  │ Session selector ▾  [Ollama▾]│                                 │
│  ├───────────────────────────┤ │  ┌─────────────────────────────┐ │
│  │                             │ │  │ Artifact: <title>    [✕]    │ │
│  │  Message history            │ │  │ ─ Sandboxed Preview ─        │ │
│  │  (streaming bubbles)        │ │  │                              │ │
│  │                             │ │  │  <rendered md / iframe html> │ │
│  │  [Episode: Guest, 14:32]    │ │  │                              │ │
│  │  citation chips under       │ │  └─────────────────────────────┘ │
│  │  each grounded answer       │ │  [Copy]  [Download]  [Ship30 ✎]  │
│  ├───────────────────────────┤ │                                   │
│  │ [Ask a question...]  [↑]   │ │                                   │
│  └───────────────────────────┘ │                                   │
└───────────────────────────────┴─────────────────────────────────┘
```

- **Left pane** is always present; it's the primary surface.
- **Right pane** slides in only when a message produces an artifact (a `ship30` essay or an HTML snippet). It is not a permanent split — most Q&A turns never open it, which keeps the chat pane full-width by default.
- **Provider badge** (`ModelSelector.tsx`) sits in the chat header, not buried in settings — the assignment's grounding-vs-speed trade-off is something the user should see and control every turn, not configure once and forget.

## 2. Component State Machine

```
        ┌─────────┐   user sends message   ┌────────────┐
        │  idle    │ ──────────────────────►│  retrieving │
        └─────────┘                         └─────┬──────┘
             ▲                                     │
             │                          chunks found│chunks empty
             │                                     ▼         ▼
             │                          ┌────────────┐  ┌────────────────┐
             │                          │  streaming  │  │ out_of_domain   │
             │                          └─────┬──────┘  │ (canned message)│
             │                                │          └────────┬────────┘
             │            stream complete,    │                   │
             │            no artifact tag     │  artifact tag      │
             │◄───────────────────────────────┤  detected          │
             │                                ▼                    │
             │                     ┌─────────────────────┐         │
             │                     │ artifact_rendering   │         │
             │                     └─────────┬────────────┘         │
             │                               │ render success/error  │
             └───────────────────────────────┴────────────────────────┘
                                idle (right pane open if artifact)
```

- `retrieving`: shows a skeleton/status chip (`"Retrieving transcripts..."`) sourced from the SSE `status` event — never a generic spinner, so the user knows *what* is happening during the latency budget defined in the PRD (<4s to first token).
- `out_of_domain`: renders visually distinct from a normal answer (muted background, no citation chips) so it's never mistaken for a grounded response.
- `artifact_rendering`: the right pane mounts `SandboxedIframe` (HTML) or `react-markdown` (Markdown) only after the full artifact payload is received — no partial-HTML streaming into the iframe, since incremental `srcdoc` updates would either flicker or risk rendering unterminated/unsafe markup mid-stream.

## 3. Interaction Details

- **Citation chips** are individually clickable — clicking `[Episode: Guest, 14:32]` doesn't play audio (out of scope) but expands an inline snippet of the exact retrieved chunk, so the user can verify grounding without leaving the chat.
- **Ship 30 trigger**: every grounded assistant message gets a small `✎ Ship 30` affordance. Clicking it re-sends the same retrieved context with `mode="ship30"` rather than re-running retrieval — this avoids a second (possibly different) retrieval pass producing an essay grounded in different sources than the answer the user just read.
- **Provider switch mid-session**: switching the badge only affects the *next* message; existing messages in history keep a `provider` tag so the transcript honestly reflects which model produced which answer (relevant for the demo video's trade-off discussion).

## 4. Responsive Behavior

| Breakpoint | Behavior |
|---|---|
| `≥ 1024px` (desktop) | Side-by-side dual-pane as above |
| `640–1023px` (tablet) | Artifact pane becomes a full-width overlay (slide-over from the right) instead of a fixed split, triggered by the same open/close state |
| `< 640px` (mobile) | Single-column; artifact opens as a full-screen route (`/artifact/:id`) with a back button, since a docked pane isn't usable at that width |

Tailwind breakpoints (`md:`, `lg:`) map directly to this table — no custom media queries needed.

## 5. Accessibility & Empty States

- Streaming text updates use `aria-live="polite"` on the message container so screen readers announce new tokens without interrupting on every character.
- Empty session state: a short set of example prompts ("What did Brian Chesky say about 100 Detail?") rather than a blank input — reduces first-query friction for the demo and for real usage.
- Artifact pane empty state (before any artifact exists): a one-line hint, not a blank panel, explaining what triggers it.
