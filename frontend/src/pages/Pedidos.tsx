import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ErroApi, type Pedidos as TPedidos } from '../api'
import { AppLayout, useAviso } from '../components/app'
import { Aviso } from '../components/ui'
import { mudarPeriodo, periodoAtual, quando, telefoneLegivel } from '../util'

/** O que o gabinete pediu aos clientes: faturas em falta e dúvidas sobre faturas. */
export default function Pedidos() {
  const [qs, setQs] = useSearchParams()
  const periodo = qs.get('periodo') || periodoAtual()
  const [d, setD] = useState<TPedidos | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState<string | null>(null)
  const aviso = useAviso()

  const ler = useCallback(() => {
    api.pedidos(periodo).then(setD).catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível carregar os pedidos.'))
  }, [periodo])
  useEffect(() => { ler() }, [ler])

  async function pedir(id: string, nome: string) {
    setOcupado(id)
    try { const r = await api.pedirFaturas(id, periodo); aviso.mostrar(`Pedido enviado a ${nome} por ${r.canal === 'sms' ? 'SMS' : 'email'}.`); ler() }
    catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível enviar.', 'bad') }
    finally { setOcupado(null) }
  }
  async function pedirTodas() {
    setOcupado('todas')
    try {
      const r = await api.pedirTodas(periodo)
      const ok = r.enviados.length, nao = r.ignoradas.length
      aviso.mostrar(ok ? `Pedido enviado a ${ok} ${ok === 1 ? 'empresa' : 'empresas'}.${nao ? ` ${nao} sem envio: ${r.ignoradas.map((x) => `${x.nome} (${x.motivo})`).join(', ')}.` : ''}`
        : `Nenhum pedido enviado: ${r.ignoradas.map((x) => `${x.nome} (${x.motivo})`).join(', ')}.`, ok ? 'ok' : 'bad')
      ler()
    } catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível enviar.', 'bad') }
    finally { setOcupado(null) }
  }

  if (erro) return <AppLayout><Aviso>{erro}</Aviso></AppLayout>
  const mes = d?.periodo_txt.split(' ')[0] ?? ''
  const podemPedir = d ? d.em_falta.filter((e) => e.meio).length : 0

  return (
    <AppLayout>
      <header className="painel__topo">
        <div>
          <div className="periodo">
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês anterior" onClick={() => setQs({ periodo: mudarPeriodo(periodo, -1) })}>‹</button>
            <span className="periodo__nome">{d?.periodo_txt ?? '…'}</span>
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Mês seguinte" disabled={periodo >= periodoAtual()} onClick={() => setQs({ periodo: mudarPeriodo(periodo, 1) })}>›</button>
          </div>
          <h1 className="painel__titulo">Pedidos aos <span className="pf-hl">clientes</span></h1>
        </div>
      </header>
      {!d ? <div className="carregar-painel" aria-busy="true">A carregar…</div> : (
        <>
          <section className="stats" aria-label="Resumo">
            <div className="pf-stat"><div className="pf-stat__label">Sem faturas de {mes}</div><div className={`pf-stat__value${d.contagens.em_falta ? ' is-warn' : ''}`}>{d.contagens.em_falta}</div><div className="pf-stat__sub">{d.contagens.em_falta === 1 ? 'empresa' : 'empresas'}</div></div>
            <div className={`pf-stat${d.contagens.respostas ? ' pf-stat--brand' : ''}`}><div className="pf-stat__label">Respostas por ver</div><div className="pf-stat__value">{d.contagens.respostas}</div><div className="pf-stat__sub">dúvidas respondidas pelo cliente</div></div>
            <div className="pf-stat"><div className="pf-stat__label">À espera do cliente</div><div className="pf-stat__value">{d.contagens.a_espera}</div><div className="pf-stat__sub">dúvidas sem resposta</div></div>
          </section>

          <section className="bloco" aria-labelledby="duv-t">
            <h2 id="duv-t" className="bloco__titulo">Dúvidas sobre faturas</h2>
            {d.duvidas.length === 0 ? <p className="muted15" style={{ margin: 0 }}>Nenhuma dúvida em aberto. Para perguntar algo ao cliente, use "Perguntar ao cliente" ao conferir uma fatura.</p> : (
              <ul className="lista-pedidos">
                {d.duvidas.map((x) => (
                  <li key={x.fatura_id} className={x.estado === 'resposta' ? 'is-nova' : ''}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="forte15 cortar">{x.empresa.nome} <span className="muted14">· {[x.fornecedor, x.numero, x.total].filter(Boolean).join(' · ')}</span></div>
                      {x.ultima && <div className="muted14 cortar">{x.ultima.lado === 'cliente' ? 'Cliente: ' : 'Você: '}“{x.ultima.texto}” · {quando(x.ultima.em)}</div>}
                    </div>
                    <span className={`pf-pill ${x.estado === 'resposta' ? 'pf-pill--ok' : 'pf-pill--warn'}`}>{x.estado === 'resposta' ? 'Respondeu' : 'À espera'}</span>
                    <Link to={`/faturas/${x.fatura_id}`} className="pf-btn pf-btn--sm">Abrir</Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="bloco" aria-labelledby="falta-t">
            <div className="bloco__cabeca">
              <h2 id="falta-t" className="bloco__titulo">Sem faturas de {mes}</h2>
              {podemPedir > 0 && (
                <button type="button" className="pf-btn pf-btn--primary pf-btn--sm" disabled={!!ocupado} onClick={pedirTodas}>
                  {ocupado === 'todas' ? 'A enviar…' : `Pedir a ${podemPedir === 1 ? '1 empresa' : `todas (${podemPedir})`}`}
                </button>
              )}
            </div>
            {d.em_falta.length === 0 ? <p className="muted15" style={{ margin: 0 }}>Todas as empresas já enviaram faturas de {mes}.</p> : (
              <ul className="lista-pedidos">
                {d.em_falta.map((e) => (
                  <li key={e.id}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <Link to={`/empresas/${e.id}?periodo=${periodo}`} className="forte15 link-empresa">{e.nome}</Link>
                      <div className="muted14 cortar">
                        {e.meio === 'sms' ? `${e.contacto.nome ?? 'Contacto'} · ${telefoneLegivel(e.contacto.telefone)}` : e.meio === 'email' ? `${e.contacto.nome ?? 'Contacto'} · ${e.contacto.email}` : 'Sem telemóvel nem email'}
                        {e.pedido_em && ` · pedido ${quando(e.pedido_em).toLowerCase()}`}
                      </div>
                    </div>
                    {e.meio
                      ? <button type="button" className="pf-btn pf-btn--sm" disabled={!!ocupado} onClick={() => pedir(e.id, e.nome)}>{ocupado === e.id ? 'A enviar…' : e.pedido_em ? 'Pedir outra vez' : 'Pedir faturas'}</button>
                      : <Link to={`/empresas/${e.id}?periodo=${periodo}`} className="pf-btn pf-btn--sm pf-btn--ghost">Adicionar contacto</Link>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="bloco" aria-labelledby="hist-t">
            <h2 id="hist-t" className="bloco__titulo">Pedidos enviados <span className="muted14" style={{ fontWeight: 400 }}>· últimos 90 dias</span></h2>
            {d.pedidos.length === 0 ? <p className="muted15" style={{ margin: 0 }}>Ainda não pediu faturas a nenhum cliente.</p> : (
              <div className="tabela-caixa">
                <table className="pf-table" style={{ minWidth: 640 }}>
                  <thead><tr><th>Enviado</th><th>Empresa</th><th>Mês</th><th>Por</th><th>Resultado</th></tr></thead>
                  <tbody>
                    {d.pedidos.map((p) => (
                      <tr key={p.id}>
                        <td className="nowrap">{quando(p.enviado_em)} <span className="muted13">· {p.canal === 'sms' ? 'SMS' : 'email'}</span></td>
                        <td><Link to={`/empresas/${p.empresa.id}?periodo=${p.periodo.slice(0, 7)}`} className="link-empresa">{p.empresa.nome}</Link></td>
                        <td>{p.periodo_txt}</td>
                        <td className="muted">{p.quem ?? '—'}</td>
                        <td>{p.respondido ? <span className="pf-pill pf-pill--ok">Enviou faturas</span> : <span className="pf-pill pf-pill--none">Sem resposta</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
      {aviso.elemento}
    </AppLayout>
  )
}
