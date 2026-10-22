-- Migración 002: Tabla de ubicaciones en vivo para hojas de ruta
CREATE TABLE IF NOT EXISTS ubicaciones_hojas_ruta (
    id_hoja_ruta    INT(11)         NOT NULL,
    id_chofer       INT(11)         NOT NULL,
    latitud         DECIMAL(10,7)   NOT NULL,
    longitud        DECIMAL(10,7)   NOT NULL,
    precision_m     DECIMAL(8,2)    DEFAULT NULL,
    fecha_actualizacion DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_hoja_ruta),
    INDEX idx_ubicaciones_fecha (fecha_actualizacion),
    CONSTRAINT fk_ubicacion_hoja FOREIGN KEY (id_hoja_ruta) REFERENCES hojas_de_ruta(id_hoja_ruta) ON DELETE CASCADE,
    CONSTRAINT fk_ubicacion_chofer FOREIGN KEY (id_chofer) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
