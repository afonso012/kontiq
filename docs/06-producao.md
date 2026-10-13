# Pôr a Kontiq online

Tudo o que é preciso para correr em produção já está no repositório: `Dockerfile` (aplicação web + API),
`deploy/docker-compose.yml` (base de dados, aplicação e HTTPS automático com Caddy),
`deploy/copia-seguranca.sh` (cópias diárias) e `deploy/.env.exemplo` (configuração).

## O que é preciso comprar

| O quê | Para quê | Notas |
| --- | --- | --- |
| Domínio `kontiq.pt` | Endereço da aplicação e dos emails | Registador acreditado pela DNS.pt |
| Servidor virtual na UE | Onde a aplicação corre | 2 vCPU, 4 GB RAM, 40 GB disco, Ubuntu 24.04. Chega para dezenas de gabinetes |
| Fornecedor de email (SMTP) | Códigos, convites, pedidos de faturas, resumo semanal | Brevo, Mailjet, Amazon SES… quase todos têm plano gratuito para pouco volume |
| (Mais tarde) SMS | Portal do cliente por telemóvel | Até lá, os clientes entram com código por email |
| (Mais tarde) Pagamentos | Cobrar as subscrições | Cartão, MB WAY e Multibanco |

## Passo a passo (uma vez)

1. **Servidor.** Crie o servidor numa região da UE, com a sua chave SSH. Anote o IP.
2. **Domínio.** No painel do domínio, crie um registo `A` de `kontiq.pt` e outro de `www.kontiq.pt` para esse IP.
3. **Docker.** No servidor:
   ```sh
   curl -fsSL https://get.docker.com | sh
   sudo mkdir -p /opt/kontiq && sudo chown $USER /opt/kontiq
   git clone <o seu repositório privado> /opt/kontiq
   ```
4. **Configuração.**
   ```sh
   cd /opt/kontiq/deploy
   cp .env.exemplo .env
   openssl rand -hex 32   # corra três vezes: SECRET_KEY, DB_PASSWORD_DONO, DB_PASSWORD_APP
   nano .env               # preencha DOMINIO, as três chaves e o SMTP
   ```
   A aplicação recusa arrancar se a chave secreta for fraca, se os pagamentos estiverem em modo
   simulado ou se o endereço não for `https://`.
5. **Arrancar.**
   ```sh
   docker compose up -d --build
   docker compose logs -f app     # esperar por "Application startup complete"
   ```
   O Caddy pede o certificado HTTPS sozinho na primeira visita. Abra `https://kontiq.pt` e crie a
   conta do seu gabinete como qualquer cliente faria. Não corra `python -m app.demo` em produção.
6. **Email.** No fornecedor SMTP, adicione ao domínio os registos SPF e DKIM que ele indicar. Teste
   com "Recuperar palavra-passe" e com "Enviar-me agora" em Equipa.
7. **Agendamentos.** `crontab -e` no servidor:
   ```cron
   # Cópia de segurança às 3h, guardada 14 dias
   0 3 * * * /opt/kontiq/deploy/copia-seguranca.sh >> /var/log/kontiq-copias.log 2>&1
   # Resumo semanal à segunda às 8h (hora do servidor: ponha-o em Europe/Lisbon)
   0 8 * * 1 cd /opt/kontiq/deploy && docker compose exec -T app python -m app.resumo >> /var/log/kontiq-resumo.log 2>&1
   ```
   `sudo timedatectl set-timezone Europe/Lisbon` acerta a hora do servidor.
8. **Cópias fora do servidor.** Uma cópia que só existe no mesmo servidor não protege de tudo.
   Configure o `rclone` para um armazenamento de objetos na UE e defina `COPIAS_REMOTO` no crontab.
9. **Erros (opcional).** Crie um projeto gratuito no Sentry e ponha o DSN em `SENTRY_DSN`.
   Sem Sentry, os erros ficam em `docker compose logs app`, em JSON, com a referência que a pessoa vê no ecrã.

## Atualizar para uma versão nova

```sh
cd /opt/kontiq && git pull
cd deploy && docker compose up -d --build   # as migrações da base de dados correm ao arrancar
```

## Recuperar de uma cópia de segurança

```sh
cd /opt/kontiq/deploy
docker compose stop app
docker compose exec -T db pg_restore -U faturas -d faturas --clean --if-exists < /opt/kontiq/copias/base-AAAA-MM-DD_HHMM.dump
docker compose run --rm -T app sh -c "tar -C /dados -xzf -" < /opt/kontiq/copias/documentos-AAAA-MM-DD_HHMM.tgz
docker compose start app
```
Experimente a recuperação uma vez noutro servidor antes de ter clientes: uma cópia que nunca foi
restaurada é só uma esperança.

## Antes de abrir ao público

- [ ] Preencher os dados do responsável em `frontend/src/pages/Legal.tsx` (nome, NIF, morada) e pedir a
      um jurista que reveja a política de privacidade, os termos e o acordo de tratamento de dados.
- [ ] Email a funcionar com SPF e DKIM (os emails não podem cair no spam: são códigos de acesso).
- [ ] Cópias de segurança a correr e uma recuperação testada.
- [ ] `PAGAMENTOS_MODO=desligado` até haver fornecedor; os gabinetes ficam no período de teste.
- [ ] Decidir o modo dos SMS. Sem fornecedor, convide os clientes do portal pelo email.
- [ ] Confirmar com um gabinete o formato do e-Fatura e o modelo de importação do programa dele.

## O que fica de fora por agora

- Envio real de SMS e cobrança das subscrições (precisam de fornecedor e de conta).
- Email de entrada por empresa (precisa de receber email no domínio).
- Armazenamento de documentos em S3: por agora ficam no disco do servidor, num volume com cópia diária.
