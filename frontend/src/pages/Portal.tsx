import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ErroApi } from '../api'
import { Aviso, BotaoSeta, Campo, CodigoInput, mmss, useContagem } from '../components/ui'
import { useSessao } from '../sessao'

/** Entrada do cliente do gabinete: sem palavra-passe, recebe um código por SMS ou email. */
export default function Portal() {
  const { definir } = useSessao()
  const nav = useNavigate()
  const [canal, setCanal] = useState<'sms' | 'email'>('sms')
  const [destino, setDestino] = useState('')
  const [passo, setPasso] = useState<1 | 2>(1)
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [aCarregar, setACarregar] = useState(false)
  const [espera, setEspera] = useContagem(0)

  async function pedir(e?: FormEvent) {
    e?.preventDefault()
    setErro(null)
    if (!destino.trim()) return setErro(canal === 'sms' ? 'Escreva o número de telemóvel.' : 'Escreva o email.')
    setACarregar(true)
    try {
      await api.pedirCodigoPortal(canal, destino)
      setPasso(2); setCodigo(''); setEspera(60)
    } catch (err) { setErro(err instanceof ErroApi ? err.message : 'Não foi possível enviar o código.') }
    finally { setACarregar(false) }
  }

  async function entrar(valor = codigo) {
    if (valor.length !== 6) return setErro('Escreva os 6 dígitos do código.')
    setErro(null); setACarregar(true)
    try {
      const eu = await api.entrarPortal(canal, destino, valor)
      definir(eu)
      nav('/portal/inicio', { replace: true })
    } catch (err) {
      setErro(err instanceof ErroApi ? err.message : 'Não foi possível entrar.')
      setCodigo('')
    } finally { setACarregar(false) }
  }

  const onde = canal === 'sms' ? `+351 ${destino.replace(/\D/g, '').slice(-9).replace(/(\d{3})(\d{3})(\d{3})/, '$1 $2 $3')}` : destino

  return (
    <div className="portal">
      <header className="portal__topo pf-glow">
        <div className="portal__gabinete">
          <span className="avatar" aria-hidden="true">PF</span>
          <div><div className="forte15">Portal de faturas</div><div className="muted12">do seu gabinete de contabilidade</div></div>
        </div>
        <h1 className="portal__titulo">Envie as faturas com uma <span className="pf-hl">foto</span></h1>
        <p className="muted15">Sem palavras-passe: recebe um código e entra.</p>
      </header>

      {passo === 1 ? (
        <form className="portal__form" onSubmit={pedir} noValidate>
          <div className="segmentado" role="group" aria-label="Receber o código por">
            <button type="button" className={canal === 'sms' ? 'on' : ''} aria-pressed={canal === 'sms'}
              onClick={() => { setCanal('sms'); setDestino(''); setErro(null) }}>Telemóvel</button>
            <button type="button" className={canal === 'email' ? 'on' : ''} aria-pressed={canal === 'email'}
              onClick={() => { setCanal('email'); setDestino(''); setErro(null) }}>Email</button>
          </div>
          {erro && <Aviso>{erro}</Aviso>}
          {canal === 'sms' ? (
            <Campo rotulo="Número de telemóvel" mono type="tel" inputMode="tel" autoComplete="tel-national" placeholder="912 345 678"
              value={destino} onChange={(e) => setDestino(e.target.value)} ajuda="O número que deu ao seu contabilista." autoFocus />
          ) : (
            <Campo rotulo="Email" type="email" inputMode="email" autoComplete="email" value={destino}
              onChange={(e) => setDestino(e.target.value)} ajuda="O email que deu ao seu contabilista." autoFocus />
          )}
          <BotaoSeta aCarregar={aCarregar}>Receber código</BotaoSeta>
          <div className="portal__fim muted13">
            <span>Ainda não tem acesso? Peça um convite ao seu contabilista.</span>
            <Link to="/entrar">Sou contabilista</Link>
          </div>
        </form>
      ) : (
        <form className="portal__form" onSubmit={(e) => { e.preventDefault(); entrar() }} noValidate>
          <p className="muted15" style={{ margin: 0 }}>Se <b className="ink">{onde}</b> tiver acesso, recebe um código de 6 dígitos.</p>
          {erro && <Aviso>{erro}</Aviso>}
          <CodigoInput valor={codigo} mudar={setCodigo} erro={!!erro} aoCompletar={(v) => entrar(v)} />
          <BotaoSeta aCarregar={aCarregar}>Entrar</BotaoSeta>
          <div className="muted14 centro">
            {espera > 0 ? <span>Reenviar em <span className="pf-mono">{mmss(espera)}</span></span>
              : <button type="button" className="link-botao" onClick={() => pedir()}>Reenviar código</button>}
            {' · '}<button type="button" className="link-botao" onClick={() => { setPasso(1); setErro(null) }}>Mudar {canal === 'sms' ? 'número' : 'email'}</button>
          </div>
        </form>
      )}
    </div>
  )
}
