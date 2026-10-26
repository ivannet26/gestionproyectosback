CREATE PROCEDURE `sp_aplicar_estado_actividad`(IN p_proyecto BIGINT UNSIGNED,
 IN p_actividad BIGINT UNSIGNED,IN p_destino VARCHAR(20),IN p_motivo VARCHAR(500))
SQL SECURITY INVOKER
BEGIN
 DECLARE v_origen VARCHAR(20) DEFAULT NULL;
 DECLARE v_estado_proyecto VARCHAR(20) DEFAULT NULL;
 DECLARE v_responsable BIGINT UNSIGNED DEFAULT NULL;
 DECLARE v_persona BIGINT UNSIGNED DEFAULT NULL;
 DECLARE v_administrador BOOLEAN DEFAULT FALSE;
 DECLARE v_regla_origen VARCHAR(20);
 DECLARE v_regla_destino VARCHAR(20);
 SELECT estado_codigo INTO v_estado_proyecto FROM proyecto
 WHERE id=p_proyecto AND archivado=0 FOR UPDATE;
 SELECT estado_codigo,responsable_id INTO v_origen,v_responsable FROM actividad
 WHERE id=p_actividad AND proyecto_id=p_proyecto AND archivada=0 FOR UPDATE;
 SELECT u.trabajador_id INTO v_persona FROM usuario u JOIN trabajador t ON t.id=u.trabajador_id
 WHERE u.id=@gm_usuario_id AND u.activo=1 AND t.activo=1
 AND (SELECT COUNT(*) FROM usuario_rol ur WHERE ur.usuario_id=u.id)=1
 AND EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo IN ('ADMINISTRADOR','TRABAJADOR'))
 AND NOT EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo NOT IN ('ADMINISTRADOR','TRABAJADOR'));
 SELECT EXISTS(SELECT 1 FROM usuario_rol WHERE usuario_id=@gm_usuario_id AND rol_codigo='ADMINISTRADOR') INTO v_administrador;
 IF v_origen IS NULL OR v_estado_proyecto IS NULL OR v_estado_proyecto IN ('FINALIZADO','CANCELADO') OR v_persona IS NULL THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Se requiere actividad vigente, cuenta autorizada y proyecto abierto.';
 END IF;
 IF v_administrador=0 AND (
 NOT((v_responsable<=>v_persona) OR EXISTS(SELECT 1 FROM actividad_responsable_adicional WHERE actividad_id=p_actividad AND trabajador_id=v_persona))
 OR NOT EXISTS(SELECT 1 FROM proyecto WHERE id=p_proyecto AND trabajador_cambia_estado=1)
 OR NOT EXISTS(SELECT 1 FROM proyecto_miembro WHERE proyecto_id=p_proyecto AND trabajador_id=v_persona AND activo=1)
 OR NOT EXISTS(SELECT 1 FROM v_trabajador_area_autorizada va WHERE va.trabajador_id=v_persona
 AND EXISTS(SELECT 1 FROM proyecto p WHERE p.id=p_proyecto AND p.area_id=va.area_id))) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Se requiere asignacion, participacion, area y permiso de cambio de estado.';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM estado_actividad WHERE codigo=p_destino)
 OR EXISTS(SELECT 1 FROM estado_actividad_definicion WHERE estado_codigo=p_destino AND proyecto_id<>p_proyecto)
 OR (EXISTS(SELECT 1 FROM proyecto_estado_actividad WHERE proyecto_id=p_proyecto)
 AND NOT EXISTS(SELECT 1 FROM proyecto_estado_actividad WHERE proyecto_id=p_proyecto AND estado_codigo=p_destino))
 OR (EXISTS(SELECT 1 FROM estado_actividad_definicion WHERE estado_codigo=p_destino)
 AND NOT EXISTS(SELECT 1 FROM proyecto_estado_actividad WHERE proyecto_id=p_proyecto AND estado_codigo=p_destino)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Estado fuera del proyecto o no habilitado.';
 END IF;
 IF v_origen<>p_destino THEN
  SET v_regla_origen=fn_regla_estado_actividad(p_proyecto,v_origen);
  SET v_regla_destino=fn_regla_estado_actividad(p_proyecto,p_destino);
  UPDATE actividad SET estado_codigo=p_destino,
  avance=CASE WHEN v_regla_destino='COMPLETADA' THEN 100 WHEN v_regla_destino IN ('PENDIENTE','CANCELADA') THEN 0
   WHEN v_regla_origen IN ('COMPLETADA','CANCELADA') THEN 0 ELSE avance END,
  actualizado_en=UTC_TIMESTAMP(6) WHERE id=p_actividad AND proyecto_id=p_proyecto;
 END IF;
END
