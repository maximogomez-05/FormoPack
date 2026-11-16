SET @carga_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='vehiculos' AND COLUMN_NAME='volumen_maximo_m3');
SET @carga_sql = IF(@carga_existe=0,'ALTER TABLE vehiculos ADD COLUMN volumen_maximo_m3 DECIMAL(10,3) NOT NULL DEFAULT 0.000','DO 0');
PREPARE carga_stmt FROM @carga_sql;
EXECUTE carga_stmt;
DEALLOCATE PREPARE carga_stmt;

SET @carga_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='bultos' AND COLUMN_NAME='volumen_m3');
SET @carga_sql = IF(@carga_existe=0,'ALTER TABLE bultos ADD COLUMN volumen_m3 DECIMAL(10,3) DEFAULT NULL','DO 0');
PREPARE carga_stmt FROM @carga_sql;
EXECUTE carga_stmt;
DEALLOCATE PREPARE carga_stmt;

-- Reconstruye una estimación con el factor volumétrico histórico (5000 cm³/kg).
UPDATE bultos
SET volumen_m3 = ROUND(peso_volumetrico / 200, 3)
WHERE volumen_m3 IS NULL AND peso_volumetrico > 0;
