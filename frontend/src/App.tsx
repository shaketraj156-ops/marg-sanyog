import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './components/Layout'
import { Loading } from './components/ui'
import { LoginPage } from './pages/LoginPage'

// Pages with charts are loaded on demand so the first screen stays small.
const HomePage = lazy(() => import('./pages/home/HomePage').then((m) => ({ default: m.HomePage })))
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const RequestsPage = lazy(() => import('./pages/requests/RequestsPage').then((m) => ({ default: m.RequestsPage })))
const PlansPage = lazy(() => import('./pages/plans/PlansPage').then((m) => ({ default: m.PlansPage })))
const PlanDetailPage = lazy(() => import('./pages/plans/PlanDetailPage').then((m) => ({ default: m.PlanDetailPage })))
const CalendarPage = lazy(() => import('./pages/CalendarPage').then((m) => ({ default: m.CalendarPage })))

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/requests" element={<RequestsPage />} />
          <Route path="/plans" element={<PlansPage />} />
          <Route path="/plans/:id" element={<PlanDetailPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
