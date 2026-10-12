import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, ErroApi } from '../api'
import { AsideEntrar, AuthLayout } from '../components/layout'
import { Aviso, BotaoSeta, BotoesSociais, Campo } from '../components/ui'
import { destino, useSessao } from '../sessao'

export default function Entrar() {
  const { eu, definir } = useSessao()
  const nav = useNavigate()
  const loc = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [manter, setManter] = useState(true)
  const [erro, setErro] = useState<string | null>(null)
  const [aCarregar, setACarregar] = useState(false)
  const reposta = (loc.state as { reposta?: boolean } | null)?.reposta

  async function submeter(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    if (!email.trim() || !password) return setErro('Escreva o email e a palavra-passe.')
    setACarregar(true)
    try {
      const eu = await api.entrar(email, password, manter)
      definir(eu)
      nav(destino(eu), { replace: true })
    } catch (err) {
      setErro(err instanceof ErroApi ? err.message : 'Não foi possível entrar.')
      setPassword('')
    } finally {
      setACarregar(false)
    }
  }

  return (
    <AuthLayout topo={<span className="muted14">Ainda não tem conta? <Link to="/registo">Criar conta</Link></span>} aside={<AsideEntrar />}>
      <form className="form" onSubmit={submeter} noValidate>
        {eu?.tipo === 'portal' && (
          <Aviso tipo="info">Tem sessão iniciada no portal como {eu.utilizador.nome}. Ao entrar como contabilista, essa sessão termina. <Link to="/portal/inicio">Voltar ao portal</Link></Aviso>
        )}
        <div>
          <h1 className="form__titulo">Bem-vindo de volta</h1>
          <p className="form__lead">Entre para ver as faturas dos seus clientes.</p>
        </div>
        {reposta && <Aviso tipo="info">Palavra-passe alterada. Já pode entrar.</Aviso>}
        <BotoesSociais />
        {erro && <Aviso>{erro}</Aviso>}
        <Campo rotulo="Email" type="email" autoComplete="email" placeholder="nome@gabinete.pt" value={email}
          onChange={(e) => setEmail(e.target.value)} autoFocus />
        <Campo rotulo="Palavra-passe" type="password" autoComplete="current-password" value={password}
          onChange={(e) => setPassword(e.target.value)}
          extra={<Link to="/recuperar" state={{ email }} className="link13">Esqueceu-se?</Link>} />
        <label className="check">
          <input type="checkbox" checked={manter} onChange={(e) => setManter(e.target.checked)} />
          Manter sessão iniciada neste computador
        </label>
        <BotaoSeta aCarregar={aCarregar}>Entrar</BotaoSeta>
        <p className="form__nota">É cliente de um gabinete? <Link to="/portal">Entre no portal do cliente</Link></p>
      </form>
    </AuthLayout>
  )
}
