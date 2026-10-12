import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ErroApi, type EmpresaPainel, type EstadoFatura, type FaturasEmpresa, type ResultadoCarregar } from '../api'
import { AppLayout, Gaveta, useAviso } from '../components/app'
import { Aviso } from '../components/ui'
import { mudarPeriodo, periodoAtual } from '../util'
import { EmpresaGaveta } from './EmpresaGaveta'

const ESTADOS: Record<EstadoFatura, [string, string]> = {
  bad: ['Com problemas', 'pf-pill pf-pill--bad'], warn: ['Por conferir', 'pf-pill pf-pill--warn'],
  ok: ['Conferida', 'pf-pill pf-pill--ok'], rejeitada: ['Rejeitada', 'pf-pill pf-pill--none'],
}
const FILTROS: [EstadoFatura | 'todas', string][] = [['todas', 'Todas'], ['warn', 'Por conferir'], ['bad', 'Com problemas'], ['ok', 'Conferidas'], ['rejeitada', 'Rejeitadas']]

export const dataCurta = (iso: string | null) => iso ? iso.split('-').reverse().join('/') : '—'

export function Origem({ metodo, confianca }: { metodo: string; confianca: number | null }) {
  if (metodo === 'qr') return <span className="pf-src pf-src--qr">QR</span>
  if (metodo === 'ia') {
    const pct = Math.round((confianca ?? 0) * 100)
    return <span className={`pf-src pf-src--ia${pct < 80 ? ' is-low' : ''}`}>IA {pct}%</span>
  }
  return <span className="pf-src pf-src--man">Manual</span>
}

export default function EmpresaFaturas() {
  const { id = '' } = useParams()
  const [qs, setQs] = useSearchParams()
  const periodo = qs.get('periodo') || periodoAtual()
  const nav = useNavigate()
  const [d, setD] = useState<FaturasEmpresa | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [filtro, setFiltro] = useState<EstadoFatura | 'todas'>('todas')
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [carregar, setCarregar] = useState(false)
  const [editar, setEditar] = useState<EmpresaPainel | null>(null)
  const aviso = useAviso()
  const local = useLocation()
  useEffect(() => {
    const m = (local.state as { aviso?: string } | null)?.aviso
    if (m) { aviso.mostrar(m); window.history.replaceState({}, '') }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local.state])

  const ler = useCallback(() => {
    setErro(null)
    api.faturasEmpresa(id, periodo).then((r) => { setD(r); setSel(new Set()) })
      .catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível carregar as faturas.'))
  }, [id, periodo])
  useEffect(() => { ler() }, [ler])

  const lista = useMemo(() => d ? d.faturas.filter((f) => filtro === 'todas' ? f.estado !== 'rejeitada' : f.estado === filtro) : [], [d, filtro])
  const porConferir = d ? d.faturas.filter((f) => f.estado === 'warn' || f.estado === 'bad') : []

  async function abrirEditar() {
    const p = await api.painel(periodo).catch(() => null)
    const e = p?.empresas.find((x) => x.id === id)
    if (e) setEditar(e)
  }
  async function conferirSelecionadas() {
    try {
      const r = await api.conferirLote([...sel])
      aviso.mostrar(r.falhadas.length ? `${r.conferidas} conferidas. ${r.falhadas.length} ficaram de fora: ${r.falhadas[0].mensagem}` : `${r.conferidas} faturas conferidas.`, r.falhadas.length ? 'bad' : 'ok')
      ler()
    } catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível conferir.', 'bad') }
  }
  const mudaPeriodo = (p: string) => setQs({ periodo: p })

  if (erro) return <AppLayout><Aviso>{erro}</Aviso><Link to="/painel" className="pf-btn" style={{ alignSelf: 'flex-start' }}>Voltar ao painel</Link></AppLayout>
  if (!d) return <AppLayout><div className="carregar-painel" aria-busy="true">A carregar…</div></AppLayout>
  const t = d.totais
  const n = (k: EstadoFatura | 'todas') => k === 'todas' ? d.faturas.filter((f) => f.estado !== 'rejeitada').length : d.faturas.filter((f) => f.estado === k).length
  const todasSel = lista.length > 0 && lista.every((f) => sel.has(f.id))

  return (
    <AppLayout>
      <div className="migalhas"><Link to="/painel">Painel</Link> · {d.periodo_txt}</div>
      <header className="painel__topo" style={{ marginTop: -8 }}>
        <div style={{ minWidth: 0 }}>
          <h1 className="painel__titulo" style={{ marginTop: 0 }}>{d.empresa.nome}</h1>
          <div className="chips">
            <span className="chip">NIF <b className="pf-mono">{d.empresa.nif}</b></span>
            <span className="chip">IVA <b>{d.empresa.periodicidade_iva}</b></span>
            <span className="chip">Portal <b>{d.empresa.portal ?? 'sem acesso'}</b></span>
          </div>
        </div>
        <div className="painel__acoes">
          <div className="periodo">
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês anterior" onClick={() => mudaPeriodo(mudarPeriodo(periodo, -1))}>‹</button>
            <span className="periodo__nome">{d.periodo_txt}</span>
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês seguinte" disabled={periodo >= periodoAtual()} onClick={() => mudaPeriodo(mudarPeriodo(periodo, 1))}>›</button>
          </div>
          <button type="button" className="pf-btn" onClick={abrirEditar}>Editar empresa</button>
          <button type="button" className="pf-btn" onClick={() => setCarregar(true)}>Carregar faturas</button>
          {porConferir.length > 0 && (
            <button type="button" className="pf-btn pf-btn--primary pf-btn--arrow" onClick={() => nav(`/faturas/${porConferir[0].id}`)}>
              Conferir {porConferir.length} {porConferir.length === 1 ? 'fatura' : 'faturas'}
              <span className="pf-btn__arrow"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 11 11 5M6 5h5v5" /></svg></span>
            </button>
          )}
        </div>
      </header>

      <section className="stats" aria-label="Números da empresa">
        <div className="pf-stat"><div className="pf-stat__label">Total de compras</div><div className="pf-stat__value">{t.faturas ? t.total_txt : '—'}</div><div className="pf-stat__sub">{t.faturas} {t.faturas === 1 ? 'fatura' : 'faturas'} · IVA {t.iva_txt}</div></div>
        <div className="pf-stat"><div className="pf-stat__label">Conferidas</div><div className="pf-stat__value">{t.conferidas}</div><div className="pf-stat__sub">prontas a exportar</div></div>
        <div className="pf-stat"><div className="pf-stat__label">Por conferir</div><div className={`pf-stat__value${t.por_conferir ? ' is-warn' : ''}`}>{t.por_conferir}</div><div className="pf-stat__sub">{t.por_conferir ? `${t.qr} pelo QR · ${t.manual} manuais` : 'tudo em dia'}</div></div>
        <div className="pf-stat"><div className="pf-stat__label">Problemas</div><div className={`pf-stat__value${t.problemas ? ' is-bad' : ''}`}>{t.problemas}</div><div className="pf-stat__sub">{t.problemas ? 'faturas com erros' : 'nenhum'}</div></div>
      </section>

      {d.faturas.length === 0 ? (
        <div className="vazio-faturas pf-glow">
          <h2>Ainda não há faturas de {d.periodo_txt}</h2>
          <p className="muted15">Carregue PDFs ou fotografias com o código QR da AT. As que não tiverem QR entram para preencher.</p>
          <button type="button" className="pf-btn pf-btn--primary" onClick={() => setCarregar(true)}>Carregar faturas</button>
        </div>
      ) : (
        <section className="bloco" aria-label="Faturas">
          <div className="bloco__cabeca">
            <div className="pf-tabs" role="tablist" aria-label="Filtrar por estado">
              {FILTROS.map(([k, r]) => (
                <button key={k} type="button" role="tab" className="pf-tab" aria-selected={filtro === k} onClick={() => { setFiltro(k); setSel(new Set()) }}>
                  {r} <span className="pf-tab__count">{n(k)}</span>
                </button>
              ))}
            </div>
            {sel.size > 0 && (
              <div className="barra-sel">
                {sel.size} {sel.size === 1 ? 'selecionada' : 'selecionadas'}
                <button type="button" className="pf-btn pf-btn--sm pf-btn--primary" onClick={conferirSelecionadas}>Marcar como conferidas</button>
                <button type="button" className="pf-btn pf-btn--sm" onClick={() => setSel(new Set())}>Cancelar</button>
              </div>
            )}
          </div>
          <div className="tabela-caixa">
            <table className="pf-table tabela-faturas">
              <thead><tr>
                <th style={{ width: 24 }}><input type="checkbox" className="cx" aria-label="Selecionar todas" checked={todasSel}
                  onChange={() => setSel(todasSel ? new Set() : new Set(lista.filter((f) => f.estado !== 'ok').map((f) => f.id)))} /></th>
                <th>Data</th><th>Fornecedor</th><th>Documento</th><th>Classificação</th><th className="dir">IVA</th><th className="dir">Total</th><th>Estado</th>
              </tr></thead>
              <tbody>
                {lista.map((f) => (
                  <tr key={f.id} className="linha-clicavel" onClick={(e) => { if (!(e.target as HTMLElement).closest('input,a,button')) nav(`/faturas/${f.id}`) }}>
                    <td><input type="checkbox" className="cx" aria-label={`Selecionar ${f.numero ?? 'fatura'}`} disabled={f.estado === 'ok' || f.estado === 'rejeitada'}
                      checked={sel.has(f.id)} onChange={() => { const s = new Set(sel); if (s.has(f.id)) { s.delete(f.id) } else { s.add(f.id) } setSel(s) }} /></td>
                    <td className="pf-mono nowrap">{dataCurta(f.data)}</td>
                    <td><Link to={`/faturas/${f.id}`} className="link-empresa">{f.fornecedor ?? 'Por preencher'}</Link><span className="pf-table__sub">{f.nif ?? ''}</span></td>
                    <td className="nowrap"><span className="pf-mono">{f.numero ?? '—'}</span> <Origem metodo={f.metodo} confianca={f.confianca} /></td>
                    <td>{f.conta ? <><span className="pf-mono muted">{f.conta}</span> {f.conta_nome}</> : <span style={{ color: 'var(--warn)' }}>Por classificar</span>}</td>
                    <td className="is-num">{f.iva}</td>
                    <td className="is-num">{f.total}</td>
                    <td><span className={ESTADOS[f.estado][1]}>{ESTADOS[f.estado][0]}</span>{f.nota_curta && f.estado !== 'ok' && <span className="nota-linha">{f.nota_curta}</span>}</td>
                  </tr>
                ))}
                {lista.length === 0 && <tr><td colSpan={8} className="centro muted" style={{ padding: 32 }}>Nenhuma fatura com este filtro.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <CarregarModal aberto={carregar} empresaId={id} periodo={periodo} empresa={d.empresa.nome}
        fechar={() => { setCarregar(false); ler() }}
        conferir={(fid) => nav(`/faturas/${fid}`)} />
      <EmpresaGaveta aberto={!!editar} empresa={editar} fechar={() => setEditar(null)} gravado={(m) => { setEditar(null); aviso.mostrar(m); ler() }} />
      {aviso.elemento}
    </AppLayout>
  )
}

type Ficheiro = { chave: string; nome: string; estado: 'a enviar' | ResultadoCarregar['estado']; r?: ResultadoCarregar }

function CarregarModal({ aberto, empresaId, periodo, empresa, fechar, conferir }: {
  aberto: boolean; empresaId: string; periodo: string; empresa: string; fechar: () => void; conferir: (id: string) => void
}) {
  const [fichs, setFichs] = useState<Ficheiro[]>([])
  const [sobre, setSobre] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (aberto) setFichs([]) }, [aberto])

  async function enviar(lista: File[]) {
    if (!lista.length) return
    const novos = lista.map((f, i) => ({ chave: `${Date.now()}-${i}`, nome: f.name, estado: 'a enviar' as const }))
    setFichs((a) => [...novos, ...a])
    // Em grupos de 5, para mostrar progresso e não fazer um pedido enorme.
    for (let i = 0; i < lista.length; i += 5) {
      const grupo = lista.slice(i, i + 5), chaves = novos.slice(i, i + 5).map((n) => n.chave)
      try {
        const { resultados } = await api.carregar(empresaId, periodo, grupo)
        setFichs((a) => a.map((f) => { const k = chaves.indexOf(f.chave); return k >= 0 ? { ...f, estado: resultados[k].estado, r: resultados[k] } : f }))
      } catch (e) {
        const msg = e instanceof ErroApi ? e.message : 'Não foi possível carregar.'
        setFichs((a) => a.map((f) => chaves.includes(f.chave) ? { ...f, estado: 'erro', r: { nome: f.nome, estado: 'erro', mensagem: msg, fatura_id: null, fornecedor: null, numero: null, total: null, metodo: null } } : f))
      }
    }
  }

  const prontas = fichs.filter((f) => f.r?.fatura_id && (f.estado === 'lida' || f.estado === 'manual'))
  const aEnviar = fichs.some((f) => f.estado === 'a enviar')
  const resumo = ['lida', 'manual', 'repetido', 'erro'].map((k) => [k, fichs.filter((f) => f.estado === k).length] as const).filter(([, n]) => n)
  const nomes: Record<string, string> = { lida: 'lidas pelo QR', manual: 'para preencher', repetido: 'repetidos', erro: 'com erro' }

  return (
    <Gaveta aberto={aberto} fechar={fechar} titulo="Carregar faturas" subtitulo={`${empresa} · ${periodo.split('-').reverse().join('/')}`}
      rodape={<>
        <button type="button" className="pf-btn" onClick={fechar}>Fechar</button>
        <button type="button" className="pf-btn pf-btn--primary" disabled={!prontas.length || aEnviar} onClick={() => prontas[0]?.r?.fatura_id && conferir(prontas[0].r.fatura_id)}>
          {prontas.length ? `Conferir ${prontas.length === 1 ? 'a carregada' : `as ${prontas.length} carregadas`}` : 'Conferir'}
        </button>
      </>}>
      <div className="form-gaveta">
        <label className={`zona-largar pf-glow${sobre ? ' is-sobre' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setSobre(true) }} onDragLeave={() => setSobre(false)}
          onDrop={(e) => { e.preventDefault(); setSobre(false); enviar([...e.dataTransfer.files]) }}>
          <span className="zona-largar__icone"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 16V4m0 0-4 4m4-4 4 4" /><path d="M4 16v4h16v-4" /></svg></span>
          <span className="forte17">Arraste para aqui PDFs ou fotografias</span>
          <span className="muted15">ou <u style={{ color: 'var(--brand)' }}>escolha ficheiros</u> · até 20 MB cada · PDF, JPG, PNG, HEIC</span>
          <input ref={input} type="file" multiple accept=".pdf,image/*,.heic" className="sr-only"
            onChange={(e) => { enviar([...(e.target.files ?? [])]); e.target.value = '' }} />
        </label>

        {fichs.length > 0 && (
          <>
            <div className="linha"><span className="forte15">{fichs.length} {fichs.length === 1 ? 'ficheiro' : 'ficheiros'}</span>
              <span className="muted14">{aEnviar ? 'A ler…' : resumo.map(([k, n]) => `${n} ${nomes[k]}`).join(' · ')}</span></div>
            <ul className="ficheiros">
              {fichs.map((f) => (
                <li key={f.chave} className={`ficheiro${f.estado === 'erro' ? ' is-erro' : ''}`}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="ficheiro__nome pf-mono">{f.nome}</div>
                    {f.estado === 'a enviar'
                      ? <div className="barra mt8"><span className="barra__indet" /></div>
                      : <div className="muted14">{f.estado === 'lida' ? [f.r?.fornecedor, f.r?.numero, f.r?.total].filter(Boolean).join(' · ') : f.r?.mensagem}</div>}
                  </div>
                  {f.estado === 'lida' && <><span className="pf-src pf-src--qr">QR</span><span className="pf-pill pf-pill--ok">Lida</span></>}
                  {f.estado === 'manual' && <span className="pf-pill pf-pill--warn">Preencher</span>}
                  {f.estado === 'repetido' && <span className="pf-pill pf-pill--none">Repetido</span>}
                  {f.estado === 'erro' && <span className="pf-pill pf-pill--bad">Erro</span>}
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="dica">
          <span>Faturas com o código QR da AT são lidas sozinhas. As outras entram para preencher ao conferir.</span>
        </div>
      </div>
    </Gaveta>
  )
}
