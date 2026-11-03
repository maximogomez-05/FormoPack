-- La revisión excepcional y el cobro se guardan en una misma transacción.
CREATE TABLE IF NOT EXISTS revisiones_pago_mp (
    id_pago INT PRIMARY KEY,
    id_orden CHAR(32) NOT NULL,
    id_administrador INT NOT NULL,
    preferencia_original VARCHAR(100) NOT NULL,
    preferencia_cobro VARCHAR(100) NOT NULL,
    motivo VARCHAR(500) NOT NULL,
    fecha_revision DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_pago) REFERENCES pagos(id_pago),
    FOREIGN KEY (id_orden) REFERENCES ordenes_pago_mp(id_orden),
    FOREIGN KEY (id_administrador) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
