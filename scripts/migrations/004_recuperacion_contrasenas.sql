-- Migración 004: Tabla de recuperación de contraseñas por código de un solo uso
CREATE TABLE IF NOT EXISTS recuperacion_contrasenas (
    id_recuperacion INT NOT NULL AUTO_INCREMENT,
    id_usuario      INT NOT NULL,
    codigo          VARCHAR(10) NOT NULL,
    expira_en       DATETIME NOT NULL,
    utilizado       TINYINT(1) NOT NULL DEFAULT 0,
    creado_en       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_recuperacion),
    INDEX idx_recuperacion_usuario (id_usuario),
    INDEX idx_recuperacion_codigo (codigo),
    CONSTRAINT fk_recuperacion_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
