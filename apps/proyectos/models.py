from django.db import models
from django.utils import timezone

from apps.organization.models import Area
from apps.workers.models import Worker


class ProjectType(models.Model):
    code = models.CharField(primary_key=True, max_length=30, db_column="codigo")
    name = models.CharField(max_length=100, db_column="nombre")

    class Meta:
        managed = False
        db_table = "tipo_proyecto"


class ProjectState(models.Model):
    code = models.CharField(primary_key=True, max_length=20, db_column="codigo")
    name = models.CharField(max_length=70, db_column="nombre")
    terminal = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = "estado_proyecto"


class TaskState(models.Model):
    code = models.CharField(primary_key=True, max_length=20, db_column="codigo")
    name = models.CharField(max_length=70, db_column="nombre")
    terminal = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = "estado_actividad"


class TaskTransition(models.Model):
    pk = models.CompositePrimaryKey("source", "target")
    source = models.CharField(max_length=20, db_column="origen")
    target = models.CharField(max_length=20, db_column="destino")
    supervision_required = models.BooleanField(default=False, db_column="requiere_supervision")
    reason_required = models.BooleanField(default=False, db_column="requiere_motivo")

    class Meta:
        managed = False
        db_table = "transicion_actividad"


class Project(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=40, unique=True, db_column="codigo")
    name = models.CharField(max_length=180, db_column="nombre")
    description = models.TextField(null=True, db_column="descripcion")
    area = models.ForeignKey(Area, db_column="area_id", on_delete=models.DO_NOTHING)
    type_code = models.CharField(max_length=30, db_column="tipo_codigo")
    state_code = models.CharField(max_length=20, default="PLANIFICADO", db_column="estado_codigo")
    priority = models.PositiveSmallIntegerField(default=3, db_column="prioridad")
    start_date = models.DateField(null=True, db_column="fecha_inicio")
    end_date = models.DateField(null=True, db_column="fecha_fin")
    confidential = models.BooleanField(default=False, db_column="confidencial")
    archived = models.BooleanField(default=False, db_column="archivado")
    available = models.BooleanField(default=False, db_column="disponible_por_area")
    worker_edit = models.BooleanField(default=False, db_column="trabajador_edita_tareas")
    worker_state = models.BooleanField(default=False, db_column="trabajador_cambia_estado")
    created_at = models.DateTimeField(default=timezone.now, db_column="creado_en")
    updated_at = models.DateTimeField(default=timezone.now, db_column="actualizado_en")

    class Meta:
        managed = False
        db_table = "proyecto"


class ProjectMember(models.Model):
    pk = models.CompositePrimaryKey("project_id", "worker_id")
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING, db_column="proyecto_id")
    worker = models.ForeignKey(Worker, on_delete=models.DO_NOTHING, db_column="trabajador_id")
    project_role = models.CharField(max_length=20, default="COLABORADOR", db_column="rol_proyecto")
    active = models.BooleanField(default=True, db_column="activo")

    class Meta:
        managed = False
        db_table = "proyecto_miembro"


class Task(models.Model):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING, db_column="proyecto_id")
    phase_id = models.PositiveBigIntegerField(null=True, db_column="fase_id")
    parent = models.ForeignKey("self", null=True, on_delete=models.DO_NOTHING, db_column="padre_id")
    name = models.CharField(max_length=180, db_column="nombre")
    responsible = models.ForeignKey(Worker, null=True, on_delete=models.DO_NOTHING, db_column="responsable_id")
    state_code = models.CharField(max_length=20, db_column="estado_codigo")
    priority = models.PositiveSmallIntegerField(default=3, db_column="prioridad")
    start_date = models.DateField(db_column="fecha_inicio")
    due_date = models.DateField(db_column="fecha_fin")
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_column="avance")
    reason = models.CharField(max_length=500, null=True, db_column="motivo_cambio")
    archived = models.BooleanField(default=False, db_column="archivada")
    created_at = models.DateTimeField(default=timezone.now, db_column="creado_en")
    updated_at = models.DateTimeField(default=timezone.now, db_column="actualizado_en")

    class Meta:
        managed = False
        db_table = "actividad"


class TaskDependency(models.Model):
    pk = models.CompositePrimaryKey("project_id", "predecessor_id", "successor_id")
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING, db_column="proyecto_id")
    predecessor = models.ForeignKey(Task, related_name="outgoing_dependencies", on_delete=models.DO_NOTHING, db_column="predecesora_id")
    successor = models.ForeignKey(Task, related_name="incoming_dependencies", on_delete=models.DO_NOTHING, db_column="sucesora_id")

    class Meta:
        managed = False
        db_table = "dependencia_actividad"


class ProjectArea(models.Model):
    pk = models.CompositePrimaryKey("project_id", "area_id")
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING, db_constraint=False, db_column="proyecto_id")
    area = models.ForeignKey(Area, on_delete=models.DO_NOTHING, db_constraint=False, db_column="area_id")

    class Meta:
        db_table = "proyecto_area"


class ProjectRequirement(models.Model):
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING, db_constraint=False, db_column="proyecto_id")
    name = models.CharField(max_length=120, db_column="nombre")
    kind = models.CharField(max_length=20, db_column="clase")

    class Meta:
        db_table = "proyecto_requisito"
        constraints = [models.UniqueConstraint(fields=["project", "name", "kind"], name="uq_proyecto_requisito")]


class TaskLabel(models.Model):
    task = models.ForeignKey(Task, on_delete=models.DO_NOTHING, db_constraint=False, db_column="actividad_id")
    requirement = models.ForeignKey(ProjectRequirement, null=True, on_delete=models.DO_NOTHING, db_column="requisito_id")
    name = models.CharField(max_length=120, db_column="nombre")
    kind = models.CharField(max_length=20, db_column="clase")

    class Meta:
        db_table = "actividad_etiqueta"
        constraints = [models.UniqueConstraint(fields=["task", "name", "kind"], name="uq_actividad_etiqueta")]
