import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ErroApi, type FaturasGabinete } from '../api'
import { AppLayout } from '../components/app'
import { Aviso } from '../components/ui'
import { mudarPeriodo, periodoAtual } from '../util'
import { ESTADOS, Origem } from './EmpresaFaturas'

const FILTROS: [keyof FaturasGabinete['contagens'], string][] = [
  ['todas', 'Todas'], ['por_conferir', 'Por conferir'], ['problemas', 'Com problemas'], ['duvidas', 'Com dúvidas'],
  ['conferidas', 'Conferidas'], ['exportadas', 'Exportadas'], ['rejeitadas', 'Rejeitadas'],
]
const dataCurta = (iso: string | null) => iso ? new Date(iso).toLocaleDateString('pt-PT') : '—'

/** Todas as faturas do gabinete num mês, de todas as empresas. */
export default function Faturas() {
  const [qs, setQs] = useSearchParams()
  const periodo = qs.get('periodo') || periodoAtual()
  const filtro = qs.get('filtro') || 'todas'
  const empresa = qs.get('empresa') || ''
  const q = qs.get('q') || ''
  const [texto, setTexto] = useState(q)
  const [d, setD] = useState<FaturasGabinete | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [aCarregar, setACarregar] = useState(false)
  const nav = useNavigate()

  const mudar = (k: string, v: string) => {
    const n = new URLSearchParams(qs)
    if (v) n.set(k, v); else n.delete(k)
    setQs(n, { replace: k === 'q' })
  }

  useEffect(() => {
    const t = setTimeout(() => { if (texto.trim() !== q) mudar('q', texto.trim()) }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [texto])

  useEffect(() => {
    setErro(null); setACarregar(true)
    api.todasFaturas({ periodo, filtro, q, empresa, inicio: 0 }).then(setD)
      .catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível carregar as faturas.'))
      .finally(() => setACarregar(false))
  }, [periodo, filtro, q, empresa])

  async function mais() {
    if (!d) return
    setACarregar(true)
    try {
      const r = await api.todasFaturas({ periodo, filtro, q, empresa, inicio: d.faturas.length })
      setD({ ...r, faturas: [...d.faturas, ...r.faturas] })
    } finally { setACarregar(false) }
  }

  return (
    <AppLayout>
      <header className="painel__topo">
        <div>
          <div className="periodo">
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês anterior" onClick={() => mudar('periodo', mudarPeriodo(periodo, -1))}>‹</button>
            <span className="periodo__nome">{d?.periodo_txt ?? '…'}</span>
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês seguinte" disabled={periodo >= periodoAtual()} onClick={() => mudar('periodo', mudarPeriodo(periodo, 1))}>›</button>
          </div>
          <h1 className="painel__titulo">Todas as <span className="pf-hl">faturas</span></h1>
        </div>
        <div className="painel__acoes acoes-faturas">
          <label className="procura">
            <span className="sr-only">Procurar</span>
            <input className="pf-field__input" type="search" placeholder="Fornecedor, NIF ou número" value={texto} onChange={(e) => setTexto(e.target.value)} />
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          </label>
          <select className="sel filtro-empresa" aria-label="Empresa" value={empresa} onChange={(e) => mudar('empresa', e.target.value)}>
            <option value="">Todas as empresas</option>
            {d?.empresas.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
          </select>
        </div>
      </header>

      <section className="bloco" aria-label="Faturas">
        <div className="bloco__cabeca">
          <div className="pf-tabs" role="tablist" aria-label="Filtrar por estado">
            {FILTROS.map(([k, r]) => (
              <button key={k} type="button" role="tab" className="pf-tab" aria-selected={filtro === k} onClick={() => mudar('filtro', k === 'todas' ? '' : k)}>
                {r} <span className="pf-tab__count">{d?.contagens[k] ?? '·'}</span>
              </button>
            ))}
          </div>
          {d && d.total > 0 && <span className="muted14">{d.total} {d.total === 1 ? 'fatura' : 'faturas'} · {d.total_txt}</span>}
        </div>
        {erro && <Aviso>{erro}</Aviso>}
        {d && d.faturas.length === 0 && !aCarregar && (
          <div className="vazio">
            <p className="forte15" style={{ margin: 0 }}>{q || empresa || filtro !== 'todas' ? 'Nenhuma fatura com estes filtros.' : `Ainda não há faturas de ${d.periodo_txt}.`}</p>
            <p className="muted14" style={{ margin: '6px 0 0' }}>{q || empresa || filtro !== 'todas'
              ? <button type="button" className="link-botao" onClick={() => { setTexto(''); setQs({ periodo }) }}>Limpar filtros</button>
              : <>Carregue faturas numa empresa ou peça-as aos clientes em <Link to="/pedidos">Pedidos</Link>.</>}</p>
          </div>
        )}
        {d && d.faturas.length > 0 && (
          <div className="tabela-caixa">
            <table className="pf-table tabela-faturas-todas" aria-busy={aCarregar}>
              <thead><tr><th>Data</th><th>Empresa</th><th>Fornecedor</th><th>Documento</th><th className="dir">Total</th><th>Estado</th></tr></thead>
              <tbody>
                {d.faturas.map((f) => (
                  <tr key={f.id} className="linha-clicavel" onClick={() => nav(`/faturas/${f.id}`)}>
                    <td className="pf-mono nowrap">{dataCurta(f.data)}</td>
                    <td><Link to={`/empresas/${f.empresa.id}?periodo=${periodo}`} className="link-empresa" onClick={(e) => e.stopPropagation()}>{f.empresa.nome}</Link></td>
                    <td><Link to={`/faturas/${f.id}`} className="ink" onClick={(e) => e.stopPropagation()}>{f.fornecedor ?? 'Por preencher'}</Link>{f.nif && <span className="pf-table__sub">{f.nif}</span>}</td>
                    <td className="nowrap"><span className="pf-mono">{f.numero ?? '—'}</span> <Origem metodo={f.metodo} confianca={f.confianca} /></td>
                    <td className="is-num">{f.total}</td>
                    <td>
                      <span className={ESTADOS[f.estado][1]}>{f.exportada ? 'Exportada' : ESTADOS[f.estado][0]}</span>
                      {f.nota_curta && f.estado !== 'ok' && <span className="nota-linha">{f.nota_curta}</span>}
                      {f.duvida && <span className={`nota-linha nota-duvida${f.duvida === 'resposta' ? ' is-nova' : ''}`}>{f.duvida === 'resposta' ? '● O cliente respondeu' : 'À espera do cliente'}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {d?.mais && <button type="button" className="pf-btn" style={{ alignSelf: 'center' }} disabled={aCarregar} onClick={mais}>{aCarregar ? 'A carregar…' : 'Mostrar mais'}</button>}
      </section>
    </AppLayout>
  )
}
