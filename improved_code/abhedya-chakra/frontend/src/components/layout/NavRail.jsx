import { NavLink } from 'react-router-dom'

const ITEMS = [
  ['01', 'Dashboard', '/'],
  ['02', 'Investigation', '/investigate'],
  ['03', 'Accounts', '/accounts'],
  ['04', 'Cases', '/cases'],
  ['05', 'System', '/system'],
]

export default function NavRail({ dataset }) {
  return (
    <aside className="rail">
      <nav>
        {ITEMS.map(([num, label, to]) => (
          <NavLink key={to} to={to} end={to === '/'}
                   className={({ isActive }) => (isActive ? 'on' : '')}>
            <span className="n">{num}</span><span className="l">{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="rail-foot">
        <div>Investigator workstation</div>
        <div className="sep" />
        <div>The backend is the source of truth. This interface displays
             measurements; it does not calculate them.</div>
        <div className="sep" />
        <div className="mono">api v1.0 · {dataset?.summary?.source_file ?? 'no dataset'}</div>
      </div>
    </aside>
  )
}
