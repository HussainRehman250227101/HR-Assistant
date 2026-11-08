from io import BytesIO
import tempfile
from docx import Document
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from pypdf import PdfWriter
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User,UserRole
from requisitions.models import Requisition,RequisitionStatus
from .models import Candidate,CandidateEvent,CandidateStatus,ResumeDocument,ResumeProcessingStatus
from .services.processing import process_resume_document
from .validators import DOCX_MIME


def make_docx(filename="resume.docx",text="Senior engineer with PLC, SCADA and industrial automation experience."):
    buffer=BytesIO()
    doc=Document()
    doc.add_paragraph(text)
    doc.save(buffer)
    return SimpleUploadedFile(filename,buffer.getvalue(),content_type=DOCX_MIME)


def make_scanned_pdf():
    buffer=BytesIO()
    writer=PdfWriter()
    writer.add_blank_page(width=612,height=792)
    writer.write(buffer)
    return SimpleUploadedFile("scanned.pdf",buffer.getvalue(),content_type="application/pdf")


class CandidateAndResumeAPITests(APITestCase):
    def setUp(self):
        self.temp_dir=tempfile.TemporaryDirectory()
        self.media_override=override_settings(MEDIA_ROOT=self.temp_dir.name)
        self.media_override.enable()
        self.recruiter=User.objects.create_user(username="recruiter4",email="recruiter4@example.test",password="Strong-Test-Password-123!",role=UserRole.ADMIN)
        self.manager=User.objects.create_user(username="manager4",email="manager4@example.test",password="Strong-Test-Password-123!",role=UserRole.HIRING_MANAGER)
        self.interviewer=User.objects.create_user(username="interviewer4",email="interviewer4@example.test",password="Strong-Test-Password-123!",role=UserRole.RECRUITER)
        self.other_manager=User.objects.create_user(username="manager5",email="manager5@example.test",password="Strong-Test-Password-123!",role=UserRole.HIRING_MANAGER)
        self.requisition=Requisition.objects.create(title="Senior Controls Engineer",department="Engineering",description="Industrial controls role.",status=RequisitionStatus.OPEN,created_by=self.recruiter,hiring_manager=self.manager)
        self.client.force_authenticate(user=self.recruiter)
        self.list_url=reverse("candidates:candidate-list")
        self.payload={"requisition":self.requisition.id,"full_name":"Jane Candidate","email":"JANE.CANDIDATE@example.test","phone":"+923001234567","location":"Lahore"}

    def tearDown(self):
        self.media_override.disable()
        self.temp_dir.cleanup()

    def create_candidate(self,**overrides):
        data={**self.payload,**overrides}
        return Candidate.objects.create(requisition=self.requisition,full_name=data["full_name"],email=data["email"].lower() if data["email"] else None,phone=data.get("phone",""),created_by=self.recruiter)

    def upload_url(self,candidate):
        return reverse("candidates:candidate-resume-upload",args=[candidate.public_id])

    def test_anonymous_users_cannot_list_candidates(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.list_url).status_code,status.HTTP_401_UNAUTHORIZED)

    def test_recruiter_can_create_candidate_and_email_is_normalized(self):
        response=self.client.post(self.list_url,self.payload,format="json")
        self.assertEqual(response.status_code,status.HTTP_201_CREATED,response.data)
        candidate=Candidate.objects.get()
        self.assertEqual(candidate.email,"jane.candidate@example.test")
        self.assertEqual(candidate.current_status,CandidateStatus.RESUME_RECEIVED)
        self.assertEqual(candidate.contact_consent_status,"PENDING")
        self.assertEqual(candidate.events.count(),1)

    def test_candidate_lifecycle_status_is_read_only(self):
        response=self.client.post(self.list_url,{**self.payload,"current_status":"APPROVED_FOR_SCREENING"},format="json")
        self.assertEqual(response.status_code,status.HTTP_201_CREATED)
        self.assertEqual(Candidate.objects.get().current_status,CandidateStatus.RESUME_RECEIVED)

    def assign_interview(self,candidate,interviewer,status_value="SCHEDULED"):
        from datetime import timedelta
        from django.utils import timezone
        from scheduling.models import Interview
        start=timezone.now()+timedelta(days=3)
        return Interview.objects.create(candidate=candidate,requisition=candidate.requisition,interviewer=interviewer,timezone="Asia/Karachi",status=status_value,confirmed_start=start,confirmed_end=start+timedelta(minutes=45),mode="ONSITE",location="Office",created_by=self.recruiter)

    def test_recruiter_interviewer_sees_only_candidates_assigned_to_them(self):
        assigned=self.create_candidate()
        other_req=Requisition.objects.create(title="Automation Engineer",department="Engineering",description="Another role.",status=RequisitionStatus.OPEN,created_by=self.recruiter,hiring_manager=self.other_manager)
        not_assigned=Candidate.objects.create(requisition=other_req,full_name="Other Candidate",email="other@example.test",created_by=self.recruiter)
        cancelled=Candidate.objects.create(requisition=other_req,full_name="Cancelled Candidate",email="cancelled@example.test",created_by=self.recruiter)
        self.assign_interview(assigned,self.interviewer)
        self.assign_interview(cancelled,self.interviewer,"CANCELLED")
        self.client.force_authenticate(user=self.interviewer)
        response=self.client.get(self.list_url)
        self.assertEqual(response.status_code,status.HTTP_200_OK)
        self.assertEqual([c["public_id"] for c in response.data["results"]],[str(assigned.public_id)])
        detail=self.client.get(reverse("candidates:candidate-detail",args=[not_assigned.public_id]))
        self.assertEqual(detail.status_code,status.HTTP_404_NOT_FOUND)

    def test_hiring_manager_has_full_access_to_every_candidate(self):
        self.create_candidate()
        other_req=Requisition.objects.create(title="Automation Engineer",department="Engineering",description="Another role.",status=RequisitionStatus.OPEN,created_by=self.recruiter,hiring_manager=self.other_manager)
        Candidate.objects.create(requisition=other_req,full_name="Other Candidate",email="other@example.test",created_by=self.recruiter)
        self.client.force_authenticate(user=self.manager)
        self.assertEqual(len(self.client.get(self.list_url).data["results"]),2)
        created=self.client.post(self.list_url,{**self.payload,"email":"hm.created@example.test"},format="json")
        self.assertEqual(created.status_code,status.HTTP_201_CREATED)

    def test_recruiter_interviewer_cannot_create_or_edit_candidates(self):
        candidate=self.create_candidate()
        self.assign_interview(candidate,self.interviewer)
        self.client.force_authenticate(user=self.interviewer)
        response=self.client.post(self.list_url,self.payload,format="json")
        self.assertEqual(response.status_code,status.HTTP_403_FORBIDDEN)
        edit=self.client.patch(reverse("candidates:candidate-detail",args=[candidate.public_id]),{"full_name":"Changed"},format="json")
        self.assertEqual(edit.status_code,status.HTTP_403_FORBIDDEN)

    def test_upload_accepts_docx_and_queues_it_without_exposing_text(self):
        candidate=self.create_candidate()
        response=self.client.post(self.upload_url(candidate),{"file":make_docx()},format="multipart")
        self.assertEqual(response.status_code,status.HTTP_201_CREATED,response.data)
        doc=ResumeDocument.objects.get(candidate=candidate)
        self.assertEqual(doc.processing_status,ResumeProcessingStatus.PENDING)
        self.assertEqual(doc.content_type,DOCX_MIME)
        self.assertNotIn("extracted_text",response.data)

    def test_upload_rejects_unsupported_extension(self):
        candidate=self.create_candidate()
        upload=SimpleUploadedFile("resume.exe",b"MZ-data",content_type="application/octet-stream")
        response=self.client.post(self.upload_url(candidate),{"file":upload},format="multipart")
        self.assertEqual(response.status_code,status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ResumeDocument.objects.count(),0)

    def test_duplicate_file_bytes_are_rejected(self):
        candidate=self.create_candidate()
        payload=make_docx().read()
        first=self.client.post(self.upload_url(candidate),{"file":SimpleUploadedFile("resume.docx",payload,content_type=DOCX_MIME)},format="multipart")
        second=self.client.post(self.upload_url(candidate),{"file":SimpleUploadedFile("resume.docx",payload,content_type=DOCX_MIME)},format="multipart")
        self.assertEqual(first.status_code,status.HTTP_201_CREATED)
        self.assertEqual(second.status_code,status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ResumeDocument.objects.filter(candidate=candidate).count(),1)

    def test_batch_upload_creates_placeholder_candidates_for_identity_review(self):
        url=reverse("candidates:requisition-resume-batch-upload",args=[self.requisition.reference_code])
        response=self.client.post(url,{"files":[make_docx("first.docx","First synthetic resume."),make_docx("second.docx","Second synthetic resume.")]},format="multipart")
        self.assertEqual(response.status_code,status.HTTP_201_CREATED,response.data)
        self.assertEqual(response.data["uploaded_count"],2)
        self.assertTrue(response.data["identity_review_required"])
        self.assertEqual(Candidate.objects.count(),2)
        self.assertTrue(all(c.identity_review_required and c.email is None for c in Candidate.objects.all()))

    def test_scanned_pdf_is_flagged_for_manual_review_without_inventing_text(self):
        candidate=self.create_candidate()
        upload_response=self.client.post(self.upload_url(candidate),{"file":make_scanned_pdf()},format="multipart")
        self.assertEqual(upload_response.status_code,status.HTTP_201_CREATED)
        doc=ResumeDocument.objects.get(candidate=candidate)
        processed=process_resume_document(doc,actor=self.recruiter)
        candidate.refresh_from_db()
        self.assertEqual(processed.processing_status,ResumeProcessingStatus.NEEDS_MANUAL_REVIEW)
        self.assertEqual(candidate.current_status,CandidateStatus.NEEDS_MANUAL_REVIEW)
        self.assertEqual(processed.extracted_text,"")
        self.assertEqual(processed.error_code,"NO_SELECTABLE_TEXT")

    def test_docx_extraction_succeeds_but_text_is_not_exposed_in_document_api(self):
        candidate=self.create_candidate()
        self.client.post(self.upload_url(candidate),{"file":make_docx()},format="multipart")
        doc=ResumeDocument.objects.get(candidate=candidate)
        processed=process_resume_document(doc,actor=self.recruiter)
        response=self.client.get(reverse("candidates:resume-document-detail",args=[processed.public_id]))
        self.assertEqual(processed.processing_status,ResumeProcessingStatus.COMPLETED)
        self.assertIn("industrial automation",processed.extracted_text.lower())
        self.assertEqual(response.status_code,status.HTTP_200_OK)
        self.assertNotIn("extracted_text",response.data)

    def test_recruiter_interviewer_cannot_download_resume(self):
        candidate=self.create_candidate()
        self.client.post(self.upload_url(candidate),{"file":make_docx()},format="multipart")
        doc=ResumeDocument.objects.get(candidate=candidate)
        self.assign_interview(candidate,self.interviewer)
        self.client.force_authenticate(user=self.interviewer)
        response=self.client.get(reverse("candidates:resume-document-download",args=[doc.public_id]))
        self.assertEqual(response.status_code,status.HTTP_403_FORBIDDEN)


    def test_batch_upload_browsable_page_renders_file_picker_for_open_requisition(self):
        url=reverse("candidates:requisition-resume-batch-upload",args=[self.requisition.reference_code])
        response=self.client.get(url,HTTP_ACCEPT="text/html")
        self.assertEqual(response.status_code,status.HTTP_200_OK)
        self.assertContains(response,"multipart/form-data")
        self.assertContains(response,'type="file"')

    def test_batch_upload_browsable_page_rejects_non_open_requisition(self):
        self.requisition.status=RequisitionStatus.CLOSED
        self.requisition.save(update_fields=("status",))
        url=reverse("candidates:requisition-resume-batch-upload",args=[self.requisition.reference_code])
        response=self.client.get(url,HTTP_ACCEPT="text/html")
        self.assertEqual(response.status_code,status.HTTP_404_NOT_FOUND)

    def test_processing_is_idempotent_for_completed_document(self):
        candidate=self.create_candidate()
        self.client.post(self.upload_url(candidate),{"file":make_docx()},format="multipart")
        doc=ResumeDocument.objects.get(candidate=candidate)
        first=process_resume_document(doc)
        second=process_resume_document(first)
        self.assertEqual(second.processing_status,ResumeProcessingStatus.COMPLETED)
        self.assertEqual(CandidateEvent.objects.filter(candidate=candidate,event_type=CandidateEvent.EventType.RESUME_EXTRACTION_COMPLETED).count(),1)
