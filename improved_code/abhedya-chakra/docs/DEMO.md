# Demo Playbook — Abhedya-Chakra

Everything needed to deliver the five minutes that 40% of the score depends on.
Owner: **M4**, driven by **M2**, narrated by **M1**.

---

## 1. Roles — agree these now, not at 7 a.m.

| Role | Who | Does |
|---|---|---|
| **Driver** | M2 | Hands on keyboard. Types only what the script says. Never improvises a click. |
| **Narrator** | M1 | Speaks. Answers technical questions. Watches the clock. |
| **Spotter** | M4 | Holds the backup laptop, sample PDFs open, demo video queued. Says nothing unless something breaks. |
| **Silent** | M3 | Ready to answer detection/metrics questions if asked. Otherwise silent. |

Two people talking at a hackathon demo sounds like panic. One voice.

---

## 2. The five-minute script

### 0:00–0:30 · The problem

> "A victim loses two and a half lakh rupees to a digital-arrest scam. The bank sends the investigating officer a CSV with **two million rows**. Today, finding where that money went takes days. The money is gone in hours."

*(No slides yet. Just say it. Make eye contact.)*

### 0:30–1:00 · The system is already loaded

Show the system status screen.

> "Two million transactions, ingested in forty-one seconds, fully indexed — on this laptop."

**Turn off the Wi-Fi, visibly.**

> "Everything from here runs offline. Nothing leaves this machine."

*(This is the single most memorable thirty seconds of the demo. Do it deliberately, with the Wi-Fi icon on screen.)*

### 1:00–2:00 · The blind query

> "Give us any victim account ID from the dataset."

Driver types it. Enter. The `query_ms` readout appears.

> "**Four hundred milliseconds.** ₹2,50,000 siphoned. One Layer-1 collector. Five Layer-2 distributors. Eleven Layer-3 cash-out nodes. ₹1,86,400 is still sitting in six accounts right now."

*(Point at the graph as you say each layer. The dagre layout reads left to right exactly like the problem statement diagram — let them see that.)*

### 2:00–2:45 · The evidence, not the picture

Click the Layer-1 collector.

> "This account received the full amount and dispersed ninety-nine percent of it within four minutes and ten seconds, split five ways. That velocity signature is what makes it a mule, and the system tells you *why* — it is not a black box score."

Click a Layer-3 terminal node.

> "IP address 185-dot-22, device `Linux_Script`, narration 'USDT P2P settlement'. This is where the money leaves the banking system."

### 2:45–3:15 · Time

Drag the timeline slider. Press Play.

> "The entire laundering operation completed in forty-five minutes, inside a fifteen-day dataset. Here it is minute by minute."

### 3:15–4:15 · Court-ready output

Click **FREEZE REQUISITION**. PDF appears.

> "A Section 94 BNSS notice — the provision that replaced Section 91 CrPC — generated per beneficiary bank, with exact account numbers, IFSC codes and disputed transaction IDs. Ready for the officer's signature."

Click **CASE DIARY**. Scroll to the chronology and the recommended-freeze list.

> "And the case diary: chronological, with every amount and timestamp, and a prioritised list of accounts to freeze first."

### 4:15–4:45 · The part nobody else will have

Point at the validation badge.

> "Forty-seven of forty-seven facts verified against the source dataset. The language model never writes a number — the database does. The model is only allowed to write prose; it is **programmatically forbidden from emitting digits**, and a validator re-checks every account, amount and transaction ID against the evidence before the document is released. That is how you get a legal document out of an AI system without hallucination."

### 4:45–5:00 · Close on numbers

Benchmark slide.

> "&lt;measured&gt;-second ingest. &lt;measured&gt;-millisecond trace. Detection F1 of &lt;measured&gt; under &lt;stated evaluation regime&gt;. Fully offline. Victim account to signed freeze notice in under two minutes."

**Read these off `docs/benchmarks.json` after `make bench`. Do not rehearse a number you have not measured, and always name the evaluation regime when you say "F1" — we may have no ground-truth labels (PRD §24.2).**

---

## 3. Pre-flight checklist

Print this. Tape it to the laptop. Tick it at 7:30 a.m.

```text
STATE
[ ] Dataset pre-ingested; artifacts present; backend warm
[ ] LRU cache pre-warmed on 5 test accounts
[ ] 20 verified test account IDs on a card next to the laptop
[ ] Wi-Fi off — full flow re-tested in that state

MACHINE
[ ] Resolution 1366×768, browser zoom 100%  (hackathon projectors are not Retina)
[ ] One browser tab. No bookmarks bar. No console open.
[ ] Notifications off. Do-not-disturb on. Slack/WhatsApp quit.
[ ] Power plugged in. Battery saver off. Screen sleep disabled.
[ ] Terminal font size bumped if any terminal will be shown

BACKUPS
[ ] Sample case_diary.pdf and freeze_requisition.pdf open in a second tab
[ ] 3-minute demo video on the desktop, tested, audio off
[ ] Backup laptop booted, same state, same test IDs
[ ] git tag v1.0-freeze pushed · USB copy · cloud copy

PEOPLE
[ ] Driver, narrator, spotter agreed
[ ] Script rehearsed end to end at least 3 times, timed
[ ] Whoever slept last has had coffee
```

---

## 4. When it breaks (it might)

| Symptom | Do this, immediately, without apologising |
|---|---|
| Query returns nothing | "This account looks like a mule rather than a victim — let me trace it upstream instead." Click the upstream button. **This is a feature, not a save.** |
| Graph is slow or frozen | Click `[Simplify view]`. "I'm capping this to the top hundred nodes by traced value — in a real investigation you never want the whole network on screen anyway." |
| Backend died | Spotter hands over the backup laptop. Narrator keeps talking through the architecture slide. Do not debug on stage. |
| LLM is slow | Toggle it off. "The documents are template-driven — the model only writes the narrative paragraph, so we don't depend on it." |
| Everything is on fire | Play the video. Keep narrating over it. Finish on the benchmark slide. |

**The rule: never say "it usually works". Narrate forward.** Judges remember composure more than they remember a glitch.

---

## 5. Expected questions, and the honest answers

| Question | Answer |
|---|---|
| *"How does this scale past two million rows?"* | "Ingestion is streaming-capable, so row count is bounded by disk, not RAM. The graph scales with *accounts*, not transactions — twenty-five thousand accounts is a few megabytes of CSR, so even a ten-times-bigger log barely changes traversal cost." |
| *"What if the mule pattern changes?"* | "Every threshold is in one config file, and the rule cards are pluggable. The scoring interface is `features → (score, reasons)`, so a learned model drops in behind the same contract without touching anything else." |
| *"How do you know the AI isn't making things up?"* | "It structurally cannot. The model is prompted with only the evidence summary and forbidden from emitting digits; all facts come from a typed evidence object sourced from the database; and a validator checks every account, amount and ID in the output against that object before release. We can show you the test where a lying model stub gets rejected." |
| *"What's your false-positive rate?"* | Give the real number and the two operating points — investigative at MRI ≥ 60, actionable at MRI ≥ 80. Then mention the named suppression rules you added after false-positive analysis. |
| *"Is this actually usable by a police officer?"* | "The workflow is one input field and one button. The output is a document in the format a nodal officer already processes. What it is not is a freeze actuator — a human officer verifies and signs. That boundary is deliberate." |
| *"Why not Neo4j / a GNN / Spark?"* | ADR answer: "Twenty-five thousand nodes doesn't need a graph database, and deployment simplicity is a scored criterion. A GNN is the roadmap, but with no supplied labels we'd be training on our own assumptions — heuristics we can explain beat a black box we can't." |
| *"What would you do with another week?"* | Cross-bank entity resolution, learned scoring with real labels, NCRP/1930 integration, multi-case management with audited chain of custody. |

---

## 6. Slide deck outline (8 slides, backup for the live demo)

| # | Slide | One line on it |
|---|---|---|
| 1 | Title | ABHEDYA-CHAKRA · the problem in one sentence |
| 2 | The problem | Victim → 2M rows → days of manual work → money gone |
| 3 | What we built | The pipeline diagram, one arrow per stage |
| 4 | Architecture | Fact store / graph store / feature store, and why they're separate |
| 5 | Detection | Rule cards → MRI 0–100 → layer assignment, with a real reason list |
| 6 | Anti-hallucination | The template-vs-model inversion diagram + the validation badge |
| 7 | Results | Benchmark table + precision/recall + the FP-fix progression |
| 8 | Scope & roadmap | What it is not, and what comes next |

Screenshots, not bullet lists, wherever possible. One idea per slide.

---

## 7. Final 30 minutes before judging

```text
T-30  Full dry run, timed, in demo conditions. Fix nothing afterwards.
T-20  Pre-flight checklist ticked top to bottom.
T-15  Backup laptop verified on the same test ID.
T-10  Stop touching the code. Close the editor. Really.
T-05  Driver and narrator run the first sixty seconds once more, quietly.
T-00  Wi-Fi off. Browser on the status screen. Breathe.
```

> The system is finished. The only variable left is the delivery.
