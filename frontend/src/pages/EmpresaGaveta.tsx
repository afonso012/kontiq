import { useEffect, useState, type FormEvent } from 'react'
import { api, ErroApi, type EmpresaPainel } from '../api'
import { Gaveta } from '../components/app'
import { Aviso, Campo } from '../components/ui'
import { nifValido, telefoneLegivel } from '../util'

type Form = { nif: string; nome: string; periodicidade_iva: string; contacto_nome: string; telefone: string; email: string; convidar: boolean }
const vazio: Form = { nif: '', nome: '', periodicidade_iva: 'trimestral', contacto_nome: '', telefone: '', email: '', convidar: true }

/** Adicionar ou editar uma empresa-cliente, num painel lateral. */
export function EmpresaGaveta({ aberto, empresa, fechar, gravado }: {
  aberto: boolean
  empresa: EmpresaPainel | null
  fechar: () => void
  gravado: (mensagem: string) => void
}) {
  const [f, setF] = useState<Form>(vazio)
  const [erros, setErros] = useState<Record<string, string>>({})
  const [geral, setGeral] = useState<string | null>(null)
  const [aGravar, setAGravar] = useState(false)

  useEffect(() => {
    if (!aberto) return
    setErros({}); setGeral(null)
    setF(empresa ? {
      nif: empresa.nif, nome: empresa.nome, periodicidade_iva: empresa.periodicidade_iva,
      contacto_nome: empresa.contacto.nome ?? '', telefone: telefoneLegivel(empresa.contacto.telefone),
      email: empresa.contacto.email ?? '', convidar: false,
    } : vazio)
  }, [aberto, empresa])

  const muda = (k: keyof Form) => (e: { target: { value: string } }) => { setF({ ...f, [k]: e.target.value }); setErros({ ...erros, [k]: '' }) }
  const nif = f.nif.replace(/\s/g, '')
  const jaNoPortal = !!empresa?.portal
  const primeiro = f.contacto_nome.trim().split(/\s+/)[0] || 'O contacto'

  async function gravar(e: FormEvent) {
    e.preventDefault()
    setGeral(null)
    const novos: Record<string, string> = {}
    if (!nifValido(nif)) novos.nif = 'NIF inválido: confirme os 9 dígitos.'
    if (f.nome.trim().length < 2) novos.nome = 'Escreva o nome da empresa.'
    if (f.convidar) {
      if (!f.contacto_nome.trim()) novos.contacto_nome = 'Escreva o nome de quem envia as faturas.'
      if (!f.telefone.trim() && !f.email.trim()) novos.telefone = 'Indique o telemóvel ou o email para enviar o convite.'
    }
    if (Object.keys(novos).length) return setErros(novos)
    setAGravar(true)
    const dados = { nif, nome: f.nome.trim(), periodicidade_iva: f.periodicidade_iva, contacto_nome: f.contacto_nome.trim() || null,
      telefone: f.telefone.trim() || null, email: f.email.trim() || null, convidar: f.convidar }
    try {
      if (empresa) await api.editarEmpresa(empresa.id, dados)
      else await api.criarEmpresa(dados)
      const convite = f.convidar ? (dados.telefone ? ` Convite enviado por SMS para ${dados.telefone.replace(/\D/g, '').slice(-9).replace(/(\d{3})(\d{3})(\d{3})/, '$1 $2 $3')}.` : ` Convite enviado para ${dados.email}.`) : ''
      gravado(`${dados.nome} ${empresa ? 'atualizada' : 'adicionada'}.${convite}`)
    } catch (err) {
      if (err instanceof ErroApi && err.campo) setErros({ [err.campo]: err.message })
      else setGeral(err instanceof ErroApi ? err.message : 'Não foi possível gravar.')
    } finally { setAGravar(false) }
  }

  const textoBotao = aGravar ? 'Um momento…' : empresa ? (f.convidar ? 'Gravar e enviar convite' : 'Gravar') : (f.convidar ? 'Adicionar e enviar convite' : 'Adicionar empresa')

  return (
    <Gaveta aberto={aberto} fechar={fechar} titulo={empresa ? 'Editar empresa' : 'Adicionar empresa'}
      subtitulo={empresa ? empresa.nome : 'Uma empresa-cliente do gabinete.'}
      rodape={<>
        <button type="button" className="pf-btn" onClick={fechar}>Cancelar</button>
        <button type="submit" form="form-empresa" className="pf-btn pf-btn--primary" disabled={aGravar} aria-busy={aGravar}>{textoBotao}</button>
      </>}>
      <form id="form-empresa" className="form-gaveta" onSubmit={gravar} noValidate>
        {geral && <Aviso>{geral}</Aviso>}
        <div className="duas">
          <Campo rotulo="NIF" mono inputMode="numeric" maxLength={11} value={f.nif} onChange={muda('nif')} erro={erros.nif}
            ok={nif.length === 9 && nifValido(nif) ? '✓ NIF válido' : null} />
          <div className="pf-field" style={{ minWidth: 0 }}>
            <span className="pf-field__label" id="iva-rotulo">IVA</span>
            <div className="segmentado" role="group" aria-labelledby="iva-rotulo">
              {[['mensal', 'Mensal'], ['trimestral', 'Trimestral']].map(([v, r]) => (
                <button key={v} type="button" className={f.periodicidade_iva === v ? 'on' : ''} aria-pressed={f.periodicidade_iva === v}
                  onClick={() => setF({ ...f, periodicidade_iva: v })}>{r}</button>
              ))}
            </div>
          </div>
        </div>
        <Campo rotulo="Nome da empresa" autoComplete="off" value={f.nome} onChange={muda('nome')} erro={erros.nome} />

        <div className="separador" />
        <div>
          <div className="forte17">Quem envia as faturas</div>
          <div className="muted15">Pode acrescentar mais pessoas depois.</div>
        </div>
        <Campo rotulo="Nome" autoComplete="off" value={f.contacto_nome} onChange={muda('contacto_nome')} erro={erros.contacto_nome} />
        <div className="duas">
          <Campo rotulo="Telemóvel" mono type="tel" inputMode="tel" placeholder="912 345 678" value={f.telefone} onChange={muda('telefone')} erro={erros.telefone} />
          <Campo rotulo={<>Email <span className="opcional">(opcional)</span></>} type="email" placeholder="nome@empresa.pt" value={f.email} onChange={muda('email')} erro={erros.email} />
        </div>

        <div className="convite">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="forte15">{jaNoPortal ? 'Reenviar o convite para o portal' : 'Convidar já para o portal'}</div>
            <div className="muted14">{jaNoPortal ? 'Esta empresa já tem acesso ao portal.' : `${primeiro} recebe ${f.telefone.trim() ? 'um SMS' : 'um email'} com o link e entra com um código. Sem palavras-passe.`}</div>
          </div>
          <button type="button" role="switch" aria-checked={f.convidar} aria-label="Enviar convite para o portal"
            className={`interruptor${f.convidar ? ' on' : ''}`} onClick={() => { setF({ ...f, convidar: !f.convidar }); setErros({}) }}><span /></button>
        </div>
      </form>
    </Gaveta>
  )
}
