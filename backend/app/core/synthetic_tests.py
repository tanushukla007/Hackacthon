"""
Deterministic typology tests (brief §27).

These are what replaces an accuracy figure when no labels exist. Each case is
a hand-constructed set of transactions whose shape is known because we wrote
it, so the correct behaviour is known too. The suite asserts RELATIVE
behaviour - "a rapid pass-through account must outrank a legitimate hub of the
same size" - rather than absolute scores, because an absolute score target
would just be a threshold fitted to a fixture.

Nothing here is evidence about the real dataset, and the API labels it as
synthetic every time it is returned.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import features as feat
from . import risk

DAY = 86400
T0 = 1789000000          # fixed epoch: the suite must be reproducible


class _Builder:
    """Accumulates synthetic transactions and assigns account indices."""

    def __init__(self) -> None:
        self.rows: list[tuple[int, int, float, int]] = []
        self.names: dict[str, int] = {}

    def acct(self, name: str) -> int:
        if name not in self.names:
            self.names[name] = len(self.names)
        return self.names[name]

    def tx(self, src: str, dst: str, amount: float, t: int) -> None:
        self.rows.append((self.acct(src), self.acct(dst), float(amount), int(t)))

    def frame(self) -> tuple[pl.DataFrame, int]:
        n = len(self.names)
        df = pl.DataFrame({
            "src_idx": np.array([r[0] for r in self.rows], dtype=np.int32),
            "dst_idx": np.array([r[1] for r in self.rows], dtype=np.int32),
            "amount_f": np.array([r[2] for r in self.rows], dtype=np.float64),
            "ts_epoch": np.array([r[3] for r in self.rows], dtype=np.int64),
        })
        # Columns the feature builder reads but these cases do not exercise.
        df = df.with_columns(
            pl.lit("HDFC").alias("sender_bank"),
            pl.lit("ICIC").alias("receiver_bank"),
            pl.lit(False).alias("is_foreign_ip"),
            pl.lit(False).alias("is_automation_device"),
            pl.lit(False).alias("narr_crypto"),
            pl.lit(False).alias("narr_wallet"),
            pl.lit(False).alias("narr_cashout"),
            pl.lit(0, dtype=pl.UInt8).alias("signal_families"),
            pl.int_range(pl.len()).cast(pl.Int64).alias("source_row_id"),
            pl.lit("UPI").alias("payment_mode"),
            pl.lit("iOS").alias("device_type"),
        )
        return df, n


def _build_world() -> tuple[_Builder, dict]:
    """One synthetic world containing every typology, so all cases are scored
    against the same population - a percentile only means something relative
    to a population."""
    b = _Builder()
    notes: dict[str, str] = {}

    # --- 1. victim -> collector -> distributor -> terminal chain ------------
    t = T0
    for i in range(12):
        b.tx(f"victim_{i}", "collector_A", 50000 + i * 1000, t + i * 60)
    b.tx("collector_A", "distributor_A", 580000, t + 15 * 60)
    for i in range(9):
        b.tx("distributor_A", f"terminal_{i}", 60000, t + 20 * 60 + i * 30)
    notes["chain"] = "victim fan-in -> single forward -> fan-out to terminals"

    # --- 2/3. legitimate hubs: high degree, but slow and balanced -----------
    for i in range(60):                       # fan-in hub, spread over 10 days
        b.tx(f"payer_{i}", "legit_hub_in", 20000, t + i * (DAY // 6))
    for i in range(30):                       # pays out slowly, keeps a float
        b.tx("legit_hub_in", f"payee_{i}", 12000, t + DAY + i * (DAY // 4))
    for i in range(55):
        b.tx("legit_hub_out", f"salary_{i}", 30000, t + 2 * DAY + i * (DAY // 5))
    for i in range(20):
        b.tx(f"funder_{i}", "legit_hub_out", 90000, t + i * (DAY // 3))
    notes["legit_hub"] = "high degree, slow turnover, no burst"

    # --- 4. rapid pass-through mule -----------------------------------------
    for i in range(10):
        b.tx(f"src_pt_{i}", "mule_passthrough", 45000, t + 3 * DAY + i * 20)
    for i in range(8):
        b.tx("mule_passthrough", f"out_pt_{i}", 55000, t + 3 * DAY + 240 + i * 20)
    notes["rapid_passthrough"] = "inflow dispersed within minutes"

    # --- 5/6. slow fan-in and slow fan-out ----------------------------------
    for i in range(25):
        b.tx(f"slow_in_{i}", "slow_collector", 40000, t + 4 * DAY + i * 3600)
    b.tx("slow_collector", "slow_sink", 500000, t + 9 * DAY)
    for i in range(25):
        b.tx("slow_distributor", f"slow_out_{i}", 30000, t + 4 * DAY + i * 3600)
    b.tx("slow_funder", "slow_distributor", 800000, t + 3 * DAY)
    notes["slow"] = "same degree as the mule, spread over days"

    # --- 7. scatter-gather / 8. gather-scatter ------------------------------
    for i in range(8):
        b.tx("scatter_src", f"scatter_mid_{i}", 50000, t + 5 * DAY + i * 15)
    for i in range(8):
        b.tx(f"scatter_mid_{i}", "scatter_sink", 49000, t + 5 * DAY + 600 + i * 15)
    notes["scatter_gather"] = "one to many to one, minutes apart"

    # --- 9. amount splitting -------------------------------------------------
    b.tx("split_funder", "splitter", 900000, t + 6 * DAY)
    for i in range(18):
        b.tx("splitter", f"split_out_{i}", 49500, t + 6 * DAY + 120 + i * 10)
    notes["amount_splitting"] = "one large in, many near-identical outs"

    # --- 10. cycle / ring ----------------------------------------------------
    ring = ["ring_a", "ring_b", "ring_c", "ring_d"]
    for i, a in enumerate(ring):
        b.tx(a, ring[(i + 1) % len(ring)], 75000, t + 7 * DAY + i * 300)
    notes["cycle"] = "closed 4-account loop"

    # --- quiet background population ----------------------------------------
    for i in range(120):
        b.tx(f"normal_{i}", f"normal_{(i * 7 + 3) % 120}", 1200 + i, t + 8 * DAY + i * 900)
    notes["background"] = "ordinary low-volume accounts"

    return b, notes


def _score_world():
    b, notes = _build_world()
    df, n = b.frame()
    F = feat.build_features(df, n)
    P = {k: feat.percentile_ranks(v) for k, v in F.items() if v.dtype.kind in "fiu"}
    mri = np.zeros(n)
    detail = {}
    for i in range(n):
        s = risk.score_account(i, F, P, 0.0)
        mri[i] = s["mri"]
        detail[i] = s
    idx = b.names
    return idx, mri, detail, F, notes


def run() -> dict:
    """Execute the suite and report what the detector actually did."""
    idx, mri, detail, F, notes = _score_world()
    m = lambda name: float(mri[idx[name]])      # noqa: E731
    rank = {a: r + 1 for r, a in enumerate(
        sorted(idx, key=lambda a: -mri[idx[a]]))}

    cases: list[dict] = []

    def case(name, typology, expectation, passed, observed):
        cases.append({"case": name, "typology": typology, "expectation": expectation,
                      "passed": bool(passed), "observed": observed})

    case("rapid pass-through outranks a legitimate fan-in hub",
         "Rapid Pass-Through vs hub guard",
         "a mule that forwards within minutes must score above a slow hub of similar degree",
         m("mule_passthrough") > m("legit_hub_in"),
         {"mule_passthrough": round(m("mule_passthrough"), 2),
          "legit_hub_in": round(m("legit_hub_in"), 2),
          "mule_rank": rank["mule_passthrough"], "hub_rank": rank["legit_hub_in"]})

    case("rapid pass-through outranks a legitimate fan-out hub",
         "Rapid Pass-Through vs hub guard",
         "high out-degree alone must not beat genuine pass-through behaviour",
         m("mule_passthrough") > m("legit_hub_out"),
         {"mule_passthrough": round(m("mule_passthrough"), 2),
          "legit_hub_out": round(m("legit_hub_out"), 2)})

    case("fast collector outranks slow collector at equal degree",
         "Burst / velocity",
         "timing must change the score when degree is held roughly constant",
         m("collector_A") > m("slow_collector"),
         {"collector_A": round(m("collector_A"), 2),
          "slow_collector": round(m("slow_collector"), 2),
          "in_degree_fast": int(F["in_degree"][idx["collector_A"]]),
          "in_degree_slow": int(F["in_degree"][idx["slow_collector"]])})

    case("fast distributor outranks slow distributor at equal degree",
         "Burst / velocity",
         "same test on the dispersal side",
         m("distributor_A") > m("slow_distributor"),
         {"distributor_A": round(m("distributor_A"), 2),
          "slow_distributor": round(m("slow_distributor"), 2)})

    case("amount splitting is detected",
         "Amount Splitting",
         "one large credit broken into many near-identical debits should rank highly",
         rank["splitter"] <= max(10, int(0.05 * len(idx))),
         {"splitter_mri": round(m("splitter"), 2), "rank": rank["splitter"],
          "out_degree": int(F["out_degree"][idx["splitter"]])})

    case("scatter-gather middles are not ignored",
         "Scatter-Gather",
         "pass-through middles of a scatter-gather should outrank background accounts",
         m("scatter_mid_0") > m("normal_5"),
         {"scatter_mid_0": round(m("scatter_mid_0"), 2),
          "normal_5": round(m("normal_5"), 2)})

    case("ordinary accounts stay low",
         "No-signal control",
         "an account with two slow transactions must not reach HIGH",
         detail[idx["normal_5"]]["band"] in ("LOW", "MEDIUM"),
         {"normal_5": round(m("normal_5"), 2),
          "band": detail[idx["normal_5"]]["band"]})

    # Asserted on SCORE, not rank: most of this synthetic world scores zero, so
    # rank among tied zeros carries no information. A victim must score near
    # nothing and must sit far below the accounts that handled its money.
    case("victims are not scored as perpetrators",
         "Victim-relative",
         "a victim that only sends once must score near zero and far below the "
         "collector that received from it",
         m("victim_0") < 10.0 and m("victim_0") < m("collector_A") / 3,
         {"victim_0": round(m("victim_0"), 2),
          "collector_A": round(m("collector_A"), 2),
          "band": detail[idx["victim_0"]]["band"],
          "rank_note": ("rank %d of %d, but most of this world ties at zero, so rank "
                        "is not the meaningful measure here"
                        % (rank["victim_0"], len(idx)))})

    case("terminal fan-out leaves score above background",
         "Suspicious Terminal",
         "accounts receiving from a distributor in a burst should exceed background",
         m("terminal_0") >= m("normal_5"),
         {"terminal_0": round(m("terminal_0"), 2), "normal_5": round(m("normal_5"), 2)})

    case("hub guard: degree alone does not create a high score",
         "Hub guard",
         "the highest-degree account in the world must not automatically be rank 1",
         rank["legit_hub_in"] > 1,
         {"legit_hub_in_degree": int(F["in_degree"][idx["legit_hub_in"]]),
          "legit_hub_in_rank": rank["legit_hub_in"],
          "rank_1_account": min(idx, key=lambda a: rank[a])})

    passed = sum(1 for c in cases if c["passed"])
    return {
        "regime": "SYNTHETIC_TYPOLOGY_TESTS",
        "ground_truth_available": False,
        "what_this_is": (
            "Constructed transaction patterns with known shape, scored by the production "
            "engine. This measures whether the detector responds to the behaviours it "
            "claims to detect. It is NOT an accuracy figure and says nothing about how "
            "many real mules exist in any real dataset."),
        "accounts_in_synthetic_world": len(idx),
        "cases_total": len(cases),
        "cases_passed": passed,
        "cases_failed": len(cases) - passed,
        "cases": cases,
        "world_description": notes,
    }
