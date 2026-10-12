// Ligação à API. A sessão vai num cookie httpOnly: o browser envia-o sozinho.

export type Eu = {
  tipo: 'gabinete' | 'portal'
  utilizador: { id: string; nome: string; email: string; email_confirmado: boolean }
  gabinete: { id: string; nome: string } | null
  papel?: string | null
}

export class ErroApi extends Error {
  constructor(public status: number, public codigo: string, mensagem: string, public campo: string | null = null) {
    super(mensagem)
  }
}

async function pedido<T>(metodo: 'GET' | 'POST' | 'PUT', caminho: string, corpo?: unknown): Promise<T> {
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
  atencao: { nivel: 'bad' | 'warn'; empresa_id: string; empresa: string; codigo: string; titulo: string; detalhe: string; pedido?: boolean }[]
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
