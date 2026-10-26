-- ============================================================
-- FormoPack Express — Script DDL de Inicialización
-- Base de Datos: formopack_db
-- Versión: 1.0 (Sprint 2)
-- Motor: MySQL 8.0+ / InnoDB
-- ============================================================

CREATE DATABASE IF NOT EXISTS formopack_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE formopack_db;

-- ============================================================
-- 1. USUARIOS (ya existente del Sprint 1, se recrea si no existe)
-- ============================================================
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario      INT(11)         NOT NULL AUTO_INCREMENT,
    nombre          VARCHAR(100)    NOT NULL,
    email           VARCHAR(100)    NOT NULL,
    credenciales_hash VARCHAR(255)  NOT NULL,
    tipo_usuario    ENUM('administrador', 'recepcionista', 'chofer') NOT NULL,
    nro_licencia    VARCHAR(50)     DEFAULT NULL,
    activo          TINYINT(1)      NOT NULL DEFAULT 1,
    PRIMARY KEY (id_usuario),
    UNIQUE KEY uk_usuarios_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS recuperacion_contrasenas (
    id_recuperacion INT(11)         NOT NULL AUTO_INCREMENT,
    id_usuario      INT(11)         NOT NULL,
    codigo          VARCHAR(10)     NOT NULL,
    expira_en       DATETIME        NOT NULL,
    utilizado       TINYINT(1)      NOT NULL DEFAULT 0,
    creado_en       TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_recuperacion),
    INDEX idx_recuperacion_usuario (id_usuario),
    INDEX idx_recuperacion_codigo (codigo),
    CONSTRAINT fk_recuperacion_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 2. CLIENTES (Remitentes y Destinatarios)
-- ============================================================
CREATE TABLE IF NOT EXISTS clientes (
    id_cliente      INT(11)         NOT NULL AUTO_INCREMENT,
    dni             VARCHAR(15)     NOT NULL,
    nombre_completo VARCHAR(100)    NOT NULL,
    telefono        VARCHAR(20)     NOT NULL,
    email           VARCHAR(100)    DEFAULT NULL,
    PRIMARY KEY (id_cliente),
    UNIQUE KEY uk_clientes_dni (dni),
    INDEX idx_clientes_telefono (telefono)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 3. LOCALIDADES (Destinos con distancia en KM para ruteo)
-- ============================================================
CREATE TABLE IF NOT EXISTS localidades (
    id_localidad    INT(11)         NOT NULL AUTO_INCREMENT,
    nombre          VARCHAR(100)    NOT NULL,
    distancia_km    DECIMAL(8,2)    NOT NULL DEFAULT 0.00,
    PRIMARY KEY (id_localidad),
    UNIQUE KEY uk_localidades_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 4. SEGUROS (Coberturas y porcentajes por excedente)
-- ============================================================
CREATE TABLE IF NOT EXISTS seguros (
    id_seguro               INT(11)         NOT NULL AUTO_INCREMENT,
    cobertura_estandar      DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    porcentaje_excedente    DECIMAL(5,2)    NOT NULL DEFAULT 0.00,
    PRIMARY KEY (id_seguro)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 5. VEHÍCULOS (Flota de transporte)
-- ============================================================
CREATE TABLE IF NOT EXISTS vehiculos (
    id_vehiculo     INT(11)         NOT NULL AUTO_INCREMENT,
    patente         VARCHAR(10)     NOT NULL,
    capacidad_kg    DECIMAL(10,2)   NOT NULL DEFAULT 0.00,
    estado          VARCHAR(30)     NOT NULL DEFAULT 'disponible',
    PRIMARY KEY (id_vehiculo),
    UNIQUE KEY uk_vehiculos_patente (patente)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 6. HOJAS DE RUTA (Despachos asignados a chofer + vehículo)
-- ============================================================
CREATE TABLE IF NOT EXISTS hojas_de_ruta (
    id_hoja_ruta    INT(11)         NOT NULL AUTO_INCREMENT,
    nro_despacho    VARCHAR(20)     NOT NULL,
    fecha_emision   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id_chofer       INT(11)         NOT NULL,
    id_vehiculo     INT(11)         NOT NULL,
    estado          ENUM('abierta','cerrada') NOT NULL DEFAULT 'abierta',
    fecha_cierre    DATETIME                  DEFAULT NULL,
    PRIMARY KEY (id_hoja_ruta),
    UNIQUE KEY uk_hojas_nro_despacho (nro_despacho),
    CONSTRAINT fk_hojas_chofer    FOREIGN KEY (id_chofer)   REFERENCES usuarios(id_usuario),
    CONSTRAINT fk_hojas_vehiculo  FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ubicaciones_hojas_ruta (
    id_hoja_ruta    INT(11)         NOT NULL,
    id_chofer       INT(11)         NOT NULL,
    latitud         DECIMAL(10,7)   NOT NULL,
    longitud        DECIMAL(10,7)   NOT NULL,
    precision_m     DECIMAL(8,2)    DEFAULT NULL,
    fecha_actualizacion DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_hoja_ruta),
    INDEX idx_ubicaciones_fecha (fecha_actualizacion),
    CONSTRAINT fk_ubicacion_hoja FOREIGN KEY (id_hoja_ruta) REFERENCES hojas_de_ruta(id_hoja_ruta) ON DELETE CASCADE,
    CONSTRAINT fk_ubicacion_chofer FOREIGN KEY (id_chofer) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 7. ENVÍOS (Entidad central del sistema)
-- ============================================================
CREATE TABLE IF NOT EXISTS envios (
    id_envio            INT(11)         NOT NULL AUTO_INCREMENT,
    nro_guia            VARCHAR(20)     NOT NULL,
    id_remitente        INT(11)         NOT NULL,
    id_destinatario     INT(11)         NOT NULL,
    id_localidad_destino INT(11)        NOT NULL,
    id_seguro           INT(11)         DEFAULT NULL,
    id_hoja_ruta        INT(11)         DEFAULT NULL,
    direccion_destino   VARCHAR(200)    NOT NULL,
    valor_declarado     DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    modalidad_pago      ENUM('efectivo', 'digital', 'cuenta_corriente') NOT NULL DEFAULT 'efectivo',
    costo_total         DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    estado_actual       VARCHAR(30)     NOT NULL DEFAULT 'recibido',
    es_devolucion       TINYINT(1)      NOT NULL DEFAULT 0,
    fecha_creacion      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_envio),
    UNIQUE KEY uk_envios_nro_guia (nro_guia),
    INDEX idx_envios_estado (estado_actual),
    INDEX idx_envios_fecha (fecha_creacion),
    CONSTRAINT fk_envios_remitente      FOREIGN KEY (id_remitente)          REFERENCES clientes(id_cliente),
    CONSTRAINT fk_envios_destinatario   FOREIGN KEY (id_destinatario)       REFERENCES clientes(id_cliente),
    CONSTRAINT fk_envios_localidad      FOREIGN KEY (id_localidad_destino)  REFERENCES localidades(id_localidad),
    CONSTRAINT fk_envios_seguro         FOREIGN KEY (id_seguro)             REFERENCES seguros(id_seguro),
    CONSTRAINT fk_envios_hoja_ruta      FOREIGN KEY (id_hoja_ruta)          REFERENCES hojas_de_ruta(id_hoja_ruta)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 8. BULTOS (Paquetes individuales de un envío)
-- ============================================================
CREATE TABLE IF NOT EXISTS bultos (
    id_bulto            INT(11)         NOT NULL AUTO_INCREMENT,
    id_envio            INT(11)         NOT NULL,
    peso_real           DECIMAL(8,2)    NOT NULL DEFAULT 0.00,
    peso_volumetrico    DECIMAL(8,2)    NOT NULL DEFAULT 0.00,
    es_fragil           TINYINT(1)      NOT NULL DEFAULT 0,
    PRIMARY KEY (id_bulto),
    INDEX idx_bultos_envio (id_envio),
    CONSTRAINT fk_bultos_envio FOREIGN KEY (id_envio) REFERENCES envios(id_envio) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 9. HISTORIAL DE ESTADOS (Timeline de tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS historial_estados (
    id_historial    INT(11)         NOT NULL AUTO_INCREMENT,
    id_envio        INT(11)         NOT NULL,
    fecha_hora      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado          VARCHAR(30)     NOT NULL,
    ubicacion       VARCHAR(100)    DEFAULT NULL,
    observacion     TEXT            DEFAULT NULL,
    PRIMARY KEY (id_historial),
    INDEX idx_historial_envio (id_envio),
    INDEX idx_historial_fecha (fecha_hora),
    CONSTRAINT fk_historial_envio FOREIGN KEY (id_envio) REFERENCES envios(id_envio) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 10. TURNOS DE CAJA (Apertura/Cierre por recepcionista)
-- ============================================================
CREATE TABLE IF NOT EXISTS turnos_caja (
    id_turno            INT(11)         NOT NULL AUTO_INCREMENT,
    id_recepcionista    INT(11)         NOT NULL,
    fecha_apertura      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre        DATETIME        DEFAULT NULL,
    saldo_inicial       DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    ingresos_efectivo   DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    ingresos_digitales  DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    estado_caja         ENUM('abierto', 'cerrado') NOT NULL DEFAULT 'abierto',
    PRIMARY KEY (id_turno),
    INDEX idx_turnos_recepcionista (id_recepcionista),
    INDEX idx_turnos_estado (estado_caja),
    CONSTRAINT fk_turnos_recepcionista FOREIGN KEY (id_recepcionista) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 11. PAGOS (Registro de cobros por envío)
-- ============================================================
CREATE TABLE IF NOT EXISTS pagos (
    id_pago             INT(11)         NOT NULL AUTO_INCREMENT,
    id_envio            INT(11)         NOT NULL,
    id_turno            INT(11)         DEFAULT NULL,
    monto               DECIMAL(12,2)   NOT NULL,
    fecha               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tipo_pago           ENUM('efectivo', 'digital') NOT NULL DEFAULT 'efectivo',
    monto_entregado     DECIMAL(12,2)   DEFAULT NULL,
    id_transaccion_qr   VARCHAR(100)    DEFAULT NULL,
    billetera_virtual   VARCHAR(50)     DEFAULT NULL,
    id_transaccion_ext  VARCHAR(100)    DEFAULT NULL COMMENT 'ID de pago externo (Mercado Pago payment_id)',
    PRIMARY KEY (id_pago),
    INDEX idx_pagos_envio (id_envio),
    INDEX idx_pagos_turno (id_turno),
    INDEX idx_pagos_transaccion_ext (id_transaccion_ext),
    CONSTRAINT fk_pagos_envio  FOREIGN KEY (id_envio)  REFERENCES envios(id_envio),
    CONSTRAINT fk_pagos_turno  FOREIGN KEY (id_turno)  REFERENCES turnos_caja(id_turno)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 12. COMPROBANTES INTERNOS (No fiscales, PDF)
-- ============================================================
CREATE TABLE IF NOT EXISTS comprobantes_internos (
    id_comprobante      INT(11)         NOT NULL AUTO_INCREMENT,
    id_envio            INT(11)         NOT NULL,
    nro_comprobante     VARCHAR(30)     NOT NULL,
    tipo_comprobante    VARCHAR(20)     NOT NULL DEFAULT 'recepcion',
    fecha_emision       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_comprobante),
    UNIQUE KEY uk_comprobantes_nro (nro_comprobante),
    INDEX idx_comprobantes_envio (id_envio),
    CONSTRAINT fk_comprobantes_envio FOREIGN KEY (id_envio) REFERENCES envios(id_envio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 13. INTENTOS DE ENTREGA (POD - Prueba de Entrega)
-- ============================================================
CREATE TABLE IF NOT EXISTS intentos_entrega (
    id_intento          INT(11)         NOT NULL AUTO_INCREMENT,
    id_envio            INT(11)         NOT NULL,
    id_hoja_ruta        INT(11)         NOT NULL,
    fecha_hora          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    coordenadas_gps     VARCHAR(50)     DEFAULT NULL,
    tipo_intento        ENUM('entregado', 'fallido') NOT NULL,
    dni_receptor        VARCHAR(15)     DEFAULT NULL,
    firma_receptor      TEXT            DEFAULT NULL,
    foto_remito         VARCHAR(255)    DEFAULT NULL,
    motivo_fallo        VARCHAR(100)    DEFAULT NULL,
    PRIMARY KEY (id_intento),
    INDEX idx_intentos_envio (id_envio),
    INDEX idx_intentos_hoja (id_hoja_ruta),
    CONSTRAINT fk_intentos_envio      FOREIGN KEY (id_envio)      REFERENCES envios(id_envio),
    CONSTRAINT fk_intentos_hoja_ruta  FOREIGN KEY (id_hoja_ruta)  REFERENCES hojas_de_ruta(id_hoja_ruta)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 14. CHATS DE SOPORTE AL CLIENTE
-- ============================================================
CREATE TABLE IF NOT EXISTS chats_soporte (
    id_chat             INT(11)         NOT NULL AUTO_INCREMENT,
    session_id          VARCHAR(64)     NOT NULL,
    cliente_nombre      VARCHAR(100)    NOT NULL,
    cliente_email       VARCHAR(120)    DEFAULT NULL,
    nro_guia            VARCHAR(30)     DEFAULT NULL,
    estado              ENUM('sin_atender', 'en_progreso') NOT NULL DEFAULT 'sin_atender',
    id_usuario_atendiendo INT(11)       DEFAULT NULL,
    nombre_usuario_atendiendo VARCHAR(100) DEFAULT NULL,
    fecha_creacion      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id_chat),
    UNIQUE KEY uk_chats_session (session_id),
    INDEX idx_soporte_estado (estado),
    INDEX idx_soporte_usuario (id_usuario_atendiendo),
    CONSTRAINT fk_soporte_usuario FOREIGN KEY (id_usuario_atendiendo) REFERENCES usuarios(id_usuario) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 15. MENSAJES DE SOPORTE AL CLIENTE
-- ============================================================
CREATE TABLE IF NOT EXISTS mensajes_soporte (
    id_mensaje          INT(11)         NOT NULL AUTO_INCREMENT,
    id_chat             INT(11)         NOT NULL,
    remitente_tipo      ENUM('cliente', 'soporte') NOT NULL,
    remitente_nombre    VARCHAR(100)    NOT NULL,
    mensaje             TEXT            NOT NULL,
    fecha_envio         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_mensaje),
    INDEX idx_msg_chat (id_chat),
    CONSTRAINT fk_msg_chat FOREIGN KEY (id_chat) REFERENCES chats_soporte(id_chat) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- DATOS SEMILLA (Seed Data)
-- ============================================================

-- Localidades de Formosa con distancias aproximadas desde la capital
INSERT INTO localidades (nombre, distancia_km) VALUES
    ('Formosa Capital',     0.00),
    ('Clorinda',            120.00),
    ('Pirané',              180.00),
    ('El Colorado',         160.00),
    ('Laguna Blanca',       60.00),
    ('Ibarreta',            280.00),
    ('Las Lomitas',         300.00),
    ('Ingeniero Juárez',    450.00),
    ('Herradura',           40.00),
    ('Villa Dos Trece',     185.00),
    ('General Belgrano',    200.00),
    ('Comandante Fontana',  310.00),
    ('Estanislao del Campo', 330.00),
    ('Misión Laishí',       50.00),
    ('San Martín Dos',      360.00)
ON DUPLICATE KEY UPDATE distancia_km = VALUES(distancia_km);

-- Seguro base (cobertura estándar gratuita hasta $50.000)
INSERT INTO seguros (cobertura_estandar, porcentaje_excedente) VALUES
    (50000.00, 2.00),
    (100000.00, 1.50),
    (250000.00, 1.00)
ON DUPLICATE KEY UPDATE
    cobertura_estandar = VALUES(cobertura_estandar),
    porcentaje_excedente = VALUES(porcentaje_excedente);

-- Usuarios iniciales de prueba (contraseñas con hash Bcrypt)
-- admin@formopack.com / admin123
-- recepcion@formopack.com / recep456
-- chofer@formopack.com / chofer789
INSERT INTO usuarios (nombre, email, credenciales_hash, tipo_usuario, nro_licencia, activo) VALUES
    ('Administrador Sistema', 'admin@formopack.com', '$2b$12$2RijUv8m0fZ5XAVEfg6I..zvCToVW8dmtmD3KJFzAP3c1s1m3erPS', 'administrador', NULL, 1),
    ('Maria Recepcionista', 'recepcion@formopack.com', '$2b$12$FKOiYKNciRZJkko/.c.u0emTbfo8BddiG5QYVuIUGYkUOntOUAJqi', 'recepcionista', NULL, 1),
    ('Carlos Chofer', 'chofer@formopack.com', '$2b$12$hKw3va/yuDZddKdx8fti..orvEm3327VLE5Q0wLmRl/Cl4f.k31ZC', 'chofer', 'LI-123456', 1)
ON DUPLICATE KEY UPDATE
    id_usuario = usuarios.id_usuario;

-- ============================================================
-- MIGRACIONES IDEMPOTENTES (compatibilidad con BDs existentes)
-- ============================================================
SET @formopack_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'clientes' AND COLUMN_NAME = 'email');
SET @formopack_sql = IF(@formopack_existe = 0,
    'ALTER TABLE clientes ADD COLUMN email VARCHAR(100) DEFAULT NULL', 'DO 0');
PREPARE formopack_stmt FROM @formopack_sql;
EXECUTE formopack_stmt;
DEALLOCATE PREPARE formopack_stmt;
SET @formopack_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'hojas_de_ruta' AND COLUMN_NAME = 'estado');
SET @formopack_sql = IF(@formopack_existe = 0,
    'ALTER TABLE hojas_de_ruta ADD COLUMN estado ENUM(''abierta'',''cerrada'') NOT NULL DEFAULT ''abierta''', 'DO 0');
PREPARE formopack_stmt FROM @formopack_sql;
EXECUTE formopack_stmt;
DEALLOCATE PREPARE formopack_stmt;
SET @formopack_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'hojas_de_ruta' AND COLUMN_NAME = 'fecha_cierre');
SET @formopack_sql = IF(@formopack_existe = 0,
    'ALTER TABLE hojas_de_ruta ADD COLUMN fecha_cierre DATETIME DEFAULT NULL', 'DO 0');
PREPARE formopack_stmt FROM @formopack_sql;
EXECUTE formopack_stmt;
DEALLOCATE PREPARE formopack_stmt;

-- ============================================================
-- FIN DEL SCRIPT DDL
-- ============================================================

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

-- No cambia contraseñas ni obliga a cuentas existentes a renovar su clave.
SET @primer_acceso_existe = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='usuarios' AND COLUMN_NAME='debe_cambiar_password');
SET @primer_acceso_sql = IF(@primer_acceso_existe=0,
    'ALTER TABLE usuarios ADD COLUMN debe_cambiar_password TINYINT(1) NOT NULL DEFAULT 0', 'DO 0');
PREPARE primer_acceso_stmt FROM @primer_acceso_sql;
EXECUTE primer_acceso_stmt;
DEALLOCATE PREPARE primer_acceso_stmt;

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
