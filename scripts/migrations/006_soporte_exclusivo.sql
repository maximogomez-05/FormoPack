-- Cierre, purga de mensajes y exclusividad de soporte. Detener la aplicación antes de migrar.
ALTER TABLE chats_soporte MODIFY estado ENUM('sin_atender','en_progreso','cerrado') NOT NULL DEFAULT 'sin_atender';
SET @soporte_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='chats_soporte' AND COLUMN_NAME='fecha_cierre');
SET @soporte_sql = IF(@soporte_existe=0, 'ALTER TABLE chats_soporte ADD COLUMN fecha_cierre DATETIME DEFAULT NULL', 'DO 0');
PREPARE soporte_stmt FROM @soporte_sql;
EXECUTE soporte_stmt;
DEALLOCATE PREPARE soporte_stmt;
SET @soporte_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='chats_soporte' AND COLUMN_NAME='id_usuario_cierre');
SET @soporte_sql = IF(@soporte_existe=0, 'ALTER TABLE chats_soporte ADD COLUMN id_usuario_cierre INT DEFAULT NULL', 'DO 0');
PREPARE soporte_stmt FROM @soporte_sql;
EXECUTE soporte_stmt;
DEALLOCATE PREPARE soporte_stmt;

-- La baja de personal es lógica. RESTRICT preserva los responsables históricos.
SET @soporte_fk = NULL;
SELECT CONSTRAINT_NAME INTO @soporte_fk FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='chats_soporte'
  AND COLUMN_NAME='id_usuario_atendiendo' AND REFERENCED_TABLE_NAME='usuarios' LIMIT 1;
SET @soporte_sql = IF(@soporte_fk IS NULL, 'DO 0', CONCAT('ALTER TABLE chats_soporte DROP FOREIGN KEY `', REPLACE(@soporte_fk, '`', '``'), '`'));
PREPARE soporte_stmt FROM @soporte_sql;
EXECUTE soporte_stmt;
DEALLOCATE PREPARE soporte_stmt;
ALTER TABLE chats_soporte ADD CONSTRAINT fk_soporte_operador FOREIGN KEY (id_usuario_atendiendo) REFERENCES usuarios(id_usuario);
SET @soporte_existe = (SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='chats_soporte'
      AND COLUMN_NAME='id_usuario_cierre' AND REFERENCED_TABLE_NAME='usuarios');
SET @soporte_sql = IF(@soporte_existe=0, 'ALTER TABLE chats_soporte ADD CONSTRAINT fk_soporte_cierre FOREIGN KEY (id_usuario_cierre) REFERENCES usuarios(id_usuario)', 'DO 0');
PREPARE soporte_stmt FROM @soporte_sql;
EXECUTE soporte_stmt;
DEALLOCATE PREPARE soporte_stmt;
UPDATE chats_soporte SET estado='sin_atender' WHERE estado='en_progreso' AND id_usuario_atendiendo IS NULL;
SET @soporte_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='chats_soporte' AND COLUMN_NAME='operador_activo');
SET @soporte_sql = IF(@soporte_existe=0, 'ALTER TABLE chats_soporte ADD COLUMN operador_activo INT GENERATED ALWAYS AS (CASE WHEN estado = ''en_progreso'' THEN id_usuario_atendiendo ELSE NULL END) STORED', 'DO 0');
PREPARE soporte_stmt FROM @soporte_sql;
EXECUTE soporte_stmt;
DEALLOCATE PREPARE soporte_stmt;
SET @soporte_existe = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='chats_soporte' AND INDEX_NAME='uk_soporte_operador_activo');
SET @soporte_sql = IF(@soporte_existe=0, 'ALTER TABLE chats_soporte ADD UNIQUE KEY uk_soporte_operador_activo (operador_activo)', 'DO 0');
PREPARE soporte_stmt FROM @soporte_sql;
EXECUTE soporte_stmt;
DEALLOCATE PREPARE soporte_stmt;
