"""
Integer-encoded CSR graph + value-weighted traversal.

DATA_CONTEXT.md: strings never enter the hot path (§11); parallel edges are
preserved (§12.2); money cannot leave before it arrives (§20.2); the hub guard
reports truncation instead of silently pruning (§20.4).
NetworkX is deliberately absent from the query path.
"""
from __future__ import annotations

import numpy as np

from ..config import (BEAM_PER_HOP, HUB_DEGREE_PERCENTILE, MAX_EDGES, MAX_NODES,
                      MIN_EDGE_SHARE_OF_ARRIVAL, MIN_HUB_DEGREE, MIN_VALUE_FRACTION)


class CSR:
    """One direction of adjacency. indices/eid are parallel arrays."""
    __slots__ = ("indptr", "indices", "eid")

    def __init__(self, indptr: np.ndarray, indices: np.ndarray, eid: np.ndarray):
        self.indptr, self.indices, self.eid = indptr, indices, eid

    def neighbours(self, node: int) -> tuple[np.ndarray, np.ndarray]:
        a, b = self.indptr[node], self.indptr[node + 1]
        return self.indices[a:b], self.eid[a:b]


def build_csr(src: np.ndarray, dst: np.ndarray, n_nodes: int) -> tuple[CSR, CSR]:
    """Forward (by sender) and reverse (by receiver) CSR over the same edge ids."""
    def one(key: np.ndarray, other: np.ndarray) -> CSR:
        order = np.argsort(key, kind="stable").astype(np.int64)
        counts = np.bincount(key, minlength=n_nodes)
        indptr = np.zeros(n_nodes + 1, dtype=np.int64)
        np.cumsum(counts, out=indptr[1:])
        return CSR(indptr, other[order].astype(np.int32), order.astype(np.int64))
    return one(src, dst), one(dst, src)


def hub_mask(in_deg: np.ndarray, out_deg: np.ndarray) -> tuple[np.ndarray, float]:
    total = in_deg.astype(np.int64) + out_deg.astype(np.int64)
    cut = max(float(np.percentile(total, HUB_DEGREE_PERCENTILE)), float(MIN_HUB_DEGREE))
    return total >= cut, cut


class TraceResult(dict):
    pass


def trace_forward(g, seed: int, seed_ts: int, seed_amount: float, max_hops: int,
                  window_end: int | None = None) -> TraceResult:
    """
    Value-weighted forward expansion from a victim account.

    Each frontier entry carries (node, attributed_value, arrival_ts, hop, via_edge).
    An edge is only followed if it occurs AFTER the money arrived (temporal
    causality) and carries at least MIN_VALUE_FRACTION of the seed amount.
    """
    fw = g.fw
    amt, ts = g.amount, g.ts
    min_value = max(seed_amount * MIN_VALUE_FRACTION, 0.0)

    best_value = {seed: float(seed_amount)}
    arrival = {seed: int(seed_ts)}
    hop_of = {seed: 0}
    parent_edge: dict[int, int] = {}
    edges: list[dict] = []
    seen_edges: set[int] = set()
    truncation: str | None = None

    frontier = [(seed, float(seed_amount), int(seed_ts))]
    for hop in range(1, max_hops + 1):
        nxt: list[tuple[int, float, int]] = []
        for node, value, t_in in frontier:
            if g.is_hub[node] and hop > 1:
                truncation = truncation or "HUB_GUARD"
                continue
            nbr, eids = fw.neighbours(node)
            if nbr.size == 0:
                continue
            e_ts, e_amt = ts[eids], amt[eids]
            keep = e_ts >= t_in
            if window_end is not None:
                keep &= e_ts <= window_end
            # follow the money: ignore this account's unrelated small payments
            keep &= e_amt >= max(min_value, value * MIN_EDGE_SHARE_OF_ARRIVAL)
            if not keep.any():
                continue
            idx = np.flatnonzero(keep)
            if idx.size > BEAM_PER_HOP:                      # value-weighted beam
                idx = idx[np.argsort(e_amt[idx])[::-1][:BEAM_PER_HOP]]
                truncation = truncation or "MIN_VALUE"
            pool = float(e_amt[idx].sum()) or 1.0
            for k in idx:
                tgt, eid = int(nbr[k]), int(eids[k])
                carried = value * float(e_amt[k]) / pool
                if eid not in seen_edges:
                    if len(edges) >= MAX_EDGES:
                        truncation = "MAX_EDGES"
                        break
                    seen_edges.add(eid)
                    edges.append({"eid": eid, "src": node, "dst": tgt,
                                  "hop": hop, "attributed": carried})
                if carried > best_value.get(tgt, 0.0):
                    best_value[tgt] = carried
                    arrival[tgt] = int(e_ts[k])
                    parent_edge[tgt] = eid
                if tgt not in hop_of:
                    if len(hop_of) >= MAX_NODES:
                        truncation = "MAX_NODES"
                        break
                    hop_of[tgt] = hop
                    nxt.append((tgt, carried, int(e_ts[k])))
            if truncation in ("MAX_NODES", "MAX_EDGES"):
                break
        if truncation in ("MAX_NODES", "MAX_EDGES") or not nxt:
            if not nxt and hop < max_hops:
                pass
            break
        nxt.sort(key=lambda x: -x[1])
        frontier = nxt[:BEAM_PER_HOP]
    if max_hops < 1:
        truncation = truncation or "MAX_HOPS"
    return TraceResult(nodes=hop_of, value=best_value, arrival=arrival,
                       parent_edge=parent_edge, edges=edges, truncation=truncation)


def shortest_value_path(g, a: int, b: int, max_hops: int) -> list[int] | None:
    """BFS over the forward graph; returns the edge ids of one path a -> b."""
    from collections import deque
    prev: dict[int, tuple[int, int]] = {}
    q = deque([(a, 0)])
    seen = {a}
    while q:
        node, d = q.popleft()
        if node == b:
            path, cur = [], b
            while cur != a:
                p, eid = prev[cur]
                path.append(eid)
                cur = p
            return path[::-1]
        if d >= max_hops:
            continue
        nbr, eids = g.fw.neighbours(node)
        for k in range(nbr.size):
            t = int(nbr[k])
            if t not in seen:
                seen.add(t)
                prev[t] = (node, int(eids[k]))
                q.append((t, d + 1))
    return None
