from datetime import date
from unittest import skipIf, skipUnless
import json
import tempfile

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from userProfile.models import Profile
from yatra.models import RegistrationPhase, RegistrationPolicy, Yatra, YatraInstallment
from yatra_registration.models import YatraRegistration, YatraEligibility
from payment.models import Payment
from yatra_registration.serializers import YatraRegistrationDetailSerializer
from yatra_registration.views import phase_for_registration


class ComplimentaryRegistrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('guest-user')
        self.profile = Profile.objects.create(user=self.user, first_name='Guest')
        self.yatra = Yatra.objects.create(title='Guest Yatra', description='Test', start_date=date(2027, 1, 1), end_date=date(2027, 1, 2), location='Test', capacity=10)
        self.phase = RegistrationPhase.objects.create(yatra=self.yatra, name='Phase')
        YatraInstallment.objects.create(yatra=self.yatra, phase=self.phase, label='First', amount=3500)
        self.registration = YatraRegistration.objects.create(yatra=self.yatra, phase=self.phase, registered_by=self.profile, registered_for=self.profile, is_complimentary=True, status='paid')

    def test_exempt_from_payment_and_phase_preserved(self):
        reg = self.registration
        self.assertEqual((reg.total_amount, reg.paid_amount, reg.pending_amount), (0, 0, 0))
        self.assertEqual(phase_for_registration(self.yatra, reg), self.phase)
        self.assertEqual(YatraRegistrationDetailSerializer(reg).data['installments'], [])
        reg.update_status()
        self.assertEqual(reg.status, 'paid')
        reg.status = 'cancelled'
        reg.save()
        reg.update_status()
        self.assertEqual(reg.status, 'cancelled')


@skipIf(apps.is_installed('django.contrib.admin'), 'Requires API settings')
class ComplimentaryAPITests(ComplimentaryRegistrationTests):
    def test_mixed_checkout_is_atomic_and_charges_only_paid_profile(self):
        actor = get_user_model().objects.create_superuser('mixed-admin', 'admin@example.com', 'password')
        actor_profile = Profile.objects.create(user=actor, first_name='Admin')
        monk_user = get_user_model().objects.create_user('mixed-monk')
        monk = Profile.objects.create(user=monk_user, first_name='Monk', marital_status='brahmachari_temple', mentor=actor_profile, profile_verification_status='verified')
        paid_user = get_user_model().objects.create_user('mixed-paid')
        paid = Profile.objects.create(user=paid_user, first_name='Paid', mentor=actor_profile, profile_verification_status='verified')
        RegistrationPolicy.objects.create(yatra=self.yatra, requires_approval=True)
        inst = self.phase.installments.first()
        inst.start_date = date(2020, 1, 1)
        inst.save()
        for profile in (monk, paid):
            YatraEligibility.objects.create(yatra=self.yatra, profile=profile, approved_by=actor_profile, is_approved=True)
        data = {
            'registrations': json.dumps({str(monk.pk): {'form_fields': {}, 'installments_selected': []}, str(paid.pk): {'form_fields': {}, 'installments_selected': ['First']}}),
            'registration_installments': json.dumps([{'profile_id': str(paid.pk), 'installments': ['First']}]),
            'complimentary_profile_ids': json.dumps([str(monk.pk)]),
            'transaction_id': 'mixed-checkout', 'total_amount': '3500.00',
        }
        client = APIClient()
        client.force_authenticate(actor)
        url = f'/payments/{self.yatra.pk}/checkout/'
        self.assertEqual(client.post(url, data, format='multipart').status_code, 400)
        self.assertFalse(YatraRegistration.objects.filter(registered_for=monk).exists())
        with tempfile.TemporaryDirectory() as media:
            with override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': media}}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
                invalid = client.post(url, {**data, 'total_amount': '1.00', 'screenshot': SimpleUploadedFile('proof.png', b'proof', content_type='image/png')}, format='multipart')
                self.assertEqual(invalid.status_code, 400)
                self.assertFalse(YatraRegistration.objects.filter(registered_for__in=[monk, paid]).exists())
                response = client.post(url, {**data, 'screenshot': SimpleUploadedFile('proof.png', b'proof', content_type='image/png')}, format='multipart')
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(Payment.objects.get().total_amount, 3500)
                self.assertEqual(YatraRegistration.objects.get(registered_for=monk).status, 'paid')
                self.assertTrue(YatraRegistration.objects.get(registered_for=monk).is_complimentary)
                self.assertEqual(YatraRegistration.objects.get(registered_for=paid).status, 'partial')

    def test_only_superuser_can_create_and_capacity_is_enforced(self):
        url = f'/payments/{self.yatra.pk}/checkout/'
        actor = get_user_model().objects.create_superuser('frontend-admin', 'admin@example.com', 'password')
        actor_profile = Profile.objects.create(user=actor, first_name='Admin')
        other_user = get_user_model().objects.create_user('new-guest')
        other = Profile.objects.create(user=other_user, first_name='New', marital_status='brahmachari_temple', mentor=actor_profile, profile_verification_status='verified')
        RegistrationPolicy.objects.create(yatra=self.yatra, requires_approval=True)
        inst = self.phase.installments.first()
        inst.start_date = date(2020, 1, 1)
        inst.save()
        payload = {'registrations': json.dumps({str(other.pk): {'form_fields': {'shirt': 'M'}, 'installments_selected': []}}), 'registration_installments': '[]', 'complimentary_profile_ids': json.dumps([str(other.pk)])}
        client = APIClient()
        client.force_authenticate(self.user)
        self.assertEqual(client.post(url, payload, format='multipart').status_code, 403)
        client.force_authenticate(actor)
        self.assertEqual(client.post(url, payload, format='multipart').status_code, 400)
        YatraEligibility.objects.create(yatra=self.yatra, profile=other, approved_by=actor_profile, is_approved=True)
        other.marital_status = 'married'
        other.save(update_fields=['marital_status'])
        self.assertEqual(client.post(url, payload, format='multipart').status_code, 400)
        other.marital_status = 'brahmachari_temple'
        other.save(update_fields=['marital_status'])
        self.yatra.capacity = 1
        self.yatra.save(update_fields=['capacity'])
        self.assertEqual(client.post(url, payload, format='multipart').status_code, 400)
        self.yatra.capacity = 2
        self.yatra.save(update_fields=['capacity'])
        self.assertEqual(client.post(url, payload, format='multipart').status_code, 201)
        registration = YatraRegistration.objects.get(yatra=self.yatra, registered_for=other)
        self.assertTrue(registration.is_complimentary)
        self.assertEqual(registration.status, 'paid')
        self.assertEqual(registration.registered_by, actor_profile)
        self.assertEqual(registration.form_data, {'shirt': 'M'})
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(client.get(f'/yatras/{self.yatra.pk}/{other.pk}/registrations/').status_code, 200)
        listing = client.get(f'/yatras/{self.yatra.pk}/register/')
        self.assertTrue(listing.data['can_register_complimentary'])
        self.assertTrue(any(str(p['id']) == str(other.pk) for p in listing.data['profiles']))

    def test_guest_is_displayed_without_installments_and_cannot_pay_or_cancel(self):
        RegistrationPolicy.objects.create(yatra=self.yatra, requires_approval=False)
        self.yatra.is_cancellation_open = True
        self.yatra.save(update_fields=['is_cancellation_open'])
        client = APIClient()
        client.force_authenticate(self.user)
        detail = client.get(f'/yatras/{self.yatra.pk}/{self.profile.pk}/registrations/')
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data['is_complimentary'])
        self.assertEqual(detail.data['installments'], [])
        listing = client.get(f'/yatras/{self.yatra.pk}/register/')
        self.assertEqual(listing.status_code, 200)
        profile = next(p for p in listing.data['profiles'] if str(p['id']) == str(self.profile.pk))
        self.assertTrue(profile['is_complimentary'])
        self.assertEqual(profile['installments_info'], [])
        self.assertEqual(client.delete(f'/yatras/{self.yatra.pk}/register/', {'profile_id': str(self.profile.pk)}, format='json').status_code, 403)
        self.assertEqual(client.post(f'/yatra-transfers/registrations/{self.registration.pk}/substitute/', {}, format='json').status_code, 403)
        payment = client.post(f'/payments/{self.yatra.pk}/checkout/', {
            'transaction_id': 'guest-payment', 'total_amount': '3500.00',
            'registrations': json.dumps({str(self.profile.pk): {'form_fields': {}, 'installments_selected': ['First']}}),
            'registration_installments': json.dumps([{'profile_id': str(self.profile.pk), 'installments': ['First']}]),
            'screenshot': SimpleUploadedFile('proof.png', b'proof', content_type='image/png'),
        }, format='multipart')
        self.assertEqual(payment.status_code, 400)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.status, 'paid')


@skipUnless(apps.is_installed('django.contrib.admin'), 'Requires admin settings')
class ComplimentaryAdminTests(ComplimentaryRegistrationTests):
    def test_permissions_and_count(self):
        from django.contrib import admin
        from yatra.admin import YatraAdmin
        from yatra_registration.admin import YatraRegistrationAdmin

        superuser = get_user_model().objects.create_superuser('guest-admin', 'a@example.com', 'password')
        staff = get_user_model().objects.create_user('guest-staff', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='change_yatraregistration'), Permission.objects.get(codename='delete_yatraregistration'))
        request = RequestFactory().get('/')
        request.user = staff
        registration_admin = YatraRegistrationAdmin(YatraRegistration, admin.site)
        self.assertFalse(registration_admin.has_add_permission(request))
        self.assertIn('is_complimentary', registration_admin.get_exclude(request))
        self.assertFalse(registration_admin.has_change_permission(request, self.registration))
        self.assertFalse(registration_admin.has_delete_permission(request, self.registration))
        request.user = superuser
        self.assertFalse(registration_admin.has_add_permission(request))
        self.assertIn('is_complimentary', registration_admin.get_exclude(request, self.registration))
        self.assertIn('CONFIRMED (B)', str(registration_admin.registration_status(self.registration)))
        yatra_admin = YatraAdmin(Yatra, admin.site)
        self.assertEqual(yatra_admin.get_queryset(request).get(pk=self.yatra.pk).started_registration_count, 1)

