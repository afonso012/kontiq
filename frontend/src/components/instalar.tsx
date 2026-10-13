import { useEffect, useState } from 'react'

type PedidoInstalar = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> }
const CHAVE = 'kontiq-instalar-fechado'

function fechadoAntes() {
  try { return localStorage.getItem(CHAVE) === '1' } catch { return false }
}

/** Convite para instalar o portal no ecrã principal do telemóvel (Android: botão; iPhone: instruções). */
export function ConviteInstalar() {
  const [pedido, setPedido] = useState<PedidoInstalar | null>(null)
  const [fechado, setFechado] = useState(fechadoAntes)
  const instalada = typeof window !== 'undefined' && (window.matchMedia?.('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true)
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : ''
  const iphone = /iPhone|iPad|iPod/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua)
  const telemovel = /Android|iPhone|iPad|iPod/.test(ua)

  useEffect(() => {
    const f = (e: Event) => { e.preventDefault(); setPedido(e as PedidoInstalar) }
    window.addEventListener('beforeinstallprompt', f)
    const ok = () => { setPedido(null); setFechado(true) }
    window.addEventListener('appinstalled', ok)
    return () => { window.removeEventListener('beforeinstallprompt', f); window.removeEventListener('appinstalled', ok) }
  }, [])

  function fechar() {
    setFechado(true)
    try { localStorage.setItem(CHAVE, '1') } catch { /* sem armazenamento: só nesta visita */ }
  }
  async function instalar() {
    if (!pedido) return
    await pedido.prompt()
    const r = await pedido.userChoice.catch(() => ({ outcome: 'dismissed' }))
    if (r.outcome === 'accepted') fechar()
    setPedido(null)
  }

  if (instalada || fechado || !telemovel || (!pedido && !iphone)) return null
  return (
    <div className="instalar pf-glass" role="region" aria-label="Instalar a aplicação">
      <img src="/icones/icone-192.png" alt="" width={44} height={44} className="instalar__icone" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="forte15">Tenha a Kontiq no ecrã principal</div>
        {pedido
          ? <div className="muted13">Abre num toque, sem App Store, direto para tirar a foto.</div>
          : <div className="muted13">Toque em <b>Partilhar</b> <span aria-hidden="true">⬆︎</span> e depois em <b>Adicionar ao ecrã principal</b>.</div>}
      </div>
      {pedido && <button type="button" className="pf-btn pf-btn--sm pf-btn--primary" onClick={instalar}>Instalar</button>}
      <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost instalar__fechar" aria-label="Agora não" onClick={fechar}>×</button>
    </div>
  )
}
