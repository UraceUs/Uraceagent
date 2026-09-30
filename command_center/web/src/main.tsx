import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/glass.css'
import App from './App.tsx'
import { iniciarObservabilidade } from './observabilidade'
import { iniciarTituloAutomatico } from './titulo'

try { const t = localStorage.getItem('cc.theme'); if (t === 'dark' || t === 'light') document.documentElement.dataset.theme = t } catch { /* sem storage */ }

iniciarObservabilidade()
iniciarTituloAutomatico()

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
