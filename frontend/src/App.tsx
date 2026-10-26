import { useState } from 'react'
import { getMeta, useApi } from './api'
import DayAhead from './DayAhead'
import Accuracy from './Accuracy'

const TABS = { brief: 'Day-ahead brief', accuracy: 'Forecast accuracy' } as const

export default function App() {
  const [tab, setTab] = useState<keyof typeof TABS>('brief')
  const meta = useApi(getMeta, [])

  return (
    <>
      <header className="masthead">
        <div className="wrap masthead-row">
          <span className="brand">Wind Desk</span>
          <nav className="tabs" role="tablist">
            {(Object.keys(TABS) as (keyof typeof TABS)[]).map((k) => (
              <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>
                {TABS[k]}
              </button>
            ))}
          </nav>
          <span className="asof">GB national wind · Elexon BMRS · Jan 2026 decisions</span>
        </div>
      </header>
      <main className="wrap">
        {meta.error && <p className="error">Could not reach the API: {meta.error}</p>}
        {meta.data && (tab === 'brief' ? <DayAhead meta={meta.data} /> : <Accuracy meta={meta.data} />)}
      </main>
    </>
  )
}
