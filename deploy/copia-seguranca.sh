#!/bin/sh
# Cópia de segurança diária: base de dados + documentos, guardadas 14 dias.
# Agendar no servidor (crontab -e), por exemplo às 3h:
#   0 3 * * * /opt/kontiq/deploy/copia-seguranca.sh >> /var/log/kontiq-copias.log 2>&1
# Opcional: COPIAS_REMOTO="rclone:bucket/kontiq" envia também para fora do servidor (rclone configurado).
set -eu
cd "$(dirname "$0")"
DESTINO=${COPIAS_DIR:-/opt/kontiq/copias}
DIAS=${COPIAS_DIAS:-14}
QUANDO=$(date +%Y-%m-%d_%H%M)
mkdir -p "$DESTINO"

echo "$(date -Is) a copiar a base de dados…"
docker compose exec -T db pg_dump -U faturas -d faturas --format=custom > "$DESTINO/base-$QUANDO.dump"

echo "$(date -Is) a copiar os documentos…"
docker compose exec -T app tar -C /dados -czf - documentos > "$DESTINO/documentos-$QUANDO.tgz"

# Confirma que a cópia da base de dados se lê (não vale a pena ter cópias estragadas).
docker compose exec -T db pg_restore --list < "$DESTINO/base-$QUANDO.dump" > /dev/null

find "$DESTINO" -name 'base-*.dump' -mtime +"$DIAS" -delete
find "$DESTINO" -name 'documentos-*.tgz' -mtime +"$DIAS" -delete

if [ -n "${COPIAS_REMOTO:-}" ]; then
  rclone copy "$DESTINO" "$COPIAS_REMOTO" --max-age 25h
fi
echo "$(date -Is) cópia feita: $(du -sh "$DESTINO/base-$QUANDO.dump" | cut -f1) base, $(du -sh "$DESTINO/documentos-$QUANDO.tgz" | cut -f1) documentos"
