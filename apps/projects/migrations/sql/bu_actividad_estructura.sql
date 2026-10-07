CREATE TRIGGER bu_actividad_estructura BEFORE UPDATE ON actividad FOR EACH ROW
BEGIN
 IF NEW.id<>OLD.id OR NEW.proyecto_id<>OLD.proyecto_id THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='El identificador y proyecto de una actividad son inmutables.';
 END IF;
 IF NEW.archivada=1 AND EXISTS(SELECT 1 FROM actividad WHERE padre_id=OLD.id AND archivada=0) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Archive primero las subtareas activas.';
 END IF;
 IF NOT(NEW.padre_id<=>OLD.padre_id) OR NOT(NEW.fase_id<=>OLD.fase_id) OR NEW.fecha_inicio<>OLD.fecha_inicio OR NEW.fecha_fin<>OLD.fecha_fin THEN
  CALL sp_validar_estructura_actividad(NEW.id,NEW.proyecto_id,NEW.fase_id,NEW.padre_id,NEW.fecha_inicio,NEW.fecha_fin);
 END IF;
 SET NEW.actualizado_en=UTC_TIMESTAMP(6);
END
