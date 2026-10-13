// Ligação à API. A sessão vai num cookie httpOnly: o browser envia-o sozinho.

export type Eu = {
  tipo: 'gabinete' | 'portal'
  utilizador: { id: string; nome: string; email: string; email_confirmado: boolean }
  gabinete: { id: string; nome: string } | null
  papel?: string | null
  subscricao?: ResumoSubscricao
}

export type ResumoSubscricao = {
  plano: string; plano_nome: string; estado: 'teste' | 'expirada' | 'ativa' | 'em_atraso' | 'suspensa' | 'cancelada'
  estado_nome: string; dias: number | null; pode_trabalhar: boolean; aviso: string | null
}
export type PlanoSub = {
  id: string; nome: string; para: string; inclui: string[]; destaque: boolean; empresas: number; pessoas: number | null
  mensal: string; anual: string; anual_por_mes: string; cabe: boolean
}
export type PagamentoSub = {
  id: string; plano: string; plano_nome: string; ciclo: 'mensal' | 'anual'; valor: string; iva: string; total: string
  estado: 'pendente' | 'pago' | 'falhado' | 'anulado'; fornecedor: string; criado_em: string; pago_em: string | null
  periodo_fim: string | null; quem: string | null; modo?: string
}
export type Subscricao = ResumoSubscricao & {
  ciclo: 'mensal' | 'anual'; cancelar_no_fim: boolean; fim_teste: string | null; proxima_renovacao: string | null; preco: string
  uso: { empresas: number; pessoas: number; convites: number }; limites: { empresas: number; pessoas: number | null }
  planos: PlanoSub[]; pagamentos: PagamentoSub[]; pode_gerir: boolean; modo_pagamento: string
}

export class ErroApi extends Error {
  constructor(public status: number, public codigo: string, mensagem: string, public campo: string | null = null) {
    super(mensagem)
  }
}

async function pedido<T>(metodo: 'GET' | 'POST' | 'PUT' | 'DELETE', caminho: string, corpo?: unknown): Promise<T> {
  let r: Response
  try {
    r = await fetch(caminho, {
      method: metodo,
      credentials: 'same-origin',
      headers: corpo === undefined ? {} : { 'Content-Type': 'application/json' },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    })
  } catch {
    throw new ErroApi(0, 'rede', 'Sem ligação ao servidor. Verifique a internet e tente outra vez.')
  }
  const dados = await r.json().catch(() => null)
  if (!r.ok) {
    if (dados && typeof dados.mensagem === 'string') throw new ErroApi(r.status, dados.codigo, dados.mensagem, dados.campo)
    throw new ErroApi(r.status, 'erro', 'Algo correu mal do nosso lado. Tente outra vez daqui a pouco.')
  }
  return dados as T
}

export const api = {
  eu: () => pedido<Eu>('GET', '/api/auth/eu'),
  entrar: (email: string, password: string, manter: boolean) => pedido<Eu>('POST', '/api/auth/entrar', { email, password, manter }),
  sair: () => pedido('POST', '/api/auth/sair'),
  validarConta: (nome: string, email: string, password: string) =>
    pedido('POST', '/api/auth/registo/validar-conta', { nome, email, password }),
  forca: (password: string, email: string, nome: string) =>
    pedido<{ forca: number; problema: string | null }>('POST', '/api/auth/password/forca', { password, email, nome }),
  registar: (corpo: unknown) => pedido<Eu>('POST', '/api/auth/registo', corpo),
  confirmarEmail: (codigo: string) => pedido<Eu>('POST', '/api/auth/email/confirmar', { codigo }),
  reenviarConfirmacao: () => pedido('POST', '/api/auth/email/reenviar'),
  pedirReposicao: (email: string) => pedido('POST', '/api/auth/password/pedir', { email }),
  repor: (email: string, codigo: string, password: string) => pedido<Eu>('POST', '/api/auth/password/repor', { email, codigo, password }),
  pedirCodigoPortal: (canal: 'sms' | 'email', destino: string) => pedido('POST', '/api/portal/codigo', { canal, destino }),
  entrarPortal: (canal: 'sms' | 'email', destino: string, codigo: string) =>
    pedido<Eu>('POST', '/api/portal/entrar', { canal, destino, codigo }),
  resumoPainel: () => pedido<ResumoPainel>('GET', '/api/painel/resumo'),
  resumoPortal: () => pedido<ResumoPortal>('GET', '/api/portal/resumo'),
  painel: (periodo: string) => pedido<Painel>('GET', `/api/painel?periodo=${encodeURIComponent(periodo)}`),
  criarEmpresa: (dados: DadosEmpresa) => pedido<{ id: string; nome: string }>('POST', '/api/empresas', dados),
  editarEmpresa: (id: string, dados: DadosEmpresa) => pedido<{ id: string; nome: string }>('PUT', `/api/empresas/${id}`, dados),
  convidar: (id: string) => pedido<{ canal: 'sms' | 'email' }>('POST', `/api/empresas/${id}/convite`),
  faturasEmpresa: (id: string, periodo: string) => pedido<FaturasEmpresa>('GET', `/api/empresas/${id}/faturas?periodo=${encodeURIComponent(periodo)}`),
  classificacao: () => pedido<Opcoes>('GET', '/api/classificacao'),
  fatura: (id: string) => pedido<Fatura>('GET', `/api/faturas/${id}`),
  gravarFatura: (id: string, dados: DadosFatura) => pedido<Fatura>('PUT', `/api/faturas/${id}`, dados),
  conferir: (id: string, lembrar: boolean, dados?: DadosFatura) =>
    pedido<{ seguinte: string | null; fatura: Fatura }>('POST', `/api/faturas/${id}/conferir`, { lembrar, dados }),
  conferirLote: (ids: string[]) => pedido<{ conferidas: number; falhadas: { id: string; mensagem: string }[] }>('POST', '/api/faturas/conferir-lote', { ids }),
  rejeitar: (id: string, motivo: string | null) => pedido<Fatura>('POST', `/api/faturas/${id}/rejeitar`, { motivo }),
  reabrir: (id: string) => pedido<Fatura>('POST', `/api/faturas/${id}/reabrir`),
  resolverProblema: (id: string, pid: string) => pedido<Fatura>('POST', `/api/faturas/${id}/problemas/${pid}/resolver`),
  carregar: async (empresaId: string, periodo: string, ficheiros: File[]) => {
    const fd = new FormData()
    ficheiros.forEach((f) => fd.append('ficheiros', f, f.name))
    fd.append('periodo', periodo)
    let r: Response
    try { r = await fetch(`/api/empresas/${empresaId}/documentos`, { method: 'POST', body: fd, credentials: 'same-origin' }) }
    catch { throw new ErroApi(0, 'rede', 'Sem ligação ao servidor. Verifique a internet e tente outra vez.') }
    const dados = await r.json().catch(() => null)
    if (!r.ok) throw new ErroApi(r.status, dados?.codigo ?? 'erro', dados?.mensagem ?? (r.status === 413 ? 'Ficheiros demasiado grandes.' : 'Não foi possível carregar.'))
    return dados as { resultados: ResultadoCarregar[] }
  },
  portalInicio: () => pedido<PortalInicio>('GET', '/api/portal/inicio'),
  enviarPortal: async (ficheiros: File[]) => {
    const fd = new FormData()
    ficheiros.forEach((f) => fd.append('ficheiros', f, f.name))
    let r: Response
    try { r = await fetch('/api/portal/documentos', { method: 'POST', body: fd, credentials: 'same-origin' }) }
    catch { throw new ErroApi(0, 'rede', 'Sem ligação. Verifique a internet e tente outra vez.') }
    const dados = await r.json().catch(() => null)
    if (!r.ok) throw new ErroApi(r.status, dados?.codigo ?? 'erro', dados?.mensagem ?? 'Não foi possível enviar.')
    return dados as { resultados: { nome: string; ok: boolean; repetido: boolean; mensagem: string; fornecedor: string | null; total: string | null }[] }
  },
  previsaoExportacao: (periodo: string) => pedido<PrevisaoExportacao>('GET', `/api/exportacoes/previsao?periodo=${encodeURIComponent(periodo)}`),
  configExportacao: () => pedido<ConfigExportacao>('GET', '/api/exportacoes/configuracao'),
  gravarConfigExportacao: (c: ContasExportacao) => pedido<ConfigExportacao>('PUT', '/api/exportacoes/configuracao', c),
  carregarModelo: async (ficheiro: File, programa: string) => {
    const fd = new FormData()
    fd.append('ficheiro', ficheiro, ficheiro.name)
    fd.append('programa', programa)
    let r: Response
    try { r = await fetch('/api/exportacoes/modelos', { method: 'POST', body: fd, credentials: 'same-origin' }) }
    catch { throw new ErroApi(0, 'rede', 'Sem ligação ao servidor. Verifique a internet e tente outra vez.') }
    const dados = await r.json().catch(() => null)
    if (!r.ok) throw new ErroApi(r.status, dados?.codigo ?? 'erro', dados?.mensagem ?? 'Não foi possível carregar o modelo.')
    return dados as ModeloExportacao & { sugestao: Record<string, string> }
  },
  mapearModelo: (id: string, dados: { nome?: string; programa?: string; mapeamento: Record<string, string> }) =>
    pedido<ModeloExportacao>('PUT', `/api/exportacoes/modelos/${id}`, dados),
  apagarModelo: (id: string) => pedido('DELETE', `/api/exportacoes/modelos/${id}`),
  exportar: (dados: { periodo: string; empresas: string[]; formato: string; incluir_exportadas: boolean; marcar: boolean; modelo?: string }) =>
    pedido<{ lote: string; nome: string; faturas: number; empresas: number }>('POST', '/api/exportacoes', dados),
  desfazerExportacao: (lote: string) => pedido<{ faturas: number }>('POST', `/api/exportacoes/${lote}/desfazer`),
  perguntar: (id: string, texto: string) =>
    pedido<{ duvida: 'pergunta' | 'resposta' | null; mensagens: MensagemDuvida[]; avisado: 'sms' | 'email' | null }>('POST', `/api/faturas/${id}/duvida`, { texto }),
  resolverDuvida: (id: string) => pedido<{ duvida: null; mensagens: MensagemDuvida[] }>('POST', `/api/faturas/${id}/duvida/resolver`),
  responderDuvida: (id: string, texto: string) => pedido<{ estado: 'resposta'; mensagens: MensagemDuvida[] }>('POST', `/api/portal/duvidas/${id}`, { texto }),
  subscricao: () => pedido<Subscricao>('GET', '/api/subscricao'),
  escolherPlano: (plano: string, ciclo: string) => pedido<{ pagamento: string; url: string }>('POST', '/api/subscricao/pagamentos', { plano, ciclo }),
  pagamentoSub: (id: string) => pedido<PagamentoSub>('GET', `/api/subscricao/pagamentos/${id}`),
  simularPagamento: (id: string, sucesso: boolean) => pedido<PagamentoSub>('POST', `/api/subscricao/pagamentos/${id}/simular`, { sucesso }),
  cancelarSub: () => pedido<Subscricao>('POST', '/api/subscricao/cancelar'),
  retomarSub: () => pedido<Subscricao>('POST', '/api/subscricao/retomar'),
  todasFaturas: (p: { periodo: string; filtro: string; q: string; empresa: string; inicio: number }) => {
    const qs = new URLSearchParams({ periodo: p.periodo, filtro: p.filtro, inicio: String(p.inicio) })
    if (p.q) qs.set('q', p.q)
    if (p.empresa) qs.set('empresa', p.empresa)
    return pedido<FaturasGabinete>('GET', `/api/faturas?${qs}`)
  },
  pedidos: (periodo: string) => pedido<Pedidos>('GET', `/api/pedidos?periodo=${encodeURIComponent(periodo)}`),
  pedirTodas: (periodo: string) => pedido<{ enviados: { nome: string; canal: string }[]; ignoradas: { nome: string; motivo: string }[] }>('POST', '/api/pedidos/todas', { periodo }),
  efatura: (eid: string, periodo: string) => pedido<CruzamentoEfatura>('GET', `/api/empresas/${eid}/efatura?periodo=${encodeURIComponent(periodo)}`),
  importarEfatura: async (eid: string, ficheiro: File) => {
    const fd = new FormData()
    fd.append('ficheiro', ficheiro, ficheiro.name)
    let r: Response
    try { r = await fetch(`/api/empresas/${eid}/efatura`, { method: 'POST', body: fd, credentials: 'same-origin' }) }
    catch { throw new ErroApi(0, 'rede', 'Sem ligação ao servidor. Verifique a internet e tente outra vez.') }
    const dados = await r.json().catch(() => null)
    if (!r.ok) throw new ErroApi(r.status, dados?.codigo ?? 'erro', dados?.mensagem ?? 'Não foi possível ler o ficheiro.')
    return dados as { linhas: number; meses: { periodo: string; periodo_txt: string; em_falta: number; so_kontiq: number; ok: number }[] }
  },
  pedirEfatura: (eid: string, periodo: string) => pedido<{ canal: string; faturas: number }>('POST', `/api/empresas/${eid}/efatura/pedir`, { periodo }),
  resumoIva: (eid: string, periodo: string, tipo?: string) =>
    pedido<ResumoIva>('GET', `/api/empresas/${eid}/iva?periodo=${encodeURIComponent(periodo)}${tipo ? `&tipo=${tipo}` : ''}`),
  resumoSemanal: () => pedido<{ ativo: boolean; enviado_em: string | null }>('GET', '/api/resumo'),
  mudarResumoSemanal: (ativo: boolean) => pedido<{ ativo: boolean }>('PUT', '/api/resumo', { ativo }),
  enviarResumo: () => pedido<{ email: string }>('POST', '/api/resumo/enviar'),
  equipa: () => pedido<Equipa>('GET', '/api/equipa'),
  convidarColega: (email: string, papel: string) => pedido<{ id: string; email: string }>('POST', '/api/equipa/convites', { email, papel }),
  reenviarConvite: (id: string) => pedido('POST', `/api/equipa/convites/${id}/reenviar`),
  cancelarConvite: (id: string) => pedido('DELETE', `/api/equipa/convites/${id}`),
  mudarPapel: (id: string, papel: string) => pedido('PUT', `/api/equipa/membros/${id}`, { papel }),
  removerMembro: (id: string) => pedido('DELETE', `/api/equipa/membros/${id}`),
  verConvite: (token: string) => pedido<ConviteEquipa>('GET', `/api/convites/${encodeURIComponent(token)}`),
  aceitarConvite: (token: string, nome: string, password: string) =>
    pedido('POST', `/api/convites/${encodeURIComponent(token)}/aceitar`, { nome, password }),
  pedirFaturas: (id: string, periodo: string) => pedido<{ canal: 'sms' | 'email' }>('POST', `/api/empresas/${id}/pedir-faturas`, { periodo }),
}

export type Estado = 'bad' | 'warn' | 'ok' | 'none'

export type EmpresaPainel = {
  id: string; nome: string; nif: string; estado: Estado
  faturas: number; total: number; total_txt: string; conferidas: number; por_conferir: number; com_erro: number
  ultima: string; pedido_em: string | null; portal: boolean; periodicidade_iva: string
  contacto: { nome: string | null; telefone: string | null; email: string | null }
}

export type Painel = {
  periodo: string; periodo_txt: string
  gabinete: { nome: string; programa: string | null }
  totais: { total: number; total_txt: string; faturas: number; empresas: number; conferidas: number; por_conferir: number
    ia_por_conferir: number; problemas: number; problemas_txt: string; pct_conferido: number }
  atencao: { nivel: 'bad' | 'warn'; empresa_id: string; empresa: string; codigo: string; titulo: string; detalhe: string; pedido?: boolean; fatura_id?: string }[]
  empresas: EmpresaPainel[]
  onboarding: { empresas: boolean; portal: boolean }
}

export type DadosEmpresa = {
  nif: string; nome: string; periodicidade_iva: string
  contacto_nome: string | null; telefone: string | null; email: string | null; convidar: boolean
}

export type ResumoPainel = {
  gabinete: { nome: string; nif: string; programa: string | null }
  utilizador: { nome: string }
  empresas: number
  faturas_mes: number
  membros: number
  mes: string
}

export type ResumoPortal = {
  empresa: { nome: string; nif: string }
  gabinete: { nome: string }
  utilizador: { nome: string }
  faturas_mes: number
  mes: string
}

export type ResultadoCarregar = {
  nome: string; estado: 'lida' | 'ia' | 'manual' | 'repetido' | 'erro'; mensagem: string
  fatura_id: string | null; fornecedor: string | null; numero: string | null; total: string | null; metodo: string | null
}

export type EstadoFatura = 'ok' | 'warn' | 'bad' | 'rejeitada'

export type LinhaFatura = {
  id: string; data: string | null; fornecedor: string | null; nif: string | null; numero: string | null; tipo: string
  metodo: 'qr' | 'ia' | 'manual'; confianca: number | null; conta: string | null; conta_nome: string | null
  iva: string; total: string; total_n: number; estado: EstadoFatura; nota: string | null; nota_curta: string | null; exportada?: boolean; duvida?: 'pergunta' | 'resposta' | null; fora_efatura?: boolean
}

export type FaturasEmpresa = {
  empresa: { id: string; nome: string; nif: string; periodicidade_iva: string; portal: string | null; email_entrada: string }
  periodo: string; periodo_txt: string
  totais: { faturas: number; total_txt: string; iva_txt: string; conferidas: number; por_conferir: number; qr: number; manual: number; problemas: number }
  faturas: LinhaFatura[]
  efatura: { importado_em: string | null; total: number; em_falta: number; so_kontiq: number; ok: number }
}

export type Opcoes = {
  categorias: { id: string; nome: string; conta: string | null; tratamento: string }[]
  contas: { codigo: string; descricao: string }[]
  tratamentos: { id: string; nome: string }[]
  tipos: { id: string; nome: string }[]
}

export type Fatura = {
  id: string; estado: 'por_conferir' | 'conferida' | 'exportada' | 'rejeitada'; estado_vista: EstadoFatura
  empresa: { id: string; nome: string; nif: string }; periodo: string
  documento: { id: string; nome: string; tipo: string; canal: string; recebido: string } | null
  metodo: 'qr' | 'ia' | 'manual'; confianca: number | null; modo_leitura?: string | null
  fornecedor: { nome: string; nif: string; pais: string; faturas: number; conhecido: boolean }
  tipo_documento: string; numero: string; atcud: string; data: string; nif_adquirente: string | null
  linhas: { espaco: string; tipo_taxa: string; taxa: number | null; base: string; iva: string }[]
  base_total: string; iva_total: string; total: string; total_txt: string
  categoria_id: string | null; conta: string | null; tratamento_iva: string; origem_classificacao: string
  regra: { criada: string; geral: boolean } | null
  notas: string
  duvida: 'pergunta' | 'resposta' | null
  mensagens: MensagemDuvida[]
  contacto: { nome: string | null; telefone: string | null; email: string | null }
  problemas: { id: string; codigo: string; nivel: 'erro' | 'aviso'; mensagem: string }[]
  duplicado_de: string | null
  fila: { posicao: number; total: number; anterior: string | null; seguinte: string | null }
  conferida_em: string | null
}

export type DadosFatura = {
  fornecedor: string; nif: string; pais: string; tipo_documento: string; numero: string; atcud: string; data: string
  linhas: { espaco: string; tipo_taxa?: string | null; taxa: number | null; base: string; iva: string }[]
  total: string; categoria_id: string | null; conta: string | null; tratamento_iva: string; notas: string
}

export type PrevisaoExportacao = {
  periodo: string; periodo_txt: string
  empresas: { id: string; nome: string; nif: string; prontas: number; por_conferir: number; exportadas: number; total_txt: string }[]
  formatos: { id: string; nome: string }[]
  modelos: { id: string; nome: string; programa: string; programa_nome: string; pronto: boolean }[]
  historico: { lote: string; em: string; formato: string; formato_nome: string; periodo: string; periodo_txt: string; faturas: number
    empresas: number; empresa: string | null; nome: string | null; quem: string | null; marcou: boolean; desfeita: string | null }[]
}

export type PortalInicio = {
  empresa: { nome: string; nif: string }; gabinete: { nome: string }; utilizador: { nome: string }
  mes_txt: string; enviados_mes: number
  enviados: { id: string; nome: string; enviado_em: string; canal: string; por_mim: boolean; estado: 'recebida' | 'tratada' | 'rejeitada'
    fornecedor: string | null; total: string | null; data: string | null }[]
  pedido: { periodo_txt: string; enviado_em: string | null } | null
  duvidas: DuvidaPortal[]
}

export type MensagemDuvida = { id: string; lado: 'gabinete' | 'cliente'; autor: string | null; texto: string; em: string }
export type DuvidaPortal = {
  fatura_id: string; estado: 'pergunta' | 'resposta'; numero: string | null; fornecedor: string | null
  data: string | null; total: string | null; documento: { id: string; nome: string } | null; mensagens: MensagemDuvida[]
}

export type MembroEquipa = {
  id: string; utilizador_id: string; nome: string; email: string; papel: 'dono' | 'admin' | 'colaborador'; papel_nome: string
  ultimo_login: string | null; ativo: boolean
}
export type Equipa = {
  eu: { id: string; papel: string; pode_gerir: boolean }
  membros: MembroEquipa[]
  convites: { id: string; email: string; papel: string; papel_nome: string; criado_em: string; expira_em: string }[]
}
export type ConviteEquipa = { gabinete: string; email: string; papel: string; convidado_por: string | null; conta_existe: boolean }

export type FaturasGabinete = {
  periodo: string; periodo_txt: string; filtro: string; q: string
  contagens: Record<'todas' | 'por_conferir' | 'problemas' | 'duvidas' | 'conferidas' | 'exportadas' | 'rejeitadas', number>
  total: number; total_txt: string; mais: boolean
  faturas: (LinhaFatura & { empresa: { id: string; nome: string }; estado_bd: string })[]
  empresas: { id: string; nome: string }[]
}
export type Pedidos = {
  periodo: string; periodo_txt: string
  em_falta: { id: string; nome: string; nif: string; portal: boolean; pedido_em: string | null; meio: 'sms' | 'email' | null
    contacto: { nome: string | null; telefone: string | null; email: string | null } }[]
  pedidos: { id: string; empresa: { id: string; nome: string }; periodo: string; periodo_txt: string; canal: string
    enviado_em: string; quem: string | null; respondido: boolean }[]
  duvidas: { fatura_id: string; estado: 'pergunta' | 'resposta'; empresa: { id: string; nome: string }; fornecedor: string | null
    numero: string | null; total: string | null; ultima: { texto: string; lado: 'gabinete' | 'cliente'; em: string } | null }[]
  contagens: { em_falta: number; respostas: number; a_espera: number }
}

export type ContasExportacao = {
  diario: string; conta_fornecedor: string; fornecedor_com_nif: boolean
  contas_iva: Record<string, string>; tipos_documento: Record<string, string>; descricao: string
}
export type ModeloExportacao = {
  id: string; nome: string; programa: string; programa_nome: string; folha: string | null; linha_cabecalho: number
  cabecalhos: { col: number; nome: string }[]; mapeamento: Record<string, string>; criado_em: string | null
}
export type ConfigExportacao = {
  config: ContasExportacao; padrao: ContasExportacao; tipos_taxa: Record<string, string>
  campos: { id: string; nome: string }[]; programas: { id: string; nome: string }[]; modelos?: ModeloExportacao[]
}

export type CruzamentoEfatura = {
  periodo: string; periodo_txt: string; importado_em: string | null; total_efatura: number; ok: number
  em_falta: { id: string; nif: string; fornecedor: string | null; numero: string; tipo: string | null; data: string; total: string | null }[]
  so_kontiq: { id: string; nif: string; fornecedor: string | null; numero: string | null; data: string | null; total: string }[]
}

type ValoresIva = { base: string; iva: string; dedutivel: string; base_n: number; iva_n: number; dedutivel_n: number }
export type ResumoIva = {
  empresa: { id: string; nome: string; nif: string; periodicidade_iva: string }
  tipo: 'mes' | 'trimestre'; periodo: string; periodo_txt: string; faturas: number; por_conferir: number; notas_credito: number
  totais: ValoresIva & { nao_dedutivel: string }
  campos: { campo: string; nome: string; valor: string; valor_n: number }[]
  taxas: (ValoresIva & { espaco: string; taxa: string; pct: number | null })[]
  tratamentos: (ValoresIva & { id: string; nome: string })[]
  contas: (ValoresIva & { conta: string; nome: string })[]
}
