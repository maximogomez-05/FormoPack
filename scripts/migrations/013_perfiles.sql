CREATE TABLE IF NOT EXISTS fotos_perfil (
    id_usuario INT PRIMARY KEY,
    imagen MEDIUMBLOB NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
