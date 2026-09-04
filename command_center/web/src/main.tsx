import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import App from './App.tsx'

try { const t = localStorage.getItem('cc.theme'); if (t === 'dark' || t === 'light') document.documentElement.dataset.theme = t } catch { /* sem storage */ }

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
