/** Utilitários partilhados pelos ecrãs. */

export function nifValido(nif: string) {
  if (!/^([123568]\d|45|7[0124579]|9[0189])\d{7}$/.test(nif)) return false
  const soma = [...nif.slice(0, 8)].reduce((s, d, i) => s + Number(d) * (9 - i), 0)
  const resto = soma % 11
  return Number(nif[8]) === (resto < 2 ? 0 : 11 - resto)
}

export const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
const MESES_CURTOS = ['jan.', 'fev.', 'mar.', 'abr.', 'mai.', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.']

export const periodoAtual = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }

export function mudarPeriodo(p: string, delta: number) {
  const [a, m] = p.split('-').map(Number)
  const d = new Date(a, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** "Hoje, 10:42", "Ontem", "9 out." */
export function quando(iso: string) {
  const d = new Date(iso), hoje = new Date()
  const dia = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const dif = Math.round((dia(hoje) - dia(d)) / 86400000)
  if (dif === 0) return `Hoje, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (dif === 1) return 'Ontem'
  return `${d.getDate()} ${MESES_CURTOS[d.getMonth()]}${d.getFullYear() !== hoje.getFullYear() ? ' ' + d.getFullYear() : ''}`
}

export const telefoneLegivel = (t: string | null) => t ? t.replace(/^\+351(\d{3})(\d{3})(\d{3})$/, '$1 $2 $3') : ''
