import type { ReactNode } from 'react'
import { Marca } from './ui'

/** Ecrã de entrada: formulário à esquerda, painel de marca à direita (por baixo no telemóvel). */
export function AuthLayout({ topo, children, aside }: { topo?: ReactNode; children: ReactNode; aside: ReactNode }) {
  return (
    <div className="auth">
      <main className="auth__main">
        <div className="auth__topo"><Marca />{topo}</div>
        <div className="auth__centro">{children}</div>
        <div className="auth__rodape">
          <span>Dados alojados na União Europeia</span>
          <span className="auth__links"><a href="#privacidade">Privacidade</a><a href="#termos">Termos</a><a href="mailto:ajuda@faturas.local">Ajuda</a></span>
        </div>
      </main>
      <aside className="auth__aside pf-glow">{aside}</aside>
    </div>
  )
}

export function AsideEntrar() {
  return (
    <>
      <div>
        <span className="pf-pill pf-pill--new">Novo</span>
        <span className="aside__sub">Leitura automática do código QR da AT</span>
        <h2 className="aside__titulo">As faturas dos clientes, <span className="pf-hl">conferidas</span> sozinhas</h2>
        <p className="aside__lead">Recolha, leitura e classificação SNC das faturas de compras, prontas a entrar no programa de contabilidade.</p>
      </div>
      <div className="flutuantes" aria-hidden="true">
        <div className="pf-glass flut flut--1">
          <div className="linha"><span className="pf-mono muted12">FT 2026/0457</span><span className="pf-src pf-src--qr">QR</span></div>
          <div className="flut__nome">Papelaria e Escritório Sado, Lda</div>
          <div className="linha mt14"><span className="muted13">6222 · Material de escritório</span><span className="pf-mono" style={{ whiteSpace: 'nowrap', fontSize: 15 }}>95,82 €</span></div>
        </div>
        <div className="pf-glass flut flut--2">
          <div className="muted12">Outubro · Restaurante O Faroleiro</div>
          <div className="linha mt10"><span className="pf-mono grande">14 / 14</span><span className="pf-pill pf-pill--ok">Completa</span></div>
          <div className="barra mt14"><span style={{ width: '100%' }} /></div>
        </div>
        <div className="pf-glass flut flut--3">
          <span className="pf-alert__tag erro">Erro</span>
          <span className="muted13 ink">Possível duplicado de <span className="pf-mono">FT 2026/8120</span></span>
        </div>
      </div>
    </>
  )
}

export function AsideRegisto() {
  const passos = [
    ['O cliente envia', 'Foto no portal, email próprio da empresa ou PDF. Sem instalar nada.'],
    ['Lida e validada', 'Código QR da AT ou IA, NIF, totais, duplicados e conta SNC sugerida.'],
    ['Exportada', 'Para o programa que o gabinete já usa, mês a mês.'],
  ]
  return (
    <>
      <h2 className="aside__titulo">Do telemóvel do cliente ao <span className="pf-hl">programa</span> de contabilidade</h2>
      <ol className="passos-produto">
        {passos.map(([t, d], i) => (
          <li key={t} className="pf-glass" style={{ marginLeft: i * 40 }}>
            <span className={`num${i === 1 ? ' num--brand' : ''}`}>{i + 1}</span>
            <div><strong>{t}</strong><p>{d}</p></div>
          </li>
        ))}
      </ol>
    </>
  )
}

export function AsideGabinete({ nome, programa }: { nome: string; programa: string }) {
  return (
    <div className="aside__centrado">
      <span className="muted13">Assim o veem os seus clientes</span>
      <div className="pf-glass preview-portal" aria-hidden="true">
        <div className="preview-portal__topo">
          <div className="muted12">Portal de faturas de</div>
          <div className="preview-portal__nome">{nome.trim() || 'O seu gabinete'}</div>
        </div>
        <div className="preview-portal__corpo">
          <div>Olá, <b>Sr. Joaquim</b></div>
          <div className="linha"><span>Outubro · faturas enviadas</span><span className="pf-mono">11</span></div>
          <div className="barra"><span style={{ width: '78%' }} /></div>
          <div className="pf-alert pf-alert--warn compacto"><span className="pf-alert__tag">Falta</span><span>Fatura da EDP de setembro</span></div>
          <span className="pf-btn pf-btn--primary" style={{ justifyContent: 'center', height: 46 }}>Tirar foto a uma fatura</span>
        </div>
      </div>
      <span className="muted13">Exportação preparada para <b className="ink">{programa}</b></span>
    </div>
  )
}
