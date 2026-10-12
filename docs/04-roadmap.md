# Roadmap

## Fase 0 — Fundações ✅
- [x] Modelo de dados completo (20 tabelas) e migrações
- [x] Isolamento entre gabinetes com Row Level Security, com testes
- [x] Dados base: contas SNC e categorias
- [x] Validação de NIF e leitura do código QR da AT, com testes
- [x] Ambiente local (Docker: PostgreSQL + MinIO)

## Fase 1 — API do gabinete
- [x] Autenticação: registo do gabinete, confirmar email, entrar/sair, repor palavra-passe
- [x] Portal do cliente: entrar por código (SMS simulado / email)
- [x] Aplicação web (React) com os ecrãs de entrada e registo
- [ ] Convites de colaboradores e de clientes do portal
- [ ] Entrar com Google e Microsoft (precisa de domínio e app registada)
- [ ] Envio real de email (fornecedor SMTP) e SMS (fornecedor a escolher)
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
