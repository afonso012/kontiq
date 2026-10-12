import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ErroApi } from '../api'
import { AsideGabinete, AsideRegisto, AuthLayout } from '../components/layout'
import { Aviso, BotaoSeta, BotoesSociais, Campo, IndicadorForca, Passos } from '../components/ui'
import { useSessao } from '../sessao'
import { nifValido } from '../util'

const PROGRAMAS = [['toconline', 'TOConline'], ['primavera', 'Primavera'], ['phc', 'PHC'], ['sage', 'Sage'], ['outro', 'Outro']] as const
const DIMENSOES = [['ate_20', 'Até 20'], ['21_50', '21–50'], ['51_150', '51–150'], ['mais_150', 'Mais de 150']] as const

type Erros = Record<string, string>

export default function Registo() {
  const { definir } = useSessao()
  const nav = useNavigate()
  const [passo, setPasso] = useState<1 | 2>(1)
  const [conta, setConta] = useState({ nome: '', email: '', password: '', aceito: false })
  const [gab, setGab] = useState({ nif: '', telefone: '', nome: '', programa: 'toconline', dimensao: '21_50' })
  const [erros, setErros] = useState<Erros>({})
  const [geral, setGeral] = useState<string | null>(null)
  const [aCarregar, setACarregar] = useState(false)
  const [forca, setForca] = useState<{ forca: number; problema: string | null } | null>(null)

  // Força da palavra-passe, perguntada ao servidor (mesmas regras que o registo).
  useEffect(() => {
    if (!conta.password) return setForca(null)
    const t = setTimeout(() => api.forca(conta.password, conta.email, conta.nome).then(setForca).catch(() => {}), 250)
    return () => clearTimeout(t)
  }, [conta.password, conta.email, conta.nome])

  function tratar(err: unknown) {
    if (err instanceof ErroApi && err.campo) {
      setErros({ [err.campo]: err.message })
      if (['nome', 'email', 'password'].includes(err.campo)) setPasso(1)
    } else setGeral(err instanceof ErroApi ? err.message : 'Não foi possível criar a conta.')
  }

  async function continuar(e: FormEvent) {
    e.preventDefault()
    setErros({}); setGeral(null)
    const novos: Erros = {}
    if (conta.nome.trim().length < 2) novos.nome = 'Escreva o seu nome.'
    if (!/^\S+@\S+\.\S{2,}$/.test(conta.email.trim())) novos.email = 'Este email não parece válido.'
    if (!conta.password) novos.password = 'Escolha uma palavra-passe.'
    else {
      // Pergunta de novo: o indicador pode ainda não ter apanhado a última alteração.
      const atual = await api.forca(conta.password, conta.email, conta.nome).catch(() => null)
      if (atual) setForca(atual)
      if (atual?.problema) novos.password = atual.problema
    }
    if (!conta.aceito) novos.aceito = 'Precisa de aceitar os termos para continuar.'
    if (Object.keys(novos).length) return setErros(novos)
    setACarregar(true)
    try {
      await api.validarConta(conta.nome, conta.email, conta.password)
      setPasso(2)
      window.scrollTo(0, 0)
    } catch (err) { tratar(err) } finally { setACarregar(false) }
  }

  async function criar(e: FormEvent) {
    e.preventDefault()
    setErros({}); setGeral(null)
    const nif = gab.nif.replace(/\s/g, '')
    const novos: Erros = {}
    if (!nifValido(nif)) novos.nif = 'NIF inválido: confirme os 9 dígitos.'
    if (gab.nome.trim().length < 2) novos.nome_gabinete = 'Escreva o nome do gabinete.'
    if (Object.keys(novos).length) return setErros(novos)
    setACarregar(true)
    try {
      const eu = await api.registar({
        nome: conta.nome, email: conta.email, password: conta.password,
        gabinete: { nome: gab.nome, nif, telefone: gab.telefone || null, programa: gab.programa, dimensao: gab.dimensao },
      })
      definir(eu)
      nav('/confirmar-email', { replace: true })
    } catch (err) { tratar(err) } finally { setACarregar(false) }
  }

  const nifLimpo = gab.nif.replace(/\s/g, '')
  const nomePrograma = PROGRAMAS.find(([v]) => v === gab.programa)?.[1] ?? ''

  if (passo === 1) {
    return (
      <AuthLayout topo={<span className="muted14">Já tem conta? <Link to="/entrar">Entrar</Link></span>} aside={<AsideRegisto />}>
        <form className="form" onSubmit={continuar} noValidate>
          <Passos atual={1} />
          <div>
            <span className="muted13">Passo 1 de 3 · A sua conta</span>
            <h1 className="form__titulo mt8">Criar conta do gabinete</h1>
            <p className="form__lead">Depois convida os colaboradores e as empresas-cliente.</p>
          </div>
          <BotoesSociais />
          {geral && <Aviso>{geral}</Aviso>}
          <Campo rotulo="Nome" autoComplete="name" value={conta.nome} erro={erros.nome} autoFocus
            onChange={(e) => { setConta({ ...conta, nome: e.target.value }); setErros({ ...erros, nome: '' }) }} />
          <Campo rotulo="Email profissional" type="email" autoComplete="email" value={conta.email} erro={erros.email}
            onChange={(e) => { setConta({ ...conta, email: e.target.value }); setErros({ ...erros, email: '' }) }} />
          <Campo rotulo="Palavra-passe" type="password" autoComplete="new-password" value={conta.password}
            erro={erros.password}
            ajuda={!conta.password ? 'Pelo menos 12 caracteres.' : forca?.problema ?? ['Fraca', 'Fraca', 'Razoável', 'Boa', 'Muito boa'][forca?.forca ?? 0]}
            depois={conta.password ? <IndicadorForca forca={forca?.problema ? Math.min(1, forca.forca) : forca?.forca ?? 0} texto="Força da palavra-passe" /> : null}
            onChange={(e) => { setConta({ ...conta, password: e.target.value }); setErros({ ...erros, password: '' }) }} />
          <label className={`check${erros.aceito ? ' is-error' : ''}`}>
            <input type="checkbox" checked={conta.aceito} onChange={(e) => { setConta({ ...conta, aceito: e.target.checked }); setErros({ ...erros, aceito: '' }) }} />
            <span>Aceito os <a href="#termos">Termos</a> e o <a href="#rgpd">Acordo de tratamento de dados (RGPD)</a></span>
          </label>
          {erros.aceito && <span className="erro13">{erros.aceito}</span>}
          <BotaoSeta aCarregar={aCarregar}>Continuar</BotaoSeta>
        </form>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout topo={<button type="button" className="link-botao" onClick={() => setPasso(1)}>← Voltar</button>}
      aside={<AsideGabinete nome={gab.nome} programa={nomePrograma} />}>
      <form className="form form--largo" onSubmit={criar} noValidate>
        <Passos atual={2} />
        <div>
          <span className="muted13">Passo 2 de 3 · O gabinete</span>
          <h1 className="form__titulo mt8">Fale-nos do gabinete</h1>
          <p className="form__lead">Usamos isto para preparar as exportações e o portal dos seus clientes.</p>
        </div>
        {geral && <Aviso>{geral}</Aviso>}
        <div className="duas">
          <Campo rotulo="NIF do gabinete" mono inputMode="numeric" maxLength={11} value={gab.nif} autoFocus
            erro={erros.nif} ok={nifLimpo.length === 9 && nifValido(nifLimpo) ? '✓ NIF válido' : null}
            onChange={(e) => setGab({ ...gab, nif: e.target.value })} />
          <Campo rotulo={<>Telemóvel <span className="opcional">(opcional)</span></>} mono type="tel" autoComplete="tel"
            placeholder="912 345 678" value={gab.telefone} erro={erros.telefone}
            onChange={(e) => setGab({ ...gab, telefone: e.target.value })} />
        </div>
        <Campo rotulo="Nome do gabinete" autoComplete="organization" value={gab.nome} erro={erros.nome_gabinete}
          ajuda="É o nome que os clientes veem no portal." onChange={(e) => setGab({ ...gab, nome: e.target.value })} />
        <fieldset className="opcoes">
          <legend>Programa de contabilidade</legend>
          <div>
            {PROGRAMAS.map(([v, r]) => (
              <button key={v} type="button" className={`opt${gab.programa === v ? ' on' : ''}`} aria-pressed={gab.programa === v}
                onClick={() => setGab({ ...gab, programa: v })}>{r}</button>
            ))}
          </div>
        </fieldset>
        <fieldset className="opcoes">
          <legend>Quantas empresas acompanha?</legend>
          <div>
            {DIMENSOES.map(([v, r]) => (
              <button key={v} type="button" className={`opt${gab.dimensao === v ? ' on' : ''}`} aria-pressed={gab.dimensao === v}
                onClick={() => setGab({ ...gab, dimensao: v })}>{r}</button>
            ))}
          </div>
        </fieldset>
        <BotaoSeta aCarregar={aCarregar}>Criar gabinete</BotaoSeta>
      </form>
    </AuthLayout>
  )
}
