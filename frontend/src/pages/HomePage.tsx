import { Link } from 'react-router-dom'

export function HomePage() {
  return (
    <div className="relative overflow-hidden">
      <section className="relative grid min-h-[72vh] items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="relative z-10 max-w-xl animate-[fadeUp_700ms_ease_both]">
          <p className="mb-3 font-display text-sm font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
            Survival of the fittest weights
          </p>
          <h1 className="font-display text-5xl font-bold leading-[1.05] text-[var(--color-felt-deep)] sm:text-6xl">
            Chess Bot Tournament
          </h1>
          <p className="mt-5 text-lg leading-relaxed text-[var(--color-ink-soft)]">
            Breed alpha-beta bots with random evaluation weights, crown a winner,
            then challenge the champion yourself.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/tournament" className="btn-primary rounded-md px-5 py-2.5 text-sm font-semibold">
              Start a tournament
            </Link>
            <Link to="/play" className="btn-secondary rounded-md px-5 py-2.5 text-sm font-semibold">
              Play against a bot
            </Link>
          </div>
        </div>

        <div className="relative animate-[fadeUp_900ms_ease_both]">
          <div className="absolute -inset-6 rounded-[2rem] bg-[radial-gradient(circle_at_30%_20%,rgba(196,92,38,0.25),transparent_55%),radial-gradient(circle_at_80%_70%,rgba(31,77,58,0.35),transparent_50%)] blur-sm" />
          <div className="panel relative overflow-hidden rounded-2xl p-6 shadow-[0_20px_50px_rgba(26,20,16,0.18)]">
            <div className="grid grid-cols-8 overflow-hidden rounded-lg shadow-inner">
              {Array.from({ length: 64 }, (_, i) => {
                const row = Math.floor(i / 8)
                const col = i % 8
                const dark = (row + col) % 2 === 1
                return (
                  <div
                    key={i}
                    className="aspect-square"
                    style={{
                      background: dark ? '#b58863' : '#f0d9b5',
                      animation: `squarePulse 2.8s ease-in-out ${(i % 8) * 0.04 + row * 0.05}s infinite`,
                    }}
                  />
                )
              })}
            </div>
            <div className="mt-5 flex items-end justify-between gap-4">
              <div>
                <p className="font-display text-xl font-semibold text-[var(--color-felt-deep)]">score = a·x + b·y + c·z</p>
                <p className="mt-1 text-sm text-[var(--color-ink-soft)]">Material · Controlled squares · Checking moves</p>
              </div>
              <span className="text-4xl opacity-80" aria-hidden>♞</span>
            </div>
          </div>
        </div>
      </section>

      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(16px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes squarePulse {
          0%, 100% { filter: brightness(1); }
          50% { filter: brightness(1.06); }
        }
      `}</style>
    </div>
  )
}
