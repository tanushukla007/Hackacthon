import { ClaimType, RowId } from '../common/Primitives'

export default function EvidenceDocket({ items, onRemove, onCommit }) {
  return (
    <div className="docket">
      <div className="colhead">
        <h3>Evidence basket</h3><span className="rule" />
        <span className="mono dim" style={{ fontSize: 11 }}>{items.length} item(s)</span>
        <button className="btn" disabled={!items.length} onClick={onCommit}>Attach to case</button>
      </div>
      {!items.length && (
        <div className="colbody tiny">
          Empty. Claims added here keep their source_row_ids, their claim type and the dataset
          fingerprint, so anything exported can be recomputed from the original file.
        </div>
      )}
      {items.map((e) => (
        <div className="docket-item" key={e.evidence_id}>
          <ClaimType type={e.claim_type} />
          <div>
            <div className="claim">{e.claim}</div>
            <div className="meta">
              {e.account_id && <span className="mono">{e.account_id}</span>}
              <span>{e.source_row_count ?? e.source_row_ids?.length ?? 0} source rows</span>
              {e.source_row_ids?.slice(0, 3).map((r) => <RowId key={r} id={r} />)}
              <span className="mono dim">{e.dataset_fingerprint}</span>
            </div>
          </div>
          <button className="btn ghost" onClick={() => onRemove(e.evidence_id)}>Remove</button>
        </div>
      ))}
    </div>
  )
}
