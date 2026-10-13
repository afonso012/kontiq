import { useEffect, useRef, useState } from 'react'
import type { MensagemDuvida } from '../api'
import { quando } from '../util'

/** Mensagens entre o gabinete e o cliente. `eu` é o lado de quem está a ver (fica à direita). */
export function Mensagens({ mensagens, eu }: { mensagens: MensagemDuvida[]; eu: 'gabinete' | 'cliente' }) {
  const fim = useRef<HTMLDivElement>(null)
  useEffect(() => { fim.current?.scrollIntoView({ block: 'nearest' }) }, [mensagens.length])
  if (!mensagens.length) return null
  return (
    <div className="conversa__lista">
      {mensagens.map((m) => (
        <div key={m.id} className={`balao${m.lado === eu ? ' balao--eu' : ''}`}>
          <div className="balao__texto">{m.texto}</div>
          <div className="balao__quem">{m.lado === eu ? 'Você' : (m.autor ?? (m.lado === 'cliente' ? 'Cliente' : 'Gabinete'))} · {quando(m.em)}</div>
        </div>
      ))}
      <div ref={fim} />
    </div>
  )
}

/** Caixa de texto com botão de enviar. Ctrl/⌘+Enter envia. */
export function Escrever({ enviar, rotulo, placeholder, ajuda, autoFocus }: {
  enviar: (texto: string) => Promise<boolean>; rotulo: string; placeholder: string; ajuda?: string; autoFocus?: boolean
}) {
  const [texto, setTexto] = useState('')
  const [aEnviar, setAEnviar] = useState(false)
  async function ir() {
    if (!texto.trim() || aEnviar) return
    setAEnviar(true)
    const ok = await enviar(texto.trim()).finally(() => setAEnviar(false))
    if (ok) setTexto('')
  }
  return (
    <div className="conversa__escrever">
      <textarea className="pf-field__input conversa__texto" rows={2} maxLength={1000} placeholder={placeholder} value={texto} autoFocus={autoFocus}
        aria-label={placeholder} onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); ir() } }} />
      <div className="conversa__acoes">
        {ajuda ? <span className="muted13">{ajuda}</span> : <span />}
        <button type="button" className="pf-btn pf-btn--primary pf-btn--sm" disabled={!texto.trim() || aEnviar} onClick={ir}>{aEnviar ? 'A enviar…' : rotulo}</button>
      </div>
    </div>
  )
}
