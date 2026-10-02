"""
The in-process dataset singleton.

Immutable dataset facts live here; mutable case state lives in cases.py.
Nothing downstream recomputes a measurement with its own logic.
"""
from __future__ import annotations

import threading
import uuid, time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

from ..config import ARTIFACT_DIR, MAX_HOPS_DEFAULT
from . import features as feat
from . import graph as gr
from .ingest import build_profile, fingerprint_file, normalize_and_derive, write_profile

FACTS_PARQUET = ARTIFACT_DIR / "facts.parquet"


class DatasetStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state = "EMPTY"            # EMPTY | LOADING | READY | FAILED
        self.job_id: str | None = None  # identifies one ingestion run
        self.stage = None
        self.stages: list[dict] = []
        self.error: str | None = None
        self.fingerprint: str | None = None
        self.profile: dict | None = None
        self.source_path: Path | None = None
        self.idx_to_id: list[str] = []
        self.id_to_idx: dict[str, int] = {}
        self.F: dict[str, np.ndarray] = {}
        self.P: dict[str, np.ndarray] = {}
        self.fw: gr.CSR | None = None
        self.rv: gr.CSR | None = None
        self.amount = self.ts = self.src = self.dst = self.row_id = None
        self.is_hub: np.ndarray | None = None
        self.hub_cut = 0.0
        self.con: duckdb.DuckDBPyConnection | None = None
        self._tls = threading.local()      # DuckDB connections are not thread-safe:
        self._gen = 0                      # every worker thread gets its own cursor
        self.loaded_at: float | None = None
        self.ingest_seconds: float | None = None
        self.timings: dict[str, float] = {}
        self.mri = None
        self.band: list[str] = []
        self.role: list[str] = []
        self.reason: list[str] = []

    # ------------------------------------------------------------------ load
    def load(self, src: Path) -> None:
        with self.lock:
            if self.state == "LOADING":
                raise RuntimeError("INGEST_IN_PROGRESS")
            self.state, self.stages, self.error = "LOADING", [], None
            self.job_id = "ing_" + uuid.uuid4().hex[:12]
        t_all = time.perf_counter()

        def stage(name: str):
            self.stage = name
            return time.perf_counter()

        try:
            t = stage("fingerprint")
            fp = fingerprint_file(src)
            self._done("fingerprint", t)

            t = stage("normalize")
            df = normalize_and_derive(src)
            self._done("normalize", t)

            t = stage("encode")
            accounts = (pl.concat([df["Sender_Account"], df["Receiver_Account"]])
                          .unique(maintain_order=True))
            self.idx_to_id = accounts.to_list()
            self.id_to_idx = {a: i for i, a in enumerate(self.idx_to_id)}
            m = pl.DataFrame({"acct": self.idx_to_id,
                              "i": np.arange(len(self.idx_to_id), dtype=np.int32)})
            df = (df.join(m.rename({"acct": "Sender_Account", "i": "src_idx"}),
                          on="Sender_Account", how="left")
                    .join(m.rename({"acct": "Receiver_Account", "i": "dst_idx"}),
                          on="Receiver_Account", how="left"))
            assert self.idx_to_id[self.id_to_idx[self.idx_to_id[0]]] == self.idx_to_id[0]
            self._done("encode", t)

            t = stage("facts")
            df.write_parquet(FACTS_PARQUET)
            self.con = duckdb.connect()
            self._gen += 1
            self.con.execute(
                f"CREATE OR REPLACE VIEW txn AS SELECT * FROM read_parquet('{FACTS_PARQUET}')")
            self._done("facts", t)

            t = stage("graph")
            self.src = df["src_idx"].to_numpy().astype(np.int32)
            self.dst = df["dst_idx"].to_numpy().astype(np.int32)
            self.amount = df["amount_f"].to_numpy()
            self.ts = df["ts_epoch"].to_numpy().astype(np.int64)
            self.row_id = df["source_row_id"].to_numpy().astype(np.int64)
            self.fw, self.rv = gr.build_csr(self.src, self.dst, len(self.idx_to_id))
            self._done("graph", t)

            t = stage("features")
            self.F = feat.build_features(df, len(self.idx_to_id))
            self.P = {k: feat.percentile_ranks(v) for k, v in self.F.items()
                      if v.dtype.kind in "fiu"}
            self.is_hub, self.hub_cut = gr.hub_mask(self.F["in_degree"], self.F["out_degree"])
            self._done("features", t)

            t = stage("profile")
            el = time.perf_counter() - t_all
            self.profile = build_profile(df, src, fp, el)
            self.profile["hub_threshold_degree"] = self.hub_cut
            self.profile["hub_accounts"] = int(self.is_hub.sum())
            write_profile(self.profile)
            self._done("profile", t)

            t = time.perf_counter()
            self._score_all()
            self._done("score", t)

            self.fingerprint = fp
            self.source_path = src
            self.ingest_seconds = round(time.perf_counter() - t_all, 2)
            self.loaded_at = time.time()
            self.state, self.stage = "READY", None
            del df
        except Exception as exc:                       # noqa: BLE001
            self.state, self.error, self.stage = "FAILED", f"{type(exc).__name__}: {exc}", None
            raise

    def _score_all(self) -> None:
        """Cache MRI / band / role for every account so ranking is O(1) per request."""
        from . import risk as _risk
        rate = float(self.profile["signal_cooccurrence"]["cooccurrence_rate"])
        n = len(self.idx_to_id)
        self._rank_order = None
        self.mri = np.zeros(n, dtype=np.float32)
        self.band = [""] * n
        self.role = [""] * n
        self.reason = [""] * n
        for i in range(n):
            s = _risk.score_account(i, self.F, self.P, rate)
            r = _risk.role_assessment(i, self.F, self.P)
            self.mri[i] = s["mri"]
            self.band[i] = s["band"]
            self.role[i] = r["role"]
            self.reason[i] = s["reason"]

    def ranking_order(self) -> np.ndarray:
        """Indices of every account, best candidate first.

        Computed once per load and cached. Ties break on index so the ranking
        is stable between calls - an unstable order would make Precision@K
        move around without the detector changing.
        """
        if getattr(self, "_rank_order", None) is None:
            self._rank_order = np.lexsort((np.arange(len(self.mri)), -self.mri))
        return self._rank_order

    def _done(self, name: str, t0: float) -> None:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        self.timings[name] = ms
        self.stages.append({"stage": name, "ms": ms})

    # --------------------------------------------------------------- helpers
    @property
    def db(self) -> duckdb.DuckDBPyConnection:
        """A cursor private to the calling thread, over the shared fact store.

        uvicorn runs sync endpoints in a thread pool; sharing one DuckDB
        connection across threads interleaves result sets and silently returns
        wrong rows. A per-thread cursor is the documented fix.
        """
        if self.con is None:
            raise RuntimeError("DATASET_NOT_LOADED")
        cur = getattr(self._tls, "cur", None)
        if cur is None or getattr(self._tls, "gen", -1) != self._gen:
            cur = self.con.cursor()
            self._tls.cur = cur
            self._tls.gen = self._gen
        return cur

    @property
    def ready(self) -> bool:
        return self.state == "READY"

    @property
    def n_accounts(self) -> int:
        return len(self.idx_to_id)

    @property
    def n_rows(self) -> int:
        return int(self.profile["rows"]) if self.profile else 0

    @property
    def cooccurrence_rate(self) -> float:
        if not self.profile:
            return 0.0
        return float(self.profile["signal_cooccurrence"]["cooccurrence_rate"])

    def idx(self, account_id: str) -> int | None:
        return self.id_to_idx.get(account_id)

    def aid(self, i: int) -> str:
        return self.idx_to_id[i]

    def edge_row(self, eid: int) -> dict:
        """One edge -> the transaction payload, always carrying source_row_id."""
        rid = int(self.row_id[eid])
        q = self.db.execute(
            "SELECT Transaction_ID, Sender_Account, Receiver_Account, Sender_IFSC, "
            "Receiver_IFSC, amount_f, timestamp, payment_mode, Narration, IP_Address, "
            "device_type, source_row_id, dup_txn_id, is_foreign_ip, "
            "is_automation_device, narr_crypto, narr_wallet, narr_cashout "
            "FROM txn WHERE source_row_id = ?", [rid]).fetchone()
        return _txn_payload(q)

    def rows_for(self, source_row_ids: list[int]) -> list[dict]:
        if not source_row_ids:
            return []
        ph = ",".join("?" * len(source_row_ids))
        rs = self.db.execute(
            "SELECT Transaction_ID, Sender_Account, Receiver_Account, Sender_IFSC, "
            "Receiver_IFSC, amount_f, timestamp, payment_mode, Narration, IP_Address, "
            "device_type, source_row_id, dup_txn_id, is_foreign_ip, is_automation_device, "
            f"narr_crypto, narr_wallet, narr_cashout FROM txn WHERE source_row_id IN ({ph}) "
            "ORDER BY timestamp", source_row_ids).fetchall()
        return [_txn_payload(r) for r in rs]


def _txn_payload(r) -> dict:
    if r is None:
        return {}
    return {
        "transaction_id": r[0], "sender_account": r[1], "receiver_account": r[2],
        "sender_ifsc": r[3], "receiver_ifsc": r[4], "amount": float(r[5]),
        "timestamp": str(r[6]), "payment_mode": r[7], "narration": r[8],
        "ip_address": r[9], "device_type": r[10],
        "source_row_id": int(r[11]),              # first-class, always present
        "duplicate_transaction_id": bool(r[12]),
        "signals": {"foreign_ip": bool(r[13]), "automation_device": bool(r[14]),
                    "crypto_narration": bool(r[15]), "wallet_narration": bool(r[16]),
                    "cashout_narration": bool(r[17])},
    }


STORE = DatasetStore()
DEFAULT_HOPS = MAX_HOPS_DEFAULT
