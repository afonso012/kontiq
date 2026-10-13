import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ErroApi, type CruzamentoEfatura } from '../api'
import { Gaveta } from './app'
import { Aviso } from './ui'
import { quando } from '../util'

const dataCurta = (iso: string | null) => iso ? new Date(iso).toLocaleDateString('pt-PT') : '—'

/** Cruzar as faturas recebidas com a lista do e-Fatura (CSV do Portal das Finanças). */
export function EfaturaGaveta({ aberto, fechar, empresaId, empresa, periodo, mudou, avisar }: {
  aberto: boolean; fechar: () => void; empresaId: string; empresa: string; periodo: string
  mudou: () => void; avisar: (m: string, tipo?: 'ok' | 'bad') => void
}) {
  const [c, setC] = useState<CruzamentoEfatura | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [aLer, setALer] = useState(false)
  const [aPedir, setAPedir] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const ler = useCallback(() => {
    api.efatura(empresaId, periodo).then(setC).catch((e) => setErro(e instanceof ErroApi ? e.message : 'Não foi possível abrir.'))
  }, [empresaId, periodo])
  useEffect(() => { if (aberto) { setErro(null); setC(null); ler() } }, [aberto, ler])

  async function importar(f: File | undefined) {
    if (!f) return
    setALer(true); setErro(null)
    try {
      const r = await api.importarEfatura(empresaId, f)
      const outros = r.meses.filter((m) => m.periodo.slice(0, 7) !== periodo)
      avisar(`${r.linhas} ${r.linhas === 1 ? 'fatura lida' : 'faturas lidas'} do e-Fatura${outros.length ? ` (também ${outros.map((m) => m.periodo_txt).join(', ')})` : ''}.`)
      ler(); mudou()
    } catch (e) { setErro(e instanceof ErroApi ? e.message : 'Não foi possível ler o ficheiro.') }
    finally { setALer(false); if (input.current) input.current.value = '' }
  }
  async function pedir() {
    setAPedir(true)
    try { const r = await api.pedirEfatura(empresaId, periodo); avisar(`Pedido enviado por ${r.canal === 'sms' ? 'SMS' : 'email'} com ${r.faturas} ${r.faturas === 1 ? 'fatura' : 'faturas'} em falta.`); mudou() }
    catch (e) { avisar(e instanceof ErroApi ? e.message : 'Não foi possível enviar.', 'bad') }
    finally { setAPedir(false) }
  }

  const importado = !!c?.importado_em
  return (
    <Gaveta aberto={aberto} fechar={fechar} titulo="Cruzar com o e-Fatura" subtitulo={`${empresa} · ${c?.periodo_txt ?? ''}`}
      rodape={<>
        <button type="button" className="pf-btn pf-btn--ghost" onClick={fechar}>Fechar</button>
        <button type="button" className={`pf-btn${importado ? '' : ' pf-btn--primary'}`} disabled={aLer} onClick={() => input.current?.click()}>
          {aLer ? 'A ler…' : importado ? 'Carregar outra vez' : 'Carregar ficheiro do e-Fatura'}
        </button>
        <input ref={input} type="file" accept=".csv,text/csv,text/plain" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={(e) => importar(e.target.files?.[0])} />
      </>}>
      <div className="form">
        {erro && <Aviso>{erro}</Aviso>}
        {!c ? <div className="carregar-painel" aria-busy="true">A carregar…</div> : !importado ? (
          <>
            <p className="muted15" style={{ margin: 0 }}>Veja que faturas de compra os fornecedores comunicaram às Finanças e quais o cliente ainda não enviou.</p>
            <ol className="passos-efatura">
              <li>No Portal das Finanças, entre no <b>e-Fatura</b> com o NIF da empresa e escolha <b>Adquirente</b>.</li>
              <li>Em <b>Verificar faturas</b>, escolha o mês de {c.periodo_txt.split(' ')[0]} e carregue em <b>Pesquisar</b>.</li>
              <li>Carregue em <b>Obter dados para Excel</b> e guarde o ficheiro.</li>
              <li>Carregue-o aqui, tal como veio. Pode trazer vários meses: cada um fica no seu sítio.</li>
            </ol>
          </>
        ) : (
          <>
            <div className="efatura-resumo">
              <div><span className="efatura-resumo__n">{c.total_efatura}</span><span className="muted13">nas Finanças</span></div>
              <div><span className="efatura-resumo__n ok">{c.ok}</span><span className="muted13">recebidas</span></div>
              <div><span className={`efatura-resumo__n${c.em_falta.length ? ' warn' : ''}`}>{c.em_falta.length}</span><span className="muted13">em falta</span></div>
              <div><span className={`efatura-resumo__n${c.so_kontiq.length ? ' bad' : ''}`}>{c.so_kontiq.length}</span><span className="muted13">não comunicadas</span></div>
            </div>
            <p className="muted13" style={{ margin: 0 }}>Ficheiro carregado {quando(c.importado_em!).toLowerCase()}. Quando o cliente enviar as que faltam, saem da lista sozinhas.</p>

            <section>
              <div className="linha" style={{ marginBottom: 8 }}>
                <h3 className="forte15" style={{ margin: 0 }}>Em falta ({c.em_falta.length})</h3>
                {c.em_falta.length > 0 && <button type="button" className="pf-btn pf-btn--sm pf-btn--primary" disabled={aPedir} onClick={pedir}>{aPedir ? 'A enviar…' : 'Pedir ao cliente'}</button>}
              </div>
              {c.em_falta.length === 0 ? <p className="muted14" style={{ margin: 0 }}>Todas as faturas do e-Fatura já foram recebidas.</p> : (
                <ul className="lista-pedidos">
                  {c.em_falta.map((x) => (
                    <li key={x.id}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="forte15 cortar">{x.fornecedor ?? `NIF ${x.nif}`}</div>
                        <div className="muted13"><span className="pf-mono">{x.numero}</span> · {dataCurta(x.data)}{x.tipo ? ` · ${x.tipo}` : ''}</div>
                      </div>
                      <span className="pf-mono">{x.total ?? '—'}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {c.so_kontiq.length > 0 && (
              <section>
                <h3 className="forte15" style={{ margin: '0 0 4px' }}>Recebidas mas não comunicadas ({c.so_kontiq.length})</h3>
                <p className="muted13" style={{ margin: '0 0 8px' }}>O fornecedor não as comunicou às Finanças. Confirme com o fornecedor antes de deduzir o IVA.</p>
                <ul className="lista-pedidos">
                  {c.so_kontiq.map((x) => (
                    <li key={x.id}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <Link to={`/faturas/${x.id}`} className="forte15 cortar link-empresa">{x.fornecedor ?? `NIF ${x.nif}`}</Link>
                        <div className="muted13"><span className="pf-mono">{x.numero ?? '—'}</span> · {dataCurta(x.data)}</div>
                      </div>
                      <span className="pf-mono">{x.total}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </Gaveta>
  )
}
