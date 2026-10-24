-- Seguridad de recuperación y revocación de sesiones. Ejecutar fuera del servidor web.
SET @formopack_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'usuarios' AND COLUMN_NAME = 'version_sesion');
SET @formopack_sql = IF(@formopack_existe = 0,
    'ALTER TABLE usuarios ADD COLUMN version_sesion INT UNSIGNED NOT NULL DEFAULT 0', 'DO 0');
PREPARE formopack_stmt FROM @formopack_sql;
EXECUTE formopack_stmt;
DEALLOCATE PREPARE formopack_stmt;
SET @formopack_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recuperacion_contrasenas' AND COLUMN_NAME = 'codigo_hash');
SET @formopack_sql = IF(@formopack_existe = 0,
    'ALTER TABLE recuperacion_contrasenas ADD COLUMN codigo_hash CHAR(64) DEFAULT NULL', 'DO 0');
PREPARE formopack_stmt FROM @formopack_sql;
EXECUTE formopack_stmt;
DEALLOCATE PREPARE formopack_stmt;
SET @formopack_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'recuperacion_contrasenas' AND COLUMN_NAME = 'intentos_fallidos');
SET @formopack_sql = IF(@formopack_existe = 0,
    'ALTER TABLE recuperacion_contrasenas ADD COLUMN intentos_fallidos TINYINT UNSIGNED NOT NULL DEFAULT 0', 'DO 0');
PREPARE formopack_stmt FROM @formopack_sql;
EXECUTE formopack_stmt;
DEALLOCATE PREPARE formopack_stmt;

-- Invalidar y borrar OTP antiguos en claro. Los nuevos registros usan codigo vacío.
UPDATE recuperacion_contrasenas SET codigo = '', utilizado = 1 WHERE codigo <> '';

CREATE TABLE IF NOT EXISTS limites_recuperacion (
    clave_cuenta CHAR(64) NOT NULL PRIMARY KEY,
    ventana_inicio DATETIME NOT NULL,
    solicitudes INT UNSIGNED NOT NULL DEFAULT 0,
    ultimo_envio DATETIME DEFAULT NULL,
    INDEX idx_limites_ventana (ventana_inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
