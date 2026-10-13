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
- [x] Equipa do gabinete: convidar por email (administrador ou colaborador), mudar papel, remover
- [x] Convites de clientes do portal (SMS ou email)
- [ ] Entrar com Google e Microsoft (precisa de domínio e app registada)
- [ ] Envio real de email (fornecedor SMTP) e SMS (fornecedor a escolher)
- [x] CRUD de empresas-cliente
- [x] Carregar documento → guardar (disco local; S3 na fase 5) → criar fatura
- [x] Leitura do QR no servidor (PDF e imagem)
- [x] Validações e deteção de duplicados
- [x] Classificação com regras por fornecedor
- [x] Estado do mês por empresa (painel de clientes)
- [x] Registo de atividade

## Fase 2 — Interfaces
- [x] Painel do gabinete: números do mês, o que precisa de atenção, empresas por estado
- [x] Faturas da empresa, carregar PDFs/fotos e conferir (documento ao lado, fila, duplicados, regras)
- [x] Portal do cliente: enviar faturas (foto ou ficheiro), ver o estado do que enviou e os pedidos do gabinete
- [x] Dúvidas sobre uma fatura: o gabinete pergunta na conferência, o cliente é avisado e responde no portal, a resposta aparece no painel
- [x] Faturas: todas as faturas do gabinete num mês, com filtros (estado, empresa) e pesquisa
- [x] Pedidos: empresas sem faturas (pedir a todas de uma vez), dúvidas em aberto e histórico de pedidos
- [x] Portal do cliente instalável no telemóvel (manifesto, ícones, service worker; instalação completa precisa de HTTPS)
- [x] Resumo semanal por email às pessoas do gabinete (python -m app.resumo, agendar à segunda de manhã)
- [ ] Email de entrada por empresa

## Fase 3 — Leitura com IA
- [ ] Fila de tarefas e worker
- [x] Leitura de faturas sem QR com nível de confiança: modo de teste (regras sobre o texto do PDF) e modo Claude (precisa de chave)
- [ ] Ativar o modo Claude com uma chave real e medir custo/qualidade
- [x] Revisão das faturas lidas automaticamente (aviso de confiança baixa)

## Fase 4 — Integrações
- [x] Exportações CSV, Excel (com resumo do IVA) e ZIP com documentos; marcar como exportadas e desfazer
- [x] Lançamentos de compras (gasto, IVA dedutível, fornecedor) com contas configuráveis por gabinete
- [x] Exportação TOConline (campos do modelo de importação — a confirmar com o modelo real)
- [x] Modelo do programa: o gabinete carrega o Excel de importação (Sage, Primavera, PHC…) e mapeia as colunas
- [ ] Confirmar os formatos com gabinetes reais; Sage for Accountants por TXT/XML; autoliquidação
- [ ] APIs: InvoiceXpress, Moloni
- [x] Cruzamento com o e-Fatura: carregar o CSV "Obter dados para Excel", faturas em falta (pedir ao cliente) e não comunicadas
- [x] Resumo do IVA por mês/trimestre com os campos sugeridos do quadro 06 da declaração periódica (Excel)

## Fase 5 — Produção
- [x] Nome do produto: Kontiq (domínio kontiq.pt)
- [ ] Registar kontiq.pt (e marca no INPI)
- [ ] Alojamento na UE, cópias de segurança, monitorização
- [ ] RGPD: contrato de subcontratante, política de privacidade, retenção
- [x] Subscrições: 3 planos (Arranque 29 €, Gabinete 79 €, Pro 149 €), teste de 30 dias, limites de empresas e pessoas, mensal/anual, cancelar, atraso e suspensão — pagamento simulado
- [ ] Ligar um fornecedor de pagamentos real (cartão, MB WAY, Multibanco) e emitir fatura da subscrição
