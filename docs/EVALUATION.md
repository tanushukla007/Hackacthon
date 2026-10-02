# Evaluation — Abhedya-Chakra

How we measure whether this thing actually works, and the numbers to fill in before submission.
Owner: **M3 (Detection / Data)**, with M1 on the performance benchmarks.

---

## 1. What the judges score

| Criterion | Weight | Measured by |
|---|---:|---|
| Blind victim query | **40%** | 5 unannounced victim account IDs → trace, L1, L2, L3, live visualisation |
| Detection accuracy | **30%** | Precision / recall against 1,500 injected mule accounts among 23,500 regular accounts |
| Court-ready output | **20%** | Quality, factual accuracy, readiness of the S.94 BNSS notice and case diary |
| Architecture & engineering | **10%** | Code quality, memory management, deployment simplicity |

Everything below exists to produce defensible numbers for rows 1, 2 and 4, and a defensible process for row 3.

---

## 2. Detection metrics

### 2.1 Definitions

With the account-level binary task (*is this account a mule?*) over all N ≈ 25,000 accounts:

```text
            predicted mule      predicted normal
 actual mule      TP                   FN
 actual normal    FP                   TN

 Precision = TP / (TP + FP)      "of the accounts we accused, how many were mules?"
 Recall    = TP / (TP + FN)      "of the real mules, how many did we catch?"
 F1        = 2PR / (P + R)
 FPR       = FP / (FP + TN)      "how much noise do we hand the investigator?"
```

**Prediction rule:** `predicted_mule = MRI ≥ τ`, where τ is chosen by the sweep in §2.3.

**Ground-truth availability: UNKNOWN.** The problem statement describes 1,500 mule + 23,500 regular accounts, and we observe ≈24,873 accounts — consistent, but **we hold no labels** (mentor Q1, OPEN). Until that is resolved every metric below is reported under the **heuristic self-validation** regime and must be labelled as such. Never present a self-validated score as accuracy against ground truth.

**Class balance (as described by the PS):** 1,500 / 25,000 = **6% positives**. Accuracy is a useless metric here (predicting "nobody is a mule" scores 94%). **Never report accuracy. Report precision, recall, F1 and the PR curve.**

### 2.2 Operating-point philosophy

Precision and recall are not symmetric in this domain:

- A **false negative** means stolen money walks out of the banking system.
- A **false positive** means an investigator wastes time on an innocent account — and, if it reaches a freeze notice, an innocent citizen loses access to their money.

We therefore run **two operating points** and say so explicitly:

| Point | Threshold | Use |
|---|---|---|
| **Investigative** (recall-leaning) | `MRI ≥ 60` | What appears in the money trail and case diary — cast wide, a human reviews |
| **Actionable** (precision-leaning) | `MRI ≥ 80` | What appears in the freeze requisition — accuse only when confident |

Reporting both is a better answer to a judge than a single tuned number, and it is the honest engineering position.

### 2.3 Threshold sweep protocol

```text
for τ in 40, 45, 50, … 90:
    compute TP, FP, FN, TN, P, R, F1, FPR
plot PR curve, mark the knee
pick τ* = argmax F1               → report as the headline number
pick τ_act = smallest τ with P ≥ 0.95  → the freeze threshold
```

Record the full table — a sweep table is far more convincing than one number:

| τ | TP | FP | FN | Precision | Recall | F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 40 | | | | | | |
| 50 | | | | | | |
| 60 | | | | | | |
| 70 | | | | | | |
| 80 | | | | | | |
| 90 | | | | | | |

### 2.4 Per-layer classification

Layer labels are **relative to a victim** (PRD §16), so layer accuracy is evaluated per victim query:

| Layer | Precision | Recall | Notes |
|---|---:|---:|---|
| L1 collector | | | depth-1 from victim + collector role |
| L2 distributor | | | depth-2 + fan-out 3–7 |
| L3 terminal | | | terminal signals or no onward flow |

Also report **confusion between adjacent layers** (L2 called L3 is a much smaller error than L1 called L3) and the **mean confidence** of correct vs incorrect assignments — if confidence does not separate them, the confidence score is not doing its job.

---

## 3. Ground truth

### 3.1 If labels are supplied
Load `data/raw/labels.csv` (`account_no, is_mule, layer`), join on the account dictionary, run §2.3. Done.

### 3.2 If labels are not supplied — synthetic injection

`tools/inject_mules.py` builds a validation set we control:

```text
1. Copy the dataset.
2. Sample K victims (default 100) from accounts with a plausible retail profile.
3. For each victim, synthesise a laundering chain:
      victim ──(₹50k–₹5L, one debit)──▶ L1 collector
      L1 ──(split into 3–7, 90–99% of inflow, 3–15 min later)──▶ L2 distributors
      L2 ──(split again, some to existing accounts)──▶ L3 terminals
      L3: foreign IP (185.x / 194.x), Web_Emulator or Linux_Script,
          crypto/wallet narration, sink ratio ≥ 0.85
4. Vary difficulty deliberately:
      easy   (40%): textbook pattern, all signals present
      medium (40%): one signal missing, slower velocity (20–60 min)
      hard   (20%): partial pass-through (70–85%), no terminal signal,
                    mixed with legitimate traffic on the same accounts
5. Write labels.csv with account_no, is_mule, layer, chain_id, difficulty.
```

Then report metrics **broken down by difficulty**. "F1 0.94 on easy, 0.88 on medium, 0.71 on hard" is a far stronger claim than one aggregate number, and it tells the judge you know where your detector breaks.

**Do not tune thresholds on the same injection you report on.** Generate two seeds: `seed=1` for tuning, `seed=2` for reporting.

### 3.3 Sanity checks before trusting any number
- [ ] Injected mules are not trivially separable by a single feature (if `in_degree` alone gives F1 0.99, the injector is too clean).
- [ ] Injected mules **both send and receive** — an injector that makes collectors receive-only tests a fiction (PRD §2.4).
- [ ] Terminal signals (foreign IP / automation device / crypto-wallet narration) appear on **≈0.13% of rows** and plausibly co-occur as one injected set, so they can only find L3. Recall on L1/L2 must come from topology and behaviour — evaluate those layers separately.
- [ ] The regular-account population contains legitimate high-fan-in accounts (merchants, aggregators), otherwise precision is flattered.
- [ ] Degree and amount distributions of injected accounts overlap the real population.

---

## 4. False-positive analysis (do this; it wins the argument)

Take the top 10 false positives at τ*, print the feature row, the fired rules and the reason list, and classify each:

| # | Account | MRI | Fired rules | Why it is actually benign | Fix |
|---|---|---:|---|---|---|
| 1 | | | | e.g. salary disbursement account | suppressor S3 |
| 2 | | | | e.g. merchant aggregator | `is_hub` cap |

Each fix becomes a suppression rule in `config.py` (PRD §14.3). Re-run the sweep after each change and record the delta. **A table showing precision climbing from 0.71 → 0.89 across four named fixes is one of the most persuasive slides you can show a technical judge.**

Also sample 10 false negatives: which signal was missing? That tells you whether to widen a window or add a rule.

---

## 5. Blind-query readiness (the 40%)

This is not scored by a metric, it is scored by whether it works in front of a person. Treat it as a test suite.

### 5.1 Drill protocol — run five times before the freeze

```text
Teammate picks a random account ID from the dataset (not pre-tested).
Start a stopwatch.
  t+0.0   type, Enter
  t+?     loading skeleton
  t+?     KPIs + graph rendered, layers colour-coded      ← record this time
  t+?     narrate the finding in one sentence
  t+?     click top terminal node, read the evidence
  t+?     generate the freeze requisition
Record: time-to-first-render, correctness, anything that looked broken.
```

### 5.2 Results log

| Run | Account ID | Render (ms) | Hops found | L1/L2/L3 | Doc OK | Issues |
|---|---|---:|---|---|:--:|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |

### 5.3 Edge cases that must not break the demo

| Case | Expected behaviour |
|---|---|
| Account does not exist | Friendly error + fuzzy suggestion |
| Account has only incoming transactions | Offer the upstream trace, never an empty canvas |
| Account is a hub / aggregator | Marked `AGGREGATOR`, not expanded, excluded from freeze list |
| Account has a single transaction | Renders a two-node graph, documents still generate |
| Trail is deeper than 4 hops | Truncation banner, `truncated: true` in the payload |
| Two judges query in quick succession | LRU cache serves the repeat instantly |

---

## 6. Performance benchmarks

Run `make bench` three times; report the **median**. Record the hardware.

```text
Hardware: ______________________  RAM: ____  OS: ____  Python: ____
Dataset : 2,000,000 rows · 15 days · ______ accounts · sha256:________
```

| Benchmark | Target | Run 1 | Run 2 | Run 3 | Median | Status |
|---|---|---:|---:|---:|---:|:--:|
| Ingest total | ≤ 60 s | | | | | |
| — parse | | | | | | |
| — normalize + encode | | | | | | |
| — persist | | | | | | |
| — features + CSR + score | | | | | | |
| Peak RSS (ingest) | ≤ 6 GB | | | | | |
| Steady RSS (serving) | ≤ 2.5 GB | | | | | |
| Cold start (artifacts → ready) | ≤ 5 s | | | | | |
| 4-hop trace p50 | | | | | | |
| 4-hop trace **p95** | ≤ 2 s | | | | | |
| 4-hop trace p99 | | | | | | |
| Account search p95 | ≤ 1 s | | | | | |
| Timeline re-filter | ≤ 150 ms | | | | | |
| Graph render 500n/1500e | interactive | | | | | |
| Case diary (no LLM) | ≤ 2 s | | | | | |
| Case diary (with LLM) | ≤ 10 s | | | | | |

**Trace benchmark method:** 100 randomly sampled accounts with ≥ 1 outgoing transaction, plus 20 known mule-chain victims. Report both populations separately — mule victims are the realistic case and are usually *faster* because the trail is well-defined.

**Measure the split:** backend `query_ms` vs end-to-end perceived (including render). Report both; mentors may define the 2-second target either way (open question Q5).

---

## 7. Document quality (the 20%)

Not a numeric metric, so use a rubric and self-score honestly before submission.

| # | Check | ✔ |
|---|---|:--:|
| 1 | All nine PS-required case-diary elements present | |
| 2 | Every account number in the document exists in the dataset | |
| 3 | Every amount matches a transaction or a computed total | |
| 4 | Every transaction ID resolves to a real row | |
| 5 | Chronology is correctly ordered and complete | |
| 6 | Statutory citation correct (S.94 BNSS ≡ S.91 CrPC, r/w S.106 BNSS) | |
| 7 | One requisition per beneficiary bank, correctly addressed | |
| 8 | IFSC codes valid and matched to the right account | |
| 9 | Prints cleanly on A4, headers repeat across pages | |
| 10 | Disclaimer and IO signature block present | |
| 11 | Dataset fingerprint printed for provenance | |
| 12 | Validation badge shows `n/n facts verified` | |

**Hallucination test (must pass):** run the generator against a deliberately lying model stub that injects a fake account number and a fake amount. The validator must reject, retry, and fall back to the template, with **zero** fabricated facts in the final PDF. Log the rejection — showing a judge the system catching a lie is more convincing than claiming it cannot happen.

---

## 8. Results summary (fill before submission)

```text
┌──────────────────────────────────────────────────────────────────────┐
│ DETECTION                                                            │
│   Threshold τ* ......... __        Precision ....... __              │
│   Recall ............... __        F1 .............. __              │
│   FP ................... __        FN .............. __              │
│   Layer accuracy: L1 __  L2 __  L3 __                                │
│   By difficulty:  easy __  medium __  hard __                        │
│                                                                      │
│ PERFORMANCE                                                          │
│   Ingest 2M ............ __ s      (target ≤ 60 s)                   │
│   4-hop trace p95 ...... __ ms     (target ≤ 2,000 ms)               │
│   Peak RSS ............. __ GB     (target ≤ 6 GB)                   │
│                                                                      │
│ DOCUMENTS                                                            │
│   Facts verified ....... __/__     Unverified entities ...... 0      │
│   Hallucination test ... PASS/FAIL                                   │
│                                                                      │
│ BLIND DRILL                                                          │
│   Runs passed .......... __/5      Median render ........... __ ms   │
└──────────────────────────────────────────────────────────────────────┘
```

## 9. Honest limitations (say these before a judge finds them)

- Detection is heuristic, not learned; thresholds are calibrated on synthetic or supplied labels and would need recalibration per bank and per dataset.
- Layer labels are relative to a queried victim, not absolute properties of an account.
- Value attribution is proportional, not FIFO/LIFO; real forensic accounting may use a different convention, and the attribution model is a configurable choice.
- We do not resolve account holders' identities, link accounts by KYC, or handle cross-bank entity resolution.
- Evaluation on injected mules measures our ability to find patterns we ourselves defined; supplied ground truth would be stronger evidence.

Stating these costs nothing and buys credibility. Every judge knows a hackathon prototype has limits; the ones who impress are the teams that already know which.
