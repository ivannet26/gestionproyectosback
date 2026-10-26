from django.db import DatabaseError, IntegrityError
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    PublicationCreateSerializer,
    PublicationStateSerializer,
    PublicationUpdateSerializer,
)
from .services import (
    change_publication_state,
    create_publication,
    list_publications,
    publication_catalog,
    publication_for_user,
    apply_publication,
    publication_snapshot,
    update_publication,
)


class PublicationApiView(APIView):
    def handle_exception(self, error):
        if isinstance(error, DatabaseError):
            # 1644: trigger SIGNAL; 3819: MySQL CHECK constraint.
            conflict = isinstance(error, IntegrityError) or (error.args and error.args[0] in (1644, 3819))
            code = 409 if conflict else 503
            message = (
                "La operación incumple una restricción de la publicación"
                if code == 409
                else "El servicio de publicaciones no está disponible. Revisa conexión y esquema de base de datos"
            )
            return Response({"detail": message}, status=code)
        return super().handle_exception(error)


class PublicationCatalogView(PublicationApiView):
    def get(self, request):
        return Response(publication_catalog(request.user))


class PublicationListView(PublicationApiView):
    serializer_class = PublicationCreateSerializer

    def get(self, request):
        return Response(
            [
                publication_snapshot(publication, request.user)
                for publication in list_publications(request.user, request.query_params)
            ]
        )

    def post(self, request):
        serializer = PublicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        publication = create_publication(request.user, serializer.validated_data)
        return Response(publication_snapshot(publication, request.user), status=201)


class PublicationDetailView(PublicationApiView):
    serializer_class = PublicationUpdateSerializer

    def get(self, request, publication_id):
        return Response(publication_snapshot(publication_for_user(request.user, publication_id), request.user))

    def patch(self, request, publication_id):
        serializer = PublicationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        publication = update_publication(request.user, publication_id, serializer.validated_data)
        return Response(publication_snapshot(publication, request.user))


class PublicationStateView(PublicationApiView):
    serializer_class = PublicationStateSerializer

    def post(self, request, publication_id):
        serializer = PublicationStateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        publication = change_publication_state(
            request.user, publication_id, serializer.validated_data["state"]
        )
        return Response(publication_snapshot(publication, request.user))


class PublicationApplyView(PublicationApiView):
    def post(self, request, publication_id):
        publication = apply_publication(request.user, publication_id)
        return Response(publication_snapshot(publication, request.user), status=201)
