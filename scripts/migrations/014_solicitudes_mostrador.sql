CREATE TABLE IF NOT EXISTS solicitudes_mostrador (
    id_usuario INT NOT NULL,
    solicitud_id CHAR(32) NOT NULL,
    id_envio INT NULL,
    PRIMARY KEY (id_usuario, solicitud_id),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_envio) REFERENCES envios(id_envio) ON DELETE CASCADE
) ENGINE=InnoDB;
