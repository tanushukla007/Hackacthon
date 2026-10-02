# ABHEDYA-CHAKRA — Detection Remediation Report

**Void Hacks() 8.0 · progress report against the 36-point remediation brief**
Status: **session 1 of N — foundations landed, detection rebuild in progress**
Every number below was measured in this workspace on the date of writing. Where
a number cannot be measured, the field says so instead of carrying a value.

---

## 0. The two facts that govern everything else

### 0.1 The 2M dataset is not in this workspace

```
data/raw/
  SYNTHETIC_DEV_250k.csv     31 MB   250,000 rows   6,069 accounts
```

A filesystem-wide search (`find / -xdev -iname "*VoidHacks*" -o -iname "*2M*" …`)
returns nothing resembling `VoidHacks8_MuleAccount_2M_Transactions.csv`.

**Consequence.** The figures in the brief — 24,873 accounts, ~2,250 duplicate
`Transaction_ID`s, 115 s ingestion, a 66 s stage, LOW 13,128 / MEDIUM 11,745 —
come from a run on your machine. They cannot be reproduced, confirmed or
optimised here. Nothing in this report restates them as if this workspace had
produced them.

Everything built in this session is dataset-independent and activates on the
real file the moment it is placed in `data/raw/`.

### 0.2 No ground truth exists

`GROUND_TRUTH_AVAILABLE = false`, established by code, not by assumption
(`backend/app/core/ground_truth.py`). The discovery pass searches
`data/`, `data/raw/`, `data/labels/`, `data/ground_truth/`, `data/artifacts/`
and the project root for `.csv/.tsv/.json/.parquet` files whose name suggests
labels, then requires both an account-like column and a label-like column.
Files that fail are listed with the reason, so "no labels" is never confused
with "a label file we could not read".

**Therefore:** no accuracy, precision, recall, F1, specificity, MCC, ROC-AUC,
PR-AUC, confusion matrix, Precision@K or Recall@K is published anywhere in the
system today. The brief's "approximately 1,500 mule accounts" is recorded as
an **unverified external expectation** and is never treated as a label set.

---

## 1. Root cause of the account-count discrepancy

**Answer: not yet attributable to a cause, and deliberately not guessed at.**

`GET /api/accounts/stats` now measures every mechanism that could produce a
difference between an expected universe and the observed count:

| Field | Meaning |
|---|---|
| `observed_accounts` | distinct accounts appearing in any transaction |
| `sender_accounts` / `receiver_accounts` | each side of the ledger |
| `sender_only` / `receiver_only` / `both_sides` | accounts that only ever send, only ever receive, or do both |
| `raw_identities_before_normalisation` | distinct raw strings before cleaning |
| `normalization_collisions` | normalised values produced by **more than one** raw string |
| `accounts_lost_to_normalisation` | `raw_identities − observed` — identities that merged |
| `collision_examples` | the actual colliding raw forms, up to 10 |
| `malformed_account_numbers` | not 12 digits after stripping; no digits at all |
| `accounts_in_ground_truth_only` | labelled accounts that never transact |
| `accounts_in_transactions_only` | transacting accounts absent from the label file |
| `unexplained_residual` | difference minus what the mechanisms above explain |

Measured on the 250k fixture (0.11 s; expect ~1 s at 2M since only two columns
are scanned):

```
observed_accounts 6,069 · sender_only 0 · receiver_only 0 · both_sides 6,069
normalization_collisions 0 · accounts_lost_to_normalisation 0
malformed_account_numbers 0 · ground_truth_available false
```

**Critically, the detectors are proven to work rather than merely to return
zero.** `tools/test_reconcile.py` builds a CSV containing, by construction, a
sender-only account, a receiver-only account, two raw forms of one account
(`400-0000-00001` and `4000 0000 0001`), a short number that zero-pads, and a
label file listing an account that never transacts. All 18 assertions pass: the
collision is found, the padded account is reported, the never-transacting
labelled account is found, and the residual is computed arithmetically.

**What the dashboard says now.** `"6,069 observed transaction accounts"` —
and on your file it will say `"24,873 observed transaction accounts"`. The
verdict field states plainly:

> No verified account universe exists in the workspace, so there is nothing to
> reconcile against. 24,873 is the number of distinct accounts that appear in a
> transaction; it is reported as exactly that and is not an error. A problem
> statement saying "approximately 25,000 accounts" is an expectation, not a
> reference file.

If you pass `?expected=25000`, the endpoint echoes it as **caller-supplied**,
subtracts what the mechanisms explain, and prints the remainder as
`unexplained_residual` rather than inventing a story for it.

**Likely explanation, stated as a hypothesis and not as a finding:** in a
24,873-of-25,000 case, the 127 missing accounts are most often accounts in the
problem-statement universe that never transact. That is testable the instant
either the real CSV or an account-universe file exists — `sender_only`,
`receiver_only` and `accounts_in_ground_truth_only` will settle it.

---

## 2. Why the risk distribution has no high tail

This one **is** reproducible here, because the same scoring engine runs on the
fixture, and it shows the identical failure mode: LOW/MEDIUM only, CRITICAL
empty. `tools/diagnose_risk.py` (`make diagnose`) measures it:

```
MRI distribution over 6,069 accounts
  p50 26.20   p75 34.40   p90 44.00   p95 48.70   p99 53.83   max 65.70
  LOW 3,827 (63.1%)   MEDIUM 2,240 (36.9%)   HIGH 2 (0.03%)   CRITICAL 0

component            weight     max     p99     p90     p50   % zero
  pass_through           25   25.00   24.69   22.31   11.09     0.1%
  velocity               20   20.00   19.75   17.77    0.00    61.5%
  fan_in                 15   14.96    6.03    5.47    3.03     0.3%
  fan_out                15   15.00   11.17    9.54    5.03     0.4%
  terminal_signals       15    9.00    9.00    0.00    0.00    93.3%
  behavioral_anomaly     10    7.68    0.00    0.00    0.00    99.4%

accounts with N components strong (>=60% of weight)
  0 strong: 2,025   max MRI 28.30
  1 strong: 2,556   max MRI 47.10
  2 strong: 1,169   max MRI 56.30
  3 strong:   316   max MRI 65.50
  4 strong:     3   max MRI 65.70
```

### Three defects, each visible in that table

**(a) Percentile scoring gives every account a participation score.**
Components are scored as `percentile / 100 × weight`. The *median* account
therefore collects 11.09 of 25 on pass-through and lands at MRI ≈ 26 having
done nothing unusual. That is why 37% of the population sits in MEDIUM: not
because 37% are suspicious, but because the scale has no zero. A normal
account must score near zero for a high tail to mean anything.

**(b) `fan_in` and `fan_out` are mutually exclusive in practice.**
Accounts are collectors *or* distributors; the top of the table never earns
both. The reachable maximum is therefore ≈ 25 + 20 + 15 + small ≈ 65.
Observed maximum: **65.70**. CRITICAL (≥ 80) is unreachable by construction —
the band is dead code. There is no component rewarding the classic mule that
collects *and* disperses, which is exactly the behaviour the brief's §11
example says should score highest.

**(c) Two components cannot reach their own weight.**
`terminal_signals` maxes at 9.00 of 15 (60%) and `behavioral_anomaly` at 7.68
of 10, so 25 points of the 100-point scale are partly unreachable.

**(d) [FIXED THIS SESSION] Tied measurements received different scores.**
`percentile_ranks()` ranked values with `argsort`, which gives tied values
**distinct** ranks according to where they happened to sit in the account
array. Two accounts with byte-for-byte identical behaviour therefore received
different percentiles, and so different MRIs. Because `velocity` is zero for
61.5% of accounts, one zero-velocity account could score 0 on that component
while another scored ~61 — purely from array position. The account array was
itself built in hash order, so **the same CSV could produce different scores
on different runs**. This was found while rewriting ingestion: the new
account ordering permuted the feature arrays, and the MRI distribution moved
even though every per-account measurement was provably unchanged.

The function now assigns tied values the **same** rank, reporting the share of
accounts measured *strictly lower*, so the lowest observed value always scores
0 and ranking is permutation-invariant. The account index is additionally now
built in sorted order, so a given CSV produces a byte-identical result on
every run.

Effect on the 250k fixture — the distribution moved **down**, which is the
correct direction, because accounts with no measured activity no longer
collect phantom percentile credit:

| | before | after |
|---|---:|---:|
| MRI p50 | 26.20 | **24.60** |
| MRI p90 | 44.00 | **40.60** |
| MEDIUM band | 2,240 | **1,908** |
| LOW band | 3,827 | **4,159** |

Separation improved where it matters: in the synthetic typology suite the
legitimate fan-in hub fell from 38.1 to **24.9** while the rapid pass-through
mule held at **58.8**. All ten typology cases still pass. This is a partial
down-payment on defect (a), not a substitute for it — the scale still has no
true zero point.

**The remaining fix is not a threshold change** (and the brief is right to
forbid one). It is: re-base components on absolute, robust-normalised
measurements so ordinary behaviour scores ~0; add an **intermediary**
component so collect-and-disperse stacks; and add the independent signals
listed in §9 of the brief so genuinely multi-signal accounts accumulate.
That work is in progress — see §6.

---

## 3. What landed this session

| Component | File | Verified by |
|---|---|---|
| Ground-truth discovery | `backend/app/core/ground_truth.py` | `tools/test_reconcile.py` (planted label file found; account/label columns identified; counts read from file) |
| Account reconciliation | `backend/app/core/reconcile.py` | same, 18/18 assertions |
| Evaluation engine | `backend/app/core/evaluate.py` | `tools/test_evaluate.py` 28/28, **exact agreement with scikit-learn** on ROC-AUC, average precision, confusion matrix and MCC |
| Synthetic typology suite | `backend/app/core/synthetic_tests.py` | 10/10 cases over a 417-account constructed world |
| Risk diagnosis | `tools/diagnose_risk.py` | output in §2 |
| `GET /api/accounts/stats` | `routes.py` | live, 200 |
| `GET /api/accounts/ranking` | `routes.py` | live, canonical Top-K |
| `/api/eval/*` ×7 | `routes.py` | live; were `501` stubs |

### The evaluation engine, specifically

Implemented in NumPy rather than imported from scikit-learn, so tie-handling
and the average-precision definition are visible in the repository — then
checked against scikit-learn to prove the implementations agree.

- Confusion matrix, precision, recall, specificity, F1, balanced accuracy, MCC.
- ROC curve + AUC; PR curve + average precision (step-wise, not trapezoidal,
  because trapezoidal PR interpolation is optimistically biased).
- Precision@K and Recall@K at 100/250/500/1000/1500/2000, each returning
  `recovered`, both metrics, and a plain-English `statement` so the two cannot
  be confused. Recall@1500 answers "of the ~1,500 real red flags, how many did
  we recover in our top 1,500"; Precision@1500 answers "of our top 1,500, how
  many were real".
- Threshold sweep, carrying an explicit warning against reading the best row
  off the table and reporting it as test performance.
- Top-10 false positives (confidently wrong) and false negatives (missed by the
  widest margin).
- **Accounts with no label are excluded and the exclusion count is published.**
  Treating unlabelled accounts as negatives would invent thousands of true
  negatives and inflate specificity and accuracy. Accuracy is returned but
  always paired with a note that it is dominated by true negatives here.

Today every one of these endpoints returns `available: false` with the reason
and the list of paths searched. They become real numbers automatically when a
label file appears — no code change, no flag.

### What replaces accuracy while labels are absent

`POST /api/eval/self-validation` runs 10 deterministic typology tests over a
constructed 417-account world containing a victim→collector→distributor→
terminal chain, two legitimate high-degree hubs, a rapid pass-through mule,
slow fan-in/fan-out twins, scatter-gather, amount splitting, a 4-account ring
and 120 ordinary accounts. It asserts *relative* behaviour, never a target
score:

```
PASS  rapid pass-through outranks a legitimate fan-in hub    58.8 vs 38.1
PASS  rapid pass-through outranks a legitimate fan-out hub
PASS  fast collector outranks slow collector at equal degree
PASS  fast distributor outranks slow distributor at equal degree
PASS  amount splitting is detected
PASS  scatter-gather middles are not ignored
PASS  ordinary accounts stay low
PASS  victims are not scored as perpetrators
PASS  terminal fan-out leaves score above background
PASS  hub guard: degree alone does not create a high score
```

The payload states in full that this is **not** an accuracy figure and says
nothing about how many real mules exist in any real dataset.

One of these tests failed when first written, and the failure was instructive:
"victims are not scored as perpetrators" asserted a *rank* threshold, but in a
world where most accounts score zero, rank among tied zeros is meaningless.
The assertion was corrected to test the score (victim 2.0 versus collector
45.1), not the rank. The detector was right; the test was wrong.

---

## 4. Report fields the brief asks for

Measurable now, on the 250k fixture only:

| # | Field | Value |
|---|---|---|
| 1 | Root cause of 24,873 vs 25,000 | **Not established** — no real file and no reference universe here. Measurement apparatus built and proven (§1). |
| 2 | Ground truth exists | **No** (`GROUND_TRUTH_AVAILABLE = false`), searched paths published |
| 3 | Labelled suspects | **n/a** — no label file |
| 8 | Account count | 6,069 (fixture) |
| 9 | Transaction count | 250,000 (fixture) |
| 10 | Duplicate `Transaction_ID` | 275 ids over 550 rows (fixture) |
| 11 | Ranked accounts | 6,069 — every account receives a score and a rank |
| 12 | Flagged candidates | 2 HIGH, 0 CRITICAL — **this is the defect in §2, not a finding** |
| 13–31 | Precision … confusion matrix | **Unavailable — no ground truth.** Engine implemented and sklearn-verified; activates on a label file |
| 34 | Top 20 ranked | `GET /api/accounts/ranking?limit=20` |
| 36 | 4-hop trace p50/p95 | 44.6 ms / 79.0 ms (fixture, 250k) |

Fields 4–7 (old/new ingestion time, old/new slowest stage) and 21–30
(Precision@K / Recall@K) are **blocked on inputs that do not exist here** —
the 2M file and a label file respectively. They are not estimated.

---

## 5. Reproduction commands

```bash
bash run.sh all                       # API :8000 + workstation :5173 + demo :5174
make check                            # contract + doc/code parity + reconciliation + metrics  (41 + 18 + 28)
make diagnose                         # the risk-distribution analysis in §2
python3 tools/diagnose_risk.py FILE   # the same analysis on any CSV
curl localhost:8000/api/accounts/stats
curl localhost:8000/api/accounts/ranking?limit=20
curl localhost:8000/api/eval/summary
curl -X POST localhost:8000/api/eval/self-validation
make bench                            # ingestion + trace benchmarks on this machine
```

To activate everything that is currently blocked:

```bash
cp VoidHacks8_MuleAccount_2M_Transactions.csv data/raw/
cp your_labels.csv data/            # any CSV with an account column and a label column
curl -X POST localhost:8000/api/ingest -d '{"filename":"VoidHacks8_MuleAccount_2M_Transactions.csv"}'
```

Nothing else needs changing: discovery, reconciliation and the full metric
suite switch on by themselves.

---

## 6. Not done yet — the remaining brief

Honest status, in the order I intend to take them:

1. **Rebuild the scoring scale** (§8, §13) — absolute robust normalisation so
   ordinary accounts score ~0; an intermediary component so collect-and-disperse
   stacks; make every component able to reach its own weight.
2. **The feature set in §9** — temporal pass-through matched per inflow at
   3/5/10/15 minutes (not `total_out/total_in`), burst intensity, amount
   splitting, counterparty novelty and turnover, short cycles, layering with
   temporal constraints, device/IP switching, payment-mode concentration.
3. **The 25 typologies and reason codes** (§10) with `MIXED_TYPOLOGY` weighting
   co-occurrence of independent categories.
4. **Ingestion profiling against 2M** (§20–22) — requires the real file, or a
   2M-row synthetic stand-in if you would rather I measure now and re-measure
   later.
5. **Evaluation and suspect pages in the UI** (§7, §24–26) reading these
   endpoints — frontend renders, backend computes.
6. **Ablation harness** (§15) once there is a label set to ablate against.

---

## 7. Standing rules this work obeys

- No fabricated labels, accuracy, confusion matrix or suspect count.
- No hardcoded account IDs; no hardcoded 1,500; no threshold moved to
  manufacture a HIGH band.
- `source_row_id` remains the row key; no row is dropped; duplicate
  `Transaction_ID`s are preserved and flagged.
- One canonical scorer in `core/risk.py`; the frontend computes no risk and no
  metric.
- Layer stays victim-relative and per-trace; never a stored global label.
- A suspicious signal is evidence, never proof.
