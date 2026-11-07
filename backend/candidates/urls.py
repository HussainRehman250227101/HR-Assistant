from django.urls import include,path
from rest_framework.routers import DefaultRouter

from .views import (
    CandidateCloseView,CandidateEraseView,CandidateEventListView,CandidateResumeUploadView,CandidateViewSet,
    RequisitionResumeBatchUploadView,ResumeDocumentDetailView,
    ResumeDocumentDownloadView,ResumeDocumentProcessView,ResumeDocumentRetryView,
)

app_name="candidates"
router=DefaultRouter()
router.register(r"",CandidateViewSet,basename="candidate")

urlpatterns=[
    path("",include(router.urls)),
    path("requisition/<uuid:reference_code>/resume-batches/",RequisitionResumeBatchUploadView.as_view(),name="requisition-resume-batch-upload"),
    path("<uuid:public_id>/resumes/",CandidateResumeUploadView.as_view(),name="candidate-resume-upload"),
    path("<uuid:public_id>/events/",CandidateEventListView.as_view(),name="candidate-events"),
    path("<uuid:public_id>/close/",CandidateCloseView.as_view(),name="candidate-close"),
    path("<uuid:public_id>/erase-personal-data/",CandidateEraseView.as_view(),name="candidate-erase"),
    path("resume-documents/<uuid:public_id>/",ResumeDocumentDetailView.as_view(),name="resume-document-detail"),
    path("resume-documents/<uuid:public_id>/download/",ResumeDocumentDownloadView.as_view(),name="resume-document-download"),
    path("resume-documents/<uuid:public_id>/process/",ResumeDocumentProcessView.as_view(),name="resume-document-process"),
    path("resume-documents/<uuid:public_id>/retry/",ResumeDocumentRetryView.as_view(),name="resume-document-retry"),
]
