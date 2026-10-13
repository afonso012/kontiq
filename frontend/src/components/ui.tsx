import { useEffect, useId, useRef, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

export function Seta() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 11 11 5M6 5h5v5" />
    </svg>
  )
}

export function Marca() {
  return <Link to="/" className="marca">Kontiq</Link>
}

/** Botão principal em pílula com a seta num círculo. */
export function BotaoSeta({ children, aCarregar, disabled, type = 'submit', onClick }: {
  children: ReactNode; aCarregar?: boolean; disabled?: boolean; type?: 'submit' | 'button'; onClick?: () => void
}) {
  return (
    <button type={type} onClick={onClick} className="pf-btn pf-btn--primary pf-btn--arrow botao-grande" disabled={disabled || aCarregar} aria-busy={aCarregar}>
      {aCarregar ? 'Um momento…' : children}
      <span className="pf-btn__arrow">{aCarregar ? <span className="roda" /> : <Seta />}</span>
    </button>
  )
}

type CampoProps = InputHTMLAttributes<HTMLInputElement> & {
  rotulo: ReactNode
  ajuda?: ReactNode
  erro?: string | null
  ok?: string | null
  extra?: ReactNode
  mono?: boolean
  depois?: ReactNode
}

export function Campo({ rotulo, ajuda, erro, ok, extra, mono, depois, ...input }: CampoProps) {
  const id = useId()
  const dica = erro || ok || ajuda
  return (
    <div className={`pf-field${erro ? ' is-error' : ''}`} style={{ minWidth: 0 }}>
      <span className="campo-topo">
        <label className="pf-field__label" htmlFor={id}>{rotulo}</label>
        {extra}
      </span>
      <input id={id} className={`pf-field__input${mono ? ' pf-mono' : ''}`} aria-invalid={!!erro}
        aria-describedby={dica ? `${id}-d` : undefined} {...input} />
      {depois}
      {dica && <span id={`${id}-d`} className="pf-field__hint" style={ok && !erro ? { color: 'var(--ok)' } : undefined}>{dica}</span>}
    </div>
  )
}

/** Seis caixas para o código. Aceita colar o código inteiro. */
export function CodigoInput({ valor, mudar, erro, aoCompletar }: {
  valor: string; mudar: (v: string) => void; erro?: boolean; aoCompletar?: (v: string) => void
}) {
  const refs = useRef<(HTMLInputElement | null)[]>([])
  const digitos = Array.from({ length: 6 }, (_, i) => valor[i] ?? '')
  useEffect(() => { refs.current[0]?.focus() }, [])
  const definir = (novo: string) => {
    const limpo = novo.replace(/\D/g, '').slice(0, 6)
    mudar(limpo)
    if (limpo.length === 6) aoCompletar?.(limpo)
    refs.current[Math.min(limpo.length, 5)]?.focus()
  }
  return (
    <div className="codigo" role="group" aria-label="Código de 6 dígitos">
      {digitos.map((d, i) => (
        <input key={i} ref={(el) => { refs.current[i] = el }} className={`codigo__dig${erro ? ' is-error' : ''}`}
          aria-label={`Dígito ${i + 1}`} inputMode="numeric" autoComplete={i === 0 ? 'one-time-code' : 'off'} maxLength={6} value={d}
          onChange={(e) => {
            const v = e.target.value.replace(/\D/g, '')
            if (v.length > 1) return definir(valor.slice(0, i) + v)
            definir(valor.slice(0, i) + v + valor.slice(i + 1))
          }}
          onKeyDown={(e) => {
            if (e.key === 'Backspace' && !d && i > 0) { e.preventDefault(); definir(valor.slice(0, i - 1)) }
            if (e.key === 'ArrowLeft' && i > 0) refs.current[i - 1]?.focus()
            if (e.key === 'ArrowRight' && i < 5) refs.current[i + 1]?.focus()
          }}
          onPaste={(e) => { e.preventDefault(); definir(e.clipboardData.getData('text')) }}
        />
      ))}
    </div>
  )
}

export function IndicadorForca({ forca, texto }: { forca: number; texto: string }) {
  const cor = forca <= 1 ? 'var(--danger)' : forca === 2 ? 'var(--warn)' : 'var(--ok)'
  return (
    <span className="forca" aria-hidden="true" title={texto}>
      {[0, 1, 2, 3].map((i) => <span key={i} style={{ background: i < forca ? cor : 'var(--line)' }} />)}
    </span>
  )
}

/** Google e Microsoft: visíveis, mas só ficam ativos quando houver domínio e app registada. */
export function BotoesSociais() {
  return (
    <>
      <div className="sociais">
        <button type="button" className="pf-btn" disabled title="Disponível em breve">
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24"><path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.4h6.5a5.5 5.5 0 0 1-2.4 3.6v3h3.9c2.3-2.1 3.5-5.2 3.5-8.7z" /><path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.3v3.1A12 12 0 0 0 12 24z" /><path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6H1.3a12 12 0 0 0 0 10.8l4-3.1z" /><path fill="#EA4335" d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.3 6.6l4 3.1c.9-2.9 3.6-4.9 6.7-4.9z" /></svg>
          Google
        </button>
        <button type="button" className="pf-btn" disabled title="Disponível em breve">
          <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24"><path fill="#F25022" d="M1 1h10.5v10.5H1z" /><path fill="#7FBA00" d="M12.5 1H23v10.5H12.5z" /><path fill="#00A4EF" d="M1 12.5h10.5V23H1z" /><path fill="#FFB900" d="M12.5 12.5H23V23H12.5z" /></svg>
          Microsoft
        </button>
      </div>
      <div className="divisor">ou com email</div>
    </>
  )
}

export function Passos({ atual, total = 3 }: { atual: number; total?: number }) {
  return (
    <div className="passos" aria-label={`Passo ${atual} de ${total}`}>
      {Array.from({ length: total }, (_, i) => <span key={i} className={i < atual ? 'on' : ''} />)}
    </div>
  )
}

export function Aviso({ children, tipo = 'bad' }: { children: ReactNode; tipo?: 'bad' | 'warn' | 'info' }) {
  const tag = { bad: 'Erro', warn: 'Aviso', info: 'Info' }[tipo]
  return (
    <div className={`pf-alert pf-alert--${tipo}`} role={tipo === 'bad' ? 'alert' : 'status'}>
      <span className="pf-alert__tag">{tag}</span><div>{children}</div>
    </div>
  )
}

/** Contagem decrescente em segundos (para "reenviar em 0:42"). */
export function useContagem(inicial: number) {
  const [s, setS] = useState(inicial)
  useEffect(() => {
    if (s <= 0) return
    const t = setTimeout(() => setS(s - 1), 1000)
    return () => clearTimeout(t)
  }, [s])
  return [s, setS] as const
}

export const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
