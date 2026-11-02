CREATE TABLE IF NOT EXISTS retiros_central (
 id_envio INT PRIMARY KEY,
 ingreso DATETIME NOT NULL,
 recibe INT NOT NULL,
 vence DATE NOT NULL,
 retiro DATETIME NULL,
 entrega INT NULL,
 dni VARCHAR(15) NULL,
 firma TEXT NULL,
 FOREIGN KEY (id_envio) REFERENCES envios(id_envio),
 FOREIGN KEY (recibe) REFERENCES usuarios(id_usuario),
 FOREIGN KEY (entrega) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB;
INSERT INTO historial_estados (id_envio,estado,ubicacion,observacion)
SELECT e.id_envio,'devolucion','Retorno pendiente','Tres visitas fallidas previas. Pendiente de confirmar ingreso físico.'
FROM envios e WHERE e.estado_actual='fallido' AND
(SELECT COUNT(*) FROM intentos_entrega i WHERE i.id_envio=e.id_envio AND i.tipo_intento='fallido')>=3
AND NOT EXISTS (SELECT 1 FROM historial_estados h WHERE h.id_envio=e.id_envio AND h.estado='devolucion');
UPDATE envios e SET estado_actual='devolucion',es_devolucion=1 WHERE estado_actual='fallido'
AND (SELECT COUNT(*) FROM intentos_entrega i WHERE i.id_envio=e.id_envio AND i.tipo_intento='fallido')>=3;
