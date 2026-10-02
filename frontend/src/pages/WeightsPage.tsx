import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatWeights, type SavedWeights } from '../api'

const DEFAULTS = {
  a1: 1,
  a2: 1,
  b1: 0.5,
  b2: 1,
  c1: 0.5,
  c2: 1,
  d1: 0.3,
  d2: 1,
  e1: 0.3,
  e2: 1,
}

export function WeightsPage() {
  const [items, setItems] = useState<SavedWeights[]>([])
  const [name, setName] = useState('')
  const [vals, setVals] = useState(DEFAULTS)
  const [error, setError] = useState<string | null>(null)

  const reload = () => api.listWeights().then(setItems)

  useEffect(() => {
    reload().catch((e) => setError(e.message))
  }, [])

  const save = async () => {
    setError(null)
    try {
      await api.saveWeights({ name: name || 'Custom weights', ...vals, source: 'manual' })
      setName('')
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    }
  }

  const remove = async (id: string) => {
    await api.deleteWeights(id)
    await reload()
  }

  const fields: Array<[keyof typeof DEFAULTS, string]> = [
    ['a1', 'a1 material'],
    ['a2', 'a2 exp'],
    ['b1', 'b1 controlled'],
    ['b2', 'b2 exp'],
    ['c1', 'c1 king'],
    ['c2', 'c2 exp'],
    ['d1', 'd1 attacked'],
    ['d2', 'd2 exp'],
    ['e1', 'e1 center'],
    ['e2', 'e2 exp'],
  ]

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="font-display text-4xl font-bold text-[var(--color-felt-deep)]">Weights library</h1>
      <p className="mt-2 text-[var(--color-ink-soft)]">
        Save power-form evaluation weights (coeff × metric^exp) from tournament winners or create your own.
      </p>

      <div className="panel mt-8 rounded-xl p-5">
        <h2 className="font-display text-xl font-semibold">Save new weights</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm sm:col-span-2">
            <span className="mb-1 block">Name</span>
            <input
              className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My champion"
            />
          </label>
          {fields.map(([key, label]) => (
            <label key={key} className="text-sm">
              <span className="mb-1 block">{label}</span>
              <input
                type="number"
                step="0.01"
                className="w-full rounded-md border border-[rgba(92,58,26,0.25)] bg-white/70 px-3 py-2"
                value={vals[key]}
                onChange={(e) => setVals({ ...vals, [key]: Number(e.target.value) })}
              />
            </label>
          ))}
        </div>
        <button type="button" onClick={save} className="btn-primary mt-4 rounded-md px-4 py-2 text-sm font-semibold">
          Save
        </button>
        {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}
      </div>

      <ul className="mt-6 space-y-3">
        {items.map((w) => (
          <li key={w.id} className="panel flex flex-wrap items-center justify-between gap-3 rounded-xl p-4">
            <div>
              <p className="font-semibold">{w.name}</p>
              <p className="text-sm text-[var(--color-ink-soft)]">
                {formatWeights(w)}
                {w.bot_name ? ` · ${w.bot_name}` : ''}
              </p>
            </div>
            <div className="flex gap-2">
              <Link
                to={`/play?weight=${encodeURIComponent(w.id)}`}
                className="btn-primary rounded-md px-3 py-1.5 text-sm font-semibold"
              >
                Play
              </Link>
              <button type="button" onClick={() => remove(w.id)} className="btn-secondary rounded-md px-3 py-1.5 text-sm">
                Delete
              </button>
            </div>
          </li>
        ))}
        {items.length === 0 && (
          <li className="py-8 text-center text-sm text-[var(--color-ink-soft)]">No saved weights yet.</li>
        )}
      </ul>
    </div>
  )
}
