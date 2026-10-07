from django.db import models


class Area(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=30, db_column="codigo", unique=True)
    name = models.CharField(max_length=120, db_column="nombre", unique=True)
    active = models.BooleanField(db_column="activa")

    class Meta:
        db_table = "area"
        managed = False
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Specialty(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=120, unique=True, db_column="nombre")

    class Meta:
        db_table = "especialidad"
        managed = False
        ordering = ["name"]

    def __str__(self):
        return self.name
