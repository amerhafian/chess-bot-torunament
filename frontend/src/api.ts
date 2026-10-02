export type Weights = { a: number; b: number; c: number }

export type WeightRange = { min: number; max: number }

export type Bot = {
  id: string
  name: string
  weights: Weights
  depth: number
}

export type Game = {
  id: string
  white: Bot
  black: Bot
  status: 'pending' | 'running' | 'finished' | 'cancelled'
  fen: string
  moves: string[]
  result: string | null
  winner_bot_id: string | null
  round_index: number
  pair_key: string | null
  watchers: number
  started_at: number | null
  finished_at: number | null
  last_move_at: number | null
  tournament_id: string | null
}

export type Standing = {
  bot_id: string
  name: string
  points: number
  wins: number
  draws: number
  losses: number
  games: number
  sonneborn_berger: number
}

export type BracketMatch = {
  id: string
  round_index: number
  slot: number
  bot_a_id: string | null
  bot_b_id: string | null
  winner_id: string | null
  game_ids: string[]
  is_bye: boolean
}

export type Tournament = {
  id: string
  config: {
    bot_count: number
    format: 'round_robin' | 'single_elimination'
    depth: number
    range_a: WeightRange
    range_b: WeightRange
    range_c: WeightRange
    seed: number | null
  }
  bots: Bot[]
  games: Game[]
  status: 'pending' | 'running' | 'finished' | 'cancelled'
  standings: Standing[]
  bracket: BracketMatch[]
  winner_bot_id: string | null
  created_at: number
  finished_at: number | null
}

export type SavedWeights = {
  id: string
  name: string
  a: number
  b: number
  c: number
  source?: string | null
  bot_name?: string | null
  created_at: number
}

export type PlaySession = {
  id: string
  bot_name: string
  weights: Weights
  depth: number
  human_color: 'white' | 'black'
  fen: string
  moves: string[]
  status: 'active' | 'finished'
  result: string | null
  created_at: number
  bot_thinking: boolean
  turn: 'white' | 'black'
}

const json = async <T>(res: Response): Promise<T> => {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  createTournament: (body: unknown) =>
    fetch('/api/tournaments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => json<Tournament>(r)),

  getTournament: (id: string) =>
    fetch(`/api/tournaments/${id}`).then((r) => json<Tournament>(r)),

  listTournaments: () =>
    fetch('/api/tournaments').then((r) => json<Tournament[]>(r)),

  getGame: (id: string) =>
    fetch(`/api/games/${id}`).then((r) => json<Game>(r)),

  saveWinner: (tournamentId: string, name?: string) =>
    fetch(`/api/tournaments/${tournamentId}/save-winner`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).then((r) => json<SavedWeights>(r)),

  listWeights: () =>
    fetch('/api/weights').then((r) => json<SavedWeights[]>(r)),

  saveWeights: (body: { name: string; a: number; b: number; c: number; bot_name?: string; source?: string }) =>
    fetch('/api/weights', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => json<SavedWeights>(r)),

  deleteWeights: (id: string) =>
    fetch(`/api/weights/${id}`, { method: 'DELETE' }).then((r) => json<{ deleted: boolean }>(r)),

  createPlay: (body: unknown) =>
    fetch('/api/play', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => json<PlaySession>(r)),

  getPlay: (id: string) =>
    fetch(`/api/play/${id}`).then((r) => json<PlaySession>(r)),

  playMove: (id: string, move: string) =>
    fetch(`/api/play/${id}/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ move }),
    }).then((r) => json<PlaySession>(r)),
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}

export function formatWeights(w: Weights): string {
  return `a=${w.a.toFixed(2)} · b=${w.b.toFixed(2)} · c=${w.c.toFixed(2)}`
}
