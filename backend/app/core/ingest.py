"""
Ingest: raw CSV -> normalized + derived frame, profile artifact, fingerprint.

Contract (DATA_CONTEXT.md):
  - account numbers are STRINGS, zero-padded, never ints          (Rule 1)
  - Transaction_ID is NOT unique; nothing is keyed on it          (Rule 2)
  - no row is ever dropped or quarantined                         (Rule 3)
  - source_row_id = 0-based ordinal of the row in the source file (Rule 11)
  - every enum / distribution / bound is MEASURED, not assumed    (Rule 8)
"""
from __future__ import annotations

import hashlib, json, time
from pathlib import Path

import polars as pl

from ..config import (
    ACCOUNT_WIDTH, ARTIFACT_DIR, AUTOMATION_DEVICES, CASHOUT_KEYWORDS,
    CRYPTO_KEYWORDS, EXPECTED_COLUMNS, FOREIGN_IP_PREFIXES, IFSC_PATTERN,
    KNOWN_PAYMENT_MODES, NARRATION_EXCLUSIONS, PAYMENT_MODE_FALLBACK,
    WALLET_KEYWORDS,
)

TS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M:%S",
              "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M")


def fingerprint_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


def _kw_expr(col: pl.Expr, words: tuple[str, ...]) -> pl.Expr:
    """Boundary-aware, case-insensitive keyword hit with an exclusion list."""
    up = col.str.to_uppercase()
    hit = pl.lit(False)
    for w in words:
        hit = hit | up.str.contains(w, literal=True)
    for ex in NARRATION_EXCLUSIONS:
        hit = hit & ~up.str.contains(ex, literal=True)
    return hit


def _parse_timestamp(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.with_columns(
        pl.coalesce([
            pl.col("Timestamp").str.to_datetime(fmt, strict=False, time_unit="us")
            for fmt in TS_FORMATS
        ]).alias("timestamp")
    )


def normalize_and_derive(src: Path) -> pl.DataFrame:
    """Read the CSV and produce the canonical fact frame. Never drops a row."""
    lf = pl.scan_csv(
        src,
        infer_schema_length=0,          # everything as Utf8 first: no silent int casts
        try_parse_dates=False,
        low_memory=True,
    )
    cols = lf.collect_schema().names()
    missing = [c for c in EXPECTED_COLUMNS if c not in cols]
    if missing:
        raise ValueError("SCHEMA_MISMATCH: missing columns " + ", ".join(missing))

    acct = lambda c: (                                   # noqa: E731
        pl.col(c).str.strip_chars().str.replace_all(r"\D", "")
        .str.pad_start(ACCOUNT_WIDTH, "0")
    )
    ifsc = lambda c: pl.col(c).str.strip_chars().str.to_uppercase()  # noqa: E731

    lf = lf.with_row_index("source_row_id").with_columns(
        pl.col("Transaction_ID").str.strip_chars(),
        acct("Sender_Account").alias("Sender_Account"),
        acct("Receiver_Account").alias("Receiver_Account"),
        ifsc("Sender_IFSC").alias("Sender_IFSC"),
        ifsc("Receiver_IFSC").alias("Receiver_IFSC"),
        pl.col("Amount").cast(pl.Float64, strict=False).alias("amount_f"),
        pl.col("Payment_Mode").str.strip_chars().str.to_uppercase().alias("payment_mode"),
        pl.col("Device_Type").str.strip_chars().alias("device_type"),
        pl.col("IP_Address").str.strip_chars(),
        pl.col("Narration").fill_null(""),
    )
    lf = _parse_timestamp(lf)

    lf = lf.with_columns(
        pl.when(pl.col("payment_mode").is_in(list(KNOWN_PAYMENT_MODES)))
          .then(pl.col("payment_mode")).otherwise(pl.lit(PAYMENT_MODE_FALLBACK))
          .alias("payment_mode"),
        pl.col("Sender_IFSC").str.slice(0, 4).alias("sender_bank"),
        pl.col("Receiver_IFSC").str.slice(0, 4).alias("receiver_bank"),
        pl.col("timestamp").dt.epoch("s").alias("ts_epoch"),
        pl.col("IP_Address").str.extract(r"^(\d{1,3})\.", 1)
          .cast(pl.Int32, strict=False).alias("ip_octet1"),
        _kw_expr(pl.col("Narration"), CRYPTO_KEYWORDS).alias("narr_crypto"),
        _kw_expr(pl.col("Narration"), WALLET_KEYWORDS).alias("narr_wallet"),
        _kw_expr(pl.col("Narration"), CASHOUT_KEYWORDS).alias("narr_cashout"),
        pl.col("device_type").is_in(list(AUTOMATION_DEVICES)).alias("is_automation_device"),
        pl.col("Sender_IFSC").str.contains(IFSC_PATTERN).not_().alias("bad_sender_ifsc"),
        pl.col("Receiver_IFSC").str.contains(IFSC_PATTERN).not_().alias("bad_receiver_ifsc"),
    ).with_columns(
        pl.col("ip_octet1").is_in(list(FOREIGN_IP_PREFIXES)).fill_null(False).alias("is_foreign_ip"),
    )

    df = lf.collect(engine="streaming")

    t0 = int(df["ts_epoch"].min() or 0)
    df = df.with_columns(
        ((pl.col("ts_epoch") - t0) // 86400).cast(pl.UInt16).alias("day_index"),
        (pl.col("ts_epoch") // 60).cast(pl.Int64).alias("minute_bucket"),
        # families: network / device / narration  -> never raw boolean sum (DC §9.2)
        (pl.col("is_foreign_ip").cast(pl.UInt8)
         + pl.col("is_automation_device").cast(pl.UInt8)
         + (pl.col("narr_crypto") | pl.col("narr_wallet") | pl.col("narr_cashout")).cast(pl.UInt8)
         ).alias("signal_families"),
        pl.col("source_row_id").cast(pl.Int64),
    )
    dup = df.group_by("Transaction_ID").len().filter(pl.col("len") > 1)["Transaction_ID"]
    df = df.with_columns(pl.col("Transaction_ID").is_in(dup).alias("dup_txn_id"))
    return df


def build_profile(df: pl.DataFrame, src: Path, fingerprint: str, elapsed_s: float) -> dict:
    """Measured truth about the file. Published by GET /api/ingest/profile."""
    n = df.height
    amt = df["amount_f"]
    accounts = pl.concat([df["Sender_Account"], df["Receiver_Account"]]).unique()
    dup_ids = int(df.filter(pl.col("dup_txn_id"))["Transaction_ID"].n_unique())
    dup_rows = int(df["dup_txn_id"].sum())
    exact_dupes = n - df.unique(subset=EXPECTED_COLUMNS).height

    def dist(col: str) -> dict:
        d = df.group_by(col).len().sort("len", descending=True)
        return {str(k): int(v) for k, v in zip(d[col], d["len"])}

    fam = df.group_by("signal_families").len().sort("signal_families")
    both = df.filter(pl.col("is_foreign_ip") & pl.col("is_automation_device")).height
    any_sig = df.filter(pl.col("signal_families") > 0).height

    return {
        "dataset_fingerprint": fingerprint,
        "source_file": src.name,
        "source_bytes": src.stat().st_size,
        "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ingest_seconds": round(elapsed_s, 2),
        "rows": n,
        "columns": list(df.columns),
        "source_column_count": len(EXPECTED_COLUMNS),
        "accounts": int(accounts.len()),
        "unique_transaction_ids": int(df["Transaction_ID"].n_unique()),
        "duplicate_transaction_ids": dup_ids,
        "rows_with_duplicate_id": dup_rows,
        "duplicate_id_surplus": dup_rows - dup_ids,
        "exact_duplicate_rows": int(exact_dupes),
        "unique_pairs": int(df.select(["Sender_Account", "Receiver_Account"]).n_unique()),
        "self_loops": int(df.filter(pl.col("Sender_Account") == pl.col("Receiver_Account")).height),
        "time_window": {
            "start": str(df["timestamp"].min()),
            "end": str(df["timestamp"].max()),
            "days": int(df["day_index"].max() or 0) + 1,
            "unparsed_timestamps": int(df["timestamp"].is_null().sum()),
        },
        "amount": {
            "min": float(amt.min()), "max": float(amt.max()),
            "mean": round(float(amt.mean()), 2), "median": round(float(amt.median()), 2),
            "p90": round(float(amt.quantile(0.90)), 2),
            "p99": round(float(amt.quantile(0.99)), 2),
            "non_positive": int(df.filter(pl.col("amount_f") <= 0).height),
            "sum": round(float(amt.sum()), 2),
        },
        "payment_modes": dist("payment_mode"),
        "devices": dist("device_type"),
        "malformed_ifsc": {
            "sender": int(df["bad_sender_ifsc"].sum()),
            "receiver": int(df["bad_receiver_ifsc"].sum()),
        },
        "malformed_accounts": int(
            df.filter(~pl.col("Sender_Account").str.contains(r"^[0-9]{12}$")).height
        ),
        "signals": {
            "foreign_ip_rows": int(df["is_foreign_ip"].sum()),
            "automation_rows": int(df["is_automation_device"].sum()),
            "crypto_rows": int(df["narr_crypto"].sum()),
            "wallet_rows": int(df["narr_wallet"].sum()),
            "cashout_rows": int(df["narr_cashout"].sum()),
            "rows_with_any_signal": any_sig,
            "share_of_rows": round(any_sig / n * 100, 4) if n else 0.0,
        },
        # DATA_CONTEXT §9.2 - the finding the team must read before weighting
        "signal_cooccurrence": {
            "families_histogram": {str(k): int(v) for k, v in zip(fam["signal_families"], fam["len"])},
            "foreign_ip_and_automation": both,
            "cooccurrence_rate": round(both / max(int(df["is_foreign_ip"].sum()), 1), 4),
            "note": "A high co-occurrence rate means the signals are one injected flag, "
                    "not independent corroboration. The MRI applies a discount.",
        },
        "narration_top": dist("Narration") if df["Narration"].n_unique() <= 50 else
                         dict(list(dist("Narration").items())[:50]),
        "calibration": {"ground_truth_labels": None,
                        "note": "No labels exist. No accuracy metric is computable."},
    }


def write_profile(profile: dict) -> Path:
    out = ARTIFACT_DIR / "profile.json"
    out.write_text(json.dumps(profile, indent=2))
    return out
