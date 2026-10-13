import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useSessao } from '../sessao'

const I = {
  painel: <><rect x="3" y="3" width="7" height="9" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" /><rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="16" width="7" height="5" rx="2" /></>,
  empresas: <><path d="M4 21V7l8-4 8 4v14" /><path d="M9 21v-6h6v6" /></>,
  faturas: <><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 13h7M9 17h5" /></>,
  pedidos: <path d="M4 4h16v12H8l-4 4z" />,
  exportar: <><path d="M12 3v12m0 0-4-4m4 4 4-4" /><path d="M4 17v3h16v-3" /></>,
  equipa: <><circle cx="9" cy="8" r="3.2" /><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" /><path d="M16 4.6a3.2 3.2 0 0 1 0 6.3M18 14.8c1.9.6 3 2.6 3 5.2" /></>,
  sair: <><path d="M15 4h4v16h-4" /><path d="M10 8l-4 4 4 4M6 12h10" /></>,
}

export function Icone({ nome }: { nome: keyof typeof I }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{I[nome]}</svg>
}

const iniciais = (nome: string) => nome.split(/\s+/).filter(Boolean).map((p) => p[0]).slice(0, 2).join('').toUpperCase()

/** Estrutura das áreas do gabinete: menu à esquerda, conteúdo num cartão à direita. */
export function AppLayout({ children, glow }: { children: ReactNode; glow?: boolean }) {
  const { eu, definir } = useSessao()
  const nav = useNavigate()
  const [menu, setMenu] = useState(false)
  async function sair() {
    await api.sair().catch(() => {})
    definir(null)
    nav('/entrar', { replace: true })
  }
  const emBreve = (nome: keyof typeof I, texto: string) => (
    <span className="nav__item is-off" aria-disabled="true" title="Em breve"><Icone nome={nome} />{texto}<span className="nav__breve">em breve</span></span>
  )
  return (
    <div className="shell">
      <nav className={`nav${menu ? ' is-aberto' : ''}`} aria-label="Navegação principal">
        <div className="nav__topo">
          <span className="marca">Plataforma de Faturas</span>
          <button type="button" className="pf-btn pf-btn--sm nav__menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>Menu</button>
        </div>
        <div className="nav__lista">
          <NavLink to="/painel" className={({ isActive }) => `nav__item${isActive ? ' on' : ''}`}><Icone nome="painel" />Painel</NavLink>
          {emBreve('faturas', 'Faturas')}
          {emBreve('pedidos', 'Pedidos')}
          <NavLink to="/exportacoes" className={({ isActive }) => `nav__item${isActive ? ' on' : ''}`}><Icone nome="exportar" />Exportações</NavLink>
          <NavLink to="/equipa" className={({ isActive }) => `nav__item${isActive ? ' on' : ''}`}><Icone nome="equipa" />Equipa</NavLink>
          <div className="nav__espaco" />
          <div className="nav__conta">
            <span className="avatar" aria-hidden="true">{iniciais(eu?.utilizador.nome ?? '')}</span>
            <div className="nav__quem">
              <div className="forte15">{eu?.utilizador.nome}</div>
              <div className="muted13 cortar">{eu?.gabinete?.nome}</div>
            </div>
            <button type="button" className="pf-btn pf-btn--ghost nav__sair" aria-label="Sair" title="Sair" onClick={sair}><Icone nome="sair" /></button>
          </div>
        </div>
      </nav>
      <main className="shell__main">
        <div className={`shell__cartao${glow ? ' pf-glow' : ''}`}>{children}</div>
      </main>
    </div>
  )
}

/** Mensagem curta no canto, que desaparece sozinha. */
export function useAviso() {
  const [aviso, setAviso] = useState<{ texto: string; tipo: 'ok' | 'bad' } | null>(null)
  useEffect(() => {
    if (!aviso) return
    const t = setTimeout(() => setAviso(null), 5000)
    return () => clearTimeout(t)
  }, [aviso])
  const elemento = aviso ? (
    <div className={`toast toast--${aviso.tipo}`} role="status">{aviso.texto}</div>
  ) : <div role="status" className="sr-only" />
  return { mostrar: (texto: string, tipo: 'ok' | 'bad' = 'ok') => setAviso({ texto, tipo }), elemento }
}

/** Painel lateral (diálogo). Fecha com Esc ou clicando fora. */
export function Gaveta({ titulo, subtitulo, aberto, fechar, children, rodape }: {
  titulo: string; subtitulo?: string; aberto: boolean; fechar: () => void; children: ReactNode; rodape: ReactNode
}) {
  const ref = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!aberto) return
    const antes = document.activeElement as HTMLElement | null
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') fechar() }
    document.addEventListener('keydown', tecla)
    document.body.style.overflow = 'hidden'
    setTimeout(() => ref.current?.querySelector<HTMLElement>('input, button')?.focus(), 30)
    return () => { document.removeEventListener('keydown', tecla); document.body.style.overflow = ''; antes?.focus() }
  }, [aberto, fechar])
  if (!aberto) return null
  return (
    <div className="gaveta" onMouseDown={(e) => { if (e.target === e.currentTarget) fechar() }}>
      <section className="gaveta__painel" role="dialog" aria-modal="true" aria-labelledby="gaveta-titulo" ref={ref}>
        <header className="gaveta__topo">
          <div>
            <h2 id="gaveta-titulo" className="gaveta__titulo">{titulo}</h2>
            {subtitulo && <p className="muted15" style={{ margin: '8px 0 0' }}>{subtitulo}</p>}
          </div>
          <button type="button" className="pf-btn pf-btn--ghost gaveta__fechar" aria-label="Fechar" onClick={fechar}>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </header>
        <div className="gaveta__corpo">{children}</div>
        <footer className="gaveta__rodape">{rodape}</footer>
      </section>
    </div>
  )
}
