from datetime import timedelta
import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from apps.accounts.models import User
from apps.appointments.models import BookingPhoneVerification
from apps.practitioners.models import PractitionerApplication, PractitionerProfile
from apps.staff.models import StaffProfile
from tests.test_staff import actor, headers, staff_payload
from tests.test_customer_password_auth import issue

pytestmark=pytest.mark.django_db
OLD="Original-Password-2026!"
NEW="Replacement-Password-2026!"

@pytest.fixture(autouse=True)
def clear_limits():
    cache.clear()

def login(client,org,mobile,password=OLD):
    return client.post('/api/v1/auth/login/',{'identifier':mobile,'password':password},format='json',**headers(org))

@pytest.mark.parametrize('mobile',['9876543211','+919876543211'])
def test_approved_therapist_domestic_and_canonical_login(api_client,mobile):
    org,clinic,owner=actor('OWNER')
    api_client.force_authenticate(owner)
    created=api_client.post('/api/v1/staff/profiles/',staff_payload(clinic),format='json',**headers(org))
    staff=StaffProfile.objects.get(pk=created.data['id'])
    staff.user.set_password(OLD);staff.user.save(update_fields=['password'])
    api_client.force_authenticate(None)
    counts=(User.objects.count(),StaffProfile.objects.count(),PractitionerProfile.objects.count())
    response=login(api_client,org,mobile)
    assert response.status_code==200,response.data
    api_client.credentials(HTTP_AUTHORIZATION='Bearer '+response.data['access'])
    access=api_client.get('/api/v1/access/me/',**headers(org))
    assert access.status_code==200 and any(r['role']=='PHYSIOTHERAPIST' and r['is_active'] for r in access.data['roles'])
    assert counts==(User.objects.count(),StaffProfile.objects.count(),PractitionerProfile.objects.count())
    api_client.credentials()
    assert login(api_client,org,mobile,'wrong').status_code==401

def reset_payload(api_client,org):
    issued=issue(api_client,org)
    from django.urls import reverse
    verified=api_client.post(reverse('booking-otp-verify'),{'verification_id':issued.data['verification_id'],'mobile_number':'9876543210','otp':issued.data['otp']},format='json',**headers(org))
    assert verified.status_code==200,verified.data
    return {'verification_id':issued.data['verification_id'],'mobile_number':'9876543210','booking_verification_token':verified.data['token'],'new_password':NEW,'confirm_password':NEW}

@pytest.mark.parametrize('role',['OWNER','MANAGER','PHYSIOTHERAPIST'])
@pytest.mark.parametrize('submitted_mobile',['9876543210','+919876543210'])
@override_settings(MSG91_ENABLED=False)
def test_staff_reset_reuses_proof_revokes_refresh_without_changing_roles(api_client,role,submitted_mobile):
    org,_,user=actor(role, clinic_scoped=role=='PHYSIOTHERAPIST')
    user.mobile_number='+919876543210';user.set_password(OLD);user.save()
    refresh=RefreshToken.for_user(user)
    roles=list(user.role_assignments.values_list('id','is_active'))
    data=reset_payload(api_client,org)
    data['mobile_number']=submitted_mobile
    result=api_client.post('/api/v1/auth/account-password-reset/',data,format='json',**headers(org))
    assert result.status_code==200,result.data
    user.refresh_from_db()
    assert user.check_password(NEW) and not user.check_password(OLD)
    assert BlacklistedToken.objects.filter(token__jti=refresh['jti']).exists()
    assert list(user.role_assignments.values_list('id','is_active'))==roles
    assert not StaffProfile.objects.exists() and not PractitionerProfile.objects.exists()
    assert login(api_client,org,'9876543210',NEW).status_code==200
    assert login(api_client,org,'9876543210',OLD).status_code==401
    replay=api_client.post('/api/v1/auth/account-password-reset/',data,format='json',**headers(org))
    assert replay.status_code==400
    assert replay.data==['OTP proof already used. Please start again.']

@pytest.mark.parametrize('failure',['wrong_mobile','expired','weak','mismatch','inactive','disabled','activation_pending','inactive_role','unknown'])
@override_settings(MSG91_ENABLED=False)
def test_reset_rejects_invalid_proof_or_account_without_mutation(api_client,failure):
    org,_,user=actor('OWNER')
    user.mobile_number='+919876543210';user.set_password(OLD);user.save()
    data=reset_payload(api_client,org)
    if failure=='wrong_mobile':data['mobile_number']='9876543299'
    if failure=='expired':BookingPhoneVerification.objects.filter(pk=data['verification_id']).update(expires_at=timezone.now()-timedelta(seconds=1))
    if failure=='weak':data.update(new_password='weak',confirm_password='weak')
    if failure=='mismatch':data['confirm_password']='different'
    if failure=='inactive':user.is_active=False;user.save()
    if failure=='disabled':user.is_enabled=False;user.save()
    if failure=='activation_pending':user.set_unusable_password();user.save()
    if failure=='inactive_role':user.role_assignments.update(is_active=False)
    if failure=='unknown':user.mobile_number='+919876543299';user.save()
    before=(user.password,user.is_active,user.is_enabled,User.objects.count(),list(user.role_assignments.values_list('id','is_active')))
    response=api_client.post('/api/v1/auth/account-password-reset/',data,format='json',**headers(org))
    assert response.status_code==400,response.data
    if failure=='expired':assert response.data==['OTP verification expired. Please verify again.']
    if failure=='wrong_mobile':assert response.data==['OTP verification does not match this mobile number. Please start again.']
    if failure=='weak':assert 'new_password' in response.data
    if failure in {'inactive','disabled','activation_pending','inactive_role','unknown'}:assert response.data==['Account not found for this password reset flow.']
    user.refresh_from_db()
    assert before==(user.password,user.is_active,user.is_enabled,User.objects.count(),list(user.role_assignments.values_list('id','is_active')))

@pytest.mark.parametrize('status',['SUBMITTED','REJECTED'])
def test_pending_and_rejected_applicants_have_no_operational_access(api_client,status):
    org,_,user=actor('OWNER')
    user.role_assignments.all().delete()
    user.mobile_number='+919876543210';user.set_password(OLD);user.save()
    PractitionerApplication.objects.create(applicant=user,organization=org,status=status)
    result=login(api_client,org,'9876543210')
    assert result.status_code==200
    api_client.credentials(HTTP_AUTHORIZATION='Bearer '+result.data['access'])
    access=api_client.get('/api/v1/access/me/',**headers(org))
    assert access.status_code==200 and access.data['roles']==[]
    assert api_client.get('/api/v1/staff/me/',**headers(org)).status_code in (403,404)

@override_settings(MSG91_ENABLED=False)
def test_approved_self_registered_therapist_resets_through_shared_account_flow(api_client):
    org,_,user=actor('PHYSIOTHERAPIST',clinic_scoped=True)
    user.mobile_number='+919876543210';user.set_password(OLD);user.save()
    PractitionerApplication.objects.create(applicant=user,organization=org,status='APPROVED')
    data=reset_payload(api_client,org)
    response=api_client.post('/api/v1/auth/account-password-reset/',data,format='json',**headers(org))
    assert response.status_code==200,response.data
    user.refresh_from_db()
    assert user.check_password(NEW) and login(api_client,org,'+919876543210',NEW).status_code==200

@override_settings(MSG91_ENABLED=False)
def test_therapist_reset_proof_cannot_cross_into_customer_context(api_client):
    org,_,user=actor('PHYSIOTHERAPIST',clinic_scoped=True)
    user.mobile_number='+919876543210';user.set_password(OLD);user.save()
    data=reset_payload(api_client,org)
    wrong=api_client.post('/api/v1/auth/customer-password-reset/',data,format='json',**headers(org))
    assert wrong.status_code==400
    assert wrong.data==['Account not found for this password reset flow.']
    assert api_client.post('/api/v1/auth/account-password-reset/',data,format='json',**headers(org)).status_code==200
