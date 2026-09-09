import io
import json
import pytest
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from apps.accounts.models import User
from apps.practitioners.models import PractitionerApplication, PractitionerProfile
from apps.practitioners.services import approve_application, review_application
from apps.staff.models import StaffProfile
from tests.test_staff import actor, staff_payload, headers
from tests.test_customer_registration import issue, verify

pytestmark = pytest.mark.django_db

def photo():
    stream=io.BytesIO()
    Image.new("RGB", (10,10)).save(stream, format="PNG")
    return SimpleUploadedFile("profile.png", stream.getvalue(), content_type="image/png")

def payload(clinic, token):
    data=staff_payload(clinic, suffix="0")
    data.pop("specialization_ids")
    data.pop("registration_number")
    data.update(profile_photo=photo(), password="Practitioner-Secure-2026!", confirm_password="Practitioner-Secure-2026!",
                mobile_verification_token=token, working_days=json.dumps([0,2,4]), working_hours_start="10:00",
                working_hours_end="18:00", practitioner_type="WELLNESS", qualification="Diploma in Naturopathy",
                experience_months=6, languages_known=json.dumps(["Hindi","English","hindi"]))
    for field in ("government_id_document","qualification_document"):
        data[field]=SimpleUploadedFile(field+".pdf",b"%PDF-1.4 test",content_type="application/pdf")
    return data

@override_settings(MSG91_ENABLED=False)
def test_complete_application_pending_private_and_idempotent_approval(api_client,settings,tmp_path):
    settings.MEDIA_ROOT=tmp_path
    org,clinic,owner=actor("OWNER")
    token=verify(api_client,org,issue(api_client,org)).data["token"]
    result=api_client.post("/api/v1/practitioners/register-complete/",payload(clinic,token),format="multipart",**headers(org))
    assert result.status_code==201,result.data
    app=PractitionerApplication.objects.get(pk=result.data["id"])
    assert app.status=="SUBMITTED" and result.data["status_label"]=="Pending Approval"
    assert app.languages==["hindi","English"]
    assert app.working_days==[0,2,4] and app.service_areas.count()==1 and app.documents.count()==2
    assert not StaffProfile.objects.filter(user=app.applicant).exists()
    assert not PractitionerProfile.objects.filter(user=app.applicant).exists()
    assert not app.applicant.role_assignments.exists()
    assert api_client.get("/api/v1/practitioners/public/",**headers(org)).data==[]
    duplicate=api_client.post("/api/v1/practitioners/register-complete/",payload(clinic,token),format="multipart",**headers(org))
    assert duplicate.status_code==400
    assert User.objects.filter(mobile_number=app.mobile_number).count()==1
    app.documents.update(verification_status="VERIFIED")
    review_application(app, actor=owner, action="review")
    app.refresh_from_db()
    approve_application(app,actor=owner)
    approve_application(app,actor=owner)
    staff=StaffProfile.objects.get(user=app.applicant)
    assert staff.qualification=="Diploma in Naturopathy" and staff.service_areas.count()==1
    assert set(staff.therapy_competencies.values_list("id",flat=True)) == set(app.competencies.values_list("therapy_id",flat=True))
    assert staff.availabilityrule_set.count()==3
    assert PractitionerProfile.objects.filter(user=app.applicant).count()==1
    from apps.practitioners.serializers import PublicPractitionerSerializer
    assert PublicPractitionerSerializer().get_highest_qualification(staff.practitioner_profile)=="Diploma in Naturopathy"

@pytest.mark.parametrize("field",["profile_photo","government_id_document","qualification_document","date_of_birth","service_area_ids","therapy_competency_ids","mobile_verification_token"])
@override_settings(MSG91_ENABLED=False)
def test_incomplete_submission_never_creates_identity(api_client,field,settings,tmp_path):
    settings.MEDIA_ROOT=tmp_path
    org,clinic,_=actor("OWNER")
    data=payload(clinic,"invalid-proof")
    data.pop(field)
    before=User.objects.count()
    response=api_client.post("/api/v1/practitioners/register-complete/",data,format="multipart",**headers(org))
    assert response.status_code==400,response.data
    assert User.objects.count()==before and not PractitionerApplication.objects.exists()

@override_settings(MSG91_ENABLED=False)
def test_proof_is_bound_to_mobile_and_failed_attempt_does_not_consume_it(api_client,settings,tmp_path):
    settings.MEDIA_ROOT=tmp_path
    org,clinic,_=actor("OWNER")
    token=verify(api_client,org,issue(api_client,org)).data["token"]
    data=payload(clinic,token)
    data["mobile"]="+919876543299"
    response=api_client.post("/api/v1/practitioners/register-complete/",data,format="multipart",**headers(org))
    assert response.status_code==400 and not PractitionerApplication.objects.exists()
    response=api_client.post("/api/v1/practitioners/register-complete/",payload(clinic,token),format="multipart",**headers(org))
    assert response.status_code==201,response.data

@override_settings(MSG91_ENABLED=False)
def test_correction_preserves_canonical_fields_and_verified_identity(api_client,settings,tmp_path):
    settings.MEDIA_ROOT=tmp_path
    org,clinic,owner=actor("OWNER")
    token=verify(api_client,org,issue(api_client,org)).data["token"]
    response=api_client.post("/api/v1/practitioners/register-complete/",payload(clinic,token),format="multipart",**headers(org))
    app=PractitionerApplication.objects.get(pk=response.data["id"])
    from apps.practitioners.services import submit_application
    review_application(app, actor=owner, action="review")
    app.refresh_from_db()
    review_application(app,actor=owner,action="correction",reason="Clarify qualification")
    api_client.force_authenticate(app.applicant)
    url=f"/api/v1/practitioners/applications/me/{app.id}/"
    corrected=api_client.patch(url,{"qualification_title":"Updated qualification", "working_hours_end":"17:30", "service_areas":list(map(str,app.service_areas.values_list("id",flat=True)))},format="json",**headers(org))
    assert corrected.status_code==200,corrected.data
    assert corrected.data["service_area_names"]==["Meerut"]
    invalid=api_client.patch(url,{"mobile_number":"+919876543299"},format="json",**headers(org))
    assert invalid.status_code==400
    submit_application(app,actor=app.applicant)
    app.refresh_from_db()
    assert app.status=="RESUBMITTED" and app.qualification_title=="Updated qualification"
    assert not app.applicant.role_assignments.exists()
