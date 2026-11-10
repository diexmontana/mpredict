<?php
/*
 * Opciones del complemento (Panel de administración -> Gestionar -> Complementos -> mpredict -> Instancias).
 */
require_once INCLUDE_DIR . 'class.plugin.php';

class MpredictConfig extends PluginConfig {
    function getOptions() {
        return array(
            'url' => new TextboxField(array(
                'label' => 'Dirección de mpredict',
                'hint' => 'Dentro de Docker: http://mpredict-app:8600',
                'default' => 'http://mpredict-app:8600',
                'configuration' => array('size' => 60, 'length' => 200),
            )),
            'timeout' => new TextboxField(array(
                'label' => 'Tiempo máximo de espera (segundos)',
                'hint' => 'Si mpredict tarda más, el ticket se crea igual y la nota lo indica.',
                'default' => '30',
                'configuration' => array('size' => 5, 'length' => 3),
            )),
            'secreto' => new TextboxField(array(
                'label' => 'Secreto compartido con mpredict',
                'hint' => 'El mismo valor que MPREDICT_SECRETO en el archivo .env.',
                'default' => '',
                'configuration' => array('size' => 60, 'length' => 200),
            )),
        );
    }
}
