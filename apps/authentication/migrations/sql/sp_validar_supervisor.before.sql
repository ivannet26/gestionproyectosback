CREATE PROCEDURE sp_validar_supervisor(IN p_proyecto BIGINT UNSIGNED)
SQL SECURITY INVOKER
BEGIN
 IF NOT EXISTS(
 SELECT 1 FROM usuario u JOIN trabajador t ON t.id=u.trabajador_id AND t.activo=1
 JOIN proyecto_miembro pm ON pm.trabajador_id=u.trabajador_id AND pm.proyecto_id=p_proyecto AND pm.activo=1
 WHERE u.id=@gm_usuario_id AND u.activo=1 AND
 (pm.rol_proyecto='RESPONSABLE' OR EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo IN ('GERENCIA','COORDINADOR')))
 ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Se requiere supervisor con membresia activa del proyecto.'; END IF;
END;
