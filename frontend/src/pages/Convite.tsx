import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ErroApi, type ConviteEquipa } from '../api'
import { AsideRegisto, AuthLayout } from '../components/layout'
import { Aviso, BotaoSeta, Campo, IndicadorForca } from '../components/ui'
import { destino, useSessao } from '../sessao'

/** Página pública do link do email: criar conta (ou confirmar a existente) e entrar no gabinete. */
export default function Convite() {
  const { token = '' } = useParams()
  const { definir } = useSessao()
  const nav = useNavigate()
  const [c, setC] = useState<ConviteEquipa | null>(null)
  const [falha, setFalha] = useState<string | null>(null)
  const [nome, setNome] = useState('')
  const [password, setPassword] = useState('')
  const [erro, setErro] = useState<{ campo: string | null; msg: string } | null>(null)
  const [aCarregar, setACarregar] = useState(false)
  const [forca, setForca] = useState<{ forca: number; problema: string | null } | null>(null)

  useEffect(() => {
    api.verConvite(token).then(setC).catch((e) => setFalha(e instanceof ErroApi ? e.message : 'Não foi possível abrir o convite.'))
  }, [token])

  const novo = c ? !c.conta_existe : false
  useEffect(() => {
    if (!novo || !password) return setForca(null)
    const t = setTimeout(() => api.forca(password, c?.email ?? '', nome).then(setForca).catch(() => {}), 250)
    return () => clearTimeout(t)
  }, [password, nome, novo, c])

  async function aceitar(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    if (novo && nome.trim().length < 2) return setErro({ campo: 'nome', msg: 'Escreva o seu nome.' })
    if (!password) return setErro({ campo: 'password', msg: novo ? 'Escolha uma palavra-passe.' : 'Escreva a sua palavra-passe.' })
    setACarregar(true)
    try {
      await api.aceitarConvite(token, nome.trim(), password)
      const eu = await api.eu()
      definir(eu)
      nav(destino(eu), { replace: true })
    } catch (err) {
      setErro({ campo: err instanceof ErroApi ? err.campo : null, msg: err instanceof ErroApi ? err.message : 'Não foi possível aceitar o convite.' })
    } finally { setACarregar(false) }
  }

  return (
    <AuthLayout topo={<Link to="/entrar" className="muted14">Já tem conta? Entrar</Link>} aside={<AsideRegisto />}>
      {falha ? (
        <div className="form">
          <h1 className="form__titulo">Convite indisponível</h1>
          <Aviso tipo="warn">{falha}</Aviso>
          <Link to="/entrar" className="pf-btn pf-btn--primary" style={{ justifyContent: 'center' }}>Ir para a entrada</Link>
        </div>
      ) : !c ? <div className="carregar" aria-busy="true" /> : (
        <form className="form" onSubmit={aceitar} noValidate>
          <div>
            <span className="pf-pill pf-pill--new">Convite</span>
            <h1 className="form__titulo" style={{ marginTop: 12 }}>Junte-se à <span className="pf-hl">equipa</span></h1>
            <p className="form__lead">
              {c.convidado_por ? <><b className="ink">{c.convidado_por}</b> enviou-lhe um convite</> : 'Tem um convite'} para o gabinete <b className="ink">{c.gabinete}</b> como <b className="ink">{c.papel.toLowerCase()}</b>.
              {novo ? ' Crie a sua conta para começar.' : ' Já tem conta: confirme a palavra-passe para entrar no gabinete.'}
            </p>
          </div>
          {erro && !erro.campo && <Aviso>{erro.msg}</Aviso>}
          <Campo rotulo="Email" type="email" value={c.email} readOnly disabled ajuda="O convite é para este email." />
          {novo && (
            <Campo rotulo="Nome" autoComplete="name" value={nome} autoFocus
              erro={erro?.campo === 'nome' ? erro.msg : null} onChange={(e) => setNome(e.target.value)} />
          )}
          <Campo rotulo={novo ? 'Palavra-passe' : 'A sua palavra-passe'} type="password" autoComplete={novo ? 'new-password' : 'current-password'}
            value={password} autoFocus={!novo}
            erro={erro?.campo === 'password' ? erro.msg : null}
            ajuda={novo ? (!password ? 'Pelo menos 12 caracteres.' : forca?.problema ?? ['Fraca', 'Fraca', 'Razoável', 'Boa', 'Muito boa'][forca?.forca ?? 0]) : undefined}
            depois={novo && password ? <IndicadorForca forca={forca?.problema ? Math.min(1, forca.forca) : forca?.forca ?? 0} texto="Força" /> : null}
            onChange={(e) => { setPassword(e.target.value); if (erro?.campo === 'password') setErro(null) }} />
          <BotaoSeta aCarregar={aCarregar}>{novo ? 'Criar conta e entrar' : 'Entrar no gabinete'}</BotaoSeta>
          {!novo && <div className="muted14 centro"><Link to="/recuperar" state={{ email: c.email }}>Esqueceu-se da palavra-passe?</Link></div>}
        </form>
      )}
    </AuthLayout>
  )
}
