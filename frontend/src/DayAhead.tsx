import type { Meta } from './api'

export default function DayAhead({ meta }: { meta: Meta }) {
  return <p className="muted">Day-ahead brief for {meta.start}</p>
}
