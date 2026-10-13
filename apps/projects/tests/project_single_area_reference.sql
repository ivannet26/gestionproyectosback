CREATE TABLE `area` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `codigo` varchar(30) NOT NULL,
  `nombre` varchar(120) NOT NULL,
  `activa` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `codigo` (`codigo`),
  UNIQUE KEY `nombre` (`nombre`),
  CONSTRAINT `ck_area_activa` CHECK ((`activa` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `cliente` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `nombre` varchar(180) NOT NULL,
  `identificacion` varchar(30) DEFAULT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `identificacion` (`identificacion`),
  CONSTRAINT `ck_cliente_activo` CHECK ((`activo` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tipo_proyecto` (
  `codigo` varchar(30) NOT NULL,
  `nombre` varchar(100) NOT NULL,
  PRIMARY KEY (`codigo`),
  UNIQUE KEY `nombre` (`nombre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `estado_proyecto` (
  `codigo` varchar(20) NOT NULL,
  `nombre` varchar(70) NOT NULL,
  `terminal` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`codigo`),
  UNIQUE KEY `nombre` (`nombre`),
  CONSTRAINT `ck_estado_proyecto_terminal` CHECK ((`terminal` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `proyecto` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `codigo` varchar(40) NOT NULL,
  `nombre` varchar(180) NOT NULL,
  `descripcion` text,
  `area_id` bigint unsigned NOT NULL,
  `tipo_codigo` varchar(30) NOT NULL,
  `cliente_id` bigint unsigned DEFAULT NULL,
  `estado_codigo` varchar(20) NOT NULL DEFAULT 'BORRADOR',
  `prioridad` tinyint unsigned NOT NULL DEFAULT '3',
  `fecha_inicio` date DEFAULT NULL,
  `fecha_fin` date DEFAULT NULL,
  `confidencial` tinyint(1) NOT NULL DEFAULT '0',
  `archivado` tinyint(1) NOT NULL DEFAULT '0',
  `motivo_cambio` varchar(500) DEFAULT NULL,
  `creado_en` datetime(6) NOT NULL DEFAULT (utc_timestamp(6)),
  `actualizado_en` datetime(6) NOT NULL DEFAULT (utc_timestamp(6)),
  `disponible_por_area` tinyint(1) NOT NULL DEFAULT '0',
  `trabajador_edita_tareas` tinyint(1) NOT NULL DEFAULT '0',
  `trabajador_cambia_estado` tinyint(1) NOT NULL DEFAULT '0',
  `trabajador_crea_tareas` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `codigo` (`codigo`),
  KEY `fk_proyecto_16` (`tipo_codigo`),
  KEY `fk_proyecto_17` (`cliente_id`),
  KEY `fk_proyecto_18` (`estado_codigo`),
  KEY `ix_proyecto_seguimiento` (`area_id`,`archivado`,`estado_codigo`,`fecha_fin`),
  CONSTRAINT `fk_proyecto_15` FOREIGN KEY (`area_id`) REFERENCES `area` (`id`),
  CONSTRAINT `fk_proyecto_16` FOREIGN KEY (`tipo_codigo`) REFERENCES `tipo_proyecto` (`codigo`),
  CONSTRAINT `fk_proyecto_17` FOREIGN KEY (`cliente_id`) REFERENCES `cliente` (`id`),
  CONSTRAINT `fk_proyecto_18` FOREIGN KEY (`estado_codigo`) REFERENCES `estado_proyecto` (`codigo`),
  CONSTRAINT `ck_proyecto_booleanos` CHECK (((`confidencial` in (0,1)) and (`archivado` in (0,1)))),
  CONSTRAINT `ck_proyecto_disponible_por_area` CHECK ((`disponible_por_area` in (0,1))),
  CONSTRAINT `ck_proyecto_fechas` CHECK ((`fecha_fin` >= `fecha_inicio`)),
  CONSTRAINT `ck_proyecto_prioridad` CHECK ((`prioridad` between 1 and 4)),
  CONSTRAINT `ck_proyecto_trabajador_cambia_estado` CHECK ((`trabajador_cambia_estado` in (0,1))),
  CONSTRAINT `ck_proyecto_trabajador_crea_tareas` CHECK ((`trabajador_crea_tareas` in (0,1))),
  CONSTRAINT `ck_proyecto_trabajador_edita_tareas` CHECK ((`trabajador_edita_tareas` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `proyecto_area` (
  `area_id` bigint unsigned NOT NULL,
  `proyecto_id` bigint unsigned NOT NULL,
  PRIMARY KEY (`proyecto_id`,`area_id`),
  KEY `proyecto_area_area_id_8b15bd51` (`area_id`),
  KEY `proyecto_area_proyecto_id_220374a3` (`proyecto_id`),
  CONSTRAINT `fk_proyecto_area_area` FOREIGN KEY (`area_id`) REFERENCES `area` (`id`),
  CONSTRAINT `fk_proyecto_area_proyecto` FOREIGN KEY (`proyecto_id`) REFERENCES `proyecto` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
