import NavRail from './NavRail'
import StatusStrip from './StatusStrip'

export default function AppShell({ dataset, children }) {
  return (
    <div className="app">
      <StatusStrip dataset={dataset} />
      <NavRail dataset={dataset} />
      <main className="main">{children}</main>
    </div>
  )
}
