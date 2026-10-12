# Roadmap

## Fase 0 — Fundações ✅
- [x] Modelo de dados completo (20 tabelas) e migrações
- [x] Isolamento entre gabinetes com Row Level Security, com testes
- [x] Dados base: contas SNC e categorias
- [x] Validação de NIF e leitura do código QR da AT, com testes
- [x] Ambiente local (Docker: PostgreSQL + MinIO)

## Fase 1 — API do gabinete
- [ ] Autenticação (registo do gabinete, login, convites de colaboradores)
- [ ] CRUD de empresas-cliente
- [ ] Carregar documento → guardar no S3 → criar fatura
- [ ] Leitura do QR no servidor (PDF e imagem)
- [ ] Validações e deteção de duplicados
- [ ] Classificação com regras por fornecedor
- [ ] Estado do mês por empresa (painel de clientes)
- [ ] Registo de atividade

## Fase 2 — Interfaces
- [ ] Painel do gabinete (o protótipo passado a sério)
- [ ] Portal do cliente: enviar faturas, ver o que falta, responder a comentários
- [ ] Email de entrada por empresa

## Fase 3 — Leitura com IA
- [ ] Fila de tarefas e worker
- [ ] Extração com IA para faturas sem QR, com nível de confiança
- [ ] Revisão rápida das faturas lidas com IA

## Fase 4 — Integrações
- [ ] Exportações CSV, Excel e ZIP
- [ ] Formatos de importação: TOConline, Primavera, PHC, Sage
- [ ] APIs: InvoiceXpress, Moloni
- [ ] Cruzamento com a lista do e-Fatura (formato a confirmar)

## Fase 5 — Produção
- [ ] Alojamento na UE, cópias de segurança, monitorização
- [ ] RGPD: contrato de subcontratante, política de privacidade, retenção
- [ ] Faturação das subscrições
