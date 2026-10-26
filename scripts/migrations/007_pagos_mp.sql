-- Órdenes locales vinculadas al Checkout Pro y unicidad del pago externo.
CREATE TABLE IF NOT EXISTS ordenes_pago_mp (
    id_orden CHAR(32) PRIMARY KEY,
    id_envio INT NOT NULL,
    id_turno INT NOT NULL,
    id_usuario INT NOT NULL,
    monto DECIMAL(12,2) NOT NULL,
    collector_id VARCHAR(30) NOT NULL,
    preference_id VARCHAR(100) DEFAULT NULL,
    checkout_url VARCHAR(500) DEFAULT NULL,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_mp_preferencia (preference_id),
    UNIQUE KEY uk_mp_envio (id_envio),
    CONSTRAINT fk_mp_envio FOREIGN KEY (id_envio) REFERENCES envios(id_envio),
    CONSTRAINT fk_mp_turno FOREIGN KEY (id_turno) REFERENCES turnos_caja(id_turno),
    CONSTRAINT fk_mp_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
SET @mp_indice = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='pagos' AND INDEX_NAME='uk_pago_externo');
SET @mp_sql = IF(@mp_indice=0, 'ALTER TABLE pagos ADD UNIQUE KEY uk_pago_externo (id_transaccion_ext)', 'DO 0');
PREPARE mp_stmt FROM @mp_sql;
EXECUTE mp_stmt;
DEALLOCATE PREPARE mp_stmt;
