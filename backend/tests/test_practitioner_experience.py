from datetime import timedelta
from io import BytesIO
import pytest
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User
from apps.appointments.models import Appointment, TherapyOption, ClinicOperatingHours
from apps.availability.models import AvailabilityException, AvailabilityAuditEvent
from apps.practitioners.models import TherapyLearningGuide, PractitionerCompetency, PractitionerDocument, PractitionerAuditEvent
from apps.practitioners.learning import SECTIONS
from tests.test_dashboard_repairs import therapist
from tests.test_staff import headers

pytestmark=pytest.mark.django_db

def owner_for(org):
    return User.objects.get(role_assignments__organization=org, role_assignments__role="OWNER")

def photo():
    b=BytesIO();Image.new("RGB",(16,16),"green").save(b,format="PNG")
    return SimpleUploadedFile("photo.png",b.getvalue(),content_type="image/png")

def pdf():
    return SimpleUploadedFile("certificate.pdf",b"%PDF-1.4\n%%EOF",content_type="application/pdf")

def test_self_profile_edits_share_owner_and_public_values(api_client):
    org,_,staff,profile=therapist(api_client)
    response=api_client.patch('/api/v1/staff/me/',{'first_name':'Updated','last_name':'Therapist','email':'updated@example.com','date_of_birth':'1995-08-15','bio':'Professional bio','languages_known':['Hindi'],'experience_years':7,'service_area_ids':list(map(str,staff.service_areas.values_list('pk',flat=True)))},format='json',**headers(org))
    assert response.status_code==200,response.data
    staff.refresh_from_db();staff.user.refresh_from_db()
    assert staff.user.get_full_name()=='Updated Therapist' and staff.bio=='Professional bio'
    from apps.practitioners.serializers import PublicPractitionerSerializer
    profile.refresh_from_db(); public=PublicPractitionerSerializer(profile).data
    assert public['bio']=='Professional bio' and public['experience_years']==7 and public['languages']==['Hindi']
    api_client.force_authenticate(owner_for(org))
    owner=api_client.get(reverse('staff-detail',args=[staff.pk]),**headers(org))
    assert owner.data['date_of_birth']=='1995-08-15' and owner.data['full_name']=='Updated Therapist'

@pytest.mark.parametrize('data',[{'mobile':'+919999999999'},{'qualification':'Unverified degree'},{'therapy_competency_ids':[]},{'staff_type':'MANAGER'}])
def test_self_cannot_edit_verified_identity_or_operational_claims(api_client,data):
    org,_,staff,_=therapist(api_client)
    response=api_client.patch('/api/v1/staff/me/',data,format='json',**headers(org))
    assert response.status_code==400
    response=api_client.patch('/api/v1/auth/profile/',{'mobile_number':'+919999999999'},format='json',**headers(org))
    assert response.status_code==400
    staff.user.refresh_from_db();assert staff.user.mobile_number!='+919999999999'

def test_photo_upload_replace_remove_and_owner_canonical_read(api_client):
    org,_,staff,_=therapist(api_client)
    for _ in range(2):
        r=api_client.post('/api/v1/staff/me/photo/',{'profile_photo':photo()},format='multipart',**headers(org))
        assert r.status_code==200,r.data
        assert api_client.get('/api/v1/staff/me/photo/',**headers(org)).status_code==200
    from apps.staff.photos import profile_photo
    staff.refresh_from_db();assert profile_photo(staff)==staff.profile_photo
    assert api_client.delete('/api/v1/staff/me/photo/',**headers(org)).status_code==200
    staff.refresh_from_db();assert profile_photo(staff) is None
    assert api_client.get('/api/v1/staff/me/photo/',**headers(org)).status_code==404
    assert api_client.post('/api/v1/staff/me/photo/',{'profile_photo':pdf()},format='multipart',**headers(org)).status_code==400

def test_credential_replacement_preserves_history_and_is_reviewed_separately(api_client):
    org,_,staff,profile=therapist(api_client)
    original=staff.qualification
    for _ in range(2):
        response=api_client.post('/api/v1/staff/me/credentials/',{'kind':'QUALIFICATION','file':pdf()},format='multipart',**headers(org))
        assert response.status_code==201,response.data
    assert PractitionerDocument.objects.filter(profile=profile,verification_status='PENDING').count()==2
    assert PractitionerAuditEvent.objects.filter(profile=profile).count()==2
    listing=api_client.get('/api/v1/staff/me/credentials/',**headers(org))
    assert listing.data[0]['status']=='PENDING' and 'file' not in listing.data[0]
    doc_id=response.data['id']
    assert api_client.post(f'/api/v1/staff/credentials/{doc_id}/review/',{'status':'VERIFIED'},format='json',**headers(org)).status_code==403
    api_client.force_authenticate(owner_for(org))
    assert api_client.get(f'/api/v1/staff/credentials/{doc_id}/',**headers(org)).status_code==200
    assert api_client.post(f'/api/v1/staff/credentials/{doc_id}/review/',{'status':'VERIFIED'},format='json',**headers(org)).status_code==200
    staff.refresh_from_db();profile.refresh_from_db()
    assert staff.qualification==original and profile.is_approved

def test_therapist_and_owner_manage_current_therapies_immediately(api_client):
    org,_,staff,profile=therapist(api_client)
    learned=TherapyOption.objects.create(organization=org,name='Newly Learned Therapy',slug='newly-learned-therapy')
    removable=TherapyOption.objects.create(organization=org,name='Pending Removal Therapy',slug='pending-removal-therapy')
    initial=api_client.get('/api/v1/staff/me/competencies/',**headers(org))
    assert initial.status_code==200
    assert next(item for item in initial.data if item['therapy_id']==str(learned.id))['status']=='NOT_SELECTED'
    requested=api_client.post('/api/v1/staff/me/competencies/',{'therapy_id':str(learned.id)},format='json',**headers(org))
    assert requested.status_code==201 and requested.data['status']=='SELECTED'
    assert staff.therapy_competencies.filter(pk=learned.pk).exists()
    remove_request=api_client.post('/api/v1/staff/me/competencies/',{'therapy_id':str(removable.id)},format='json',**headers(org))
    assert api_client.delete('/api/v1/staff/me/competencies/',{'therapy_id':str(removable.id)},format='json',**headers(org)).status_code==204
    assert PractitionerCompetency.objects.get(profile=profile,therapy=removable).verification_status == 'REJECTED'
    assert PractitionerAuditEvent.objects.filter(profile=profile,metadata__therapy_id=str(removable.id),action='COMPETENCY_REMOVED').exists()
    api_client.force_authenticate(owner_for(org))
    managed=reverse('staff-competencies',args=[staff.id])
    assert api_client.post(managed,{'therapy_id':str(removable.id)},format='json',**headers(org)).status_code==201
    assert staff.therapy_competencies.filter(pk=removable.pk).exists()
    assert api_client.delete(managed,{'therapy_id':str(removable.id)},format='json',**headers(org)).status_code==204
    assert not staff.therapy_competencies.filter(pk=removable.pk).exists()
    api_client.force_authenticate(staff.user)
    final=api_client.get('/api/v1/staff/me/competencies/',**headers(org))
    assert next(item for item in final.data if item['therapy_id']==str(learned.id))['status']=='SELECTED'

def test_verified_competency_removal_blocks_future_required_appointment(api_client):
    from tests.test_scheduling import setup_domain
    from apps.practitioners.models import PractitionerProfile

    org,clinic,owner,_,_,staff,_,patient,address,therapy=setup_domain('competency-removal-safety')
    profile=PractitionerProfile.objects.create(
        user=staff.user,organization=org,clinic=clinic,staff_profile=staff,
        category='PHYSIOTHERAPIST',is_approved=True,is_open_to_work=True,approved_at=timezone.now(),
    )
    competency=PractitionerCompetency.objects.create(
        profile=profile,therapy=therapy,verification_status='VERIFIED',
        verified_by=owner,verified_at=timezone.now(),
    )
    staff.therapy_competencies.add(therapy)
    start=timezone.now()+timedelta(days=3)
    appointment=Appointment.objects.create(
        organization=org,clinic=clinic,patient=patient,therapy=therapy,physiotherapist=staff,
        scheduled_start=start,scheduled_end=start+timedelta(minutes=45),duration_minutes=45,
        status='SCHEDULED',address_line_1=address.address_line_1,city=address.city,
        region=address.region,pin_code=address.pin_code,created_by=owner,updated_by=owner,
    )
    api_client.force_authenticate(staff.user)
    response=api_client.delete(
        '/api/v1/staff/me/competencies/',{'therapy_id':str(therapy.id)},
        format='json',**headers(org),
    )
    assert response.status_code==400
    assert str(appointment.id) in str(response.data) and 'Reassign or cancel that appointment first.' in str(response.data)
    competency.refresh_from_db()
    assert competency.verification_status=='VERIFIED'
    assert staff.therapy_competencies.filter(pk=therapy.pk).exists()

def test_future_date_only_leave_is_direct_and_cancellable(api_client):
    org,_,staff,_=therapist(api_client)
    start=(timezone.now()+timedelta(days=14)).date().isoformat()
    response=api_client.post('/api/v1/availability/me/exceptions/',{'kind':'UNAVAILABLE','from_date':start,'to_date':start,'reason':'Personal leave'},format='json',**headers(org))
    assert response.status_code==201,response.data
    assert response.data['approval_status']=='APPROVED' and response.data['is_active']
    value=AvailabilityException.objects.get(pk=response.data['id'])
    assert (value.ends_at-value.starts_at)==timedelta(days=1)
    assert api_client.post(f'/api/v1/availability/me/exceptions/{value.pk}/deactivate/',{},format='json',**headers(org)).status_code==200
    value.refresh_from_db();assert not value.is_active
    assert AvailabilityAuditEvent.objects.filter(exception=value).exists()
    past=(timezone.now()-timedelta(days=1)).date().isoformat()
    assert api_client.post('/api/v1/availability/me/exceptions/',{'kind':'UNAVAILABLE','from_date':past,'to_date':past,'reason':'Past'},format='json',**headers(org)).status_code==400

def guide_setup(api_client):
    org,_,staff,_=therapist(api_client)
    therapy=TherapyOption.objects.filter(organization=org).first()
    owner=owner_for(org)
    api_client.force_authenticate(owner)
    data={'therapy':str(therapy.pk),'title_en':'Approved test guide','title_hi':'Approved Hindi test title','content_en':{key:'Organization-approved test fixture.' for key in SECTIONS},'content_hi':{key:'Hindi test fixture.' for key in SECTIONS}}
    return org,staff,owner,data

def test_owner_guide_crud_publish_and_therapist_read_only(api_client):
    org,staff,owner,data=guide_setup(api_client)
    r=api_client.post('/api/v1/learning/',data,format='json',**headers(org));assert r.status_code==201,r.data
    url=f"/api/v1/learning/{r.data['id']}/"
    api_client.force_authenticate(staff.user)
    assert api_client.get('/api/v1/learning/',**headers(org)).data['guides']==[]
    assert api_client.get(url,**headers(org)).status_code==404
    assert api_client.patch(url,{'published':True},format='json',**headers(org)).status_code==403
    api_client.force_authenticate(owner)
    missing_approval=api_client.patch(url,{'published':True},format='json',**headers(org));assert missing_approval.status_code==400
    r=api_client.patch(url,{'published':True,'clinical_approval':True},format='json',**headers(org));assert r.status_code==200,r.data
    assert r.data['version']==2 and r.data['reviewed_at']
    api_client.force_authenticate(staff.user)
    assert api_client.get(url,**headers(org)).data['title_hi']==data['title_hi']
    api_client.force_authenticate(owner)
    assert api_client.delete(url,**headers(org)).status_code==200
    assert TherapyLearningGuide.objects.count()==1
    api_client.force_authenticate(staff.user)
    assert api_client.get(url,**headers(org)).status_code==404

@pytest.mark.parametrize('url',['https://example.com/watch?v=abcdefghijk','javascript:alert(1)','https://youtube.com.evil.test/watch?v=abcdefghijk','http://youtu.be/abcdefghijk','https://www.youtube.com:bad/watch?v=abcdefghijk'])
def test_learning_rejects_unapproved_video_hosts(api_client,url):
    org,_,_,data=guide_setup(api_client)
    guide=api_client.post('/api/v1/learning/',data,format='json',**headers(org)).data
    response=api_client.post(f"/api/v1/learning/{guide['id']}/videos/",{'title':'Test','youtube_url':url,'language':'en'},format='json',**headers(org))
    assert response.status_code==400,response.data

def test_learning_assets_are_approved_scoped_and_safe(api_client):
    org,staff,owner,data=guide_setup(api_client)
    data.update(published=True,clinical_approval=True)
    g=api_client.post('/api/v1/learning/',data,format='json',**headers(org)).data
    url=f"/api/v1/learning/{g['id']}/"
    image=api_client.post(url+'images/',{'image':photo(),'alt_text':'Licensed example','rights_confirmed':True},format='multipart',**headers(org))
    assert image.status_code==201,image.data
    video={'title':'Curated fixture','youtube_url':'https://youtu.be/abcdefghijk','language':'en','approved':False}
    assert api_client.post(url+'videos/',video,format='json',**headers(org)).status_code==201
    api_client.force_authenticate(staff.user)
    result=api_client.get(url,**headers(org));assert result.data['videos']==[]
    assert 'image' not in result.data['images'][0] and 'reviewed_by' not in result.data
    assert api_client.get('/api/v1/learning/images/'+result.data['images'][0]['id']+'/',**headers(org)).status_code==200
    from tests.test_staff import actor
    foreign,_,outsider=actor('MANAGER')
    api_client.force_authenticate(outsider)
    assert api_client.get(url,**headers(foreign)).status_code==403

def test_cannot_publish_incomplete_clinical_content(api_client):
    org,_,_,data=guide_setup(api_client)
    data.update(content_hi={},published=True,clinical_approval=True)
    r=api_client.post('/api/v1/learning/',data,format='json',**headers(org))
    assert r.status_code==400 and TherapyLearningGuide.objects.count()==0
