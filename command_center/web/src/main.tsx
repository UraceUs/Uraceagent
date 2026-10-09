import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/glass.css'
import { carregarIdioma } from './i18n'
import { iniciarObservabilidade } from './observabilidade'
import { iniciarTituloAutomatico } from './titulo'

try { const t = localStorage.getItem('cc.theme'); if (t === 'dark' || t === 'light') document.documentElement.dataset.theme = t } catch { /* sem storage */ }

iniciarObservabilidade()
iniciarTituloAutomatico()

// #177: o dicionário do idioma chega antes do app, para as telas já nascerem no idioma escolhido
carregarIdioma().then(() => import('./App.tsx')).then(({ default: App }) =>
  createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>))
