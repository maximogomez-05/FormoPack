CREATE TABLE IF NOT EXISTS historial_gps (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    envio_id        INT(11)         NOT NULL,
    lat             DECIMAL(10,7)   NOT NULL,
    lng             DECIMAL(10,7)   NOT NULL,
    fecha_hora      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_historial_gps_envio_fecha (envio_id, fecha_hora, id),
    CONSTRAINT fk_historial_gps_envio FOREIGN KEY (envio_id)
        REFERENCES envios(id_envio) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;