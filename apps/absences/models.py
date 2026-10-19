from django.db import models

from apps.workers.models import Worker


class Absence(models.Model):
    id = models.BigAutoField(primary_key=True)
    worker = models.ForeignKey(Worker, on_delete=models.DO_NOTHING, db_column="trabajador_id")
    fecha_inicio = models.DateField(db_column="fecha_inicio")
    fecha_fin = models.DateField(db_column="fecha_fin")
    motivo = models.CharField(max_length=250, db_column="motivo")
    anulada = models.BooleanField(db_column="anulada", default=False)
    aprobada = models.BooleanField(db_column="aprobada", null=True, default=None)

    class Meta:
        db_table = "ausencia"
        managed = False

    def __str__(self):
        return f"{self.id} - {self.worker_id} ({self.fecha_inicio} / {self.fecha_fin})"
