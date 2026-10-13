import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ErroApi, type Equipa as TEquipa } from '../api'
import { AppLayout, Gaveta, useAviso } from '../components/app'
import { Aviso, Campo } from '../components/ui'
import { quando } from '../util'

const PAPEIS = [
  { id: 'colaborador', nome: 'Colaborador', desc: 'Recebe, confere e exporta faturas. Não gere a equipa.' },
  { id: 'admin', nome: 'Administrador', desc: 'Tudo o que o colaborador faz e ainda convida e remove pessoas.' },
]

const iniciais = (nome: string) => nome.split(/\s+/).filter(Boolean).map((p) => p[0]).slice(0, 2).join('').toUpperCase()

export default function Equipa() {
  const [d, setD] = useState<TEquipa | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [aberto, setAberto] = useState(false)
  const [aRemover, setARemover] = useState<string | null>(null)
  const aviso = useAviso()

  const ler = useCallback(() => {
    api.equipa().then(setD).catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível carregar a equipa.'))
  }, [])
  useEffect(() => { ler() }, [ler])

  async function acao(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); aviso.mostrar(ok); ler() }
    catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível concluir.', 'bad') }
  }

  if (erro) return <AppLayout><Aviso>{erro}</Aviso></AppLayout>
  if (!d) return <AppLayout><div className="carregar-painel" aria-busy="true">A carregar…</div></AppLayout>
  const gere = d.eu.pode_gerir

  return (
    <AppLayout>
      <header className="painel__topo">
        <div>
          <p className="muted15" style={{ margin: '0 0 6px' }}>{d.membros.length} {d.membros.length === 1 ? 'pessoa' : 'pessoas'} no gabinete</p>
          <h1 className="painel__titulo">A sua <span className="pf-hl">equipa</span></h1>
        </div>
        {gere && (
          <button type="button" className="pf-btn pf-btn--primary" onClick={() => setAberto(true)}>Convidar pessoa</button>
        )}
      </header>

      <ResumoSemanal avisar={aviso.mostrar} />

      <section className="bloco" aria-labelledby="eq-membros">
        <h2 id="eq-membros" className="bloco__titulo">Membros</h2>
        <div className="tabela-caixa">
          <table className="pf-table" style={{ minWidth: 640 }}>
            <thead><tr><th>Pessoa</th><th>Papel</th><th>Última entrada</th><th><span className="sr-only">Ações</span></th></tr></thead>
            <tbody>
              {d.membros.map((m) => {
                const souEu = m.utilizador_id === d.eu.id
                const editavel = gere && m.papel !== 'dono' && !souEu
                return (
                  <tr key={m.id}>
                    <td>
                      <div className="pessoa">
                        <span className="avatar" aria-hidden="true">{iniciais(m.nome)}</span>
                        <div><span className="forte15">{m.nome}{souEu && <span className="muted14"> (você)</span>}</span><span className="pf-table__sub">{m.email}</span></div>
                      </div>
                    </td>
                    <td>
                      {editavel ? (
                        <select className="sel sel--mini" aria-label={`Papel de ${m.nome}`} value={m.papel}
                          onChange={(e) => acao(() => api.mudarPapel(m.id, e.target.value), `${m.nome} agora é ${e.target.value === 'admin' ? 'administrador' : 'colaborador'}.`)}>
                          {PAPEIS.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                        </select>
                      ) : <span className={`pf-pill ${m.papel === 'dono' ? 'pf-pill--new' : 'pf-pill--none'}`}>{m.papel_nome}</span>}
                    </td>
                    <td className="muted nowrap">{m.ultimo_login ? quando(m.ultimo_login) : 'Ainda não entrou'}</td>
                    <td className="dir nowrap">
                      {editavel && (aRemover === m.id ? (
                        <>
                          <button type="button" className="pf-btn pf-btn--sm pf-btn--danger" onClick={() => { setARemover(null); acao(() => api.removerMembro(m.id), `${m.nome} saiu da equipa.`) }}>Confirmar remoção</button>
                          <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" style={{ marginLeft: 6 }} onClick={() => setARemover(null)}>Cancelar</button>
                        </>
                      ) : <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" onClick={() => setARemover(m.id)}>Remover</button>)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {(d.convites.length > 0 || gere) && (
        <section className="bloco" aria-labelledby="eq-convites">
          <h2 id="eq-convites" className="bloco__titulo">Convites por aceitar</h2>
          {d.convites.length === 0 ? (
            <p className="muted15" style={{ margin: 0 }}>Nenhum convite pendente. Quem convidar recebe um email com um link válido durante 7 dias.</p>
          ) : (
            <div className="tabela-caixa">
              <table className="pf-table" style={{ minWidth: 640 }}>
                <thead><tr><th>Email</th><th>Papel</th><th>Enviado</th><th><span className="sr-only">Ações</span></th></tr></thead>
                <tbody>
                  {d.convites.map((c) => (
                    <tr key={c.id}>
                      <td className="ink">{c.email}</td>
                      <td>{c.papel_nome}</td>
                      <td className="muted nowrap">{quando(c.criado_em)}</td>
                      <td className="dir nowrap">
                        {gere && <>
                          <button type="button" className="pf-btn pf-btn--sm" onClick={() => acao(() => api.reenviarConvite(c.id), `Convite reenviado para ${c.email}.`)}>Reenviar</button>
                          <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" style={{ marginLeft: 6 }} onClick={() => acao(() => api.cancelarConvite(c.id), 'Convite cancelado.')}>Cancelar</button>
                        </>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {!gere && <p className="muted14" style={{ margin: 0 }}>Só o dono do gabinete ou um administrador pode convidar e remover pessoas.</p>}

      <ConvidarGaveta aberto={aberto} fechar={() => setAberto(false)} enviado={(email) => { setAberto(false); aviso.mostrar(`Convite enviado para ${email}.`); ler() }} />
      {aviso.elemento}
    </AppLayout>
  )
}

function ConvidarGaveta({ aberto, fechar, enviado }: { aberto: boolean; fechar: () => void; enviado: (email: string) => void }) {
  const [email, setEmail] = useState('')
  const [papel, setPapel] = useState('colaborador')
  const [erro, setErro] = useState<{ campo: string | null; msg: string } | null>(null)
  const [aEnviar, setAEnviar] = useState(false)
  useEffect(() => { if (aberto) { setEmail(''); setPapel('colaborador'); setErro(null) } }, [aberto])

  async function enviar(e?: FormEvent) {
    e?.preventDefault()
    setErro(null)
    if (!/^\S+@\S+\.\S{2,}$/.test(email.trim())) return setErro({ campo: 'email', msg: 'Este email não parece válido.' })
    setAEnviar(true)
    try { const r = await api.convidarColega(email.trim(), papel); enviado(r.email) }
    catch (err) { setErro({ campo: err instanceof ErroApi ? err.campo : null, msg: err instanceof ErroApi ? err.message : 'Não foi possível enviar.' }) }
    finally { setAEnviar(false) }
  }

  return (
    <Gaveta aberto={aberto} fechar={fechar} titulo="Convidar pessoa" subtitulo="Enviamos um email com um link para criar a conta e entrar no gabinete."
      rodape={<>
        <button type="button" className="pf-btn pf-btn--ghost" onClick={fechar}>Cancelar</button>
        <button type="button" className="pf-btn pf-btn--primary" disabled={aEnviar} onClick={() => enviar()}>{aEnviar ? 'A enviar…' : 'Enviar convite'}</button>
      </>}>
      <form className="form" onSubmit={enviar} noValidate>
        {erro && !erro.campo && <Aviso>{erro.msg}</Aviso>}
        <Campo rotulo="Email" type="email" autoComplete="off" value={email} placeholder="nome@gabinete.pt"
          erro={erro?.campo === 'email' ? erro.msg : null} onChange={(e) => setEmail(e.target.value)} />
        <div className="pf-field">
          <span className="pf-field__label">Papel</span>
          <div className="formatos" role="radiogroup" aria-label="Papel">
            {PAPEIS.map((p) => (
              <label key={p.id} className={`formato${papel === p.id ? ' on' : ''}`}>
                <input type="radio" name="papel" value={p.id} checked={papel === p.id} onChange={() => setPapel(p.id)} className="sr-only" />
                <span className="forte15">{p.nome}</span>
                <span className="muted14">{p.desc}</span>
              </label>
            ))}
          </div>
        </div>
        <button type="submit" hidden />
      </form>
    </Gaveta>
  )
}

function ResumoSemanal({ avisar }: { avisar: (m: string, t?: 'ok' | 'bad') => void }) {
  const [r, setR] = useState<{ ativo: boolean; enviado_em: string | null } | null>(null)
  const [aEnviar, setAEnviar] = useState(false)
  useEffect(() => { api.resumoSemanal().then(setR).catch(() => {}) }, [])
  if (!r) return null
  async function mudar(ativo: boolean) {
    try { setR({ ...r!, ...(await api.mudarResumoSemanal(ativo)) }); avisar(ativo ? 'Vai receber o resumo à segunda-feira.' : 'Deixa de receber o resumo semanal.') }
    catch (e) { avisar(e instanceof ErroApi ? e.message : 'Não foi possível mudar.', 'bad') }
  }
  async function enviar() {
    setAEnviar(true)
    try { const x = await api.enviarResumo(); avisar(`Resumo enviado para ${x.email}.`); setR({ ...r!, enviado_em: new Date().toISOString() }) }
    catch (e) { avisar(e instanceof ErroApi ? e.message : 'Não foi possível enviar.', 'bad') }
    finally { setAEnviar(false) }
  }
  return (
    <section className="resumo-semanal" aria-label="Resumo semanal por email">
      <label className="interruptor">
        <input type="checkbox" role="switch" checked={r.ativo} onChange={(e) => mudar(e.target.checked)} />
        <span className="interruptor__pista" aria-hidden="true"><span /></span>
      </label>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="forte15">Resumo semanal por email</div>
        <div className="muted14">À segunda-feira: respostas dos clientes, faturas por conferir, quem ainda não enviou e o que falta do e-Fatura.{r.enviado_em ? ` Último envio ${quando(r.enviado_em).toLowerCase()}.` : ''}</div>
      </div>
      <a className="pf-btn pf-btn--sm pf-btn--ghost" href="/api/resumo/pre-visualizar" target="_blank" rel="noreferrer">Ver exemplo</a>
      <button type="button" className="pf-btn pf-btn--sm" disabled={aEnviar} onClick={enviar}>{aEnviar ? 'A enviar…' : 'Enviar-me agora'}</button>
    </section>
  )
}
