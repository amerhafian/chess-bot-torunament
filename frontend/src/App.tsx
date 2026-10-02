import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { HomePage } from './pages/HomePage'
import { PlayPage } from './pages/PlayPage'
import { TournamentLivePage } from './pages/TournamentLivePage'
import { TournamentSetupPage } from './pages/TournamentSetupPage'
import { WeightsPage } from './pages/WeightsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/tournament" element={<TournamentSetupPage />} />
          <Route path="/tournament/:id" element={<TournamentLivePage />} />
          <Route path="/play" element={<PlayPage />} />
          <Route path="/weights" element={<WeightsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  )
}
