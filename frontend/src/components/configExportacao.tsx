import { useEffect, useRef, useState } from 'react'
import { api, ErroApi, type ConfigExportacao, type ContasExportacao, type ModeloExportacao } from '../api'
import { Gaveta } from './app'
import { Aviso } from './ui'

const TIPOS_DOC: [string, string][] = [['FT', 'Fatura'], ['FS', 'Fatura simplificada'], ['FR', 'Fatura-recibo'], ['NC', 'Nota de crédito'], ['ND', 'Nota de débito'], ['VD', 'Venda a dinheiro']]

/** Contas e diário dos lançamentos + modelos dos programas carregados pelo gabinete. */
export function ConfigGaveta({ aberto, fechar, mudou, mapear }: {
  aberto: boolean; fechar: () => void; mudou: () => void; mapear: (m: ModeloExportacao, sugestao?: Record<string, string>) => void
}) {
  const [c, setC] = useState<ConfigExportacao | null>(null)
  const [form, setForm] = useState<ContasExportacao | null>(null)
  const [erro, setErro] = useState<{ campo: string | null; msg: string } | null>(null)
  const [aGravar, setAGravar] = useState(false)
  const [programa, setPrograma] = useState('sage')
  const [aCarregar, setACarregar] = useState(false)
  const ficheiro = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!aberto) return
    setErro(null)
    api.configExportacao().then((r) => { setC(r); setForm(r.config) }).catch((e) => setErro({ campo: null, msg: e instanceof ErroApi ? e.message : 'Não foi possível abrir.' }))
  }, [aberto])

  const muda = <K extends keyof ContasExportacao>(k: K, v: ContasExportacao[K]) => setForm((f) => f ? { ...f, [k]: v } : f)

  async function gravar() {
    if (!form) return
    setAGravar(true); setErro(null)
    try { await api.gravarConfigExportacao(form); mudou(); fechar() }
    catch (e) { setErro({ campo: e instanceof ErroApi ? e.campo : null, msg: e instanceof ErroApi ? e.message : 'Não foi possível gravar.' }) }
    finally { setAGravar(false) }
  }
  async function carregar(f: File | undefined) {
    if (!f) return
    setACarregar(true); setErro(null)
    try { const m = await api.carregarModelo(f, programa); mudou(); fechar(); mapear(m, m.sugestao) }
    catch (e) { setErro({ campo: null, msg: e instanceof ErroApi ? e.message : 'Não foi possível carregar o modelo.' }) }
    finally { setACarregar(false); if (ficheiro.current) ficheiro.current.value = '' }
  }
  async function apagar(m: ModeloExportacao) {
    try { await api.apagarModelo(m.id); mudou(); setC((x) => x ? { ...x, modelos: x.modelos?.filter((y) => y.id !== m.id) } : x) }
    catch (e) { setErro({ campo: null, msg: e instanceof ErroApi ? e.message : 'Não foi possível apagar.' }) }
  }

  return (
    <Gaveta aberto={aberto} fechar={fechar} titulo="Lançamentos para o programa" subtitulo="Contas usadas nos lançamentos de compras. Valem para todas as empresas do gabinete."
      rodape={<>
        <button type="button" className="pf-btn pf-btn--ghost" onClick={fechar}>Cancelar</button>
        <button type="button" className="pf-btn pf-btn--primary" disabled={aGravar || !form} onClick={gravar}>{aGravar ? 'A gravar…' : 'Gravar'}</button>
      </>}>
      {erro && !erro.campo && <Aviso>{erro.msg}</Aviso>}
      {!form || !c ? <div className="carregar-painel" aria-busy="true">A carregar…</div> : (
        <div className="form">
          <div className="pf-alert pf-alert--info"><span className="pf-alert__tag">Como fica</span>
            <div>Cada fatura: <b>débito</b> na conta da fatura (base e IVA não dedutível), <b>débito</b> no IVA dedutível e <b>crédito</b> no fornecedor. Notas de crédito ao contrário.</div></div>
          <div className="duas">
            <CampoTexto rotulo="Diário de compras" valor={form.diario} mudar={(v) => muda('diario', v)} erro={erro?.campo === 'diario' ? erro.msg : null} ajuda="O código do diário no programa." />
            <CampoTexto rotulo="Conta de fornecedores" valor={form.conta_fornecedor} mono mudar={(v) => muda('conta_fornecedor', v)} erro={erro?.campo === 'conta_fornecedor' ? erro.msg : null} />
          </div>
          <label className="check">
            <input type="checkbox" checked={form.fornecedor_com_nif} onChange={(e) => muda('fornecedor_com_nif', e.target.checked)} />
            <span className="ink">Acrescentar o NIF à conta do fornecedor<span className="muted14 bloco-linha">Ex.: {form.conta_fornecedor}514873205. Deixe desligado se o programa usa uma conta só e controla os terceiros pelo NIF.</span></span>
          </label>
          <div>
            <span className="pf-field__label">IVA dedutível por taxa</span>
            <div className="tres mt8">
              {Object.entries(c.tipos_taxa).map(([k, nome]) => (
                <CampoTexto key={k} rotulo={nome} valor={form.contas_iva[k] ?? ''} mono mudar={(v) => muda('contas_iva', { ...form.contas_iva, [k]: v })}
                  erro={erro?.campo === `contas_iva.${k}` ? erro.msg : null} />
              ))}
            </div>
          </div>
          <div>
            <span className="pf-field__label">Tipo de documento no programa</span>
            <div className="tres mt8">
              {TIPOS_DOC.map(([k, nome]) => <CampoTexto key={k} rotulo={nome} valor={form.tipos_documento[k] ?? k} mudar={(v) => muda('tipos_documento', { ...form.tipos_documento, [k]: v })} />)}
            </div>
          </div>
          <CampoTexto rotulo="Descrição do lançamento" valor={form.descricao} mudar={(v) => muda('descricao', v)} ajuda="Use {fornecedor}, {numero} e {nif}." />

          <div className="sep" />
          <div>
            <h3 className="forte17" style={{ margin: 0 }}>Modelos dos programas</h3>
            <p className="muted14" style={{ margin: '4px 0 0' }}>Para Sage, Primavera, PHC ou outro: carregue o Excel de importação de lançamentos do programa. A Kontiq preenche-o com os lançamentos, uma folha por empresa.</p>
          </div>
          {c.modelos && c.modelos.length > 0 && (
            <ul className="lista-pedidos">
              {c.modelos.map((m) => (
                <li key={m.id}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="forte15 cortar">{m.nome}</div>
                    <div className="muted13">{m.programa_nome} · {m.cabecalhos.length} colunas · {Object.keys(m.mapeamento).length ? `${Object.keys(m.mapeamento).length} preenchidas` : 'por mapear'}</div>
                  </div>
                  <button type="button" className="pf-btn pf-btn--sm" onClick={() => { fechar(); mapear(m) }}>Colunas</button>
                  <button type="button" className="pf-btn pf-btn--sm pf-btn--ghost" onClick={() => apagar(m)}>Apagar</button>
                </li>
              ))}
            </ul>
          )}
          <div className="linha" style={{ gap: 8, justifyContent: 'flex-start', flexWrap: 'wrap' }}>
            <select className="sel" style={{ width: 'auto', minWidth: 160 }} aria-label="Programa" value={programa} onChange={(e) => setPrograma(e.target.value)}>
              {c.programas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
            <button type="button" className="pf-btn" disabled={aCarregar} onClick={() => ficheiro.current?.click()}>{aCarregar ? 'A ler o modelo…' : 'Carregar modelo (.xlsx)'}</button>
            <input ref={ficheiro} type="file" accept=".xlsx" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={(e) => carregar(e.target.files?.[0])} />
          </div>
        </div>
      )}
    </Gaveta>
  )
}

/** Que dados vão em cada coluna do modelo do programa. */
export function MapearGaveta({ modelo, sugestao, fechar, gravado }: {
  modelo: ModeloExportacao | null; sugestao?: Record<string, string>; fechar: () => void; gravado: (m: ModeloExportacao) => void
}) {
  const [campos, setCampos] = useState<{ id: string; nome: string }[]>([])
  const [mapa, setMapa] = useState<Record<string, string>>({})
  const [nome, setNome] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [aGravar, setAGravar] = useState(false)

  useEffect(() => {
    if (!modelo) return
    setErro(null); setNome(modelo.nome)
    setMapa(Object.keys(modelo.mapeamento).length ? modelo.mapeamento : sugestao ?? {})
    api.configExportacao().then((r) => setCampos(r.campos)).catch(() => {})
  }, [modelo, sugestao])

  async function gravar() {
    if (!modelo) return
    setAGravar(true); setErro(null)
    try { gravado(await api.mapearModelo(modelo.id, { nome, mapeamento: mapa })) }
    catch (e) { setErro(e instanceof ErroApi ? e.message : 'Não foi possível gravar.') }
    finally { setAGravar(false) }
  }

  return (
    <Gaveta aberto={!!modelo} fechar={fechar} titulo="Colunas do modelo"
      subtitulo={modelo ? `${modelo.programa_nome} · folha "${modelo.folha}" · títulos na linha ${modelo.linha_cabecalho}. Confirme o que vai em cada coluna.` : ''}
      rodape={<>
        <button type="button" className="pf-btn pf-btn--ghost" onClick={fechar}>Cancelar</button>
        <button type="button" className="pf-btn pf-btn--primary" disabled={aGravar} onClick={gravar}>{aGravar ? 'A gravar…' : 'Gravar colunas'}</button>
      </>}>
      {modelo && (
        <div className="form">
          {erro && <Aviso>{erro}</Aviso>}
          {sugestao && !Object.keys(modelo.mapeamento).length && (
            <div className="pf-alert pf-alert--info"><span className="pf-alert__tag">Sugestão</span>
              <div>Preenchemos o que conseguimos reconhecer pelos títulos. Confirme cada linha antes de gravar.</div></div>
          )}
          <CampoTexto rotulo="Nome do modelo" valor={nome} mudar={setNome} />
          <table className="pf-table tabela-mapa">
            <thead><tr><th>Coluna no modelo</th><th>O que a Kontiq escreve</th></tr></thead>
            <tbody>
              {modelo.cabecalhos.map((cab) => (
                <tr key={cab.col}>
                  <td><span className="pf-mono muted13">{letra(cab.col)}</span> <span className="ink">{cab.nome}</span></td>
                  <td>
                    <select className="sel sel--mini" aria-label={`Coluna ${cab.nome}`} value={mapa[String(cab.col)] ?? ''}
                      onChange={(e) => setMapa((m) => { const n = { ...m }; if (e.target.value) n[String(cab.col)] = e.target.value; else delete n[String(cab.col)]; return n })}>
                      <option value="">— deixar em branco —</option>
                      {campos.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted13" style={{ margin: 0 }}>Precisa de, pelo menos, a conta e os valores (débito e crédito, ou valor com sinal). As linhas de exemplo do modelo são apagadas ao exportar.</p>
        </div>
      )}
    </Gaveta>
  )
}

function letra(n: number) {
  let s = ''
  while (n > 0) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = Math.floor((n - 1) / 26) }
  return s
}

function CampoTexto({ rotulo, valor, mudar, erro, ajuda, mono }: { rotulo: string; valor: string; mudar: (v: string) => void; erro?: string | null; ajuda?: string; mono?: boolean }) {
  return (
    <label className="pf-field c-compacto">
      <span className="pf-field__label">{rotulo}</span>
      <input className={`pf-field__input${mono ? ' pf-mono' : ''}${erro ? ' is-erro' : ''}`} value={valor} onChange={(e) => mudar(e.target.value)} />
      {erro ? <span className="erro14">{erro}</span> : ajuda ? <span className="muted13">{ajuda}</span> : null}
    </label>
  )
}
