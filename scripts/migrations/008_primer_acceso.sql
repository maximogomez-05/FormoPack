-- No cambia contraseñas ni obliga a cuentas existentes a renovar su clave.
SET @primer_acceso_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='usuarios' AND COLUMN_NAME='debe_cambiar_password');
SET @primer_acceso_sql = IF(@primer_acceso_existe=0,
    'ALTER TABLE usuarios ADD COLUMN debe_cambiar_password TINYINT(1) NOT NULL DEFAULT 0', 'DO 0');
PREPARE primer_acceso_stmt FROM @primer_acceso_sql;
EXECUTE primer_acceso_stmt;
DEALLOCATE PREPARE primer_acceso_stmt;
