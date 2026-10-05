CREATE PROCEDURE sp_cambiar_estado_actividad(IN p_proyecto BIGINT UNSIGNED,
 IN p_actividad BIGINT UNSIGNED,IN p_destino VARCHAR(20),IN p_motivo VARCHAR(500))
SQL SECURITY INVOKER
BEGIN
 DECLARE v_origen VARCHAR(20) DEFAULT NULL;
 DECLARE v_estado_proyecto VARCHAR(20) DEFAULT NULL;
 DECLARE v_responsable BIGINT UNSIGNED;
 DECLARE v_persona BIGINT UNSIGNED DEFAULT NULL;
 DECLARE v_supervision BOOLEAN DEFAULT FALSE;
 DECLARE v_administrador BOOLEAN DEFAULT FALSE;
 DECLARE v_req_supervision BOOLEAN;
 DECLARE v_req_motivo BOOLEAN;
 DECLARE v_descendientes INT;
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
 START TRANSACTION;
 SELECT estado_codigo INTO v_estado_proyecto FROM proyecto WHERE id=p_proyecto AND archivado=0 FOR UPDATE;
 SELECT estado_codigo,responsable_id INTO v_origen,v_responsable FROM actividad
 WHERE id=p_actividad AND proyecto_id=p_proyecto AND archivada=0 FOR UPDATE;
 SELECT u.trabajador_id INTO v_persona FROM usuario u JOIN trabajador t ON t.id=u.trabajador_id
 WHERE u.id=@gm_usuario_id AND u.activo=1 AND t.activo=1
 AND (SELECT COUNT(*) FROM usuario_rol ur WHERE ur.usuario_id=u.id)=1
 AND EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo IN ('ADMINISTRADOR','TRABAJADOR'))
 AND NOT EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo NOT IN ('ADMINISTRADOR','TRABAJADOR'));
 SELECT EXISTS(SELECT 1 FROM usuario_rol WHERE usuario_id=@gm_usuario_id AND rol_codigo='ADMINISTRADOR') INTO v_administrador;
 IF v_origen IS NULL OR v_estado_proyecto IS NULL OR v_estado_proyecto IN ('FINALIZADO','CANCELADO')
 OR (v_estado_proyecto<>'EN_CURSO' AND p_destino<>'CANCELADA') OR v_persona IS NULL THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Se requiere actividad vigente y proyecto en curso; cancelar admite planificacion o pausa.';
 END IF;
 IF v_administrador=0 AND (NOT EXISTS(SELECT 1 FROM proyecto_miembro WHERE proyecto_id=p_proyecto AND trabajador_id=v_persona AND activo=1)
 OR NOT EXISTS(SELECT 1 FROM proyecto p JOIN v_trabajador_area_autorizada va ON va.area_id=p.area_id
 WHERE p.id=p_proyecto AND va.trabajador_id=v_persona)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='El usuario no es miembro activo del proyecto.';
 END IF;
 SELECT (v_administrador=1 OR EXISTS(SELECT 1 FROM proyecto_miembro pm WHERE pm.proyecto_id=p_proyecto
  AND pm.trabajador_id=v_persona AND pm.activo=1 AND pm.rol_proyecto IN ('RESPONSABLE','REVISOR'))) INTO v_supervision;
 IF NOT EXISTS(SELECT 1 FROM transicion_actividad WHERE origen=v_origen AND destino=p_destino) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Transicion de actividad no permitida.';
 END IF;
 SELECT requiere_supervision,requiere_motivo INTO v_req_supervision,v_req_motivo
 FROM transicion_actividad WHERE origen=v_origen AND destino=p_destino;
 IF (v_req_supervision=1 AND v_supervision=0) OR (v_supervision=0 AND NOT(v_responsable<=>v_persona)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='El usuario no tiene permiso para esta transicion.';
 END IF;
 IF v_req_motivo=1 AND (p_motivo IS NULL OR CHAR_LENGTH(TRIM(p_motivo))=0) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Debe indicar el motivo del cambio.';
 END IF;
 IF p_destino NOT IN ('COMPLETADA','CANCELADA') THEN
  WITH RECURSIVE ancestros(id,padre_id,estado_codigo,archivada) AS (
   SELECT a.id,a.padre_id,a.estado_codigo,a.archivada FROM actividad a
   JOIN actividad h ON h.padre_id=a.id WHERE h.id=p_actividad
   UNION ALL SELECT a.id,a.padre_id,a.estado_codigo,a.archivada
    FROM actividad a JOIN ancestros r ON a.id=r.padre_id
  ) SELECT COUNT(*) INTO v_descendientes FROM ancestros WHERE archivada=1 OR estado_codigo IN ('COMPLETADA','CANCELADA');
  IF v_descendientes>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Reabra o restaure primero las actividades padre.'; END IF;
 END IF;
 IF p_destino IN ('EN_CURSO','EN_REVISION','COMPLETADA') THEN
  IF v_responsable IS NULL OR NOT EXISTS(SELECT 1 FROM proyecto_miembro pm JOIN trabajador t ON t.id=pm.trabajador_id
   WHERE pm.proyecto_id=p_proyecto AND pm.trabajador_id=v_responsable AND pm.activo=1 AND t.activo=1) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='La actividad debe tener un responsable activo del proyecto.';
  END IF;
  IF EXISTS(SELECT 1 FROM dependencia_actividad d JOIN actividad a ON a.id=d.predecesora_id
   WHERE d.proyecto_id=p_proyecto AND d.sucesora_id=p_actividad AND (a.estado_codigo<>'COMPLETADA' OR a.archivada=1)) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Hay predecesoras sin completar.';
  END IF;
 END IF;
 IF v_origen='COMPLETADA' AND EXISTS(SELECT 1 FROM dependencia_actividad d JOIN actividad s ON s.id=d.sucesora_id
  WHERE d.proyecto_id=p_proyecto AND d.predecesora_id=p_actividad AND s.estado_codigo NOT IN ('PENDIENTE','CANCELADA') AND s.archivada=0) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Replanifique las sucesoras antes de reabrir la predecesora.';
 END IF;
 IF p_destino IN ('COMPLETADA','CANCELADA') THEN
  WITH RECURSIVE hijos(id,estado_codigo,archivada) AS (
   SELECT id,estado_codigo,archivada FROM actividad WHERE padre_id=p_actividad
   UNION ALL SELECT a.id,a.estado_codigo,a.archivada FROM actividad a JOIN hijos h ON a.padre_id=h.id
  ) SELECT COUNT(*) INTO v_descendientes FROM hijos WHERE archivada=0 AND
   ((p_destino='COMPLETADA' AND estado_codigo NOT IN ('COMPLETADA','CANCELADA')) OR
    (p_destino='CANCELADA' AND estado_codigo<>'CANCELADA'));
  IF v_descendientes>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Hay subtareas incompatibles con el cierre solicitado.'; END IF;
 END IF;
 IF p_destino='COMPLETADA' AND EXISTS(SELECT 1 FROM v_estado_entregable
  WHERE actividad_id=p_actividad AND obligatorio=1 AND estado_revision<>'APROBADO') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Hay entregables obligatorios sin aprobar en su ultima version.';
 END IF;
 UPDATE actividad SET estado_codigo=p_destino,motivo_cambio=p_motivo,
 avance=CASE WHEN p_destino='COMPLETADA' THEN 100 WHEN p_destino IN ('PENDIENTE','CANCELADA') THEN 0
  WHEN v_origen IN ('COMPLETADA','CANCELADA') THEN 0 ELSE avance END,
 actualizado_en=UTC_TIMESTAMP(6) WHERE id=p_actividad;
 COMMIT;
END;
