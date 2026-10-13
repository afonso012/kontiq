import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, ErroApi, type ResumoIva as TResumo } from '../api'
import { AppLayout } from '../components/app'
import { Aviso } from '../components/ui'
import { mudarPeriodo, periodoAtual } from '../util'

/** IVA das compras do mês ou trimestre, com os campos sugeridos do quadro 06 da declaração periódica. */
export default function ResumoIva() {
  const { id = '' } = useParams()
  const [qs, setQs] = useSearchParams()
  const periodo = qs.get('periodo') || periodoAtual()
  const tipo = qs.get('tipo') || ''
  const [d, setD] = useState<TResumo | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    setErro(null)
    api.resumoIva(id, periodo, tipo || undefined).then(setD).catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível calcular.'))
  }, [id, periodo, tipo])

  const passo = d?.tipo === 'trimestre' ? 3 : 1
  const ir = (p: string, t = d?.tipo ?? tipo) => setQs({ periodo: p, ...(t ? { tipo: t } : {}) })
  const fimPeriodo = d ? mudarPeriodo(d.periodo.slice(0, 7), passo - 1) : periodo
  if (erro) return <AppLayout><Aviso>{erro}</Aviso></AppLayout>

  return (
    <AppLayout>
      <div className="migalhas"><Link to="/painel">Painel</Link> · <Link to={`/empresas/${id}?periodo=${periodo}`}>{d?.empresa.nome ?? '…'}</Link></div>
      <header className="painel__topo" style={{ marginTop: -8 }}>
        <div>
          <h1 className="painel__titulo" style={{ marginTop: 0 }}>Resumo do <span className="pf-hl">IVA</span></h1>
          <p className="muted15" style={{ margin: '6px 0 0' }}>Compras de {d?.empresa.nome ?? '…'} · IVA {d?.empresa.periodicidade_iva ?? ''}</p>
        </div>
        <div className="painel__acoes">
          <div className="pf-tabs" role="tablist" aria-label="Período">
            <button type="button" role="tab" className="pf-tab" aria-selected={d?.tipo === 'mes'} onClick={() => ir(periodo, 'mes')}>Mês</button>
            <button type="button" role="tab" className="pf-tab" aria-selected={d?.tipo === 'trimestre'} onClick={() => ir(periodo, 'trimestre')}>Trimestre</button>
          </div>
          <div className="periodo">
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Anterior" onClick={() => ir(mudarPeriodo(d?.periodo.slice(0, 7) ?? periodo, -passo))}>‹</button>
            <span className="periodo__nome">{d?.periodo_txt ?? '…'}</span>
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Seguinte" disabled={fimPeriodo >= periodoAtual()} onClick={() => ir(mudarPeriodo(d?.periodo.slice(0, 7) ?? periodo, passo))}>›</button>
          </div>
          {d && <a className="pf-btn" href={`/api/empresas/${id}/iva.xlsx?periodo=${d.periodo.slice(0, 7)}&tipo=${d.tipo}`}>Descarregar Excel</a>}
        </div>
      </header>

      {!d ? <div className="carregar-painel" aria-busy="true">A calcular…</div> : (
        <>
          {d.por_conferir > 0 && (
            <div className="pf-alert pf-alert--warn"><span className="pf-alert__tag">Aviso</span>
              <div style={{ flex: 1 }}>{d.por_conferir} {d.por_conferir === 1 ? 'fatura ainda não foi conferida' : 'faturas ainda não foram conferidas'} e não {d.por_conferir === 1 ? 'entra' : 'entram'} nestas contas.</div>
              <Link to={`/empresas/${id}?periodo=${d.periodo.slice(0, 7)}`} className="pf-btn pf-btn--sm">Conferir</Link></div>
          )}
          <section className="iva-topo">
            <div className="iva-dp">
              <div className="linha"><h2 className="bloco__titulo" style={{ margin: 0 }}>Declaração periódica · quadro 06</h2><span className="pf-pill pf-pill--new">Sugestão</span></div>
              <ul className="iva-campos">
                {d.campos.map((c) => (
                  <li key={c.campo} className={c.valor_n ? '' : 'is-zero'}>
                    <span className="iva-campos__n pf-mono">{c.campo}</span>
                    <span className="iva-campos__nome">{c.nome}</span>
                    <span className="pf-mono">{c.valor}</span>
                  </li>
                ))}
                <li className="iva-campos__total"><span /><span>IVA dedutível</span><span className="pf-mono">{d.totais.dedutivel}</span></li>
              </ul>
              <p className="muted13" style={{ margin: 0 }}>Imobilizado: contas 43 a 45. Existências: contas 3. O resto entra em outros bens e serviços. Confirme antes de submeter.</p>
            </div>
            <div className="stats iva-stats">
              <div className="pf-stat pf-stat--brand"><div className="pf-stat__label">IVA das compras</div><div className="pf-stat__value">{d.totais.iva}</div><div className="pf-stat__sub">base {d.totais.base}</div></div>
              <div className="pf-stat"><div className="pf-stat__label">IVA dedutível</div><div className="pf-stat__value">{d.totais.dedutivel}</div><div className="pf-stat__sub">{d.faturas} {d.faturas === 1 ? 'fatura conferida' : 'faturas conferidas'}</div></div>
              <div className="pf-stat"><div className="pf-stat__label">Não dedutível</div><div className="pf-stat__value">{d.totais.nao_dedutivel}</div><div className="pf-stat__sub">vai para gasto</div></div>
            </div>
          </section>

          {d.faturas === 0 ? <p className="muted15">Ainda não há faturas conferidas em {d.periodo_txt}.</p> : (
            <div className="iva-tabelas">
              <Tabela titulo="Por espaço fiscal e taxa" cab={['Espaço', 'Taxa']} linhas={d.taxas.map((t) => ({ k: `${t.espaco}${t.taxa}${t.pct}`, cols: [t.espaco, `${t.taxa}${t.pct != null ? ` · ${t.pct.toLocaleString('pt-PT')}%` : ''}`], v: t }))} />
              <Tabela titulo="Por tratamento do IVA" cab={['Tratamento']} linhas={d.tratamentos.map((t) => ({ k: t.id, cols: [t.nome], v: t }))} />
              <Tabela titulo="Por conta SNC" cab={['Conta', 'Descrição']} linhas={d.contas.map((c) => ({ k: c.conta, cols: [<span className="pf-mono" key="c">{c.conta}</span>, c.nome], v: c }))} />
            </div>
          )}
        </>
      )}
    </AppLayout>
  )
}

function Tabela({ titulo, cab, linhas }: { titulo: string; cab: string[]; linhas: { k: string; cols: React.ReactNode[]; v: { base: string; iva: string; dedutivel: string } }[] }) {
  return (
    <section className="bloco">
      <h2 className="bloco__titulo">{titulo}</h2>
      <div className="tabela-caixa">
        <table className="pf-table">
          <thead><tr>{cab.map((c) => <th key={c}>{c}</th>)}<th className="dir">Base</th><th className="dir">IVA</th><th className="dir">Dedutível</th></tr></thead>
          <tbody>{linhas.map((l) => <tr key={l.k}>{l.cols.map((c, i) => <td key={i}>{c}</td>)}<td className="is-num">{l.v.base}</td><td className="is-num">{l.v.iva}</td><td className="is-num">{l.v.dedutivel}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  )
}
