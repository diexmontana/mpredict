# osTicket 1.18.4 en español sobre PHP 8.3 + Apache.
# Basado en TAIS/app/osticket/docker/Dockerfile (probado con osTicket 1.18.4 y PHP 8.3).
FROM php:8.3-apache

ARG OSTICKET_VERSION=1.18.4
# Paquete de idioma oficial para la serie 1.18 (servidor de descargas de osTicket).
# Comprobado el 09-11-2026: HTTP 200, 467 211 bytes, ETag/MD5 44b13ddb7aeee969751a3ff2d3b1fd24.
ARG ES_URL=https://s3.amazonaws.com/downloads.osticket.com/lang/1.18.x/es_ES.phar
ARG ES_MD5=44b13ddb7aeee969751a3ff2d3b1fd24

# Extensiones de PHP que usa osTicket
RUN apt-get update \
 && apt-get install -y --no-install-recommends unzip curl libpng-dev libjpeg-dev libfreetype6-dev \
        libicu-dev libzip-dev \
 && docker-php-ext-configure gd --with-jpeg --with-freetype \
 && docker-php-ext-install -j"$(nproc)" mysqli gd intl zip opcache \
 && rm -rf /var/lib/apt/lists/*

# La API (/api/...) depende del .htaccess de osTicket
RUN a2enmod rewrite \
 && printf '<Directory /var/www/html>\n    AllowOverride All\n</Directory>\n' > /etc/apache2/conf-enabled/mpredict.conf

# osTicket desde su publicación oficial en GitHub + paquete de español (verificado con MD5)
RUN curl -fsSL -o /tmp/ost.zip \
        "https://github.com/osTicket/osTicket/releases/download/v${OSTICKET_VERSION}/osTicket-v${OSTICKET_VERSION}.zip" \
 && unzip -q /tmp/ost.zip -d /tmp/ost \
 && cp -a /tmp/ost/upload/. /var/www/html/ \
 && rm -rf /tmp/ost /tmp/ost.zip \
 && curl -fsSL -o /var/www/html/include/i18n/es_ES.phar "$ES_URL" \
 && echo "${ES_MD5}  /var/www/html/include/i18n/es_ES.phar" | md5sum -c - \
 && chown -R www-data:www-data /var/www/html

COPY iniciar.sh /usr/local/bin/iniciar.sh
COPY configurar.php /opt/mpredict/configurar.php
# Por si los archivos llegan con fines de línea de Windows (CRLF)
RUN sed -i 's/\r$//' /usr/local/bin/iniciar.sh /opt/mpredict/configurar.php && chmod +x /usr/local/bin/iniciar.sh

ENTRYPOINT ["iniciar.sh"]
CMD ["apache2-foreground"]
