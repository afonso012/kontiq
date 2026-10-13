import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ErroApi, type DuvidaPortal, type PortalInicio as Dados } from '../api'
import { Aviso } from '../components/ui'
import { Escrever, Mensagens } from '../components/conversa'
import { ConviteInstalar } from '../components/instalar'
import { useSessao } from '../sessao'
import { quando } from '../util'

type Envio = { chave: string; nome: string; estado: 'a enviar' | 'ok' | 'repetido' | 'erro'; mensagem?: string }

const ESTADO: Record<string, [string, string]> = {
  recebida: ['Recebida', 'pf-pill pf-pill--warn'], tratada: ['Tratada', 'pf-pill pf-pill--ok'], rejeitada: ['Não aceite', 'pf-pill pf-pill--bad'],
}

/** Início do portal do cliente: tirar foto ou escolher ficheiros, e ver o que já enviou. Pensado para telemóvel. */
export default function PortalInicio() {
  const [d, setD] = useState<Dados | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [envios, setEnvios] = useState<Envio[]>([])
  const camara = useRef<HTMLInputElement>(null)
  const ficheiros = useRef<HTMLInputElement>(null)
  const { definir } = useSessao()
  const nav = useNavigate()
  const [qs] = useSearchParams()
  // Atalho "Tirar foto" do ícone instalado: o browser não deixa abrir a câmara sozinho, por isso destacamos o botão.
  const destacarFoto = qs.get('acao') === 'foto'
  useEffect(() => { if (destacarFoto) camara.current?.parentElement?.querySelector<HTMLButtonElement>('.portal__foto')?.focus() }, [destacarFoto])

  const ler = useCallback(() => {
    api.portalInicio().then(setD).catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível abrir o portal.'))
  }, [])
  useEffect(() => { ler() }, [ler])

  async function enviar(lista: File[]) {
    if (!lista.length) return
    const novos: Envio[] = lista.map((f, i) => ({ chave: `${Date.now()}-${i}`, nome: f.name, estado: 'a enviar' }))
    setEnvios((a) => [...novos, ...a])
    for (let i = 0; i < lista.length; i += 3) {
      const chaves = novos.slice(i, i + 3).map((n) => n.chave)
      try {
        const { resultados } = await api.enviarPortal(lista.slice(i, i + 3))
        setEnvios((a) => a.map((e) => {
          const k = chaves.indexOf(e.chave)
          if (k < 0) return e
          const r = resultados[k]
          return { ...e, estado: r.ok ? 'ok' : r.repetido ? 'repetido' : 'erro', mensagem: r.ok ? [r.fornecedor, r.total].filter(Boolean).join(' · ') || 'Recebida' : r.mensagem }
        }))
      } catch (err) {
        const msg = err instanceof ErroApi ? err.message : 'Não foi possível enviar.'
        setEnvios((a) => a.map((e) => chaves.includes(e.chave) ? { ...e, estado: 'erro', mensagem: msg } : e))
      }
    }
    ler()
  }

  async function sair() {
    await api.sair().catch(() => {})
    definir(null)
    nav('/portal', { replace: true })
  }

  const iniciais = d?.gabinete.nome.split(/\s+/).filter((p) => p.length > 2 || /^[A-Z]/.test(p)).map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  const aEnviar = envios.some((e) => e.estado === 'a enviar')

  return (
    <div className="portal">
      <header className="portal__topo pf-glow">
        <div className="portal__gabinete">
          <span className="avatar" aria-hidden="true">{iniciais ?? '…'}</span>
          <div style={{ flex: 1, minWidth: 0 }}><div className="forte15 cortar">{d?.gabinete.nome ?? '…'}</div><div className="muted12">Portal de faturas</div></div>
          <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" onClick={sair}>Sair</button>
        </div>
        <h1 className="portal__titulo">Olá, {d?.utilizador.nome.split(' ')[0] ?? '…'}</h1>
        <p className="muted15">{d?.empresa.nome}</p>
      </header>

      <div className="portal__form">
        {erro && <Aviso>{erro}</Aviso>}
        {d?.pedido && (
          <div className="pf-alert pf-alert--warn"><span className="pf-alert__tag">Pedido</span>
            <div>
              {d.pedido.em_falta_total > 0
                ? <>Estas faturas de <b>{d.pedido.periodo_txt}</b> aparecem nas Finanças mas ainda não chegaram ao gabinete:</>
                : <>O gabinete está à espera das faturas de <b>{d.pedido.periodo_txt}</b>.</>}
              {d.pedido.em_falta_total > 0 && (
                <ul className="em-falta">
                  {d.pedido.em_falta.map((x) => (
                    <li key={`${x.fornecedor}-${x.numero}`}><b>{x.fornecedor}</b>
                      <span className="em-falta__det"><span className="pf-mono">{x.numero}</span>{x.total && <span className="pf-mono">{x.total}</span>}</span></li>
                  ))}
                  {d.pedido.em_falta_total > d.pedido.em_falta.length && <li>e mais {d.pedido.em_falta_total - d.pedido.em_falta.length}</li>}
                </ul>
              )}
            </div></div>
        )}

        {d && d.duvidas.length > 0 && (
          <section className="portal__duvidas" aria-labelledby="duvidas-t">
            <h2 id="duvidas-t" className="forte17" style={{ margin: 0 }}>
              {d.duvidas.length === 1 ? 'O gabinete tem uma dúvida' : `O gabinete tem ${d.duvidas.length} dúvidas`}
            </h2>
            {d.duvidas.map((x) => <CartaoDuvida key={x.fatura_id} d={x} atualizar={ler} />)}
          </section>
        )}

        <ConviteInstalar />

        <button type="button" className={`pf-btn pf-btn--primary botao-grande portal__foto${destacarFoto ? ' is-destaque' : ''}`} onClick={() => camara.current?.click()} disabled={aEnviar}>
          <span>Tirar foto a uma fatura</span>
          <span className="pf-btn__arrow"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg></span>
        </button>
        <button type="button" className="pf-btn botao-grande" style={{ justifyContent: 'center' }} onClick={() => ficheiros.current?.click()} disabled={aEnviar}>
          Escolher PDFs ou fotografias
        </button>
        <input ref={camara} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-hidden="true"
          onChange={(e) => { enviar([...(e.target.files ?? [])]); e.target.value = '' }} />
        <input ref={ficheiros} type="file" accept=".pdf,image/*,.heic" multiple className="sr-only" tabIndex={-1} aria-hidden="true"
          onChange={(e) => { enviar([...(e.target.files ?? [])]); e.target.value = '' }} />
        <p className="muted13 centro" style={{ margin: '-4px 0 0' }}>Fotografe a fatura inteira, de frente e com boa luz. O código QR deve ficar nítido.</p>

        {envios.length > 0 && (
          <ul className="ficheiros" aria-live="polite">
            {envios.map((e) => (
              <li key={e.chave} className={`ficheiro${e.estado === 'erro' ? ' is-erro' : ''}`}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ficheiro__nome pf-mono">{e.nome}</div>
                  {e.estado === 'a enviar' ? <div className="barra mt8"><span className="barra__indet" /></div> : <div className="muted14">{e.mensagem}</div>}
                </div>
                {e.estado === 'ok' && <span className="pf-pill pf-pill--ok">Enviada</span>}
                {e.estado === 'repetido' && <span className="pf-pill pf-pill--none">Repetida</span>}
                {e.estado === 'erro' && <span className="pf-pill pf-pill--bad">Erro</span>}
              </li>
            ))}
          </ul>
        )}

        <section className="portal__enviados" aria-labelledby="enviadas-t">
          <div className="linha">
            <h2 id="enviadas-t" className="forte17" style={{ margin: 0 }}>Enviadas</h2>
            <span className="muted14">{d ? `${d.enviados_mes} em ${d.mes_txt.split(' ')[0]}` : ''}</span>
          </div>
          {d && d.enviados.length === 0 && <p className="muted15" style={{ margin: 0 }}>Ainda não enviou faturas. As que enviar aparecem aqui.</p>}
          <ul className="lista-enviadas">
            {d?.enviados.map((x) => (
              <li key={x.id}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="forte15 cortar">{x.fornecedor ?? x.nome}</div>
                  <div className="muted13">{quando(x.enviado_em)}{x.total ? ` · ${x.total}` : ''}{x.canal !== 'portal' ? ' · pelo gabinete' : ''}</div>
                </div>
                <span className={ESTADO[x.estado][1]}>{ESTADO[x.estado][0]}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}

function CartaoDuvida({ d, atualizar }: { d: DuvidaPortal; atualizar: () => void }) {
  const [mensagens, setMensagens] = useState(d.mensagens)
  const [estado, setEstado] = useState(d.estado)
  const [erro, setErro] = useState<string | null>(null)
  const img = d.documento ? `/api/portal/documentos/${d.documento.id}/pagina/1` : null
  async function responder(texto: string) {
    setErro(null)
    try {
      const r = await api.responderDuvida(d.fatura_id, texto)
      setMensagens(r.mensagens); setEstado(r.estado)
      return true
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : 'Não foi possível enviar.')
      if (e instanceof ErroApi && e.codigo === 'sem_duvida') atualizar()
      return false
    }
  }
  return (
    <article className="duvida pf-glass">
      <div className="duvida__fatura">
        {img && <a href={img} target="_blank" rel="noreferrer" className="duvida__miniatura" aria-label="Ver a fatura"><img src={img} alt="" onError={(e) => { (e.currentTarget.parentElement as HTMLElement).style.display = 'none' }} /></a>}
        <div style={{ minWidth: 0 }}>
          <div className="forte15 cortar">{d.fornecedor ?? d.documento?.nome ?? 'Fatura'}</div>
          <div className="muted13">{[d.numero, d.data ? new Date(d.data).toLocaleDateString('pt-PT') : null, d.total].filter(Boolean).join(' · ')}</div>
          {estado === 'resposta' && <span className="pf-pill pf-pill--ok mt8">Respondida</span>}
        </div>
      </div>
      <Mensagens mensagens={mensagens} eu="cliente" />
      {erro && <Aviso>{erro}</Aviso>}
      <Escrever enviar={responder} rotulo={estado === 'resposta' ? 'Acrescentar' : 'Responder'}
        placeholder="Escreva a sua resposta…" ajuda={estado === 'resposta' ? 'O gabinete já recebeu a sua resposta.' : undefined} />
    </article>
  )
}
