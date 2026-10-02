export type Weights = {
  a1: number
  a2: number
  b1: number
  b2: number
  c1: number
  c2: number
  d1: number
  d2: number
  e1: number
  e2: number
  /** Legacy coeff aliases */
  a?: number
  b?: number
  c?: number
}

export type Evaluation = {
  score: number
  white_pct: number
  label: string
  source?: 'search' | 'static'
}

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
  search_score?: number | null
  eval_history?: Array<number | null>
  evaluation?: Evaluation
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
    range_d: WeightRange
    range_e: WeightRange
    range_exp: WeightRange
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

export type SavedWeights = Weights & {
  id: string
  name: string
  source?: string | null
  bot_name?: string | null
  created_at: number
}

export type PlaySession = {
  id: string
  bot_name: string
  weights: Weights
  depth: number
  mode?: 'human' | 'stockfish'
  human_color: 'white' | 'black'
  stockfish_color?: 'white' | 'black'
  bot_color?: 'white' | 'black'
  stockfish_depth?: number
  fen: string
  moves: string[]
  status: 'active' | 'finished'
  result: string | null
  created_at: number
  bot_thinking: boolean
  sf_thinking?: boolean
  turn: 'white' | 'black'
  search_score?: number | null
  eval_history?: Array<number | null>
  evaluation?: Evaluation
  sf_search_score?: number | null
  sf_eval_history?: Array<number | null>
  sf_evaluation?: Evaluation | null
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

  saveWeights: (body: Partial<Weights> & { name: string; bot_name?: string; source?: string }) =>
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

  stockfishStatus: () =>
    fetch('/api/stockfish').then((r) => json<{ available: boolean }>(r)),

  evaluate: (body: {
    fen: string
    weights2?: Partial<Weights>
  } & Partial<Weights>) =>
    fetch('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => json<Evaluation>(r)),
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}

export function normalizeWeights(w: Partial<Weights> | null | undefined): Weights {
  return {
    a1: w?.a1 ?? w?.a ?? 0,
    a2: w?.a2 ?? 1,
    b1: w?.b1 ?? w?.b ?? 0,
    b2: w?.b2 ?? 1,
    c1: w?.c1 ?? w?.c ?? 0,
    c2: w?.c2 ?? 1,
    d1: w?.d1 ?? 0,
    d2: w?.d2 ?? 1,
    e1: w?.e1 ?? 0,
    e2: w?.e2 ?? 1,
    a: w?.a1 ?? w?.a ?? 0,
    b: w?.b1 ?? w?.b ?? 0,
    c: w?.c1 ?? w?.c ?? 0,
  }
}

export function formatWeights(w: Partial<Weights>): string {
  const n = normalizeWeights(w)
  const parts = [
    `a=${n.a1.toFixed(2)}^${n.a2.toFixed(2)}`,
    `b=${n.b1.toFixed(2)}^${n.b2.toFixed(2)}`,
    `c=${n.c1.toFixed(2)}^${n.c2.toFixed(2)}`,
    `d=${n.d1.toFixed(2)}^${n.d2.toFixed(2)}`,
    `e=${n.e1.toFixed(2)}^${n.e2.toFixed(2)}`,
  ]
  return parts.join(' · ')
}

export function weightsToEvaluatePayload(w: Partial<Weights>): Partial<Weights> {
  const n = normalizeWeights(w)
  return {
    a1: n.a1,
    a2: n.a2,
    b1: n.b1,
    b2: n.b2,
    c1: n.c1,
    c2: n.c2,
    d1: n.d1,
    d2: n.d2,
    e1: n.e1,
    e2: n.e2,
  }
}
