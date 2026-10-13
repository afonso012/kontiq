import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ErroApi, type DadosFatura, type Fatura, type Opcoes } from '../api'
import { useAviso } from '../components/app'
import { Aviso } from '../components/ui'
import { Escrever, Mensagens } from '../components/conversa'
import { nifValido, quando, telefoneLegivel } from '../util'
import { Origem } from './EmpresaFaturas'

const TAXAS = [23, 13, 6, 0]
const eur = (v: number) => v.toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
const num = (s: string) => { const n = Number(String(s).replace(/\s/g, '').replace(',', '.')); return Number.isFinite(n) ? n : 0 }
const virgula = (s: string) => s ? s.replace('.', ',') : s
const CANAIS: Record<string, string> = { upload: 'carregada no gabinete', portal: 'enviada pelo portal', email: 'recebida por email', api: 'recebida por integração' }

function paraForm(f: Fatura): DadosFatura {
  return {
    fornecedor: f.fornecedor.nome, nif: f.fornecedor.nif, pais: f.fornecedor.pais || 'PT', tipo_documento: f.tipo_documento,
    numero: f.numero, atcud: f.atcud, data: f.data,
    linhas: f.linhas.length ? f.linhas.map((l) => ({ espaco: l.espaco, tipo_taxa: l.tipo_taxa, taxa: l.taxa, base: virgula(l.base), iva: virgula(l.iva) }))
      : [{ espaco: 'PT', taxa: 23, base: '', iva: '' }],
    total: f.total === '0.00' ? '' : virgula(f.total), categoria_id: f.categoria_id, conta: f.conta,
    tratamento_iva: f.tratamento_iva, notas: f.notas,
  }
}

export default function ConferirFatura() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const [f, setF] = useState<Fatura | null>(null)
  const [form, setForm] = useState<DadosFatura | null>(null)
  const [op, setOp] = useState<Opcoes | null>(null)
  const [lembrar, setLembrar] = useState(true)
  const [erro, setErro] = useState<string | null>(null)
  const [aGravar, setAGravar] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [rodar, setRodar] = useState(0)
  const [paginas, setPaginas] = useState(1)
  const [rejeitando, setRejeitando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [perguntar, setPerguntar] = useState(false)
  const aviso = useAviso()

  useEffect(() => { api.classificacao().then(setOp).catch(() => {}) }, [])
  useEffect(() => {
    setF(null); setErro(null); setZoom(1); setRodar(0); setRejeitando(false); setPerguntar(false)
    api.fatura(id).then((r) => {
      setF(r); setForm(paraForm(r)); setLembrar(!r.regra); setPaginas(1)
      if (r.documento) fetch(`/api/documentos/${r.documento.id}/paginas`).then((x) => x.json()).then((x) => setPaginas(x.paginas ?? 1)).catch(() => {})
    })
      .catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível abrir a fatura.'))
  }, [id])

  const voltar = f ? `/empresas/${f.empresa.id}?periodo=${f.periodo.slice(0, 7)}` : '/painel'
  const base = useMemo(() => form ? form.linhas.reduce((s, l) => s + num(l.base), 0) : 0, [form])
  const iva = useMemo(() => form ? form.linhas.reduce((s, l) => s + num(l.iva), 0) : 0, [form])
  const total = form ? num(form.total) : 0
  const diferenca = Math.round((base + iva - total) * 100) / 100
  const fechada = f?.estado === 'conferida' || f?.estado === 'rejeitada' || f?.estado === 'exportada'
  const nifLimpo = (form?.nif ?? '').replace(/\s/g, '')

  function muda<K extends keyof DadosFatura>(k: K, v: DadosFatura[K]) { setForm((x) => x ? { ...x, [k]: v } : x) }
  function mudaLinha(i: number, campo: 'taxa' | 'base' | 'iva', v: string) {
    setForm((x) => {
      if (!x) return x
      const linhas = x.linhas.map((l, j) => {
        if (j !== i) return l
        const n = { ...l, tipo_taxa: undefined, [campo]: campo === 'taxa' ? (v === '' ? null : Number(v)) : v }
        // Ao mudar a base ou a taxa, sugere o IVA (pode ser corrigido à mão).
        if ((campo === 'base' || campo === 'taxa') && n.taxa != null && n.base !== '') n.iva = virgula((Math.round(num(n.base) * n.taxa) / 100).toFixed(2))
        return n
      })
      return { ...x, linhas }
    })
  }
  function escolherCategoria(cid: string) {
    const c = op?.categorias.find((x) => x.id === cid)
    setForm((x) => x ? { ...x, categoria_id: cid || null, conta: c?.conta ?? x.conta, tratamento_iva: c?.tratamento && c.tratamento !== 'por_definir' ? c.tratamento : x.tratamento_iva } : x)
  }

  async function correr(fn: () => Promise<void>) {
    setAGravar(true); setErro(null)
    try { await fn() } catch (e) { setErro(e instanceof ErroApi ? e.message : 'Não foi possível gravar.') } finally { setAGravar(false) }
  }
  const conferir = (e?: FormEvent) => {
    e?.preventDefault()
    if (!form || !f || fechada) return
    return correr(async () => {
      const r = await api.conferir(f.id, lembrar, form)
      if (r.seguinte) nav(`/faturas/${r.seguinte}`)
      else nav(voltar, { state: { aviso: 'Todas as faturas do mês estão conferidas.' } })
    })
  }
  const gravar = () => form && f && correr(async () => { const r = await api.gravarFatura(f.id, form); setF(r); setForm(paraForm(r)); aviso.mostrar('Alterações gravadas.') })
  const rejeitar = (m: string | null) => f && correr(async () => {
    const r = await api.rejeitar(f.id, m)
    setRejeitando(false); setMotivo('')
    if (r.fila.seguinte) nav(`/faturas/${r.fila.seguinte}`)
    else nav(voltar, { state: { aviso: 'Fatura rejeitada. Não há mais faturas por conferir neste mês.' } })
  })
  const reabrir = () => f && correr(async () => { const r = await api.reabrir(f.id); setF(r); setForm(paraForm(r)) })
  async function escrever(texto: string) {
    if (!f) return false
    try {
      const r = await api.perguntar(f.id, texto)
      setF({ ...f, duvida: r.duvida, mensagens: r.mensagens })
      if (r.avisado) aviso.mostrar(r.avisado === 'sms' ? 'Enviado. O cliente recebeu um SMS com o link do portal.' : 'Enviado. O cliente recebeu um email com o link do portal.')
      return true
    } catch (e) { aviso.mostrar(e instanceof ErroApi ? e.message : 'Não foi possível enviar.', 'bad'); return false }
  }
  const fecharDuvida = () => f && correr(async () => { const r = await api.resolverDuvida(f.id); setF({ ...f, duvida: r.duvida, mensagens: r.mensagens }); aviso.mostrar('Dúvida resolvida.') })
  const resolver = (pid: string) => f && correr(async () => { const r = await api.resolverProblema(f.id, pid); setF(r) })

  if (erro && !f) return <div className="conferir"><div style={{ padding: 32 }}><Aviso>{erro}</Aviso><Link to="/painel" className="pf-btn mt14">Voltar ao painel</Link></div></div>
  if (!f || !form) return <div className="conferir"><div className="carregar-painel" style={{ padding: 32 }} aria-busy="true">A abrir a fatura…</div></div>

  const doc = f.documento
  const urlDoc = doc ? `/api/documentos/${doc.id}` : null
  const dup = f.problemas.find((p) => p.codigo === 'duplicado')
  // Numa fatura por preencher, "falta a data/total/NIF" já se vê nos campos vazios.
  const porPreencher = f.metodo === 'manual' && !f.fornecedor.nif && f.total === '0.00'
  const outros = f.problemas.filter((p) => p.codigo !== 'duplicado' && p.codigo !== 'sem_classificacao'
    && !(porPreencher && ['sem_data', 'sem_total', 'sem_nif'].includes(p.codigo)))

  return (
    <div className="conferir">
      <header className="conferir__topo">
        <div className="conferir__onde">
          <Link to={voltar} className="pf-btn pf-btn--sm">← Faturas</Link>
          <span className="forte15 cortar">{f.empresa.nome}</span>
        </div>
        {f.fila.total > 0 && (
          <div className="conferir__fila">
            <span className="muted14">Fatura <b className="ink">{f.fila.posicao}</b> de {f.fila.total}{f.estado === 'por_conferir' ? ' por conferir' : ''}</span>
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Fatura anterior" disabled={!f.fila.anterior} onClick={() => f.fila.anterior && nav(`/faturas/${f.fila.anterior}`)}>‹</button>
            <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Fatura seguinte" disabled={!f.fila.seguinte} onClick={() => f.fila.seguinte && nav(`/faturas/${f.fila.seguinte}`)}>›</button>
          </div>
        )}
      </header>

      <div className="conferir__corpo">
        <section className="documento" aria-label="Documento">
          <div className="documento__barra">
            <span className="muted14 pf-mono cortar">{doc ? `${doc.nome} · ${CANAIS[doc.canal] ?? ''} ${quando(doc.recebido).toLowerCase()}` : 'Sem documento'}</span>
            {doc && (
              <div className="documento__botoes">
                {<>
                  <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Diminuir" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>−</button>
                  <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Aumentar" onClick={() => setZoom((z) => Math.min(2.5, z + 0.25))}>+</button>
                  <button type="button" className="pf-btn pf-btn--sm periodo__seta" aria-label="Rodar" onClick={() => setRodar((r) => (r + 90) % 360)}>↻</button>
                </>}
                <a className="pf-btn pf-btn--sm" href={urlDoc!} download={doc.nome}>Descarregar</a>
              </div>
            )}
          </div>
          <div className="documento__vista">
            {!doc ? <p className="muted15 centro">Esta fatura foi criada sem documento.</p>
              : <div className="documento__paginas" style={{ transform: `rotate(${rodar}deg)`, width: `${zoom * 100}%` }}>
                  {Array.from({ length: paginas }, (_, i) => (
                    <img key={i} src={`${urlDoc}/pagina/${i + 1}`} alt={`Documento ${doc.nome}, página ${i + 1}`} className="documento__img" />
                  ))}
                </div>}
          </div>
        </section>

        <form className="dados" onSubmit={conferir} noValidate>
          <div className="dados__corpo">
            <div className="dados__cabeca">
              <div style={{ minWidth: 0 }}>
                <div className="linha" style={{ justifyContent: 'flex-start', gap: 8 }}>
                  <span className="pf-mono muted">{form.numero || 'Sem número'}</span><Origem metodo={f.metodo} confianca={f.confianca} />
                </div>
                <h1 className="dados__titulo">{form.fornecedor || 'Fornecedor por preencher'}</h1>
              </div>
              <div className="dados__total">
                <div className="pf-mono dados__valor">{eur(total)}</div>
                {total > 0 && (Math.abs(diferenca) <= 0.02
                  ? <div className="ok14">✓ Totais batem</div>
                  : <div className="erro14">Diferença de {eur(Math.abs(diferenca))}</div>)}
              </div>
            </div>

            {f.estado === 'conferida' && <div className="pf-alert pf-alert--info"><span className="pf-alert__tag">Info</span><div style={{ flex: 1 }}>Conferida {f.conferida_em ? quando(f.conferida_em).toLowerCase() : ''}. Para alterar, reabra.</div><button type="button" className="pf-btn pf-btn--sm" onClick={reabrir}>Reabrir</button></div>}
            {f.estado === 'rejeitada' && <div className="pf-alert pf-alert--warn"><span className="pf-alert__tag">Aviso</span><div style={{ flex: 1 }}>Rejeitada: não entra na exportação.</div><button type="button" className="pf-btn pf-btn--sm" onClick={reabrir}>Reabrir</button></div>}
            {f.estado === 'exportada' && <div className="pf-alert pf-alert--info"><span className="pf-alert__tag">Info</span><div>Já exportada para o programa de contabilidade.</div></div>}

            {dup && !fechada && (
              <div className="pf-alert pf-alert--bad dup">
                <div className="dup__texto"><span className="pf-alert__tag">Erro</span><div><span className="pf-alert__title">Possível duplicado.</span> {dup.mensagem}</div></div>
                <div className="dup__acoes">
                  <button type="button" className="pf-btn pf-btn--sm pf-btn--danger" onClick={() => rejeitar('Duplicado')}>É duplicado, rejeitar</button>
                  <button type="button" className="pf-btn pf-btn--sm" onClick={() => resolver(dup.id)}>Não é duplicado</button>
                  {f.duplicado_de && <Link to={`/faturas/${f.duplicado_de}`} className="pf-btn pf-btn--sm pf-btn--ghost">Ver a outra</Link>}
                </div>
              </div>
            )}
            {!fechada && outros.map((p) => (
              <div key={p.id} className={`pf-alert pf-alert--${p.nivel === 'erro' ? 'bad' : 'warn'}`}><span className="pf-alert__tag">{p.nivel === 'erro' ? 'Erro' : 'Aviso'}</span><div>{p.mensagem}</div></div>
            ))}
            {f.metodo === 'ia' && !fechada && (
              <div className="pf-alert pf-alert--info"><span className="pf-alert__tag">Info</span>
                <div>{f.modo_leitura === 'teste'
                  ? 'Lida automaticamente a partir do texto do PDF (modo de teste, sem IA). Confirme cada valor com o documento.'
                  : 'Lida automaticamente por IA. Confirme os valores com o documento.'}</div></div>
            )}
            {porPreencher && !fechada && <div className="pf-alert pf-alert--info"><span className="pf-alert__tag">Info</span><div>Sem código QR: preencha os dados a partir do documento.</div></div>}
            {erro && <Aviso>{erro}</Aviso>}
            {(f.mensagens.length > 0 || perguntar) && (
              <section className={`conversa${f.duvida === 'resposta' ? ' conversa--nova' : ''}`} aria-labelledby="conversa-t">
                <div className="conversa__cabeca">
                  <h2 id="conversa-t">Dúvida com o cliente</h2>
                  {f.duvida === 'pergunta' && <span className="pf-pill pf-pill--warn">À espera do cliente</span>}
                  {f.duvida === 'resposta' && <span className="pf-pill pf-pill--ok">O cliente respondeu</span>}
                  {!f.duvida && f.mensagens.length > 0 && <span className="pf-pill pf-pill--none">Resolvida</span>}
                  <span style={{ flex: 1 }} />
                  {f.duvida && <button type="button" className="pf-btn pf-btn--sm" onClick={fecharDuvida} disabled={aGravar}>Marcar como resolvida</button>}
                  {!f.mensagens.length && <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" onClick={() => setPerguntar(false)}>Cancelar</button>}
                </div>
                <Mensagens mensagens={f.mensagens} eu="gabinete" />
                <Escrever enviar={escrever} autoFocus={!f.mensagens.length}
                  rotulo={f.duvida === 'pergunta' ? 'Acrescentar' : 'Enviar ao cliente'}
                  placeholder={f.mensagens.length ? 'Escrever ao cliente…' : 'Ex.: Esta compra é da empresa ou pessoal?'}
                  ajuda={f.duvida === 'pergunta' ? 'O cliente já foi avisado. Vê esta mensagem no portal.'
                    : f.contacto.telefone ? `${f.contacto.nome ?? 'O cliente'} recebe um SMS para ${telefoneLegivel(f.contacto.telefone)} com o link do portal.`
                    : f.contacto.email ? `${f.contacto.nome ?? 'O cliente'} recebe um email para ${f.contacto.email} com o link do portal.`
                    : 'Esta empresa não tem telemóvel nem email: edite-a antes de perguntar.'} />
              </section>
            )}
            <fieldset disabled={fechada || aGravar} className="dados__campos">

            <div className="dados__secao">
              <h2>Fornecedor e documento</h2>
              <div className="duas">
                <CampoC rotulo="Fornecedor" value={form.fornecedor} onChange={(v) => muda('fornecedor', v)} />
                <CampoC rotulo="NIF" mono value={form.nif} onChange={(v) => muda('nif', v)}
                  dica={nifLimpo.length === 9 ? (nifValido(nifLimpo) ? '✓ válido' : 'NIF inválido') : f.fornecedor.conhecido ? `Conhecido · ${f.fornecedor.faturas} faturas` : undefined}
                  dicaTipo={nifLimpo.length === 9 && !nifValido(nifLimpo) ? 'erro' : 'ok'} />
                <label className="pf-field c-compacto"><span className="pf-field__label">Tipo</span>
                  <select className="sel" value={form.tipo_documento} onChange={(e) => muda('tipo_documento', e.target.value)}>
                    {(op?.tipos ?? [{ id: form.tipo_documento, nome: form.tipo_documento }]).map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
                  </select></label>
                <CampoC rotulo="Número" mono value={form.numero} onChange={(v) => muda('numero', v)} />
                <CampoC rotulo="Data" type="date" value={form.data} onChange={(v) => muda('data', v)} />
                <CampoC rotulo="ATCUD" mono value={form.atcud} onChange={(v) => muda('atcud', v)} />
              </div>
            </div>

            <div className="dados__secao">
              <h2>IVA</h2>
              <table className="pf-table tabela-iva">
                <thead><tr><th>Taxa</th><th className="dir">Base</th><th className="dir">IVA</th><th><span className="sr-only">Remover</span></th></tr></thead>
                <tbody>
                  {form.linhas.map((l, i) => (
                    <tr key={i}>
                      <td>
                        {l.espaco !== 'PT' || (l.taxa != null && !TAXAS.includes(Math.round(l.taxa)))
                          ? <span className="pf-mono">{l.taxa != null ? `${l.taxa}%` : l.tipo_taxa} · {l.espaco}</span>
                          : <select className="sel sel--mini" aria-label={`Taxa da linha ${i + 1}`} value={l.taxa == null ? '' : String(Math.round(l.taxa))} onChange={(e) => mudaLinha(i, 'taxa', e.target.value)}>
                              {TAXAS.map((t) => <option key={t} value={t}>{t === 0 ? 'Isento 0%' : `${t}%`}</option>)}
                            </select>}
                      </td>
                      <td><input className="inp-num pf-mono" inputMode="decimal" aria-label={`Base da linha ${i + 1}`} value={l.base} onChange={(e) => mudaLinha(i, 'base', e.target.value)} /></td>
                      <td><input className="inp-num pf-mono" inputMode="decimal" aria-label={`IVA da linha ${i + 1}`} value={l.iva} onChange={(e) => mudaLinha(i, 'iva', e.target.value)} /></td>
                      <td className="dir">{form.linhas.length > 1 && <button type="button" className="pf-btn pf-btn--ghost pf-btn--sm" aria-label={`Remover linha ${i + 1}`} onClick={() => muda('linhas', form.linhas.filter((_, j) => j !== i))}>×</button>}</td>
                    </tr>
                  ))}
                  <tr className="tabela-iva__total"><td>Total</td><td className="is-num">{eur(base)}</td><td className="is-num">{eur(iva)}</td><td /></tr>
                </tbody>
              </table>
              <div className="linha">
                <button type="button" className="pf-btn pf-btn--ghost pf-btn--sm" onClick={() => muda('linhas', [...form.linhas, { espaco: 'PT', taxa: 23, base: '', iva: '' }])}>+ Outra taxa</button>
                <label className="total-campo"><span className="pf-field__label">Total da fatura</span>
                  <input className="inp-num pf-mono" inputMode="decimal" value={form.total} onChange={(e) => muda('total', e.target.value)} placeholder="0,00" /></label>
              </div>
            </div>

            <div className="dados__secao">
              <h2>Classificação</h2>
              <div className="duas">
                <label className="pf-field c-compacto"><span className="pf-field__label">Categoria</span>
                  <select className="sel" value={form.categoria_id ?? ''} onChange={(e) => escolherCategoria(e.target.value)}>
                    <option value="">Escolher…</option>
                    {op?.categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                  </select></label>
                <label className="pf-field c-compacto"><span className="pf-field__label">Conta SNC</span>
                  <select className="sel" value={form.conta ?? ''} onChange={(e) => muda('conta', e.target.value || null)}>
                    <option value="">Escolher…</option>
                    {op?.contas.map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} · {c.descricao}</option>)}
                  </select></label>
              </div>
              <label className="pf-field c-compacto"><span className="pf-field__label">IVA na declaração</span>
                <select className="sel" value={form.tratamento_iva} onChange={(e) => muda('tratamento_iva', e.target.value)}>
                  {op?.tratamentos.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
                </select></label>
              <label className="check">
                <input type="checkbox" checked={lembrar} onChange={(e) => setLembrar(e.target.checked)} />
                <span className="ink">Lembrar para este fornecedor
                  <span className="muted14 bloco-linha">{f.regra
                    ? `Classificado pela regra criada ${quando(f.regra.criada).toLowerCase()}. Ao conferir com esta opção, a regra fica atualizada.`
                    : 'As próximas faturas deste NIF entram já classificadas.'}</span>
                </span>
              </label>
            </div>

            <CampoC rotulo={<>Nota <span className="opcional">(só o gabinete vê)</span></>} value={form.notas} onChange={(v) => muda('notas', v)} placeholder="Ex.: confirmar com o cliente se é a mesma encomenda" />
            </fieldset>
          </div>

          {!fechada && (
            <footer className="dados__rodape">
              {rejeitando ? (
                <div className="rejeitar">
                  <input className="pf-field__input" autoFocus placeholder="Motivo (opcional)" value={motivo} onChange={(e) => setMotivo(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); rejeitar(motivo || null) } }} />
                  <button type="button" className="pf-btn pf-btn--danger" onClick={() => rejeitar(motivo || null)} disabled={aGravar}>Rejeitar</button>
                  <button type="button" className="pf-btn pf-btn--ghost" onClick={() => setRejeitando(false)}>Cancelar</button>
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button type="button" className="pf-btn pf-btn--danger" onClick={() => setRejeitando(true)} disabled={aGravar}>Rejeitar</button>
                    <button type="button" className="pf-btn pf-btn--ghost" onClick={gravar} disabled={aGravar}>Gravar sem conferir</button>
                    {!f.mensagens.length && !perguntar && <button type="button" className="pf-btn pf-btn--ghost" onClick={() => setPerguntar(true)}>Perguntar ao cliente</button>}
                  </div>
                  <button type="submit" className="pf-btn pf-btn--primary botao-conferir" disabled={aGravar} aria-busy={aGravar}>
                    {aGravar ? 'Um momento…' : 'Conferida e seguinte'} <kbd>Enter</kbd>
                  </button>
                </>
              )}
            </footer>
          )}
        </form>
      </div>
      {aviso.elemento}
    </div>
  )
}

function CampoC({ rotulo, value, onChange, mono, type = 'text', dica, dicaTipo = 'ok', placeholder }: {
  rotulo: React.ReactNode; value: string; onChange: (v: string) => void; mono?: boolean; type?: string
  dica?: string; dicaTipo?: 'ok' | 'erro'; placeholder?: string
}) {
  return (
    <label className="pf-field c-compacto">
      <span className="pf-field__label">{rotulo}</span>
      <input className={`pf-field__input${mono ? ' pf-mono' : ''}`} type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      {dica && <span className={dicaTipo === 'erro' ? 'erro14' : 'ok14'}>{dica}</span>}
    </label>
  )
}
