CREATE PROCEDURE `sp_agregar_dependencia`(IN p_proyecto BIGINT UNSIGNED,
 IN p_predecesora BIGINT UNSIGNED,IN p_sucesora BIGINT UNSIGNED)
    SQL SECURITY INVOKER
BEGIN
 DECLARE v_proyecto BIGINT UNSIGNED DEFAULT NULL;
 DECLARE v_ciclo INT DEFAULT 0;
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
 SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
 START TRANSACTION;
 SELECT id INTO v_proyecto FROM proyecto WHERE id=p_proyecto AND archivado=0
 AND estado_codigo NOT IN ('FINALIZADO','CANCELADO') FOR UPDATE;
 IF v_proyecto IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Proyecto no disponible para planificacion.'; END IF;
 IF NOT EXISTS(SELECT 1 FROM usuario u JOIN trabajador t ON t.id=u.trabajador_id
 WHERE u.id=@gm_usuario_id AND u.activo=1 AND t.activo=1
 AND (SELECT COUNT(*) FROM usuario_rol ur WHERE ur.usuario_id=u.id)=1
 AND EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo='ADMINISTRADOR')) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Solo Administrador puede gestionar dependencias.';
 END IF;
 IF p_predecesora IS NULL OR p_sucesora IS NULL OR p_predecesora=p_sucesora OR
 (SELECT COUNT(*) FROM actividad WHERE proyecto_id=p_proyecto AND id IN (p_predecesora,p_sucesora) AND archivada=0)<>2 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='La dependencia requiere dos actividades distintas del mismo proyecto.';
 END IF;

 IF EXISTS(SELECT 1 FROM actividad WHERE id IN (p_predecesora,p_sucesora) AND padre_id IS NOT NULL) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Las dependencias solo admiten tareas principales.';
 END IF;
 WITH RECURSIVE alcanzables(id) AS (
  SELECT p_sucesora
  UNION DISTINCT
  SELECT d.sucesora_id FROM dependencia_actividad d JOIN alcanzables a ON a.id=d.predecesora_id
  WHERE d.proyecto_id=p_proyecto
 ) SELECT COUNT(*) INTO v_ciclo FROM alcanzables WHERE id=p_predecesora;
 IF v_ciclo>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='La dependencia generaria un ciclo.'; END IF;
 INSERT INTO dependencia_actividad(proyecto_id,predecesora_id,sucesora_id)
 VALUES(p_proyecto,p_predecesora,p_sucesora);
 COMMIT;
END
