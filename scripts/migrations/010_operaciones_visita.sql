CREATE TABLE IF NOT EXISTS operaciones_visita (
    id_chofer INT NOT NULL,
    clave VARCHAR(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    huella CHAR(64) CHARACTER SET ascii NOT NULL,
    id_intento INT NOT NULL,
    PRIMARY KEY (id_chofer, clave),
    UNIQUE KEY uq_operacion_intento (id_intento),
    FOREIGN KEY (id_intento) REFERENCES intentos_entrega(id_intento)
) ENGINE=InnoDB;
