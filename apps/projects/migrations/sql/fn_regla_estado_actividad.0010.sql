CREATE FUNCTION `fn_regla_estado_actividad`(p_proyecto BIGINT UNSIGNED,p_codigo VARCHAR(20))
RETURNS VARCHAR(20) READS SQL DATA SQL SECURITY INVOKER
BEGIN
 DECLARE v_categoria VARCHAR(20) DEFAULT NULL;
 SELECT categoria INTO v_categoria FROM estado_actividad_definicion
 WHERE proyecto_id=p_proyecto AND estado_codigo=p_codigo;
 RETURN CASE v_categoria WHEN 'not_started' THEN 'PENDIENTE' WHEN 'active' THEN 'EN_CURSO'
 WHEN 'done' THEN 'COMPLETADA' WHEN 'closed' THEN 'COMPLETADA' ELSE p_codigo END;
END
