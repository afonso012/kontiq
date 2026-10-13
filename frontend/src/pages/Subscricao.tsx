import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, ErroApi, type PagamentoSub, type Subscricao as TSub } from '../api'
import { AppLayout, useAviso } from '../components/app'
import { Aviso } from '../components/ui'
import { useSessao } from '../sessao'
import { quando } from '../util'

const data = (iso: string | null) => iso ? new Date(iso).toLocaleDateString('pt-PT', { day: 'numeric', month: 'long', year: 'numeric' }) : '—'
const PILL: Record<string, string> = { teste: 'pf-pill--new', ativa: 'pf-pill--ok', em_atraso: 'pf-pill--warn', expirada: 'pf-pill--bad', suspensa: 'pf-pill--bad', cancelada: 'pf-pill--none' }
const ESTADO_PAG: Record<string, [string, string]> = { pago: ['Pago', 'pf-pill--ok'], pendente: ['Por pagar', 'pf-pill--warn'], falhado: ['Falhou', 'pf-pill--bad'], anulado: ['Anulado', 'pf-pill--none'] }

export default function Subscricao() {
  const [d, setD] = useState<TSub | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [ciclo, setCiclo] = useState<'mensal' | 'anual'>('mensal')
  const [aEscolher, setAEscolher] = useState<string | null>(null)
  const [confirmarCancelar, setConfirmarCancelar] = useState(false)
  const { recarregar } = useSessao()
  const nav = useNavigate()
  const local = useLocation()
  const aviso = useAviso()

  const ler = useCallback(() => {
    api.subscricao().then((r) => { setD(r); if (r.estado === 'ativa') setCiclo(r.ciclo) })
      .catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível carregar a subscrição.'))
  }, [])
  useEffect(() => { ler() }, [ler])
  useEffect(() => {
    const m = (local.state as { aviso?: string } | null)?.aviso
    if (m) { aviso.mostrar(m); window.history.replaceState({}, '') }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local.state])

  async function escolher(plano: string) {
    setAEscolher(plano)
    try { const r = await api.escolherPlano(plano, ciclo); nav(r.url) }
    catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível continuar.', 'bad') }
    finally { setAEscolher(null) }
  }
  async function mudar(fn: () => Promise<TSub>, ok: string) {
    try { setD(await fn()); await recarregar(); aviso.mostrar(ok); setConfirmarCancelar(false) }
    catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível concluir.', 'bad') }
  }

  if (erro) return <AppLayout><Aviso>{erro}</Aviso></AppLayout>
  if (!d) return <AppLayout><div className="carregar-painel" aria-busy="true">A carregar…</div></AppLayout>
  const pago = d.estado === 'ativa' || d.estado === 'em_atraso'

  return (
    <AppLayout>
      <header className="painel__topo">
        <h1 className="painel__titulo">A sua <span className="pf-hl">subscrição</span></h1>
      </header>

      <section className="sub-atual" aria-label="Plano atual">
        <div>
          <div className="linha" style={{ justifyContent: 'flex-start', gap: 8 }}>
            <span className="muted14">Plano atual</span>
            <span className={`pf-pill ${PILL[d.estado]}`}>{d.estado_nome}</span>
          </div>
          <p className="sub-atual__plano">{d.plano_nome}{pago && <span className="muted15" style={{ fontSize: 17, marginLeft: 10 }}>{d.preco} / {d.ciclo === 'anual' ? 'ano' : 'mês'} + IVA</span>}</p>
          <p className="muted15" style={{ margin: 0 }}>
            {d.estado === 'teste' && <>Teste grátis até <b className="ink">{data(d.fim_teste)}</b> ({d.dias === 1 ? 'falta 1 dia' : `faltam ${d.dias} dias`}), com tudo o que o plano Gabinete inclui. Não pedimos cartão.</>}
            {d.estado === 'expirada' && <>O teste terminou a {data(d.fim_teste)}. Os seus dados estão guardados: pode consultar e exportar. Escolha um plano para voltar a carregar faturas.</>}
            {d.estado === 'ativa' && (d.cancelar_no_fim
              ? <>Termina a <b className="ink">{data(d.proxima_renovacao)}</b> e não será renovada.</>
              : <>Próxima renovação a <b className="ink">{data(d.proxima_renovacao)}</b>.</>)}
            {d.estado === 'em_atraso' && <>A renovação de {data(d.proxima_renovacao)} não foi paga. Tem {d.dias} dias para regularizar.</>}
            {(d.estado === 'suspensa' || d.estado === 'cancelada') && <>Os seus dados estão guardados: pode consultar e exportar. Escolha um plano para voltar a trabalhar.</>}
          </p>
          {d.pode_gerir && d.estado === 'ativa' && (
            <div className="mt14" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {d.cancelar_no_fim
                ? <button type="button" className="pf-btn pf-btn--sm" onClick={() => mudar(api.retomarSub, 'A subscrição volta a renovar-se.')}>Continuar com a subscrição</button>
                : confirmarCancelar
                  ? <>
                      <button type="button" className="pf-btn pf-btn--sm pf-btn--danger" onClick={() => mudar(api.cancelarSub, 'Subscrição cancelada no fim do período.')}>Sim, cancelar no fim do período</button>
                      <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" onClick={() => setConfirmarCancelar(false)}>Manter</button>
                    </>
                  : <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" onClick={() => setConfirmarCancelar(true)}>Cancelar subscrição</button>}
            </div>
          )}
        </div>
        <div className="uso" aria-label="Utilização">
          <Uso rotulo="Empresas-cliente" usado={d.uso.empresas} limite={d.limites.empresas} />
          <Uso rotulo="Pessoas na equipa" usado={d.uso.pessoas} limite={d.limites.pessoas}
            nota={d.uso.convites ? `+ ${d.uso.convites} ${d.uso.convites === 1 ? 'convite pendente' : 'convites pendentes'}` : undefined} />
        </div>
      </section>

      <section className="bloco" aria-labelledby="planos-t">
        <div className="bloco__cabeca">
          <h2 id="planos-t" className="bloco__titulo">Planos</h2>
          <div className="pf-tabs" role="tablist" aria-label="Pagamento">
            <button type="button" role="tab" className="pf-tab" aria-selected={ciclo === 'mensal'} onClick={() => setCiclo('mensal')}>Mensal</button>
            <button type="button" role="tab" className="pf-tab" aria-selected={ciclo === 'anual'} onClick={() => setCiclo('anual')}>Anual <span className="pf-tab__count">2 meses grátis</span></button>
          </div>
        </div>
        <div className="planos">
          {d.planos.map((p) => {
            const atual = pago && d.plano === p.id && d.ciclo === ciclo && !d.cancelar_no_fim
            return (
              <article key={p.id} className={`plano${p.destaque ? ' plano--destaque' : ''}${atual ? ' plano--atual' : ''}`}>
                {p.destaque && <span className="pf-pill pf-pill--new plano__selo">O mais escolhido</span>}
                <div>
                  <h3 className="plano__nome">{p.nome}</h3>
                  <p className="muted14" style={{ margin: '4px 0 0' }}>{p.para}</p>
                </div>
                <div>
                  <div className="plano__preco">
                    <span className="plano__valor">{ciclo === 'anual' ? p.anual_por_mes : p.mensal}</span>
                    <span className="muted14">/ mês + IVA</span>
                  </div>
                  <div className="muted13">{ciclo === 'anual' ? `${p.anual} por ano` : 'Sem fidelização'}</div>
                </div>
                <ul className="plano__lista">{p.inclui.map((x) => <li key={x}>{x}</li>)}</ul>
                {atual ? <span className="pf-btn" aria-disabled="true">Plano atual</span>
                  : !d.pode_gerir ? <span className="muted13 centro">Só o dono ou um administrador pode mudar de plano.</span>
                  : !p.cabe ? <span className="muted13 centro">Tem mais empresas ou pessoas do que este plano inclui.</span>
                  : <button type="button" className={`pf-btn ${p.destaque ? 'pf-btn--primary' : ''}`} disabled={!!aEscolher} onClick={() => escolher(p.id)}>
                      {aEscolher === p.id ? 'Um momento…' : pago ? `Mudar para ${p.nome}` : `Escolher ${p.nome}`}
                    </button>}
              </article>
            )
          })}
        </div>
        <p className="muted13" style={{ margin: 0 }}>
          Preços sem IVA (23%). Ao mudar de plano, o período novo começa no dia do pagamento.
          {d.modo_pagamento === 'simulado' && ' Modo de teste: os pagamentos são simulados e nada é cobrado.'}
        </p>
      </section>

      {d.pagamentos.length > 0 && (
        <section className="bloco" aria-labelledby="pag-t">
          <h2 id="pag-t" className="bloco__titulo">Pagamentos</h2>
          <div className="tabela-caixa">
            <table className="pf-table" style={{ minWidth: 640 }}>
              <thead><tr><th>Data</th><th>Plano</th><th className="dir">Total</th><th>Estado</th><th>Por</th></tr></thead>
              <tbody>
                {d.pagamentos.map((p) => (
                  <tr key={p.id}>
                    <td className="nowrap">{quando(p.pago_em ?? p.criado_em)}</td>
                    <td>{p.plano_nome} · {p.ciclo}</td>
                    <td className="is-num">{p.total}</td>
                    <td><span className={`pf-pill ${ESTADO_PAG[p.estado][1]}`}>{ESTADO_PAG[p.estado][0]}</span>
                      {p.estado === 'pendente' && <Link to={`/subscricao/pagamento/${p.id}`} className="pf-btn pf-btn--sm" style={{ marginLeft: 8 }}>Pagar</Link>}</td>
                    <td className="muted">{p.quem ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {aviso.elemento}
    </AppLayout>
  )
}

function Uso({ rotulo, usado, limite, nota }: { rotulo: string; usado: number; limite: number | null; nota?: string }) {
  const pct = limite ? Math.min(100, Math.round((usado / limite) * 100)) : 8
  return (
    <div className="uso__linha">
      <div className="uso__topo"><span>{rotulo}</span><span><b>{usado}</b> {limite ? `de ${limite}` : '· sem limite'}</span></div>
      <div className={`barra${limite && usado >= limite ? ' barra--cheia' : ''}`}><span style={{ width: `${pct}%` }} /></div>
      {nota && <span className="muted13">{nota}</span>}
    </div>
  )
}

/** Página de pagamento do modo de teste. Com um fornecedor real, o utilizador vai para a página dele. */
export function PagamentoSimulado() {
  const { id = '' } = useParams()
  const [p, setP] = useState<PagamentoSub | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [aPagar, setAPagar] = useState(false)
  const { recarregar } = useSessao()
  const nav = useNavigate()

  useEffect(() => { api.pagamentoSub(id).then(setP).catch((e) => setErro(e instanceof ErroApi ? e.message : 'Pagamento não encontrado.')) }, [id])

  async function simular(sucesso: boolean) {
    setAPagar(true); setErro(null)
    try {
      const r = await api.simularPagamento(id, sucesso)
      if (r.estado === 'pago') {
        await recarregar()
        nav('/subscricao', { replace: true, state: { aviso: `Pagamento recebido. Está agora no plano ${r.plano_nome}.` } })
      } else setP(r)
    } catch (e) { setErro(e instanceof ErroApi ? e.message : 'Não foi possível concluir.') }
    finally { setAPagar(false) }
  }

  return (
    <AppLayout>
      <div className="checkout">
        <Link to="/subscricao" className="muted14">← Voltar aos planos</Link>
        <h1 className="painel__titulo" style={{ margin: 0 }}>Confirmar <span className="pf-hl">pagamento</span></h1>
        {erro && <Aviso>{erro}</Aviso>}
        {p && (
          <>
            {p.modo === 'simulado' && (
              <div className="pf-alert pf-alert--info"><span className="pf-alert__tag">Teste</span>
                <div>Modo de pagamento simulado: nada é cobrado. Quando houver um fornecedor de pagamentos (cartão, MB WAY, Multibanco), este passo abre a página dele.</div></div>
            )}
            <div className="checkout__linhas">
              <div><span>Plano {p.plano_nome} · {p.ciclo === 'anual' ? '12 meses' : '1 mês'}</span><span className="pf-mono">{p.valor}</span></div>
              <div className="muted"><span>IVA 23%</span><span className="pf-mono">{p.iva}</span></div>
              <div className="checkout__total"><span>Total</span><span className="pf-mono">{p.total}</span></div>
            </div>
            {p.estado === 'pendente' ? (
              <>
                <button type="button" className="pf-btn pf-btn--primary botao-grande" style={{ justifyContent: 'center' }} disabled={aPagar} onClick={() => simular(true)}>
                  {aPagar ? 'A processar…' : `Pagar ${p.total}`}
                </button>
                {p.modo === 'simulado' && <button type="button" className="pf-btn pf-btn--ghost" disabled={aPagar} onClick={() => simular(false)}>Simular pagamento recusado</button>}
              </>
            ) : p.estado === 'falhado' ? (
              <Aviso>O pagamento foi recusado. Volte aos planos para tentar outra vez.</Aviso>
            ) : <Aviso tipo="info">Este pagamento já foi tratado.</Aviso>}
          </>
        )}
      </div>
    </AppLayout>
  )
}
