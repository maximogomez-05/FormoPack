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

-- ============================================================
-- 2. CLIENTES (Remitentes y Destinatarios)
-- ============================================================
CREATE TABLE IF NOT EXISTS clientes (
    id_cliente      INT(11)         NOT NULL AUTO_INCREMENT,
    dni             VARCHAR(15)     NOT NULL,
    nombre_completo VARCHAR(100)    NOT NULL,
    telefono        VARCHAR(20)     NOT NULL,
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
    PRIMARY KEY (id_hoja_ruta),
    UNIQUE KEY uk_hojas_nro_despacho (nro_despacho),
    CONSTRAINT fk_hojas_chofer    FOREIGN KEY (id_chofer)   REFERENCES usuarios(id_usuario),
    CONSTRAINT fk_hojas_vehiculo  FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
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
    PRIMARY KEY (id_pago),
    INDEX idx_pagos_envio (id_envio),
    INDEX idx_pagos_turno (id_turno),
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

-- ============================================================
-- FIN DEL SCRIPT DDL
-- ============================================================
