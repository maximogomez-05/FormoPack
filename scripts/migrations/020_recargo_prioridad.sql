SET @prioridad_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='envios' AND COLUMN_NAME='porcentaje_recargo_prioridad');
SET @prioridad_sql = IF(@prioridad_existe=0,'ALTER TABLE envios ADD COLUMN porcentaje_recargo_prioridad DECIMAL(5,2) NOT NULL DEFAULT 0.00','DO 0');
PREPARE prioridad_stmt FROM @prioridad_sql;
EXECUTE prioridad_stmt;
DEALLOCATE PREPARE prioridad_stmt;

SET @prioridad_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='envios' AND COLUMN_NAME='recargo_prioridad');
SET @prioridad_sql = IF(@prioridad_existe=0,'ALTER TABLE envios ADD COLUMN recargo_prioridad DECIMAL(12,2) NOT NULL DEFAULT 0.00','DO 0');
PREPARE prioridad_stmt FROM @prioridad_sql;
EXECUTE prioridad_stmt;
DEALLOCATE PREPARE prioridad_stmt;
