CREATE PROCEDURE sp_validar_supervisor(IN p_proyecto BIGINT UNSIGNED)
SQL SECURITY INVOKER
BEGIN
 IF NOT EXISTS(
 SELECT 1 FROM usuario u JOIN trabajador t ON t.id=u.trabajador_id AND t.activo=1
 WHERE u.id=@gm_usuario_id AND u.activo=1
 AND (SELECT COUNT(*) FROM usuario_rol ur WHERE ur.usuario_id=u.id)=1
 AND NOT EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo NOT IN ('ADMINISTRADOR','TRABAJADOR'))
 AND (
  EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo='ADMINISTRADOR')
  OR (
   EXISTS(SELECT 1 FROM usuario_rol ur WHERE ur.usuario_id=u.id AND ur.rol_codigo='TRABAJADOR')
   AND EXISTS(SELECT 1 FROM proyecto_miembro pm JOIN proyecto p ON p.id=pm.proyecto_id
    JOIN v_trabajador_area_autorizada va ON va.trabajador_id=t.id AND va.area_id=p.area_id
    WHERE pm.trabajador_id=t.id AND pm.proyecto_id=p_proyecto AND pm.activo=1 AND pm.rol_proyecto='RESPONSABLE')
  )
 )
 ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Se requiere administrador o responsable autorizado del proyecto.'; END IF;
END;
