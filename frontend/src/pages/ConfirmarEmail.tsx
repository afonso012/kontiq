import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ErroApi } from '../api'
import { Marca, Aviso, BotaoSeta, CodigoInput, mmss, useContagem } from '../components/ui'
import { useSessao } from '../sessao'

export default function ConfirmarEmail() {
  const { eu, definir } = useSessao()
  const nav = useNavigate()
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [aCarregar, setACarregar] = useState(false)
  const [espera, setEspera] = useContagem(60)

  async function confirmar(valor = codigo) {
    if (valor.length !== 6) return setErro('Escreva os 6 dígitos do código.')
    setErro(null); setACarregar(true)
    try {
      const novo = await api.confirmarEmail(valor)
      definir(novo)
      nav('/painel', { replace: true })
    } catch (err) {
      setErro(err instanceof ErroApi ? err.message : 'Não foi possível confirmar.')
      setCodigo('')
    } finally { setACarregar(false) }
  }

  async function reenviar() {
    setErro(null); setInfo(null)
    try {
      await api.reenviarConfirmacao()
      setInfo('Enviámos um código novo. O anterior deixou de funcionar.')
      setEspera(60)
    } catch (err) { setErro(err instanceof ErroApi ? err.message : 'Não foi possível reenviar.') }
  }

  async function sair() {
    await api.sair().catch(() => {})
    definir(null)
    nav('/entrar', { replace: true })
  }

  return (
    <div className="ecra-centro">
      <div className="ecra-centro__painel pf-glow">
        <div className="auth__topo"><Marca /><span className="muted13">Passo 3 de 3</span></div>
        <div className="auth__centro">
          <form className="pf-glass cartao-codigo" onSubmit={(e: FormEvent) => { e.preventDefault(); confirmar() }} noValidate>
            <span className="icone-redondo" aria-hidden="true">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="5" width="18" height="14" rx="3" /><path d="m4 7 8 6 8-6" /></svg>
            </span>
            <div>
              <h1 className="form__titulo">Confirme o seu <span className="pf-hl">email</span></h1>
              <p className="form__lead">Enviámos um código de 6 dígitos para<br /><b className="ink">{eu?.utilizador.email}</b></p>
            </div>
            {erro && <Aviso>{erro}</Aviso>}
            {info && <Aviso tipo="info">{info}</Aviso>}
            <CodigoInput valor={codigo} mudar={setCodigo} erro={!!erro} aoCompletar={(v) => confirmar(v)} />
            <BotaoSeta aCarregar={aCarregar}>Confirmar e abrir o painel</BotaoSeta>
            <div className="muted14 centro">
              Não recebeu?{' '}
              {espera > 0 ? <span>Reenviar em <span className="pf-mono">{mmss(espera)}</span></span>
                : <button type="button" className="link-botao" onClick={reenviar}>Reenviar código</button>}
              {' · '}<button type="button" className="link-botao" onClick={sair}>Sair</button>
            </div>
          </form>
        </div>
        <div className="muted13 centro">Veja também a pasta de spam. O código expira em 15 minutos.</div>
      </div>
    </div>
  )
}
