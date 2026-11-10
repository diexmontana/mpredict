<?php
/*
 * Complemento de osTicket: mpredict — asistente de pre-análisis de solicitudes de mantenimiento.
 * Basado en TAIS/app/osticket/tais-asistente.
 *
 * Instalación: esta carpeta en <osTicket>/include/plugins/mpredict-asistente
 * (en Docker se monta sola y se activa en el primer arranque).
 */
return array(
    'id' =>             'mpredict:asistente',
    'version' =>        '1.0',
    'name' =>           'mpredict - Asistente de mantenimiento',
    'author' =>         'Proyecto TAIS',
    'description' =>    'Al crearse un ticket, pide a mpredict el análisis (tipo, tamaño y archivos) y lo '
                      . 'agrega como nota interna «Análisis mpredict».',
    'plugin' =>         'mpredict.php:MpredictPlugin',
);
