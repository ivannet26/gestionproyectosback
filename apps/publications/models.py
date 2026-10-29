from django.db import models

from apps.organization.models import Specialty
from apps.projects.models import Project
from apps.workers.models import Worker


class PublicationState(models.TextChoices):
    DRAFT = "BORRADOR", "Borrador"
    OPEN = "ABIERTA", "Abierta"
    CLOSED = "CERRADA", "Cerrada"
    CANCELLED = "CANCELADA", "Cancelada"


class ProjectPublication(models.Model):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project, on_delete=models.DO_NOTHING, db_column="proyecto_id", related_name="publications"
    )
    title = models.CharField(max_length=180, db_column="titulo")
    description = models.TextField(db_column="descripcion")
    vacancies = models.PositiveSmallIntegerField(db_column="vacantes")
    weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, db_column="horas_semanales")
    opening_date = models.DateField(db_column="fecha_apertura")
    closing_date = models.DateField(db_column="fecha_cierre")
    state = models.CharField(
        max_length=10,
        choices=PublicationState.choices,
        default=PublicationState.DRAFT,
        db_column="estado",
    )

    class Meta:
        managed = False
        db_table = "publicacion_proyecto"
        ordering = ["-id"]


class PublicationRequirement(models.Model):
    pk = models.CompositePrimaryKey("publication_id", "specialty_id")
    publication = models.ForeignKey(
        ProjectPublication, on_delete=models.CASCADE, db_column="publicacion_id", related_name="requirements"
    )
    specialty = models.ForeignKey(Specialty, on_delete=models.DO_NOTHING, db_column="especialidad_id")
    minimum_level = models.PositiveSmallIntegerField(db_column="nivel_minimo")

    class Meta:
        managed = False
        db_table = "publicacion_requisito"
        ordering = ["specialty_id"]


class PublicationAssignment(models.Model):
    """Occupancy of a publication's vacancies."""

    id = models.BigAutoField(primary_key=True)
    publication = models.ForeignKey(
        ProjectPublication,
        on_delete=models.DO_NOTHING,
        db_column="publicacion_id",
        related_name="assignments",
        db_constraint=False,
    )
    worker = models.ForeignKey(
        Worker, on_delete=models.DO_NOTHING, db_column="trabajador_id", db_constraint=False
    )
    project = models.ForeignKey(
        Project, on_delete=models.DO_NOTHING, db_column="proyecto_id", db_constraint=False
    )
    start_date = models.DateField(db_column="fecha_inicio")
    end_date = models.DateField(db_column="fecha_fin")
    weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, db_column="horas_semanales")
    cancelled = models.BooleanField(default=False, db_column="anulada")
    observation = models.CharField(max_length=500, null=True, blank=True, db_column="observacion")

    class Meta:
        managed = False
        db_table = "asignacion_proyecto"
