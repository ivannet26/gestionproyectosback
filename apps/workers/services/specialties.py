from rest_framework import status
from rest_framework.response import Response

from ..models import WorkerSpecialty


def handle_worker_specialties(worker, request, specialty_id=None, serializer_class=None):
    specialty_id = specialty_id or request.data.get("specialty_id") or request.data.get("id")
    if request.method == "GET":
        return Response(serializer_class(worker.worker_specialties.select_related("specialty").all(), many=True).data)
    if request.method == "DELETE":
        WorkerSpecialty.objects.filter(worker=worker, specialty_id=specialty_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    level = request.data.get("level")
    ws, created = WorkerSpecialty.objects.get_or_create(
        worker=worker, specialty_id=specialty_id, defaults={"level": level or 1}
    )
    if not created:
        ws.level = level if level is not None else ws.level + request.data.get("increment", 1)
        WorkerSpecialty.objects.filter(worker=worker, specialty_id=specialty_id).update(level=ws.level)
    return Response(serializer_class(ws).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
