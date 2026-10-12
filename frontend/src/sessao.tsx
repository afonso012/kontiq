import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, ErroApi, type Eu } from './api'

type Estado = { eu: Eu | null; carregado: boolean; definir: (eu: Eu | null) => void; recarregar: () => Promise<void> }

const Ctx = createContext<Estado>({ eu: null, carregado: false, definir: () => {}, recarregar: async () => {} })

export function SessaoProvider({ children }: { children: ReactNode }) {
  const [eu, setEu] = useState<Eu | null>(null)
  const [carregado, setCarregado] = useState(false)
  const recarregar = useCallback(async () => {
    try {
      setEu(await api.eu())
    } catch (e) {
      if (!(e instanceof ErroApi) || e.status === 401) setEu(null)
    } finally {
      setCarregado(true)
    }
  }, [])
  useEffect(() => { recarregar() }, [recarregar])
  return <Ctx.Provider value={{ eu, carregado, definir: setEu, recarregar }}>{children}</Ctx.Provider>
}

export const useSessao = () => useContext(Ctx)

/** Para onde vai quem tem esta sessão. */
export function destino(eu: Eu | null): string {
  if (!eu) return '/entrar'
  if (eu.tipo === 'portal') return '/portal/inicio'
  return eu.utilizador.email_confirmado ? '/painel' : '/confirmar-email'
}

/** Protege uma página: só entra quem tem o tipo de sessão certo. */
export function Exige({ tipo, children }: { tipo: 'gabinete' | 'gabinete-por-confirmar' | 'portal'; children: ReactNode }) {
  const { eu, carregado } = useSessao()
  const loc = useLocation()
  if (!carregado) return <div className="carregar" aria-busy="true" />
  if (!eu) return <Navigate to={tipo === 'portal' ? '/portal' : '/entrar'} replace state={{ de: loc.pathname }} />
  const certo =
    (tipo === 'portal' && eu.tipo === 'portal') ||
    (tipo === 'gabinete' && eu.tipo === 'gabinete' && eu.utilizador.email_confirmado) ||
    (tipo === 'gabinete-por-confirmar' && eu.tipo === 'gabinete' && !eu.utilizador.email_confirmado)
  return certo ? <>{children}</> : <Navigate to={destino(eu)} replace />
}

/** Páginas de entrada: quem já tem sessão segue em frente. */
export function SoSemSessao({ children }: { children: ReactNode }) {
  const { eu, carregado } = useSessao()
  if (!carregado) return <div className="carregar" aria-busy="true" />
  return eu ? <Navigate to={destino(eu)} replace /> : <>{children}</>
}
