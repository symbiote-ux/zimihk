import { getMeta, useApi } from './api'
import DayAhead from './DayAhead'

export default function App() {
  const meta = useApi(getMeta, [])

  return (
    <>
      <header className="masthead">
        <div className="wrap masthead-row">
          <span className="brand">Wind Desk</span>
          <span className="asof">GB national wind · live from Elexon BMRS</span>
        </div>
      </header>
      <main className="wrap">
        {meta.error && <p className="error">Could not reach the API: {meta.error} <button className="retry" onClick={meta.retry}>Retry</button></p>}
        {meta.data && <DayAhead meta={meta.data} />}
      </main>
    </>
  )
}
