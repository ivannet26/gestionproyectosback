from django.db import models

from apps.organization.models import Area, Specialty


class Worker(models.Model):
    id = models.BigAutoField(primary_key=True)
    area = models.ForeignKey(Area, on_delete=models.DO_NOTHING, db_column="area_id", null=True, blank=True)
    code = models.CharField(max_length=30, db_column="codigo", unique=True)
    first_names = models.CharField(max_length=100, db_column="nombres")
    last_names = models.CharField(max_length=120, db_column="apellidos")
    email = models.EmailField(max_length=254, db_column="correo", null=True, blank=True, unique=True)
    weekly_hours = models.DecimalField(
        max_digits=5, decimal_places=2, db_column="horas_semanales", null=True, blank=True
    )
    active = models.BooleanField(db_column="activo", default=True)
    all_areas = models.BooleanField(default=False, db_column="todas_las_areas")
    specialties = models.ManyToManyField(Specialty, through="WorkerSpecialty", related_name="workers")

    class Meta:
        db_table = "trabajador"
        managed = False

    def __str__(self):
        return f"{self.code} - {self.first_names} {self.last_names}"


class WorkerArea(models.Model):
    pk = models.CompositePrimaryKey("worker_id", "area_id")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, db_column="trabajador_id", db_constraint=False)
    area = models.ForeignKey(Area, on_delete=models.DO_NOTHING, db_column="area_id", db_constraint=False)

    class Meta:
        db_table = "trabajador_area"


class WorkerSpecialty(models.Model):
    pk = models.CompositePrimaryKey("worker", "specialty")
    worker = models.ForeignKey(
        Worker, on_delete=models.CASCADE, db_column="trabajador_id", related_name="worker_specialties"
    )
    specialty = models.ForeignKey(
        Specialty, on_delete=models.CASCADE, db_column="especialidad_id", related_name="worker_specialties"
    )
    level = models.PositiveSmallIntegerField(db_column="nivel", default=1)

    class Meta:
        db_table = "trabajador_especialidad"
        managed = False
