-- Historial de asignaciones por visita, independiente de la ruta actual del envío.
CREATE TABLE IF NOT EXISTS hojas_ruta_envios (
    id_hoja_ruta INT NOT NULL,
    id_envio INT NOT NULL,
    resolucion VARCHAR(30) DEFAULT NULL,
    fecha_resolucion DATETIME DEFAULT NULL,
    PRIMARY KEY (id_hoja_ruta,id_envio),
    CONSTRAINT fk_asignacion_hoja FOREIGN KEY (id_hoja_ruta) REFERENCES hojas_de_ruta(id_hoja_ruta),
    CONSTRAINT fk_asignacion_envio FOREIGN KEY (id_envio) REFERENCES envios(id_envio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
SET @log_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hojas_de_ruta' AND COLUMN_NAME='fecha_inicio');
SET @log_sql = IF(@log_existe=0,'ALTER TABLE hojas_de_ruta ADD COLUMN fecha_inicio DATETIME DEFAULT NULL','DO 0');
PREPARE log_stmt FROM @log_sql;
EXECUTE log_stmt;
DEALLOCATE PREPARE log_stmt;
SET @log_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='historial_estados' AND COLUMN_NAME='id_usuario_actor');
SET @log_sql = IF(@log_existe=0,'ALTER TABLE historial_estados ADD COLUMN id_usuario_actor INT DEFAULT NULL','DO 0');
PREPARE log_stmt FROM @log_sql;
EXECUTE log_stmt;
DEALLOCATE PREPARE log_stmt;
INSERT IGNORE INTO hojas_ruta_envios (id_hoja_ruta,id_envio,resolucion)
SELECT id_hoja_ruta,id_envio,CASE WHEN estado_actual IN ('entregado','devolucion','siniestro') THEN estado_actual ELSE NULL END
FROM envios WHERE id_hoja_ruta IS NOT NULL;
INSERT INTO hojas_ruta_envios (id_hoja_ruta,id_envio,resolucion,fecha_resolucion)
SELECT i.id_hoja_ruta,i.id_envio,i.tipo_intento,i.fecha_hora FROM intentos_entrega i
WHERE i.id_intento=(SELECT MAX(j.id_intento) FROM intentos_entrega j WHERE j.id_envio=i.id_envio AND j.id_hoja_ruta=i.id_hoja_ruta)
ON DUPLICATE KEY UPDATE resolucion=COALESCE(hojas_ruta_envios.resolucion,VALUES(resolucion)),fecha_resolucion=COALESCE(hojas_ruta_envios.fecha_resolucion,VALUES(fecha_resolucion));
UPDATE hojas_de_ruta h SET fecha_inicio=(SELECT MIN(i.fecha_hora) FROM intentos_entrega i WHERE i.id_hoja_ruta=h.id_hoja_ruta)
WHERE fecha_inicio IS NULL AND EXISTS (SELECT 1 FROM intentos_entrega i WHERE i.id_hoja_ruta=h.id_hoja_ruta);

SET @log_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hojas_de_ruta' AND COLUMN_NAME='chofer_activo');
SET @log_sql = IF(@log_existe=0,'ALTER TABLE hojas_de_ruta ADD COLUMN chofer_activo INT GENERATED ALWAYS AS (CASE WHEN estado = ''abierta'' THEN id_chofer ELSE NULL END) STORED','DO 0');
PREPARE log_stmt FROM @log_sql;
EXECUTE log_stmt;
DEALLOCATE PREPARE log_stmt;
SET @log_existe = (SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hojas_de_ruta' AND INDEX_NAME='uk_chofer_activo');
SET @log_sql = IF(@log_existe=0,'ALTER TABLE hojas_de_ruta ADD UNIQUE KEY uk_chofer_activo (chofer_activo)','DO 0');
PREPARE log_stmt FROM @log_sql;
EXECUTE log_stmt;
DEALLOCATE PREPARE log_stmt;

SET @log_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hojas_de_ruta' AND COLUMN_NAME='vehiculo_activo');
SET @log_sql = IF(@log_existe=0,'ALTER TABLE hojas_de_ruta ADD COLUMN vehiculo_activo INT GENERATED ALWAYS AS (CASE WHEN estado = ''abierta'' THEN id_vehiculo ELSE NULL END) STORED','DO 0');
PREPARE log_stmt FROM @log_sql;
EXECUTE log_stmt;
DEALLOCATE PREPARE log_stmt;
SET @log_existe = (SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='hojas_de_ruta' AND INDEX_NAME='uk_vehiculo_activo');
SET @log_sql = IF(@log_existe=0,'ALTER TABLE hojas_de_ruta ADD UNIQUE KEY uk_vehiculo_activo (vehiculo_activo)','DO 0');
PREPARE log_stmt FROM @log_sql;
EXECUTE log_stmt;
DEALLOCATE PREPARE log_stmt;
