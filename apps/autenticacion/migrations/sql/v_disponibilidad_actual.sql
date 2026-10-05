CREATE SQL SECURITY INVOKER VIEW v_disponibilidad_actual AS
SELECT t.id AS trabajador_id,t.area_id,CONCAT_WS(' ',t.nombres,t.apellidos) AS trabajador,
 t.activo,t.horas_semanales AS capacidad_semanal,
 COALESCE(r.proyectos,0) AS proyectos_vigentes,
 COALESCE(r.horas,0) AS horas_comprometidas,
 CASE WHEN au.trabajador_id IS NOT NULL THEN 1 ELSE 0 END AS ausente,
 CASE WHEN t.activo=0 OR au.trabajador_id IS NOT NULL THEN 0
      ELSE GREATEST(t.horas_semanales-COALESCE(r.horas,0),0) END AS horas_disponibles,
 CASE WHEN COALESCE(r.proyectos,0)=0 THEN 1 ELSE 0 END AS sin_proyecto,
 CASE WHEN COALESCE(r.horas,0)>t.horas_semanales THEN 1 ELSE 0 END AS sobrecargado,
 t.todas_las_areas
FROM trabajador t
LEFT JOIN (
 SELECT ap.trabajador_id,COUNT(DISTINCT ap.proyecto_id) AS proyectos,SUM(ap.horas_semanales) AS horas
 FROM asignacion_proyecto ap
 JOIN proyecto p ON p.id=ap.proyecto_id AND p.archivado=0
 JOIN estado_proyecto ep ON ep.codigo=p.estado_codigo AND ep.terminal=0
 JOIN proyecto_miembro pm ON pm.proyecto_id=ap.proyecto_id AND pm.trabajador_id=ap.trabajador_id AND pm.activo=1
 WHERE ap.anulada=0 AND CURDATE() BETWEEN ap.fecha_inicio AND ap.fecha_fin
 GROUP BY ap.trabajador_id
) AS r ON r.trabajador_id=t.id
LEFT JOIN (
 SELECT DISTINCT trabajador_id FROM ausencia
 WHERE anulada=0 AND CURDATE() BETWEEN fecha_inicio AND fecha_fin
) AS au ON au.trabajador_id=t.id;
