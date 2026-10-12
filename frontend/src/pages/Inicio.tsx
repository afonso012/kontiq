import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type ResumoPainel, type ResumoPortal } from '../api'
import { Marca } from '../components/ui'
import { useSessao } from '../sessao'

const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
const mesPorExtenso = (iso: string) => { const d = new Date(iso); return `${MESES[d.getMonth()]} de ${d.getFullYear()}` }

function useSair() {
  const { definir } = useSessao()
  const nav = useNavigate()
  return async (para: string) => {
    await api.sair().catch(() => {})
    definir(null)
    nav(para, { replace: true })
  }
}

/** Painel provisório do gabinete: prova que a sessão e o isolamento funcionam. */
export function Painel() {
  const [r, setR] = useState<ResumoPainel | null>(null)
  const sair = useSair()
  useEffect(() => { api.resumoPainel().then(setR).catch(() => {}) }, [])
  return (
    <div className="app">
      <header className="app__topo">
        <Marca />
        <div className="app__conta">
          <span className="muted14">{r?.utilizador.nome}</span>
          <button className="pf-btn pf-btn--sm" onClick={() => sair('/entrar')}>Sair</button>
        </div>
      </header>
      <main className="app__conteudo">
        <span className="muted14">{r?.gabinete.nome}</span>
        <h1 className="app__titulo">Olá, {r?.utilizador.nome.split(' ')[0] ?? '…'}</h1>
        <div className="stats">
          <div className="pf-stat pf-stat--brand"><div className="pf-stat__label">Empresas-cliente</div><div className="pf-stat__value">{r?.empresas ?? '–'}</div><div className="pf-stat__sub">no gabinete</div></div>
          <div className="pf-stat"><div className="pf-stat__label">Faturas de {r ? mesPorExtenso(r.mes) : '…'}</div><div className="pf-stat__value">{r?.faturas_mes ?? '–'}</div><div className="pf-stat__sub">recebidas este mês</div></div>
          <div className="pf-stat"><div className="pf-stat__label">Equipa</div><div className="pf-stat__value">{r?.membros ?? '–'}</div><div className="pf-stat__sub">com acesso</div></div>
        </div>
        <div className="pf-card vazio pf-glow">
          <span className="pf-pill pf-pill--new">Em construção</span>
          <h2>O painel de clientes vem a seguir</h2>
          <p className="muted15">A conta e a sessão já funcionam. O próximo passo é a lista de empresas com o estado do mês.</p>
        </div>
      </main>
    </div>
  )
}

/** Início provisório do portal do cliente. */
export function PortalInicio() {
  const [r, setR] = useState<ResumoPortal | null>(null)
  const sair = useSair()
  useEffect(() => { api.resumoPortal().then(setR).catch(() => {}) }, [])
  return (
    <div className="portal">
      <header className="portal__topo pf-glow">
        <div className="portal__gabinete">
          <span className="avatar" aria-hidden="true">{r?.gabinete.nome.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase() ?? '…'}</span>
          <div><div className="forte15">{r?.gabinete.nome ?? '…'}</div><div className="muted12">Portal de faturas</div></div>
        </div>
        <h1 className="portal__titulo">Olá, {r?.utilizador.nome.split(' ')[0] ?? '…'}</h1>
        <p className="muted15">{r?.empresa.nome}</p>
      </header>
      <div className="portal__form">
        <div className="linha forte15"><span>Faturas de {r ? mesPorExtenso(r.mes) : '…'}</span><span className="pf-mono">{r?.faturas_mes ?? '–'}</span></div>
        <button className="pf-btn pf-btn--primary botao-grande" disabled title="Em construção" style={{ justifyContent: 'center' }}>Tirar foto a uma fatura</button>
        <p className="muted13 centro" style={{ margin: 0 }}>O envio de faturas pelo portal vem a seguir.</p>
        <button className="pf-btn" onClick={() => sair('/portal')} style={{ justifyContent: 'center' }}>Sair</button>
      </div>
    </div>
  )
}
