from django.db import DatabaseError, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.security import IsAdministrator
from apps.organization.services.areas import active_area_options

from .models import TaskState
from .serializers import (
    DependencySerializer,
    ProjectCreateSerializer,
    TaskCreateSerializer,
    TaskEditSerializer,
    TaskStateSerializer,
)
from .services.access import project_for_user, require_admin, tasks_for_user, visible_projects
from .services.presentation import task_snapshot
from .services.projects import create_project, project_snapshot, worker_candidates
from .services.tasks import change_task_state, create_task, edit_task, manage_dependency


class ProjectApiView(APIView):
    def handle_exception(self, error):
        if isinstance(error, DatabaseError):
            code = 409 if isinstance(error, IntegrityError) or (error.args and error.args[0] == 1644) else 503
            message = (
                "La operación incumple una restricción del proyecto"
                if code == 409
                else "El servicio de proyectos no está disponible. Revisa conexión y migraciones pendientes"
            )
            return Response({"detail": message}, status=code)
        return super().handle_exception(error)


class ProjectCatalogView(ProjectApiView):
    def get(self, request):

        return Response(
            {
                "creation_date": timezone.localdate(),
                "areas": active_area_options() if request.user.global_role == "ADMINISTRADOR" else [],
                "states": list(TaskState.objects.order_by("code").values("code", "name")),
                "priorities": [
                    {"code": code, "name": name}
                    for code, name in ((1, "Urgente"), (2, "Alta"), (3, "Normal"), (4, "Baja"))
                ],
            }
        )


class ProjectWorkersView(ProjectApiView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        try:
            ids = [int(value) for value in request.query_params.get("area_ids", "").split(",") if value]
        except ValueError:
            raise ValidationError({"area_ids": "Selecciona áreas válidas"}) from None
        search = request.query_params.get("q", "").strip()
        if len(search) > 100 or len(ids) > 100 or len(set(ids)) != len(ids) or any(value < 1 for value in ids):
            raise ValidationError({"detail": "Filtros no válidos"})
        return Response(worker_candidates(ids, search))


class ProjectListView(ProjectApiView):
    serializer_class = ProjectCreateSerializer

    def get(self, request):
        return Response(
            [
                project_snapshot(project, request.user)
                for project in visible_projects(request.user).order_by("-id")[:200]
            ]
        )

    def post(self, request):
        require_admin(request.user)
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = create_project(request.user, serializer.validated_data)
        return Response(project_snapshot(project, request.user, detailed=True), status=201)


class ProjectDetailView(ProjectApiView):
    def get(self, request, project_id):
        return Response(project_snapshot(project_for_user(request.user, project_id), request.user, detailed=True))


class TaskListView(ProjectApiView):
    serializer_class = TaskCreateSerializer

    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        return Response(
            [
                task_snapshot(task, project, request.user)
                for task in tasks_for_user(request.user, project).select_related("responsible").order_by("id")
            ]
        )

    def post(self, request, project_id):
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = create_task(request.user, project_id, serializer.validated_data)
        return Response(task_snapshot(task, task.project, request.user), status=201)


class TaskDetailView(ProjectApiView):
    serializer_class = TaskEditSerializer

    def patch(self, request, project_id, task_id):
        serializer = TaskEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = edit_task(request.user, project_id, task_id, serializer.validated_data)
        return Response(task_snapshot(task, task.project, request.user))


class TaskStateView(ProjectApiView):
    serializer_class = TaskStateSerializer

    def post(self, request, project_id, task_id):
        serializer = TaskStateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = change_task_state(request.user, project_id, task_id, serializer.validated_data)
        return Response(task_snapshot(task, task.project, request.user))


class TaskDependenciesView(ProjectApiView):
    permission_classes = [IsAdministrator]
    serializer_class = DependencySerializer

    def post(self, request, project_id, task_id):
        serializer = DependencySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        manage_dependency(request.user, project_id, task_id, serializer.validated_data["predecessor_id"])
        return Response({"detail": "Dependencia agregada"}, status=201)

    def delete(self, request, project_id, task_id):
        serializer = DependencySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        manage_dependency(request.user, project_id, task_id, serializer.validated_data["predecessor_id"], remove=True)
        return Response(status=204)
