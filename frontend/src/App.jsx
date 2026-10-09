import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import Background from './components/Background'
import Home from './pages/Home'
import Watch from './pages/Watch'
import Upload from './pages/Upload'
import Login from './pages/Login'
import Register from './pages/Register'
import Profile from './pages/Profile'
import Favorites from './pages/Favorites'
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
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/watch/:id" element={<Watch />} />
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
            path="/favorites"
            element={
              <RequireAuth>
                <Favorites />
              </RequireAuth>
            }
          />
          <Route path="*" element={<div className="empty">404 · 这一帧不存在于现实</div>} />
        </Routes>
      </main>
      <AiChat />
      <footer className="footer">
        <span>SurrealVideo · 梦境视频站</span>
        <span className="faint">FastAPI × React × MySQL</span>
      </footer>
    </div>
  )
}
