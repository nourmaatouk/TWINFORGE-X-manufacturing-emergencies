import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || '/api'
const DASHBOARD_URL = import.meta.env.VITE_DASHBOARD_URL || 'http://localhost:8001'

function getSafeNextUrl() {
  const params = new URLSearchParams(window.location.search)
  const next = (params.get('next') || '').trim()
  if (!next) return ''
  try {
    const decoded = decodeURIComponent(next)
    if (decoded.startsWith('/')) return `${DASHBOARD_URL}${decoded}`
    if (decoded.startsWith(DASHBOARD_URL)) return decoded
    return ''
  } catch {
    return ''
  }
}

type Mode = 'login' | 'register' | 'success'

function App() {
  const [mode, setMode] = useState<Mode>('login')
  const [loggedInEmail, setLoggedInEmail] = useState('')
  const [redirectTo, setRedirectTo] = useState('')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [fieldError, setFieldError] = useState('')
  const [loading, setLoading] = useState(false)

  // Detect expired session
  useEffect(() => {
    const expiresAt = Number(localStorage.getItem('auth_expires_at') || '0')
    if (expiresAt > 0 && Date.now() > expiresAt) {
      localStorage.removeItem('auth_expires_at')
      setMessage('Your session expired — please sign in again.')
    }
  }, [])

  // ── Validators ──────────────────────────────────────────────
  function isValidEmail(v: string) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim().toLowerCase())
  }
  function isValidPassword(v: string) {
    return v.length >= 12 && v.length <= 128
  }

  const canLogin = useMemo(
    () => isValidEmail(email) && isValidPassword(password),
    [email, password]
  )
  const canRegister = useMemo(
    () => isValidEmail(email) && isValidPassword(password) && password === confirmPassword,
    [email, password, confirmPassword]
  )

  function clearStatus() {
    setError('')
    setMessage('')
    setFieldError('')
  }

  function switchMode(next: Mode) {
    clearStatus()
    setMode(next)
  }

  // ── Register ──────────────────────────────────────────────
  async function onRegisterSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    clearStatus()

    if (!isValidEmail(email)) {
      setFieldError('Please enter a valid email address.')
      return
    }
    if (!isValidPassword(password)) {
      setFieldError('Password must be at least 12 characters.')
      return
    }
    if (password !== confirmPassword) {
      setFieldError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(String(data?.error || 'Registration failed'))

      setConfirmPassword('')
      setPassword('')
      switchMode('login')
      setMessage(data.message || 'Account created! You can now sign in.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      setLoading(false)
    }
  }

  // ── Login ─────────────────────────────────────────────────
  async function onLoginSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    clearStatus()

    if (!isValidEmail(email)) {
      setFieldError('Please enter a valid email address.')
      return
    }
    if (!isValidPassword(password)) {
      setFieldError('Password must be at least 12 characters.')
      return
    }

    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(String(data?.error || 'Login failed'))

      setMessage('Signing in…')
      localStorage.setItem('auth_expires_at', String(Date.now() + 3600 * 1000))
      const redirect = getSafeNextUrl() || data?.redirectTo || DASHBOARD_URL
      setLoggedInEmail(email.trim().toLowerCase())
      setRedirectTo(redirect)
      setTimeout(() => setMode('success'), 400)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      setLoading(false)
    }
  }

  // ── UI ────────────────────────────────────────────────────
  return (
    <main className="auth-shell">
      <div className="bg-orb orb-a" />
      <div className="bg-orb orb-b" />
      <div className="bg-orb orb-c" />

      <div className="auth-wrap">

        {/* Brand */}
        <div className="brand">
          <span className="brand-icon">⬡</span>
          <span className="brand-name">TwinForge</span>
        </div>

        {/* Card */}
        <section className={`auth-card mode-${mode}`} key={mode}>
          <div className="card-glow" />

          {/* Tab switcher — only for login / register */}
          {(mode === 'login' || mode === 'register') && (
            <div className="tab-bar" role="tablist">
              <button
                role="tab"
                id="tab-login"
                className={`tab-btn ${mode === 'login' ? 'active' : ''}`}
                aria-selected={mode === 'login'}
                onClick={() => switchMode('login')}
              >
                Sign In
              </button>
              <button
                role="tab"
                id="tab-register"
                className={`tab-btn ${mode === 'register' ? 'active' : ''}`}
                aria-selected={mode === 'register'}
                onClick={() => switchMode('register')}
              >
                Create Account
              </button>
              <span
                className="tab-indicator"
                style={{ left: mode === 'login' ? '4px' : 'calc(50% + 2px)' }}
              />
            </div>
          )}

          {/* ════ SUCCESS SCREEN ════ */}
          {mode === 'success' && (
            <div className="success-screen">
              <div className="success-icon">✓</div>
              <h2 className="success-title">You're signed in</h2>
              <p className="success-email">{loggedInEmail}</p>
              <button
                id="btn-go-dashboard"
                className="btn-primary"
                onClick={() => { window.location.href = redirectTo }}
              >
                Go to Dashboard →
              </button>
              <button
                id="btn-sign-out"
                className="btn-signout"
                onClick={() => {
                  localStorage.removeItem('auth_expires_at')
                  fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
                  switchMode('login')
                }}
              >
                Sign out
              </button>
            </div>
          )}

          {/* ════ SIGN IN ════ */}
          {mode === 'login' && (
            <form onSubmit={onLoginSubmit} className="form-stack" noValidate>
              <div className="field-group">
                <label htmlFor="login-email">Email address</label>
                <div className="input-wrap">
                  <span className="input-icon">@</span>
                  <input
                    id="login-email"
                    type="text"
                    autoComplete="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>

              <div className="field-group">
                <label htmlFor="login-password">Password</label>
                <div className="input-wrap">
                  <span className="input-icon">🔒</span>
                  <input
                    id="login-password"
                    type="password"
                    autoComplete="current-password"
                    placeholder="At least 12 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
              </div>

              <button
                id="btn-login-submit"
                type="submit"
                className="btn-primary"
                disabled={!canLogin || loading}
              >
                {loading && <span className="spinner" />}
                {loading ? 'Signing in…' : 'Sign in →'}
              </button>
            </form>
          )}

          {/* ════ CREATE ACCOUNT ════ */}
          {mode === 'register' && (
            <form onSubmit={onRegisterSubmit} className="form-stack" noValidate>
              <div className="field-group">
                <label htmlFor="reg-email">Email address</label>
                <div className="input-wrap">
                  <span className="input-icon">@</span>
                  <input
                    id="reg-email"
                    type="text"
                    autoComplete="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>

              <div className="field-group">
                <label htmlFor="reg-password">Password</label>
                <div className="input-wrap">
                  <span className="input-icon">🔒</span>
                  <input
                    id="reg-password"
                    type="password"
                    autoComplete="new-password"
                    placeholder="At least 12 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                {password.length > 0 && <PasswordStrength password={password} />}
              </div>

              <div className="field-group">
                <label htmlFor="reg-confirm">Confirm password</label>
                <div className={`input-wrap ${confirmPassword && confirmPassword !== password ? 'input-error' : ''}`}>
                  <span className="input-icon">✓</span>
                  <input
                    id="reg-confirm"
                    type="password"
                    autoComplete="new-password"
                    placeholder="Repeat your password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                  />
                </div>
                {confirmPassword && confirmPassword !== password && (
                  <span className="hint-error">Passwords don't match</span>
                )}
              </div>

              <button
                id="btn-register-submit"
                type="submit"
                className="btn-primary"
                disabled={!canRegister || loading}
              >
                {loading && <span className="spinner" />}
                {loading ? 'Creating account…' : 'Create account →'}
              </button>

              <p className="terms-hint">
                By creating an account you agree to our secure data handling policy.
              </p>
            </form>
          )}

          {/* Status messages */}
          {fieldError && <p className="status-msg status-error" role="alert">{fieldError}</p>}
          {error && <p className="status-msg status-error" role="alert">{error}</p>}
          {message && <p className="status-msg status-success" role="status">{message}</p>}
        </section>

        <p className="footer-note">
          Protected by rate limits and short-lived session tokens.
        </p>
      </div>
    </main>
  )
}

// ── Password strength meter ──────────────────────────────────
function PasswordStrength({ password }: { password: string }) {
  const score = (() => {
    let s = 0
    if (password.length >= 12) s++
    if (password.length >= 16) s++
    if (/[A-Z]/.test(password)) s++
    if (/[0-9]/.test(password)) s++
    if (/[^A-Za-z0-9]/.test(password)) s++
    return s
  })()

  const labels = ['Too short', 'Weak', 'Fair', 'Good', 'Strong', 'Very strong']
  const colors = ['#ff4e6a', '#ff7a3a', '#ffd23a', '#9ef5a4', '#6adfff', '#a78bfa']

  return (
    <div className="pw-strength">
      <div className="pw-bars">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="pw-bar"
            style={{ background: i < score ? colors[score] : 'rgba(255,255,255,0.08)' }}
          />
        ))}
      </div>
      <span className="pw-label" style={{ color: colors[score] }}>
        {labels[score]}
      </span>
    </div>
  )
}

export default App
