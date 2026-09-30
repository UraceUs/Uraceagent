import { useCallback, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

/** Item aberto pelo CAMINHO, não por parâmetro (issue #24): /compras/12, /crm/chat/57,
 *  /equipe/3. O endereço antigo (?c=12, ?lead=57) continua valendo — redireciona para o
 *  novo, porque há link salvo, notificação no celular e item de "Precisa de atenção". */
export function useItemNaRota(base: string, nome: string, legado: string) {
  const params = useParams()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const antigo = Number(sp.get(legado)) || null
  useEffect(() => { if (antigo) nav(`${base}/${antigo}`, { replace: true }) }, [antigo, base, nav])
  const id = Number(params[nome]) || antigo
  const abrir = useCallback((n: number | null) => nav(n ? `${base}/${n}` : base), [nav, base])
  return [id, abrir] as const
}
