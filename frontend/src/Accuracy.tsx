import type { Meta } from './api'

export default function Accuracy({ meta }: { meta: Meta }) {
  return <p className="muted">Accuracy for {meta.start} – {meta.end}</p>
}
