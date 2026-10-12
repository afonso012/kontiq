import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, ErroApi } from '../api'
import { AsideEntrar, AuthLayout } from '../components/layout'
import { Aviso, BotaoSeta, Campo, CodigoInput, IndicadorForca, mmss, useContagem } from '../components/ui'
import { destino, useSessao } from '../sessao'

export default function Recuperar() {
  const { definir } = useSessao()
  const nav = useNavigate()
  const loc = useLocation()
  const [passo, setPasso] = useState<1 | 2>(1)
  const [email, setEmail] = useState((loc.state as { email?: string } | null)?.email ?? '')
  const [codigo, setCodigo] = useState('')
  const [password, setPassword] = useState('')
  const [erro, setErro] = useState<{ campo: string | null; msg: string } | null>(null)
  const [aCarregar, setACarregar] = useState(false)
  const [forca, setForca] = useState<{ forca: number; problema: string | null } | null>(null)
  const [espera, setEspera] = useContagem(0)

  useEffect(() => {
    if (!password) return setForca(null)
    const t = setTimeout(() => api.forca(password, email, '').then(setForca).catch(() => {}), 250)
    return () => clearTimeout(t)
  }, [password, email])

  async function pedir(e?: FormEvent) {
    e?.preventDefault()
    setErro(null)
    if (!/^\S+@\S+\.\S{2,}$/.test(email.trim())) return setErro({ campo: 'email', msg: 'Este email não parece válido.' })
    setACarregar(true)
    try {
      await api.pedirReposicao(email)
      setPasso(2); setEspera(60); setCodigo('')
    } catch (err) {
      setErro({ campo: null, msg: err instanceof ErroApi ? err.message : 'Não foi possível enviar o código.' })
    } finally { setACarregar(false) }
  }

  async function repor(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    if (codigo.length !== 6) return setErro({ campo: 'codigo', msg: 'Escreva os 6 dígitos do código.' })
    if (forca?.problema || !password) return setErro({ campo: 'password', msg: forca?.problema || 'Escolha uma palavra-passe nova.' })
    setACarregar(true)
    try {
      const eu = await api.repor(email, codigo, password)
      definir(eu)
      nav(destino(eu), { replace: true })
    } catch (err) {
      const campo = err instanceof ErroApi ? err.campo : null
      setErro({ campo, msg: err instanceof ErroApi ? err.message : 'Não foi possível repor.' })
      if (campo === 'codigo') setCodigo('')
    } finally { setACarregar(false) }
  }

  return (
    <AuthLayout topo={<Link to="/entrar" className="muted14">← Voltar a entrar</Link>} aside={<AsideEntrar />}>
      {passo === 1 ? (
        <form className="form" onSubmit={pedir} noValidate>
          <div>
            <h1 className="form__titulo">Repor a palavra-passe</h1>
            <p className="form__lead">Diga-nos o email da conta. Enviamos um código para criar uma palavra-passe nova.</p>
          </div>
          {erro && !erro.campo && <Aviso>{erro.msg}</Aviso>}
          <Campo rotulo="Email" type="email" autoComplete="email" value={email} autoFocus
            erro={erro?.campo === 'email' ? erro.msg : null} onChange={(e) => setEmail(e.target.value)} />
          <BotaoSeta aCarregar={aCarregar}>Enviar código</BotaoSeta>
        </form>
      ) : (
        <form className="form" onSubmit={repor} noValidate>
          <div>
            <h1 className="form__titulo">Verifique o seu email</h1>
            <p className="form__lead">Se <b className="ink">{email}</b> tiver conta, recebe um código dentro de instantes.</p>
          </div>
          {erro && (erro.campo === 'codigo' || !erro.campo) && <Aviso>{erro.msg}</Aviso>}
          <div className="pf-field">
            <span className="pf-field__label">Código</span>
            <CodigoInput valor={codigo} mudar={setCodigo} erro={erro?.campo === 'codigo'} />
          </div>
          <Campo rotulo="Palavra-passe nova" type="password" autoComplete="new-password" value={password}
            erro={erro?.campo === 'password' ? erro.msg : null}
            ajuda={!password ? 'Pelo menos 12 caracteres.' : forca?.problema ?? ['Fraca', 'Fraca', 'Razoável', 'Boa', 'Muito boa'][forca?.forca ?? 0]}
            depois={password ? <IndicadorForca forca={forca?.problema ? Math.min(1, forca.forca) : forca?.forca ?? 0} texto="Força" /> : null}
            onChange={(e) => setPassword(e.target.value)} />
          <BotaoSeta aCarregar={aCarregar}>Guardar e entrar</BotaoSeta>
          <div className="muted14 centro">
            {espera > 0 ? <span>Reenviar em <span className="pf-mono">{mmss(espera)}</span></span>
              : <button type="button" className="link-botao" onClick={() => pedir()}>Reenviar código</button>}
            {' · '}<button type="button" className="link-botao" onClick={() => { setPasso(1); setErro(null) }}>Outro email</button>
          </div>
        </form>
      )}
    </AuthLayout>
  )
}
