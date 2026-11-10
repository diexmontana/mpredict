#!/bin/bash
# Arranque del contenedor mpredict-osticket.
# Basado en TAIS/app/osticket/docker/iniciar.sh.
#
# Primera vez (volumen mpredict_osticket_estado vacío):
#   1. espera a la base de datos
#   2. ejecuta el instalador web de osTicket (el mismo formulario que se llena a mano), en español
#   3. configurar.php: osTicket reducido al mínimo y complemento mpredict activo
#   4. guarda ost-config.php en el volumen
# Siguientes veces: recupera ost-config.php del volumen y arranca Apache.
set -e
OST=/var/www/html
ESTADO=/opt/mpredict/estado
CONFIG="$OST/include/ost-config.php"
mkdir -p "$ESTADO"

echo "[mpredict] Esperando la base de datos..."
php /opt/mpredict/configurar.php esperar

if [ -f "$ESTADO/ost-config.php" ]; then
    echo "[mpredict] osTicket ya estaba instalado: se recupera su configuración."
    cp "$ESTADO/ost-config.php" "$CONFIG"
else
    echo "[mpredict] Primera ejecución: instalando osTicket en español..."
    cp "$OST/include/ost-sampleconfig.php" "$CONFIG"
    chmod 666 "$CONFIG"
    php -S 127.0.0.1:8099 -t "$OST" > /tmp/instalador.log 2>&1 &
    SERVIDOR=$!
    sleep 2
    COOKIES=$(mktemp)
    URL=http://127.0.0.1:8099/setup/install.php
    curl -s -c "$COOKIES" -b "$COOKIES" "$URL" -o /dev/null
    curl -s -c "$COOKIES" -b "$COOKIES" -d "s=prereq" "$URL" -o /dev/null
    curl -s -c "$COOKIES" -b "$COOKIES" \
        --data-urlencode "s=install" \
        --data-urlencode "name=mpredict" \
        --data-urlencode "email=soporte@example.com" \
        --data-urlencode "lang_id=es_ES" \
        --data-urlencode "fname=Administrador" \
        --data-urlencode "lname=mpredict" \
        --data-urlencode "admin_email=${ADMIN_EMAIL}" \
        --data-urlencode "username=${ADMIN_USER}" \
        --data-urlencode "passwd=${ADMIN_PASS}" \
        --data-urlencode "passwd2=${ADMIN_PASS}" \
        --data-urlencode "prefix=ost_" \
        --data-urlencode "dbhost=${DB_HOST}" \
        --data-urlencode "dbname=${DB_NAME}" \
        --data-urlencode "dbuser=${DB_USER}" \
        --data-urlencode "dbpass=${DB_PASS}" \
        --data-urlencode "timezone=America/Lima" \
        "$URL" -o /tmp/instalacion.html
    kill "$SERVIDOR" 2>/dev/null || true
    if ! grep -q "Congratulations\|Felicidades\|Felicitaciones" /tmp/instalacion.html; then
        echo "[mpredict] ERROR: el instalador de osTicket no terminó. Mensajes:"
        grep -o 'class="error">[^<&][^<]*' /tmp/instalacion.html | sed 's/class="error">/  - /' || true
        exit 1
    fi
    echo "[mpredict] osTicket instalado. Reduciéndolo al mínimo y activando el complemento..."
    php /opt/mpredict/configurar.php configurar
    cp "$CONFIG" "$ESTADO/ost-config.php"
    echo "[mpredict] Listo. Administrador: ${ADMIN_USER}"
fi

chmod 644 "$CONFIG"
[ -d "$OST/setup" ] && rm -rf "$OST/setup"     # el instalador no debe quedar accesible
chown www-data:www-data "$CONFIG"
echo "[mpredict] osTicket disponible en ${HELPDESK_URL}"
exec "$@"
