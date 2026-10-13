import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ErroApi, type PrevisaoExportacao } from '../api'
import { AppLayout, useAviso } from '../components/app'
import { Aviso } from '../components/ui'
import { mudarPeriodo, periodoAtual, quando } from '../util'

const FORMATOS = [
  { id: 'xlsx', nome: 'Excel', desc: 'Faturas, linhas de IVA e resumo do IVA por empresa e taxa.' },
  { id: 'csv', nome: 'CSV', desc: 'Uma linha por fatura, separado por ";" e com vírgula decimal.' },
  { id: 'zip', nome: 'ZIP com documentos', desc: 'O Excel e os PDFs e fotografias, arrumados por empresa.' },
]

export default function Exportacoes() {
  const [qs, setQs] = useSearchParams()
  const periodo = qs.get('periodo') || periodoAtual()
  const [d, setD] = useState<PrevisaoExportacao | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [formato, setFormato] = useState('xlsx')
  const [marcar, setMarcar] = useState(true)
  const [incluir, setIncluir] = useState(false)
  const [aExportar, setAExportar] = useState(false)
  const aviso = useAviso()

  const ler = useCallback(() => {
    setErro(null)
    api.previsaoExportacao(periodo).then((r) => {
      setD(r)
      setSel(new Set(r.empresas.filter((e) => e.prontas > 0).map((e) => e.id)))
    }).catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível carregar.'))
  }, [periodo])
  useEffect(() => { ler() }, [ler])

  const escolhidas = useMemo(() => d ? d.empresas.filter((e) => sel.has(e.id)) : [], [d, sel])
  const nFaturas = escolhidas.reduce((s, e) => s + e.prontas + (incluir ? e.exportadas : 0), 0)
  const pendentes = escolhidas.filter((e) => e.por_conferir > 0)
  const comAlgo = d ? d.empresas.filter((e) => e.prontas + e.exportadas > 0) : []
  const todas = comAlgo.length > 0 && comAlgo.every((e) => sel.has(e.id))

  async function exportar() {
    setAExportar(true)
    try {
      const r = await api.exportar({ periodo, empresas: [...sel], formato, incluir_exportadas: incluir, marcar })
      const a = document.createElement('a')
      a.href = `/api/exportacoes/${r.lote}/ficheiro`
      a.download = r.nome
      document.body.appendChild(a); a.click(); a.remove()
      aviso.mostrar(`${r.faturas} ${r.faturas === 1 ? 'fatura exportada' : 'faturas exportadas'} para ${r.nome}.`)
      ler()
    } catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível exportar.', 'bad') }
    finally { setAExportar(false) }
  }
  async function desfazer(lote: string) {
    try { const r = await api.desfazerExportacao(lote); aviso.mostrar(`${r.faturas} faturas voltaram a "conferida".`); ler() }
    catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível desfazer.', 'bad') }
  }

  if (erro) return <AppLayout><Aviso>{erro}</Aviso></AppLayout>
  if (!d) return <AppLayout><div className="carregar-painel" aria-busy="true">A carregar…</div></AppLayout>

  return (
    <AppLayout>
      <header className="painel__topo">
        <div>
          <div className="periodo">
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês anterior" onClick={() => setQs({ periodo: mudarPeriodo(periodo, -1) })}>‹</button>
            <span className="periodo__nome">{d.periodo_txt}</span>
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês seguinte" disabled={periodo >= periodoAtual()} onClick={() => setQs({ periodo: mudarPeriodo(periodo, 1) })}>›</button>
          </div>
          <h1 className="painel__titulo">Exportar para a <span className="pf-hl">contabilidade</span></h1>
        </div>
      </header>

      <div className="exportar">
        <section className="bloco exportar__empresas" aria-labelledby="exp-emp">
          <div className="bloco__cabeca">
            <h2 id="exp-emp" className="bloco__titulo">Empresas</h2>
            <label className="check" style={{ margin: 0 }}>
              <input type="checkbox" checked={todas} onChange={() => setSel(todas ? new Set() : new Set(comAlgo.map((e) => e.id)))} />
              <span className="ink">Todas com faturas</span>
            </label>
          </div>
          <div className="tabela-caixa">
            <table className="pf-table">
              <thead><tr><th style={{ width: 24 }}><span className="sr-only">Incluir</span></th><th>Empresa</th><th className="dir">Prontas</th><th className="dir">Total</th><th>Situação</th></tr></thead>
              <tbody>
                {d.empresas.map((e) => {
                  const vazia = e.prontas + e.exportadas === 0
                  return (
                    <tr key={e.id} className={vazia ? 'linha-apagada' : ''}>
                      <td><input type="checkbox" className="cx" aria-label={`Incluir ${e.nome}`} disabled={vazia} checked={sel.has(e.id)}
                        onChange={() => { const s = new Set(sel); if (s.has(e.id)) { s.delete(e.id) } else { s.add(e.id) } setSel(s) }} /></td>
                      <td><Link to={`/empresas/${e.id}?periodo=${periodo}`} className="link-empresa">{e.nome}</Link><span className="pf-table__sub">{e.nif}</span></td>
                      <td className="is-num">{e.prontas}</td>
                      <td className="is-num">{e.prontas ? e.total_txt : '—'}</td>
                      <td>
                        {e.por_conferir > 0 && <span className="pf-pill pf-pill--warn">{e.por_conferir} por conferir</span>}
                        {e.por_conferir === 0 && e.prontas > 0 && <span className="pf-pill pf-pill--ok">Pronta</span>}
                        {e.exportadas > 0 && <span className="pf-pill pf-pill--none" style={{ marginLeft: 6 }}>{e.exportadas} já exportadas</span>}
                        {vazia && e.por_conferir === 0 && <span className="muted14">Sem faturas conferidas</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="exportar__opcoes">
          <h2 className="bloco__titulo">Formato</h2>
          <div className="formatos" role="radiogroup" aria-label="Formato">
            {FORMATOS.map((f) => (
              <label key={f.id} className={`formato${formato === f.id ? ' on' : ''}`}>
                <input type="radio" name="formato" value={f.id} checked={formato === f.id} onChange={() => setFormato(f.id)} className="sr-only" />
                <span className="forte15">{f.nome}</span>
                <span className="muted14">{f.desc}</span>
              </label>
            ))}
          </div>
          <label className="check">
            <input type="checkbox" checked={marcar} onChange={(e) => setMarcar(e.target.checked)} />
            <span className="ink">Marcar como exportadas<span className="muted14 bloco-linha">Ficam bloqueadas e não entram de novo na próxima exportação. Pode desfazer no histórico.</span></span>
          </label>
          <label className="check">
            <input type="checkbox" checked={incluir} onChange={(e) => setIncluir(e.target.checked)} />
            <span className="ink">Incluir as já exportadas</span>
          </label>
          {pendentes.length > 0 && (
            <div className="pf-alert pf-alert--warn"><span className="pf-alert__tag">Aviso</span>
              <div>{pendentes.length === 1 ? pendentes[0].nome : `${pendentes.length} empresas`} ainda {pendentes.length === 1 ? 'tem' : 'têm'} faturas por conferir. Só as conferidas vão no ficheiro.</div></div>
          )}
          <button type="button" className="pf-btn pf-btn--primary pf-btn--arrow botao-exportar" disabled={!nFaturas || aExportar} onClick={exportar}>
            {aExportar ? 'A preparar…' : nFaturas ? `Exportar ${nFaturas} ${nFaturas === 1 ? 'fatura' : 'faturas'}` : 'Nada para exportar'}
            <span className="pf-btn__arrow"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 3v8m0 0-3-3m3 3 3-3M3 13h10" /></svg></span>
          </button>
          <p className="muted14" style={{ margin: 0 }}>Formatos de importação do TOConline, Primavera, PHC e Sage: em breve.</p>
        </aside>
      </div>

      <section className="bloco" aria-labelledby="exp-hist">
        <h2 id="exp-hist" className="bloco__titulo">Histórico</h2>
        {d.historico.length === 0 ? <p className="muted15" style={{ margin: 0 }}>Ainda não exportou nada.</p> : (
          <div className="tabela-caixa">
            <table className="pf-table" style={{ minWidth: 760 }}>
              <thead><tr><th>Quando</th><th>Período</th><th>Empresas</th><th className="dir">Faturas</th><th>Formato</th><th>Por</th><th><span className="sr-only">Ações</span></th></tr></thead>
              <tbody>
                {d.historico.map((h) => (
                  <tr key={h.lote} className={h.desfeita ? 'linha-apagada' : ''}>
                    <td className="nowrap">{quando(h.em)}</td>
                    <td>{h.periodo_txt}</td>
                    <td>{h.empresa ?? `${h.empresas} empresas`}</td>
                    <td className="is-num">{h.faturas}</td>
                    <td>{h.formato_nome}{h.desfeita && <span className="nota-linha">Desfeita {quando(h.desfeita).toLowerCase()}</span>}</td>
                    <td className="muted">{h.quem ?? '—'}</td>
                    <td className="dir nowrap">
                      <a className="pf-btn pf-btn--sm" href={`/api/exportacoes/${h.lote}/ficheiro`} download={h.nome ?? undefined}>Descarregar</a>
                      {h.marcou && !h.desfeita && <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" style={{ marginLeft: 6 }} onClick={() => desfazer(h.lote)}>Desfazer</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {aviso.elemento}
    </AppLayout>
  )
}
