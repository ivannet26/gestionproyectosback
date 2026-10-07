CREATE OR REPLACE SQL SECURITY INVOKER VIEW v_actividad_hoja AS
SELECT a.* FROM actividad a
JOIN proyecto p ON p.id=a.proyecto_id AND p.archivado=0
LEFT JOIN fase f ON f.id=a.fase_id AND f.proyecto_id=a.proyecto_id AND f.archivada=0
WHERE a.archivada=0 AND (a.fase_id IS NULL OR f.id IS NOT NULL)
AND NOT EXISTS(SELECT 1 FROM actividad h WHERE h.padre_id=a.id)
