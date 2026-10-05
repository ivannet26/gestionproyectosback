CREATE SQL SECURITY INVOKER VIEW v_trabajador_area_autorizada AS
SELECT t.id AS trabajador_id, a.id AS area_id
FROM trabajador t JOIN area a ON a.activa=1
WHERE t.activo=1 AND (
 t.todas_las_areas=1
 OR (t.area_id=a.id AND NOT EXISTS(SELECT 1 FROM trabajador_area ta WHERE ta.trabajador_id=t.id))
 OR EXISTS(SELECT 1 FROM trabajador_area ta WHERE ta.trabajador_id=t.id AND ta.area_id=a.id)
);
