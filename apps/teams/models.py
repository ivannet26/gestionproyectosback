from django.db import models

from apps.organization.models import Area
from apps.workers.models import Worker


class Team(models.Model):
    id = models.BigAutoField(primary_key=True)
    area = models.ForeignKey(Area, on_delete=models.DO_NOTHING, db_column="area_id")
    name = models.CharField(max_length=120, db_column="nombre")
    active = models.BooleanField(db_column="activo", default=True)

    class Meta:
        db_table = "equipo"
        managed = False
        ordering = ["name"]

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    id = models.BigAutoField(primary_key=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, db_column="equipo_id", related_name="members")
    worker = models.ForeignKey(Worker, on_delete=models.DO_NOTHING, db_column="trabajador_id")
    joined_date = models.DateField(db_column="fecha_ingreso")
    left_date = models.DateField(db_column="fecha_salida", null=True, blank=True)

    class Meta:
        db_table = "equipo_miembro"
        managed = False
        ordering = ["id"]

    def __str__(self):
        return f"{self.team_id} - {self.worker_id}"
