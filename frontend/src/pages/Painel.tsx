import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ErroApi, type EmpresaPainel, type Estado, type Painel as DadosPainel } from '../api'
import { AppLayout, useAviso } from '../components/app'
import { Aviso } from '../components/ui'
import { useSessao } from '../sessao'
import { MESES, mudarPeriodo, periodoAtual, quando } from '../util'
import { EmpresaGaveta } from './EmpresaGaveta'

const ESTADOS: Record<Estado, [string, string]> = {
  bad: ['Com problemas', 'pf-pill pf-pill--bad'], warn: ['Por conferir', 'pf-pill pf-pill--warn'],
  ok: ['Completa', 'pf-pill pf-pill--ok'], none: ['Sem faturas', 'pf-pill pf-pill--none'],
}
const FILTROS: [Estado | 'todas', string][] = [['todas', 'Todas'], ['bad', 'Com problemas'], ['warn', 'Por conferir'], ['ok', 'Completas'], ['none', 'Sem faturas']]

export default function Painel() {
  const [periodo, setPeriodo] = useState(periodoAtual())
  const [d, setD] = useState<DadosPainel | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [filtro, setFiltro] = useState<Estado | 'todas'>('todas')
  const [procura, setProcura] = useState('')
  const [gaveta, setGaveta] = useState<{ aberta: boolean; empresa: EmpresaPainel | null }>({ aberta: false, empresa: null })
  const [ocupado, setOcupado] = useState<string | null>(null)
  const aviso = useAviso()

  const carregar = useCallback(() => {
    setErro(null)
    api.painel(periodo).then(setD).catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível carregar o painel.'))
  }, [periodo])
  useEffect(() => { carregar() }, [carregar])

  const lista = useMemo(() => {
    if (!d) return []
    const q = procura.trim().toLowerCase()
    return d.empresas.filter((e) => (filtro === 'todas' || e.estado === filtro) && (!q || e.nome.toLowerCase().includes(q) || e.nif.includes(q)))
  }, [d, filtro, procura])

  const abrir = (empresa: EmpresaPainel | null) => setGaveta({ aberta: true, empresa })
  const fechar = useCallback(() => setGaveta((g) => ({ ...g, aberta: false })), [])

  async function acao(fn: () => Promise<unknown>, id: string, ok: string) {
    setOcupado(id)
    try { await fn(); aviso.mostrar(ok); carregar() }
    catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível concluir.', 'bad') }
    finally { setOcupado(null) }
  }
  const pedir = (e: { id: string; nome: string }) =>
    acao(() => api.pedirFaturas(e.id, periodo), e.id, `Pedido de faturas enviado a ${e.nome}.`)
  const convidar = (e: EmpresaPainel) =>
    acao(() => api.convidar(e.id), e.id, `Convite para o portal enviado a ${e.contacto.nome ?? e.nome}.`)

  const gavetaEl = (
    <EmpresaGaveta aberto={gaveta.aberta} empresa={gaveta.empresa} fechar={fechar}
      gravado={(m) => { fechar(); aviso.mostrar(m); carregar() }} />
  )

  if (erro) return <AppLayout><Aviso>{erro}</Aviso><button className="pf-btn" style={{ alignSelf: 'flex-start' }} onClick={carregar}>Tentar outra vez</button></AppLayout>
  if (!d) return <AppLayout><div className="carregar-painel" aria-busy="true">A carregar…</div></AppLayout>
  if (d.empresas.length === 0) return <AppLayout glow><PrimeiraVez d={d} adicionar={() => abrir(null)} />{gavetaEl}{aviso.elemento}</AppLayout>

  const mes = MESES[Number(periodo.slice(5, 7)) - 1]
  const Mes = mes[0].toUpperCase() + mes.slice(1)
  const t = d.totais
  const n = (k: Estado | 'todas') => k === 'todas' ? d.empresas.length : d.empresas.filter((e) => e.estado === k).length

  return (
    <AppLayout>
      <header className="painel__topo">
        <div>
          <div className="periodo">
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês anterior" onClick={() => setPeriodo(mudarPeriodo(periodo, -1))}>‹</button>
            <span className="periodo__nome">{d.periodo_txt}</span>
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês seguinte" disabled={periodo >= periodoAtual()} onClick={() => setPeriodo(mudarPeriodo(periodo, 1))}>›</button>
          </div>
          <h1 className="painel__titulo">
            {t.faturas ? <>{Mes}, <span className="pf-hl">{t.pct_conferido}%</span> conferido</> : <>{Mes}, ainda sem faturas</>}
          </h1>
        </div>
        <div className="painel__acoes">
          <label className="procura">
            <span className="sr-only">Procurar empresa</span>
            <input className="pf-field__input" type="search" placeholder="Procurar empresa ou NIF" value={procura} onChange={(e) => setProcura(e.target.value)} />
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          </label>
          <button type="button" className="pf-btn pf-btn--primary pf-btn--arrow" onClick={() => abrir(null)}>
            Adicionar empresa
            <span className="pf-btn__arrow"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg></span>
          </button>
        </div>
      </header>

      <section className="stats" aria-label="Números do mês">
        <div className="pf-stat pf-stat--brand"><div className="pf-stat__label">Total de compras</div><div className="pf-stat__value">{t.faturas ? t.total_txt : '—'}</div><div className="pf-stat__sub">{t.faturas} {t.faturas === 1 ? 'fatura' : 'faturas'} · {t.empresas} {t.empresas === 1 ? 'empresa' : 'empresas'}</div></div>
        <div className="pf-stat"><div className="pf-stat__label">Prontas a exportar</div><div className="pf-stat__value">{t.conferidas}</div><div className="pf-stat__sub">{t.faturas ? `${t.pct_conferido}% das faturas do mês` : 'nenhuma fatura ainda'}</div></div>
        <div className="pf-stat"><div className="pf-stat__label">Por conferir</div><div className={`pf-stat__value${t.por_conferir ? ' is-warn' : ''}`}>{t.por_conferir}</div><div className="pf-stat__sub">{!t.por_conferir ? 'tudo em dia' : t.ia_por_conferir ? `${t.ia_por_conferir} lidas por IA` : 'à espera de confirmação'}</div></div>
        <div className="pf-stat"><div className="pf-stat__label">Problemas</div><div className={`pf-stat__value${t.problemas ? ' is-bad' : ''}`}>{t.problemas}</div><div className="pf-stat__sub">{t.problemas_txt || 'nenhum por resolver'}</div></div>
      </section>

      {d.atencao.length > 0 && (
        <section className="bloco" aria-labelledby="atencao-t">
          <h2 id="atencao-t" className="bloco__titulo">Precisa de atenção</h2>
          <div className="atencao">
            {d.atencao.map((a) => (
              <div key={a.empresa_id + a.codigo} className={`pf-alert pf-alert--${a.nivel}`}>
                <span className="pf-alert__tag">{a.nivel === 'bad' ? 'Erro' : 'Aviso'}</span>
                <div className="atencao__texto"><span className="pf-alert__title">{a.titulo}</span>{a.detalhe ? ` ${a.detalhe}` : ''} · {a.empresa}</div>
                {a.fatura_id && <Link to={`/faturas/${a.fatura_id}`} className="pf-btn pf-btn--sm">Ver</Link>}
                {a.codigo === 'sem_faturas' && (
                  <button type="button" className="pf-btn pf-btn--sm" disabled={ocupado === a.empresa_id}
                    onClick={() => pedir({ id: a.empresa_id, nome: a.empresa })}>{a.pedido ? 'Pedir outra vez' : 'Pedir faturas'}</button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="bloco" aria-labelledby="empresas-t">
        <div className="bloco__cabeca">
          <h2 id="empresas-t" className="bloco__titulo">Empresas</h2>
          <div className="pf-tabs" role="tablist" aria-label="Filtrar por estado">
            {FILTROS.map(([k, r]) => (
              <button key={k} type="button" role="tab" className="pf-tab" aria-selected={filtro === k} onClick={() => setFiltro(k)}>
                {r} <span className="pf-tab__count">{n(k)}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="tabela-caixa">
          <table className="pf-table tabela-empresas">
            <thead><tr>
              <th>Empresa</th><th className="dir">Faturas</th><th className="dir">Total</th><th>Conferidas</th><th>Estado</th><th>Última atividade</th>
              <th><span className="sr-only">Ações</span></th>
            </tr></thead>
            <tbody>
              {lista.map((e) => {
                const pct = e.faturas ? Math.round(e.conferidas / e.faturas * 100) : 0
                const contacto = !!(e.contacto.telefone || e.contacto.email)
                return (
                  <tr key={e.id}>
                    <td>
                      <Link to={`/empresas/${e.id}?periodo=${periodo}`} className="link-empresa">{e.nome}</Link>
                      <span className="pf-table__sub">{e.nif}{!e.portal && <span className="sem-portal"> · sem portal</span>}</span>
                    </td>
                    <td className="is-num">{e.faturas}</td>
                    <td className="is-num">{e.total_txt}</td>
                    <td>
                      <div className="progresso">
                        <div className="barra"><span style={{ width: `${pct}%` }} /></div>
                        <span className="pf-mono progresso__n">{e.faturas ? `${e.conferidas} / ${e.faturas}` : '—'}</span>
                      </div>
                    </td>
                    <td><span className={ESTADOS[e.estado][1]}>{ESTADOS[e.estado][0]}</span></td>
                    <td className="muted">{e.estado === 'none' && e.pedido_em ? `Pedido a ${quando(e.pedido_em).toLowerCase()}` : quando(e.ultima)}</td>
                    <td className="dir">
                      {e.estado === 'none' && contacto
                        ? <button type="button" className="pf-btn pf-btn--sm" disabled={ocupado === e.id} onClick={() => pedir(e)}>Pedir faturas</button>
                        : !e.portal && contacto && e.contacto.nome
                          ? <button type="button" className="pf-btn pf-btn--sm" disabled={ocupado === e.id} onClick={() => convidar(e)}>Convidar</button>
                          : e.estado === 'warn' || e.estado === 'bad'
                            ? <Link to={`/empresas/${e.id}?periodo=${periodo}`} className="pf-btn pf-btn--sm">{e.estado === 'bad' ? 'Resolver' : 'Conferir'}</Link>
                            : <button type="button" className="pf-btn pf-btn--sm" onClick={() => abrir(e)}>Editar</button>}
                    </td>
                  </tr>
                )
              })}
              {lista.length === 0 && <tr><td colSpan={7} className="centro muted" style={{ padding: 32 }}>Nenhuma empresa com este filtro.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      {gavetaEl}
      {aviso.elemento}
    </AppLayout>
  )
}

function PrimeiraVez({ d, adicionar }: { d: DadosPainel; adicionar: () => void }) {
  const { eu } = useSessao()
  const primeiro = eu?.utilizador.nome.split(' ')[0] ?? ''
  const programa = { toconline: 'TOConline', primavera: 'Primavera', phc: 'PHC', sage: 'Sage', outro: 'o seu programa' }[d.gabinete.programa ?? 'outro'] ?? 'o seu programa'
  return (
    <div className="primeira">
      <div className="primeira__texto">
        <span className="pf-pill pf-pill--new">Conta criada</span>
        <h1 className="primeira__titulo">Bem-vindo, {primeiro}. Falta <span className="pf-hl">pouco</span>.</h1>
        <p className="primeira__lead">Três passos para receber as primeiras faturas dos seus clientes este mês.</p>
      </div>
      <ol className="passos-lista">
        <li className="passo feito">
          <span className="bola bola--ok" aria-hidden="true">✓</span>
          <div className="passo__texto"><div className="forte17">Gabinete criado</div><div className="muted15">Exportação preparada para {programa}.</div></div>
        </li>
        <li className="passo atual">
          <span className="bola bola--brand">2</span>
          <div className="passo__texto"><div className="forte17">Adicione a primeira empresa</div><div className="muted15">Basta o NIF e o contacto de quem envia as faturas.</div></div>
          <button type="button" className="pf-btn pf-btn--primary" onClick={adicionar}>Adicionar</button>
        </li>
        <li className="passo">
          <span className="bola">3</span>
          <div className="passo__texto"><div className="forte17">Convide o cliente para o portal</div><div className="muted15">Recebe um SMS e passa a enviar faturas com uma foto.</div></div>
        </li>
        <li className="passo">
          <span className="bola">4</span>
          <div className="passo__texto"><div className="forte17">Convide a equipa</div><div className="muted15">Colaboradores do gabinete, cada um com o seu acesso. Em breve.</div></div>
        </li>
      </ol>
    </div>
  )
}
