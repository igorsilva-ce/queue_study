from django.urls import path

from .views import (
    AuthTokenView,
    EtlPipelineTaskView,
    GroupStatusView,
    HealthCheckView,
    HelloTaskView,
    ParallelSumTaskView,
    PaymentTaskView,
    TaskStatusView,
    UrgentEmailTaskView,
)

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("auth/token/", AuthTokenView.as_view(), name="auth-token"),
    path("tasks/hello/", HelloTaskView.as_view(), name="task-hello"),
    path(
        "tasks/email-urgente/", UrgentEmailTaskView.as_view(), name="task-urgent-email"
    ),
    path("tasks/pagamento/", PaymentTaskView.as_view(), name="task-payment"),
    path(
        "tasks/workflows/soma-paralela/",
        ParallelSumTaskView.as_view(),
        name="workflow-parallel-sum",
    ),
    path(
        "tasks/workflows/pipeline-etl/",
        EtlPipelineTaskView.as_view(),
        name="workflow-etl-pipeline",
    ),
    path(
        "tasks/groups/<str:group_id>/", GroupStatusView.as_view(), name="group-status"
    ),
    path("tasks/<str:task_id>/", TaskStatusView.as_view(), name="task-status"),
]
