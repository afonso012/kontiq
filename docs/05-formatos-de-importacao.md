# Formatos de importação nos programas de contabilidade

Cada fatura de compra conferida dá um lançamento no diário de compras:

| Movimento | Conta | Valor |
|---|---|---|
| Débito | conta SNC da fatura (ex.: 6222) | base + IVA não dedutível |
| Débito | IVA dedutível da taxa (por omissão 2432) | parte dedutível do IVA (100%, 50% ou 0%) |
| Crédito | fornecedores (por omissão 2211, opcionalmente + NIF) | total |

Notas de crédito: débitos e créditos trocados. As contas, o diário e os tipos de documento
configuram-se em **Exportações → Configurar** (por gabinete).

## Formatos

- **TOConline** — Excel com os campos do modelo de *Contabilidade › Configuração › Importação de
  lançamentos* (Número de ordem do lançamento, Diário, Tipo de Documento, datas, Descrição,
  Controlo de terceiros, NIF/Nome do terceiro, Código da conta a movimentar, Débito, Crédito,
  Código de IVA). A ajuda do TOConline não publica a ordem exata nem o nome das colunas de valores:
  **confirmar com o modelo descarregado da aplicação**. Se não bater certo, usar "Modelo do programa".
- **Lançamentos (Excel)** — genérico, uma folha por empresa, para qualquer programa com importação
  configurável.
- **Modelo do programa** — o gabinete carrega o Excel de importação do seu programa (Sage, Primavera,
  PHC…), indica o que vai em cada coluna (a Kontiq sugere pelos títulos) e a Kontiq preenche-o, um
  ficheiro por empresa (ZIP se forem várias). As linhas de exemplo do modelo são apagadas.

## Por confirmar com gabinetes reais

- Modelo atual do TOConline (ordem e nomes das colunas, valores aceites em "Controlo de terceiros").
- Sage for Accountants importa por TXT/XML (não Excel); Sage 50 usa um modelo Excel próprio.
- Primavera e PHC: formato dos ficheiros de importação de lançamentos em uso pelos gabinetes.
- Contas de IVA dedutível habituais (subcontas por taxa e por tipo: existências, imobilizado, outros).
- Autoliquidação (compras intracomunitárias e serviços do estrangeiro): hoje sem IVA liquidado/dedutível.
