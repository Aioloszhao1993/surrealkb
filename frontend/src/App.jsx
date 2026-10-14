import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import Background from './components/Background'
import ErrorBoundary from './components/ErrorBoundary'
import Home from './pages/Home'
import DocDetail from './pages/DocDetail'
import Upload from './pages/Upload'
import Login from './pages/Login'
import Register from './pages/Register'
import Profile from './pages/Profile'
import Team from './pages/Team'
import AiChat from './components/AiChat'
import { useAuth } from './store'

function RequireAuth({ children }) {
  const { user, ready } = useAuth()
  const loc = useLocation()
  if (!ready) return <div className="page-loading">加载中…</div>
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />
  return children
}

export default function App() {
  return (
    <div className="app-shell">
      <Background />
      <Navbar />
      <main className="container">
        <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/doc/:id" element={<DocDetail />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/user/:id" element={<Profile />} />
          <Route
            path="/upload"
            element={
              <RequireAuth>
                <Upload />
              </RequireAuth>
            }
          />
          <Route
            path="/team"
            element={
              <RequireAuth>
                <Team />
              </RequireAuth>
            }
          />
          <Route path="*" element={<div className="empty">404 · 这一页不存在于现实</div>} />
        </Routes>
        </ErrorBoundary>
      </main>
      <AiChat />
      <footer className="footer">
        <span>SurrealKB · 知识库问答</span>
        <span className="faint">FastAPI × React × MySQL × 百炼</span>
      </footer>
    </div>
  )
}
