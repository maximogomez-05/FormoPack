CREATE TABLE IF NOT EXISTS correlativos_guia (
    fecha CHAR(8) PRIMARY KEY,
    ultimo INT UNSIGNED NOT NULL
) ENGINE=InnoDB;

INSERT INTO correlativos_guia (fecha, ultimo)
SELECT SUBSTRING(nro_guia, 5, 8), MAX(CAST(SUBSTRING(nro_guia, 14) AS UNSIGNED))
FROM envios
WHERE nro_guia REGEXP '^FPX-[0-9]{8}-[0-9]{1,7}$'
GROUP BY SUBSTRING(nro_guia, 5, 8)
ON DUPLICATE KEY UPDATE ultimo = GREATEST(ultimo, VALUES(ultimo));
