from django.urls import path

from .views import ProjectCatalogView, ProjectDetailView, ProjectListView, ProjectWorkersView, TaskDependenciesView, TaskDetailView, TaskListView, TaskStateView


urlpatterns = [
    path("", ProjectListView.as_view()),
    path("catalogs/", ProjectCatalogView.as_view()),
    path("workers/", ProjectWorkersView.as_view()),
    path("<int:project_id>/", ProjectDetailView.as_view()),
    path("<int:project_id>/tasks/", TaskListView.as_view()),
    path("<int:project_id>/tasks/<int:task_id>/", TaskDetailView.as_view()),
    path("<int:project_id>/tasks/<int:task_id>/state/", TaskStateView.as_view()),
    path("<int:project_id>/tasks/<int:task_id>/dependencies/", TaskDependenciesView.as_view()),
]
