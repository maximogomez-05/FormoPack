-- Migración 003: Tablas para el soporte al cliente y chats en vivo
CREATE TABLE IF NOT EXISTS chats_soporte (
    id_chat INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL UNIQUE,
    cliente_nombre VARCHAR(100) NOT NULL,
    cliente_email VARCHAR(120) NULL,
    nro_guia VARCHAR(30) NULL,
    estado ENUM('sin_atender', 'en_progreso') NOT NULL DEFAULT 'sin_atender',
    id_usuario_atendiendo INT NULL,
    nombre_usuario_atendiendo VARCHAR(100) NULL,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_soporte_estado (estado),
    INDEX idx_soporte_usuario (id_usuario_atendiendo),
    CONSTRAINT fk_soporte_usuario FOREIGN KEY (id_usuario_atendiendo)
        REFERENCES usuarios(id_usuario) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mensajes_soporte (
    id_mensaje INT AUTO_INCREMENT PRIMARY KEY,
    id_chat INT NOT NULL,
    remitente_tipo ENUM('cliente', 'soporte') NOT NULL,
    remitente_nombre VARCHAR(100) NOT NULL,
    mensaje TEXT NOT NULL,
    fecha_envio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_msg_chat (id_chat),
    CONSTRAINT fk_msg_chat FOREIGN KEY (id_chat)
        REFERENCES chats_soporte(id_chat) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
