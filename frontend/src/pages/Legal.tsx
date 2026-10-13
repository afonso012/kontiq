import { Link, useParams } from 'react-router-dom'
import { Marca } from '../components/ui'

/*
 * Textos legais. ANTES DE LANÇAR: preencher os campos entre [ ] em RESPONSAVEL e pedir a um
 * jurista que reveja (RGPD e contrato). Ver docs/06-producao.md, "Antes de abrir ao público".
 */
const RESPONSAVEL = {
  nome: '[Nome da empresa ou do empresário em nome individual]',
  nif: '[NIF]',
  morada: '[Morada]',
  email: 'privacidade@kontiq.pt',
  atualizado: '[data]',
}

type Seccao = { titulo: string; texto: (string | string[])[] }
type Documento = { titulo: string; lead: string; seccoes: Seccao[] }

const DOCS: Record<string, Documento> = {
  privacidade: {
    titulo: 'Política de privacidade',
    lead: 'Que dados a Kontiq trata, para quê, durante quanto tempo e como pode exercer os seus direitos.',
    seccoes: [
      { titulo: 'Quem somos', texto: [`A Kontiq é operada por ${RESPONSAVEL.nome}, NIF ${RESPONSAVEL.nif}, ${RESPONSAVEL.morada}. Contacto para questões de privacidade: ${RESPONSAVEL.email}.`] },
      { titulo: 'Dois papéis diferentes', texto: [
        'Dados das contas do gabinete (nome, email, telefone e dados de faturação da subscrição): a Kontiq é responsável pelo tratamento.',
        'Faturas, empresas-cliente e contactos dos clientes do gabinete: o gabinete é o responsável e a Kontiq trata-os por conta dele, como subcontratante, nos termos do Acordo de tratamento de dados.',
      ] },
      { titulo: 'Que dados tratamos', texto: [[
        'Conta: nome, email, telemóvel, palavra-passe (guardada só como resumo criptográfico, nunca em texto).',
        'Gabinete: nome, NIF, contactos, programa de contabilidade, plano e pagamentos da subscrição.',
        'Empresas-cliente e respetivos contactos indicados pelo gabinete.',
        'Documentos e faturas enviados e os dados lidos deles (NIF, números, valores, IVA).',
        'Registos técnicos: endereço IP, navegador, datas de acesso e de alterações, para segurança e para resolver problemas.',
      ]] },
      { titulo: 'Para quê e com que fundamento', texto: [[
        'Prestar o serviço contratado pelo gabinete (execução do contrato).',
        'Enviar emails e SMS necessários ao serviço: códigos de acesso, convites, pedidos de faturas (execução do contrato).',
        'Segurança, prevenção de abusos e registos de atividade (interesse legítimo).',
        'Faturação e obrigações fiscais da subscrição (obrigação legal).',
      ], 'Não vendemos dados nem os usamos para publicidade.'] },
      { titulo: 'Quem mais tem acesso', texto: ['Fornecedores que nos ajudam a prestar o serviço, todos com contrato de subcontratação: alojamento do servidor, envio de email, envio de SMS e, se ativada, leitura automática de faturas sem código QR. A lista atualizada está disponível a pedido.'] },
      { titulo: 'Durante quanto tempo', texto: ['Enquanto a conta do gabinete estiver ativa. Depois de cancelada, os dados ficam disponíveis para exportação durante 90 dias e são apagados a seguir, exceto o que a lei obrigue a guardar (por exemplo, faturas da subscrição). As cópias de segurança são substituídas ao fim de 14 dias.'] },
      { titulo: 'Os seus direitos', texto: [`Pode pedir acesso, retificação, apagamento, limitação, portabilidade ou opor-se ao tratamento através de ${RESPONSAVEL.email}. Se os dados foram carregados por um gabinete de contabilidade, encaminhamos o pedido para o gabinete. Pode também apresentar reclamação à Comissão Nacional de Proteção de Dados (CNPD).`] },
      { titulo: 'Cookies', texto: ['Usamos apenas um cookie de sessão, necessário para manter a sessão iniciada. Não usamos cookies de publicidade nem de análise de terceiros.'] },
    ],
  },
  termos: {
    titulo: 'Termos de utilização',
    lead: 'As regras de utilização da Kontiq pelos gabinetes de contabilidade e pelos seus clientes.',
    seccoes: [
      { titulo: 'O serviço', texto: [`A Kontiq, operada por ${RESPONSAVEL.nome}, NIF ${RESPONSAVEL.nif}, ajuda gabinetes de contabilidade a recolher, ler, conferir e exportar as faturas de compra dos seus clientes. Não substitui o programa de contabilidade nem o trabalho do contabilista certificado.`] },
      { titulo: 'Conta e acesso', texto: ['Quem cria a conta do gabinete garante que tem poderes para o fazer e mantém a palavra-passe em segredo. O gabinete decide quem da equipa e que clientes têm acesso e responde pelo uso que fazem.'] },
      { titulo: 'Leitura automática', texto: ['Os dados lidos dos documentos (pelo código QR ou automaticamente) são uma ajuda e devem ser conferidos antes de serem exportados ou usados em declarações. A responsabilidade pela contabilidade e pelas declarações fiscais é do gabinete.'] },
      { titulo: 'Planos, pagamento e cancelamento', texto: ['Os planos, preços e limites estão na página Subscrição. O período de teste é gratuito e não renova sozinho. A subscrição paga renova-se no fim de cada período até ser cancelada; o cancelamento produz efeitos no fim do período já pago. Com a subscrição inativa, o gabinete continua a poder consultar e exportar os seus dados.'] },
      { titulo: 'Utilização aceitável', texto: ['Não é permitido usar a Kontiq para fins ilícitos, carregar conteúdos que não sejam documentos contabilísticos, tentar aceder a dados de outros gabinetes ou sobrecarregar o serviço.'] },
      { titulo: 'Disponibilidade e responsabilidade', texto: ['Fazemos o possível para manter o serviço disponível e os dados seguros, com cópias de segurança diárias, mas podem existir interrupções para manutenção ou por falhas. Na medida permitida por lei, a responsabilidade da Kontiq limita-se ao valor pago nos últimos 12 meses.'] },
      { titulo: 'Alterações e lei aplicável', texto: ['Avisamos por email com 30 dias de antecedência de alterações relevantes a estes termos. Aplica-se a lei portuguesa.'] },
    ],
  },
  rgpd: {
    titulo: 'Acordo de tratamento de dados',
    lead: 'O acordo entre o gabinete (responsável pelo tratamento) e a Kontiq (subcontratante) sobre os dados dos clientes do gabinete, nos termos do artigo 28.º do RGPD.',
    seccoes: [
      { titulo: 'Objeto', texto: ['A Kontiq trata, por conta do gabinete, os dados contidos nas faturas e documentos dos clientes do gabinete e os contactos desses clientes, apenas para prestar o serviço contratado e segundo as instruções do gabinete dadas através da aplicação.'] },
      { titulo: 'Obrigações da Kontiq', texto: [[
        'Tratar os dados apenas para prestar o serviço e não os usar para outros fins.',
        'Garantir a confidencialidade de quem tem acesso aos dados.',
        'Aplicar medidas de segurança adequadas: isolamento dos dados de cada gabinete, palavras-passe guardadas com resumo criptográfico, ligações cifradas, registos de atividade e cópias de segurança.',
        'Recorrer a outros subcontratantes apenas com contrato equivalente e informar o gabinete de alterações.',
        'Ajudar o gabinete a responder a pedidos dos titulares dos dados.',
        'Avisar o gabinete sem demora injustificada de qualquer violação de dados pessoais.',
        'No fim do contrato, permitir a exportação e apagar os dados, salvo obrigação legal.',
      ]] },
      { titulo: 'Subcontratantes ulteriores', texto: ['Alojamento do servidor e cópias de segurança na União Europeia; envio de email; envio de SMS; e, se ativada pelo gabinete, leitura automática de faturas sem código QR. A lista atualizada está disponível a pedido.'] },
      { titulo: 'Obrigações do gabinete', texto: ['O gabinete garante que tem fundamento para tratar os dados dos seus clientes e para os carregar na Kontiq, e informa-os de que usa este serviço.'] },
    ],
  },
}

export default function Legal() {
  const { doc = 'privacidade' } = useParams()
  const d = DOCS[doc] ?? DOCS.privacidade
  return (
    <div className="legal">
      <header className="legal__topo"><Marca /><nav className="legal__nav">{Object.entries(DOCS).map(([k, v]) => <Link key={k} to={`/legal/${k}`} aria-current={k === doc ? 'page' : undefined}>{v.titulo}</Link>)}</nav></header>
      <article className="legal__corpo">
        <h1>{d.titulo}</h1>
        <p className="legal__lead">{d.lead}</p>
        {d.seccoes.map((s) => (
          <section key={s.titulo}>
            <h2>{s.titulo}</h2>
            {s.texto.map((t, i) => Array.isArray(t) ? <ul key={i}>{t.map((x) => <li key={x}>{x}</li>)}</ul> : <p key={i}>{t}</p>)}
          </section>
        ))}
        <p className="muted14">Última atualização: {RESPONSAVEL.atualizado}.</p>
      </article>
    </div>
  )
}
