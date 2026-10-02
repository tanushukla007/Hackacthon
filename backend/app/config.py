"""
ABHEDYA-CHAKRA - central configuration.

DATA_CONTEXT.md Rule 6: no threshold, keyword, prefix, device name, window or
weight may be hard-coded outside this file.
DATA_CONTEXT.md Rule 7: no absolute rupee floor. Amount bands are derived from
the measured distribution at ingest (see PERCENTILES below), never constants.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"

# Which CSV in data/raw the server loads at boot. Picking "whatever sorts
# first alphabetically" is a trap: dropping a differently-named file into
# data/raw silently changes the dataset the demo runs on. Order of precedence
# is ABHEDYA_DATASET (env) -> this name, if present -> the only CSV there ->
# refuse and wait for an explicit POST /api/ingest.
PREFERRED_DATASET = os.environ.get("ABHEDYA_DATASET", "SYNTHETIC_DEV_250k.csv")
ARTIFACT_DIR = DATA_DIR / "artifacts"
CASE_DIR = DATA_DIR / "cases"
for _d in (RAW_DIR, ARTIFACT_DIR, CASE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

API_VERSION = "1.0"

# ---------------------------------------------------------------- schema
EXPECTED_COLUMNS = [
    "Transaction_ID", "Sender_Account", "Receiver_Account",
    "Sender_IFSC", "Receiver_IFSC", "Amount", "Timestamp",
    "Payment_Mode", "Narration", "IP_Address", "Device_Type",
]
ACCOUNT_PATTERN = r"^[0-9]{12}$"
ACCOUNT_WIDTH = 12
IFSC_PATTERN = r"^[A-Z]{4}0[A-Z0-9]{6}$"
KNOWN_PAYMENT_MODES = ("UPI", "IMPS", "NEFT", "RTGS")
PAYMENT_MODE_FALLBACK = "OTHER"

# ------------------------------------------------------- terminal signals
FOREIGN_IP_PREFIXES = (185, 194)                       # [PS] configurable
AUTOMATION_DEVICES = ("Web_Emulator", "Linux_Script")  # configurable
CRYPTO_KEYWORDS = ("P2P_CRYPTO", "CRYPTO", "BTC", "USDT", "BINANCE", "WAZIRX")
WALLET_KEYWORDS = ("WALLET_TOPUP", "WALLET", "PREPAID", "LOAD")
CASHOUT_KEYWORDS = ("CASHOUT", "WITHDRAW", "ATM", "CASH")
NARRATION_EXCLUSIONS = ("CASHBACK", "CASHBACK_REVERSAL")

# ------------------------------------------------------------- velocity
VELOCITY_WINDOWS = (300, 3600, 21600, 86400)
PRIMARY_VELOCITY_WINDOW = 3600

# ------------------------------------------------------------ percentiles
# Every behavioural threshold is a percentile of the MEASURED distribution.
PCTL_DEGREE_HIGH = 95.0
PCTL_DEGREE_EXTREME = 99.0
PCTL_VELOCITY_HIGH = 95.0
HUB_DEGREE_PERCENTILE = 99.5
MIN_HUB_DEGREE = 50          # floor so tiny dev datasets do not flag everything

# ------------------------------------------------------------ pass-through
FORWARD_RATIO_CLIP = 2.0
FAST_HOLD_SECONDS = 1800     # interpretation aid only, never a verdict

# ------------------------------------------------------------- role shapes
# Role descriptors are composites. None of them may be derived from a single
# degree being zero (DATA_CONTEXT.md §15, §16).
ROLE_FANIN_PCTL = 90.0
ROLE_FANOUT_PCTL = 85.0
ROLE_SPLIT_MIN = 1.5
ROLE_FORWARD_MIN = 0.7
ROLE_TERMINAL_FAMILIES = 2
ROLE_TERMINAL_MAX_FORWARD = 0.5

# ------------------------------------------------------------------ MRI
MRI_WEIGHTS = {
    "pass_through": 25,
    "velocity": 20,
    "fan_in": 15,
    "fan_out": 15,
    "terminal_signals": 15,
    "behavioral_anomaly": 10,
}
MRI_BANDS = (("LOW", 0, 30), ("MEDIUM", 30, 60), ("HIGH", 60, 80), ("CRITICAL", 80, 101))
TERMINAL_SIGNAL_SOLO_CAP = 55.0      # terminal evidence alone can never be CRITICAL
CALIBRATION_REGIME = "HEURISTIC_SELF_VALIDATION"
MRI_DISCLAIMER = (
    "This score is a prioritisation aid produced from observed transaction behaviour. "
    "It is not a verdict, not a probability of guilt, and not a legal finding. "
    "No ground-truth labels exist for this dataset, so no accuracy claim is possible. "
    "A human investigator decides what this means."
)

# ------------------------------------------------------------- traversal
MAX_HOPS_DEFAULT = 4
MAX_HOPS_LIMIT = 6
MAX_NODES = 800
MAX_EDGES = 1500
BEAM_PER_HOP = 400           # value-weighted beam width
MIN_VALUE_FRACTION = 0.001   # prune branches carrying < 0.1% of the seed amount
MIN_EDGE_SHARE_OF_ARRIVAL = 0.05  # follow the money: an edge must carry >= 5% of what arrived

# ------------------------------------------------------------ performance
BUDGET_MS = {"trace_p95": 2000, "graph_p95": 500, "account_p95": 300, "ingest_s": 60}

# ------------------------------------------------------------------ legal
LEGAL_PRODUCTION = "Section 94 BNSS, 2023 (corresponding to Section 91 CrPC, 1973)"
LEGAL_SEIZURE = "Section 106 BNSS, 2023"
