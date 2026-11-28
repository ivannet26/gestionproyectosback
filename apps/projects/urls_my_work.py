from django.urls import path

from .views import (
    MyWorkPrioritiesView,
    MyWorkSummaryView,
    MyWorkTasksView,
    MyWorkUpcomingView,
)


urlpatterns = [
    path("summary/", MyWorkSummaryView.as_view()),
    path("tasks/", MyWorkTasksView.as_view()),
    path("upcoming/", MyWorkUpcomingView.as_view()),
    path("priorities/", MyWorkPrioritiesView.as_view()),
]
