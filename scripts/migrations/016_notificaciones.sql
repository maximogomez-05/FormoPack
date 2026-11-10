CREATE TABLE IF NOT EXISTS notificaciones_operativas (
    id_notificacion BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    clave_evento CHAR(64) NOT NULL,
    destinatario VARCHAR(100) NOT NULL,
    contenido LONGTEXT NOT NULL,
    estado ENUM('pendiente','procesando','enviado','fallido') NOT NULL DEFAULT 'pendiente',
    intentos SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    disponible_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    bloqueo_hasta DATETIME NULL,
    token CHAR(32) NULL,
    ultimo_error VARCHAR(80) NULL,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    enviado_en DATETIME NULL,
    UNIQUE KEY uq_notificacion_evento (clave_evento),
    UNIQUE KEY uq_notificacion_token (token),
    KEY idx_notificacion_pendiente (estado, disponible_en),
    KEY idx_notificacion_bloqueo (estado, bloqueo_hasta)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
