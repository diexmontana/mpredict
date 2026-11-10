<?php
/*
 * Ayudante del arranque (iniciar.sh). Basado en TAIS/app/osticket/docker/configurar.php.
 *
 *   php configurar.php esperar      espera hasta que la base de datos responda
 *   php configurar.php configurar   tras instalar osTicket, lo deja reducido al mínimo:
 *
 * Todo lo que hace son las MISMAS opciones que se cambian a mano en el panel de
 * administración (no se modifica el código de osTicket). Verificado contra el
 * código de osTicket v1.18.4 (include/class.config.php, class.nav.php,
 * class.topic.php, class.dynamic_forms.php, i18n/en_US/form.yaml).
 */
mysqli_report(MYSQLI_REPORT_OFF);

function conectar($reintentos = 1) {
    for ($i = 0; $i < $reintentos; $i++) {
        $db = @new mysqli(getenv('DB_HOST'), getenv('DB_USER'), getenv('DB_PASS'), getenv('DB_NAME'));
        if (!$db->connect_errno) {
            $db->set_charset('utf8mb4');
            return $db;
        }
        sleep(2);
    }
    fwrite(STDERR, "[mpredict] No se pudo conectar con la base de datos: {$db->connect_error}\n");
    exit(1);
}

function ejecutar($db, $sql) {
    if (!$db->query($sql)) {
        fwrite(STDERR, "[mpredict] Error SQL: {$db->error}\n  en: " . substr($sql, 0, 200) . "\n");
        exit(1);
    }
}

function opcion($db, $clave, $valor, $ns = 'core') {
    $c = $db->real_escape_string($clave);
    $v = $db->real_escape_string($valor);
    ejecutar($db, "INSERT INTO ost_config (namespace, `key`, value, updated) VALUES ('$ns', '$c', '$v', NOW())
                   ON DUPLICATE KEY UPDATE value = '$v', updated = NOW()");
}

$modo = $argv[1] ?? '';
if ($modo === 'esperar') {
    conectar(60)->close();
    exit(0);
}
if ($modo !== 'configurar') {
    fwrite(STDERR, "Uso: php configurar.php esperar|configurar\n");
    exit(2);
}
$db = conectar(5);

// 1. Idioma y dirección pública
opcion($db, 'system_language', 'es_ES');
opcion($db, 'helpdesk_url', getenv('HELPDESK_URL') ?: 'http://127.0.0.1:8680/');
echo "[mpredict]   idioma del sistema: es_ES\n";

// 2. Portal reducido: sin registro de clientes, sin base de conocimiento, sin captcha
opcion($db, 'client_registration', 'disabled');   // «Desactivado: todos los usuarios son invitados»
opcion($db, 'clients_only', '0');                 // abrir ticket sin iniciar sesión
opcion($db, 'enable_kb', '0');                    // base de conocimiento
opcion($db, 'enable_premade', '0');               // respuestas predefinidas
opcion($db, 'enable_captcha', '0');
opcion($db, 'enable_avatars', '0');               // sin imágenes de gravatar
opcion($db, 'allow_attachments', '0');            // sin adjuntos
opcion($db, 'verify_email_addrs', '0');           // los correos de prueba usan example.com
opcion($db, 'enable_auto_cron', '0');             // sin cron: nunca se marcan tickets vencidos (SLA)
opcion($db, 'default_help_topic', '0');
// sin correos: no hay cuenta de correo configurada
foreach (array('ticket_autoresponder', 'message_autoresponder', 'ticket_notice_active',
               'ticket_alert_active', 'message_alert_active', 'note_alert_active',
               'transfer_alert_active', 'assigned_alert_active', 'overdue_alert_active') as $k)
    opcion($db, $k, '0');
echo "[mpredict]   portal: sin registro, sin base de conocimiento, sin captcha, sin adjuntos ni correos\n";

// 3. Formulario: sin teléfono (campo no bloqueado: se puede desactivar, flags & ~ENABLED).
//    La prioridad ya no se muestra a los clientes en 1.18.4 (sin FLAG_CLIENT_VIEW).
ejecutar($db, "UPDATE ost_form_field f JOIN ost_form fo ON fo.id = f.form_id
               SET f.flags = f.flags & ~1 WHERE fo.type = 'U' AND f.name = 'phone'");
echo "[mpredict]   formulario: campo teléfono desactivado\n";

// 3b. «Resumen» (título): osTicket lo limita a 50 caracteres y recorta los títulos largos.
//     Su configuración no está bloqueada (sin FLAG_MASK_EDIT): se sube a 255, como en el panel.
$r = $db->query("SELECT f.id, f.configuration FROM ost_form_field f JOIN ost_form fo ON fo.id = f.form_id
                 WHERE fo.type = 'T' AND f.name = 'subject'");
if ($r && ($fila = $r->fetch_assoc())) {
    $conf = json_decode($fila['configuration'] ?: '{}', true) ?: array();
    $conf['length'] = 255;
    $conf['size'] = 60;
    $json = $db->real_escape_string(json_encode($conf));
    ejecutar($db, "UPDATE ost_form_field SET configuration = '$json' WHERE id = " . (int) $fila['id']);
    echo "[mpredict]   formulario: título de hasta 255 caracteres\n";
}

// 4. Temas de ayuda que trae osTicket: desactivados (en el portal solo saldrán «Proyecto ...»)
ejecutar($db, "UPDATE ost_help_topic SET flags = flags & ~6, updated = NOW()");   // ~(ACTIVE|ARCHIVED)
echo "[mpredict]   temas de ayuda por defecto desactivados\n";

// 5. Rol de agente mínimo: sin ningún permiso (solo ve la lista y el detalle de los tickets)
ejecutar($db, "INSERT INTO ost_role (flags, name, permissions, notes, created, updated)
               VALUES (1, 'Solo consulta (mpredict)', '{}',
                       'Creado por mpredict: sin permisos; solo ve la lista de tickets y su detalle.', NOW(), NOW())");
echo "[mpredict]   rol «Solo consulta (mpredict)» creado\n";

// 6. Página de inicio del portal
$r = $db->query("SELECT value FROM ost_config WHERE namespace = 'core' AND `key` = 'landing_page_id'");
if ($r && ($fila = $r->fetch_row()) && (int) $fila[0]) {
    $cuerpo = $db->real_escape_string(
        '<h1>Solicitudes de mantenimiento</h1><p>Para reportar un error o pedir un cambio en un proyecto, '
        . 'pulsa <b>Abrir un nuevo ticket</b>, elige el proyecto y describe la solicitud.</p>');
    ejecutar($db, "UPDATE ost_content SET body = '$cuerpo', updated = NOW() WHERE id = " . (int) $fila[0]);
    echo "[mpredict]   página de inicio del portal actualizada\n";
}

// 7. Complemento mpredict: instalado, activo y con una instancia configurada
ejecutar($db, "INSERT INTO ost_plugin (name, install_path, isphar, isactive, version, notes, installed)
               VALUES ('mpredict - Asistente de mantenimiento', 'plugins/mpredict-asistente', 0, 1, '1.0',
                       'Instalado automáticamente por el contenedor mpredict-osticket.', NOW())");
$plugin = $db->insert_id;
ejecutar($db, "INSERT INTO ost_plugin_instance (plugin_id, flags, name, notes, created, updated)
               VALUES ($plugin, 1, 'mpredict (Docker)', NULL, NOW(), NOW())");
$instancia = $db->insert_id;
$ns = "plugin.$plugin.instance.$instancia";
foreach (array('url' => getenv('MPREDICT_URL') ?: 'http://mpredict-app:8600',
               'timeout' => '30',
               'secreto' => getenv('MPREDICT_SECRETO') ?: '') as $k => $v)
    opcion($db, $k, $v, $ns);
echo "[mpredict]   complemento activo; llamará a mpredict en " . (getenv('MPREDICT_URL') ?: 'http://mpredict-app:8600') . "\n";
