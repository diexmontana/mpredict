<?php
/*
 * mpredict — lógica del complemento de osTicket.
 * Basado en TAIS/app/osticket/tais-asistente/tais.php.
 *
 * 1. Señal 'ticket.created' (al crearse un ticket):
 *      envía a mpredict  POST <url>/api/analizar  {ticket_numero, titulo, descripcion,
 *      tema_id, tema_nombre} y pega como NOTA INTERNA «Análisis mpredict» el HTML en
 *      español que devuelve mpredict (incluye los enlaces Aceptar / Descartar).
 *      Si mpredict falla o tarda más que el tiempo máximo, el ticket se crea igual
 *      y la nota lo indica.
 *
 * 2. Señal 'api' (mecanismo de osTicket para que un complemento añada rutas a su API,
 *    ver api/http.php):  POST /api/mpredict/tema  {"nombre": "Proyecto EvaP"}
 *      crea el tema de ayuda con la clase de osTicket Topic::__create (la misma que usa
 *      el instalador), público, activo y con el formulario «Detalles del ticket».
 *      Exige la cabecera X-Mpredict-Secreto = secreto de la configuración del complemento.
 */
require_once INCLUDE_DIR . 'class.plugin.php';
require_once INCLUDE_DIR . 'class.signal.php';
require_once INCLUDE_DIR . 'class.format.php';
require_once 'config.php';

class MpredictPlugin extends Plugin {
    var $config_class = 'MpredictConfig';

    function bootstrap() {
        $config = $this->getConfig();
        Signal::connect('ticket.created', function ($ticket) use ($config) {
            MpredictPlugin::analizar($ticket, $config);
        });
        Signal::connect('api', function ($dispatcher) use ($config) {
            $dispatcher->append(url_post('^/mpredict/tema$', function () use ($config) {
                MpredictPlugin::crearTema($config);
            }));
        });
    }

    /* ============================================================ análisis */
    static function analizar($ticket, $config) {
        $url = rtrim($config->get('url') ?: 'http://mpredict-app:8600', '/') . '/api/analizar';
        $timeout = max(1, (int) ($config->get('timeout') ?: 30));

        $mensaje = $ticket->getLastMessage();
        $tema = $ticket->getTopic();
        $datos = array(
            'ticket_numero' => (string) $ticket->getNumber(),
            'titulo' => (string) $ticket->getSubject(),
            'descripcion' => $mensaje ? Format::html2text((string) $mensaje->getBody(), 1000, false) : '',
            'tema_id' => $tema ? (int) $tema->getId() : null,
            'tema_nombre' => $tema ? (string) $tema->getName() : '',
        );

        $ch = curl_init($url);
        curl_setopt_array($ch, array(
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => json_encode($datos),
            CURLOPT_HTTPHEADER => array('Content-Type: application/json'),
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => $timeout,
            CURLOPT_CONNECTTIMEOUT => 5,
        ));
        $respuesta = curl_exec($ch);
        $codigo = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $errno = curl_errno($ch);
        $error = curl_error($ch);
        curl_close($ch);

        $r = ($respuesta !== false && $codigo == 200) ? json_decode($respuesta, true) : null;
        if ($r && !empty($r['nota_html'])) {
            $ticket->logNote('Análisis mpredict', $r['nota_html'], 'mpredict', false);
            return;
        }
        // Falla: el ticket ya existe; la nota explica por qué no hay análisis
        if ($errno == CURLE_OPERATION_TIMEDOUT)
            $motivo = "mpredict tardó más de $timeout segundos.";
        elseif ($errno)
            $motivo = "no se pudo conectar con mpredict ($error).";
        else {
            $detalle = json_decode((string) $respuesta, true);
            $motivo = "mpredict respondió con el código HTTP $codigo"
                . (is_array($detalle) && isset($detalle['detail']) && is_string($detalle['detail'])
                   ? ': ' . $detalle['detail'] : '.');
        }
        error_log("mpredict: sin análisis para el ticket {$datos['ticket_numero']}: $motivo");
        $ticket->logNote('Análisis mpredict: no disponible',
            '<p>No hay análisis para este ticket: ' . Format::htmlchars($motivo) . '</p>'
            . '<p><small>El ticket se creó normalmente. Comprueba que mpredict esté funcionando '
            . '(http://127.0.0.1:8600/proyectos) y que el proyecto esté «listo».</small></p>',
            'mpredict', false);
    }

    /* ============================================================ tema de ayuda */
    static function responder($codigo, $datos) {
        Http::response($codigo, json_encode($datos), 'application/json');
    }

    static function crearTema($config) {
        global $cfg;
        require_once INCLUDE_DIR . 'class.topic.php';
        require_once INCLUDE_DIR . 'class.dynamic_forms.php';
        $secreto = (string) $config->get('secreto');
        $recibido = (string) ($_SERVER['HTTP_X_MPREDICT_SECRETO'] ?? '');
        if ($secreto === '' || !hash_equals($secreto, $recibido))
            self::responder(403, array('error' => 'Secreto incorrecto o no configurado.'));

        $entrada = json_decode(file_get_contents('php://input'), true);
        $nombre = trim((string) ($entrada['nombre'] ?? ''));
        if (mb_strlen($nombre) < 5)
            self::responder(400, array('error' => 'El nombre del tema debe tener 5 caracteres o más.'));

        // Si ya existe (p. ej., se registró de nuevo el proyecto), se devuelve el mismo
        if ($id = Topic::getIdByName($nombre))
            self::responder(200, array('id' => (int) $id, 'nombre' => $nombre, 'nuevo' => false));

        $formulario = DynamicForm::lookup(array('type' => 'T'));       // «Detalles del ticket»
        $errores = array();
        $tema = Topic::__create(array(
            'topic' => $nombre,
            'topic_pid' => 0,
            'ispublic' => 1,
            // activo por «flags», igual que los temas que crea el instalador (help_topic.yaml).
            // No se pasa «status»: no es una columna y la base de datos rechaza el INSERT.
            'flags' => Topic::FLAG_ACTIVE,
            'dept_id' => $cfg->getDefaultDeptId(),
            'priority_id' => 0,
            'sla_id' => 0,
            'page_id' => 0,
            'noautoresp' => 1,
            'forms' => $formulario ? array($formulario->getId()) : array(),
            'notes' => 'Creado por mpredict: proyecto registrado en http://127.0.0.1:8600/proyectos',
        ), $errores);
        if ($errores || !$tema || !$tema->getId())
            self::responder(400, array('error' => 'osTicket rechazó el tema.', 'detalles' => $errores));
        self::responder(200, array('id' => (int) $tema->getId(), 'nombre' => $nombre, 'nuevo' => true));
    }
}
