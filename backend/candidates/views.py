"""Candidate and resume intake APIs with role-aware access."""

import logging
import threading
from pathlib import PurePath

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, permissions, status, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserRole
from accounts.permissions import IsHRAdmin, IsHRStaff, has_full_access
from requisitions.models import Requisition, RequisitionStatus
from .models import Candidate, CandidateEvent, CandidateStatus, ResumeDocument, ResumeProcessingStatus
from .serializers import CandidateEventSerializer, CandidateSerializer, ResumeBatchUploadSerializer, ResumeDocumentDetailSerializer, ResumeDocumentSummarySerializer, ResumeUploadSerializer
from .services.privacy import PrivacyError, close_candidate, erase_personal_data
from .services.processing import process_documents_parallel, process_resume_document, queue_resume_retry
from .validators import calculate_sha256, safe_filename, validate_resume_upload


logger=logging.getLogger(__name__)


def candidates_visible_to(user):
    qs=Candidate.objects.select_related("requisition","created_by","requisition__hiring_manager").prefetch_related("resume_documents")
    if has_full_access(user):
        return qs
    if user.role == UserRole.RECRUITER:  # interviewer only: just the candidates with a live interview assigned to them
        return qs.filter(interviews__interviewer=user).exclude(interviews__status="CANCELLED").distinct()
    return qs.none()


def documents_visible_to(user):
    return ResumeDocument.objects.select_related("candidate","candidate__requisition","candidate__requisition__hiring_manager").filter(candidate__in=candidates_visible_to(user))


def _extract_in_background(document_ids):
    """Extract text for freshly uploaded resumes without needing the Celery worker or an HR click.

    Runs in a daemon thread so the upload response is not delayed. Extraction is claimed atomically, so a
    concurrent Celery run or manual click can never process the same document twice.
    """
    from django.db import connection

    try:
        process_documents_parallel(document_ids)
    finally:
        connection.close()


def _queue_auto_processing(document_ids=()):
    """After the upload commits, extract the new resumes at once, then ask the Celery worker to score.

    Best effort: if the broker is unavailable the upload still succeeds and the scheduled cycle picks it up.
    """
    def enqueue():
        if document_ids:
            threading.Thread(target=_extract_in_background, args=(list(document_ids),), daemon=True).start()
        try:
            from workflows.tasks import auto_score_new_resumes  # local import avoids a candidates<->workflows cycle
            auto_score_new_resumes.delay()
        except Exception as exc:
            logger.warning("Could not queue automatic processing. exception_type=%s", type(exc).__name__)
    transaction.on_commit(enqueue)


def _save_resume(candidate,upload,actor,content_type,checksum=None):
    checksum=checksum or calculate_sha256(upload)
    if ResumeDocument.objects.filter(candidate=candidate,sha256=checksum).exists():
        raise exceptions.ValidationError({"file":"This exact resume has already been uploaded for this candidate."})
    doc=ResumeDocument.objects.create(
        candidate=candidate,file=upload,original_filename=safe_filename(upload),
        content_type=content_type,file_size=upload.size,sha256=checksum,created_by=actor,
    )
    CandidateEvent.objects.create(
        candidate=candidate,actor=actor,event_type=CandidateEvent.EventType.RESUME_UPLOADED,
        details={"resume_document_id":str(doc.public_id),"file_type":PurePath(doc.original_filename).suffix.lower().lstrip("."),"file_size":doc.file_size},
    )
    return doc


class CandidatePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CandidateViewSet(viewsets.ModelViewSet):
    serializer_class=CandidateSerializer
    pagination_class=CandidatePagination
    lookup_field="public_id"
    http_method_names=["get","post","put","patch","head","options"]
    parser_classes=[JSONParser,MultiPartParser,FormParser]

    def get_permissions(self):
        if getattr(self,"action",None) in {"create","update","partial_update"}:
            return [IsHRStaff()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs=candidates_visible_to(self.request.user)
        status_filter=self.request.query_params.get("status")
        if status_filter:
            allowed={key for key,_ in CandidateStatus.choices}
            if status_filter not in allowed:
                raise exceptions.ValidationError({"status":"Invalid candidate status."})
            qs=qs.filter(current_status=status_filter)
        req=self.request.query_params.get("requisition")
        if req:
            qs=qs.filter(requisition__reference_code=req)
        search=self.request.query_params.get("search")
        if search:
            qs=qs.filter(Q(full_name__icontains=search)|Q(email__icontains=search))
        return qs

    def perform_create(self,serializer):
        candidate=serializer.save(created_by=self.request.user)
        CandidateEvent.objects.create(candidate=candidate,actor=self.request.user,event_type=CandidateEvent.EventType.CANDIDATE_CREATED,details={"requisition_reference":str(candidate.requisition.reference_code)})

    def perform_update(self,serializer):
        if serializer.instance.personal_data_erased_at:
            raise exceptions.ValidationError({"detail":"This candidate's personal data was erased; the record can no longer be edited."})
        changed=sorted(serializer.validated_data.keys())
        candidate=serializer.save()
        if changed:
            CandidateEvent.objects.create(candidate=candidate,actor=self.request.user,event_type=CandidateEvent.EventType.CANDIDATE_UPDATED,details={"changed_fields":changed})


class CandidateResumeUploadView(GenericAPIView):
    parser_classes=[MultiPartParser,FormParser]
    permission_classes=[IsHRStaff]
    serializer_class=ResumeUploadSerializer

    def post(self,request,public_id):
        candidate=get_object_or_404(Candidate.objects.select_related("requisition"),public_id=public_id)
        if candidate.requisition.status != RequisitionStatus.OPEN:
            raise exceptions.ValidationError("Resumes can only be added to candidates for open requisitions.")
        if candidate.current_status == CandidateStatus.CLOSED:
            raise exceptions.ValidationError("A closed candidate record cannot accept another resume.")
        serializer=self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload=serializer.validated_data["file"]
        content_type=validate_resume_upload(upload)
        try:
            with transaction.atomic():
                document=_save_resume(candidate,upload,request.user,content_type)
                if candidate.current_status == CandidateStatus.NEEDS_MANUAL_REVIEW:
                    candidate.current_status=CandidateStatus.RESUME_RECEIVED
                    candidate.save(update_fields=("current_status","updated_at"))
                    CandidateEvent.objects.create(candidate=candidate,actor=request.user,event_type=CandidateEvent.EventType.STATUS_CHANGED,details={"to":CandidateStatus.RESUME_RECEIVED,"reason":"New resume uploaded"})
                _queue_auto_processing([document.pk])
        except IntegrityError as exc:
            raise exceptions.ValidationError({"file":"A duplicate resume could not be saved."}) from exc
        return Response(ResumeDocumentSummarySerializer(document).data,status=status.HTTP_201_CREATED)


class RequisitionResumeBatchUploadView(GenericAPIView):
    parser_classes=[MultiPartParser,FormParser]
    permission_classes=[IsHRStaff]
    serializer_class=ResumeBatchUploadSerializer

    def get(self,request,reference_code):
        # Enables the DRF Browsable API to render its multipart POST form.
        requisition=get_object_or_404(Requisition,reference_code=reference_code,status=RequisitionStatus.OPEN)
        return Response({"detail":"Use the multipart POST form below to upload a PDF/DOCX resume. The browsable form submits one file per request; repeat for additional resumes.","requisition_reference":str(requisition.reference_code),"upload_field":"files (one file per browsable-form submission)"})

    def post(self,request,reference_code):
        requisition=get_object_or_404(Requisition,reference_code=reference_code,status=RequisitionStatus.OPEN)
        form_serializer=self.get_serializer(data=request.data)
        form_serializer.is_valid(raise_exception=True)
        uploads=request.FILES.getlist("files") or request.FILES.getlist("file")
        if not uploads:
            raise exceptions.ValidationError({"files":"Upload one or more PDF/DOCX files using the 'files' field."})
        if len(uploads)>settings.RESUME_MAX_BATCH_FILES:
            raise exceptions.ValidationError({"files":f"A batch may contain at most {settings.RESUME_MAX_BATCH_FILES} files."})
        if sum(item.size for item in uploads)>settings.RESUME_MAX_BATCH_TOTAL_BYTES:
            raise exceptions.ValidationError({"files":"The total batch size exceeds the configured limit."})
        prepared=[]
        hashes=set()
        for upload in uploads:
            serializer=ResumeUploadSerializer(data={"file":upload})
            serializer.is_valid(raise_exception=True)
            mime=validate_resume_upload(upload)
            digest=calculate_sha256(upload)
            if digest in hashes or ResumeDocument.objects.filter(candidate__requisition=requisition,sha256=digest).exists():
                raise exceptions.ValidationError({"files":f"Duplicate resume detected: {safe_filename(upload)}"})
            hashes.add(digest)
            prepared.append((upload,mime,digest))
        result=[]
        try:
            with transaction.atomic():
                for upload,mime,digest in prepared:
                    candidate=Candidate.objects.create(
                        requisition=requisition,identity_review_required=True,created_by=request.user,
                    )
                    CandidateEvent.objects.create(candidate=candidate,actor=request.user,event_type=CandidateEvent.EventType.CANDIDATE_CREATED,details={"requisition_reference":str(requisition.reference_code),"identity_review_required":True,"intake_method":"BATCH_RESUME_UPLOAD"})
                    document=_save_resume(candidate,upload,request.user,mime,digest)
                    result.append((candidate,document))
                _queue_auto_processing([document.pk for _, document in result])
        except IntegrityError as exc:
            raise exceptions.ValidationError({"files":"The batch could not be saved because it contains duplicate data."}) from exc
        return Response({
            "requisition_reference":str(requisition.reference_code),
            "uploaded_count":len(result),
            "identity_review_required":True,
            "candidates":[{"candidate":CandidateSerializer(c).data,"resume":ResumeDocumentSummarySerializer(d).data} for c,d in result],
        },status=status.HTTP_201_CREATED)


class CandidateEventListView(APIView):
    permission_classes=[permissions.IsAuthenticated]

    def get(self,request,public_id):
        candidate=get_object_or_404(candidates_visible_to(request.user),public_id=public_id)
        return Response(CandidateEventSerializer(candidate.events.select_related("actor"),many=True).data)


class CandidateCloseView(APIView):
    permission_classes=[IsHRStaff]

    def post(self,request,public_id):
        candidate=get_object_or_404(Candidate,public_id=public_id)
        try:
            close_candidate(candidate,request.user,request.data.get("reason",""))
        except PrivacyError as exc:
            raise exceptions.ValidationError({"detail":str(exc)}) from exc
        return Response(CandidateSerializer(candidate).data)


class CandidateEraseView(APIView):
    """HR administrators only: erase personal data of a closed candidate (deletion request / retention)."""

    permission_classes=[IsHRAdmin]

    def post(self,request,public_id):
        candidate=get_object_or_404(Candidate,public_id=public_id)
        try:
            erase_personal_data(candidate,request.user,request.data.get("reason",""))
        except PrivacyError as exc:
            raise exceptions.ValidationError({"detail":str(exc)}) from exc
        candidate.refresh_from_db()
        return Response(CandidateSerializer(candidate).data)


class ResumeDocumentDetailView(APIView):
    permission_classes=[permissions.IsAuthenticated]

    def get(self,request,public_id):
        document=get_object_or_404(documents_visible_to(request.user),public_id=public_id)
        return Response(ResumeDocumentDetailSerializer(document).data)


class ResumeDocumentDownloadView(APIView):
    permission_classes=[IsHRStaff]

    def get(self,request,public_id):
        document=get_object_or_404(ResumeDocument.objects.select_related("candidate"),public_id=public_id)
        if not document.file:
            raise exceptions.NotFound("Resume file is no longer available.")
        try:
            handle=document.file.open("rb")
        except (OSError,ValueError):
            raise exceptions.NotFound("Resume file is no longer available.")
        response=FileResponse(handle,as_attachment=True,filename=document.original_filename,content_type=document.content_type)
        response["X-Content-Type-Options"]="nosniff"
        response["Cache-Control"]="private, no-store"
        return response


class ResumeDocumentProcessView(APIView):
    permission_classes=[IsHRStaff]

    def post(self,request,public_id):
        document=get_object_or_404(ResumeDocument.objects.select_related("candidate"),public_id=public_id)
        if document.processing_status != ResumeProcessingStatus.PENDING:
            raise exceptions.ValidationError({"processing_status":f"Only PENDING resumes can be processed. Current status: {document.processing_status}."})
        document=process_resume_document(document,actor=request.user)
        return Response(ResumeDocumentDetailSerializer(document).data)


class ResumeDocumentRetryView(APIView):
    permission_classes=[IsHRStaff]

    def post(self,request,public_id):
        document=get_object_or_404(ResumeDocument.objects.select_related("candidate"),public_id=public_id)
        if not queue_resume_retry(document,actor=request.user):
            raise exceptions.ValidationError({"processing_status":"Only unexpected processing failures can be retried. Parsing/manual-review errors require intervention."})
        document.refresh_from_db()
        return Response(ResumeDocumentDetailSerializer(document).data,status=status.HTTP_202_ACCEPTED)
