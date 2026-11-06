from datetime import date
from decimal import Decimal
import json
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from django.template.loader import render_to_string
from unittest.mock import patch

from payment.models import Payment
from userProfile.models import Profile
from yatra.models import Yatra, YatraInstallment, RegistrationPolicy
from yatra_registration.models import YatraRegistration, YatraRegistrationInstallment


class PaymentEmailInstallmentTests(TestCase):
    def test_rejection_followed_by_approval_renders_correct_emails(self):
        user = User.objects.create_user(username="payment-decision", email="member@example.com")
        profile = Profile.objects.create(user=user, first_name="Member")
        yatra = Yatra.objects.create(title="Test Yatra", description="Test", start_date=date(2027, 1, 1), end_date=date(2027, 1, 2), location="Test", capacity=5)
        registration = YatraRegistration.objects.create(yatra=yatra, registered_for=profile, registered_by=profile)
        installment = YatraInstallment.objects.create(yatra=yatra, label="First installment", amount="100")
        payment = Payment.objects.create(uploaded_by=profile, transaction_id="decision-test", total_amount=100)
        record = YatraRegistrationInstallment.objects.create(registration=registration, installment=installment, payment=payment)

        with patch("payment.notifications._send") as send:
            with self.captureOnCommitCallbacks(execute=True):
                payment.reject(profile)
            rejection = send.call_args.args[2]
            self.assertEqual(rejection["status"], "Rejected")
            self.assertIn("We could not approve your payment", render_to_string("emails/payment_status.html", rejection))
            record.refresh_from_db()
            self.assertFalse(record.is_paid)

            with self.captureOnCommitCallbacks(execute=True):
                payment.approve(profile)
            approval = send.call_args.args[2]
            self.assertEqual(approval["status"], "Approved")
            self.assertIn("successfully verified & approved", render_to_string("emails/payment_status.html", approval))
            self.assertEqual(approval["payment_rows"][0]["status"], "Approved")
            record.refresh_from_db()
            self.assertTrue(record.is_paid)
            self.assertEqual(send.call_count, 2)

    def test_email_identifies_only_installments_covered_by_payment(self):
        from payment.notifications import notify_payment_submitted, notify_payment_result

        user = User.objects.create_user(username="payment-email")
        profile = Profile.objects.create(user=user, first_name="Member")
        yatra = Yatra.objects.create(title="Test Yatra", description="Test", start_date=date(2027, 1, 1), end_date=date(2027, 1, 2), location="Test", capacity=5)
        registration = YatraRegistration.objects.create(yatra=yatra, registered_for=profile, registered_by=profile)
        first = YatraInstallment.objects.create(yatra=yatra, label="First installment", amount="100", order=1)
        second = YatraInstallment.objects.create(yatra=yatra, label="Second installment", amount="200", order=2)
        payment = Payment.objects.create(uploaded_by=profile, transaction_id="email-test", total_amount=100)
        YatraRegistrationInstallment.objects.create(registration=registration, installment=first, payment=payment)
        YatraRegistrationInstallment.objects.create(registration=registration, installment=second)

        with patch("payment.notifications._send") as send:
            for notify in (lambda: notify_payment_submitted(payment), lambda: notify_payment_result(payment, True, profile), lambda: notify_payment_result(payment, False, profile)):
                notify()
                context = send.call_args.args[2]
                self.assertEqual(context["payment_installments"], "First installment")
                rendered = render_to_string("emails/payment_status.html", context)
                self.assertIn("<strong>First installment</strong>", rendered)
                self.assertIn("Second installment", rendered)  # Full status table remains intact.

        from payment.notifications import _payment_installment_names
        YatraRegistrationInstallment.objects.filter(registration=registration, installment=second).update(payment=payment)
        self.assertEqual(_payment_installment_names(payment), "First installment, Second installment")


class BatchPaymentSecurityTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.storage = override_settings(STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': self.media.name}},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        })
        self.storage.enable()
        self.addCleanup(self.storage.disable)
        self.user = User.objects.create_user(username="payment-owner")
        other_user = User.objects.create_user(username="payment-other")
        self.profile = Profile.objects.create(user=self.user, profile_verification_status="verified")
        self.other = Profile.objects.create(user=other_user, profile_verification_status="verified")
        self.yatra = Yatra.objects.create(
            title="Payment Yatra", description="Test", start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 2), location="Test", capacity=5,
        )
        self.installment = YatraInstallment.objects.create(yatra=self.yatra, label="First", amount="100.00")
        RegistrationPolicy.objects.create(yatra=self.yatra, requires_approval=False)
        for profile in (self.profile, self.other):
            registration = YatraRegistration.objects.create(yatra=self.yatra, registered_for=profile, registered_by=profile)
            YatraRegistrationInstallment.objects.create(registration=registration, installment=self.installment)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/payments/{self.yatra.pk}/checkout/"

    def submit(self, profile, amount="100.00", labels=None, transaction_id="transaction-1"):
        selected = labels if labels is not None else ['First']
        return self.client.post(self.url, {
            "transaction_id": transaction_id, "total_amount": amount,
            "registration_installments": json.dumps([{"profile_id": str(profile.pk), "installments": selected}]),
            "registrations": json.dumps({str(profile.pk): {'form_fields': {}, 'installments_selected': selected}}),
            "screenshot": SimpleUploadedFile('proof.png', b'proof', content_type='image/png'),
        }, format="multipart")

    def test_unrelated_profile_cannot_be_relinked(self):
        response = self.submit(self.other)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Payment.objects.exists())
        self.assertIsNone(YatraRegistrationInstallment.objects.get(registration__registered_for=self.other).payment)

    def test_current_mentor_can_submit_for_a_scoped_profile(self):
        self.other.mentor = self.profile
        self.other.save(update_fields=["mentor"])
        response = self.submit(self.other)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(YatraRegistrationInstallment.objects.get(registration__registered_for=self.other).payment.uploaded_by, self.profile)

    def test_amount_and_selection_must_match(self):
        self.assertEqual(self.submit(self.profile, amount="1.00").status_code, 400)
        self.assertEqual(self.submit(self.profile, labels=["First", "First"]).status_code, 400)
        self.assertEqual(self.submit(self.profile, labels=[]).status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_valid_batch_is_linked_to_selected_installment(self):
        response = self.submit(self.profile)
        self.assertEqual(response.status_code, 201)
        installment = YatraRegistrationInstallment.objects.get(registration__registered_for=self.profile)
        self.assertEqual(installment.payment.total_amount, Decimal("100.00"))
        self.assertFalse(installment.is_paid)

    def test_paid_installment_cannot_be_replaced(self):
        installment = YatraRegistrationInstallment.objects.get(registration__registered_for=self.profile)
        installment.is_paid = True
        installment.save(update_fields=["is_paid"])
        self.assertEqual(self.submit(self.profile).status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_rejected_proof_can_retry_after_deadline_but_later_payment_is_blocked(self):
        first = YatraRegistrationInstallment.objects.get(registration__registered_for=self.profile)
        self.installment.end_date = date(2026, 1, 1)
        self.installment.save()
        rejected = Payment.objects.create(transaction_id='rejected-old', total_amount='100.00', uploaded_by=self.profile, proof='old.jpg', status='rejected')
        first.payment = rejected
        first.save()
        second = YatraInstallment.objects.create(yatra=self.yatra, label='Second', amount='50.00', order=1)
        YatraRegistrationInstallment.objects.create(registration=first.registration, installment=second)
        response = self.submit(self.profile, amount='50.00', labels=['Second'])
        self.assertEqual(response.status_code, 400)
        response = self.submit(self.profile)
        self.assertEqual(response.status_code, 201)
        first.refresh_from_db()
        self.assertTrue(first.payment.proof)
        self.assertNotEqual(first.payment_id, rejected.pk)
        response = self.submit(self.profile, amount='50.00', labels=['Second'], transaction_id='second-transaction')
        self.assertEqual(response.status_code, 201)

    def test_overdue_later_installment_remains_frozen_after_retry(self):
        first = YatraRegistrationInstallment.objects.get(registration__registered_for=self.profile)
        first.payment = Payment.objects.create(transaction_id='rejected-old', total_amount='100.00', uploaded_by=self.profile, proof='old.jpg', status='rejected')
        first.save()
        second = YatraInstallment.objects.create(yatra=self.yatra, label='Second', amount='50.00', order=1, end_date=date(2026, 1, 1))
        YatraRegistrationInstallment.objects.create(registration=first.registration, installment=second)
        self.assertEqual(self.submit(self.profile).status_code, 201)
        self.assertEqual(self.submit(self.profile, amount='50.00', labels=['Second'], transaction_id='second-transaction').status_code, 400)

    def test_verified_later_installment_stays_verified_after_retry(self):
        first = YatraRegistrationInstallment.objects.get(registration__registered_for=self.profile)
        first.payment = Payment.objects.create(transaction_id='rejected-old', total_amount='100.00', uploaded_by=self.profile, proof='old.jpg', status='rejected')
        first.save()
        second = YatraInstallment.objects.create(yatra=self.yatra, label='Second', amount='50.00', order=1)
        paid = YatraRegistrationInstallment.objects.create(registration=first.registration, installment=second, is_paid=True)
        self.assertEqual(self.submit(self.profile).status_code, 201)
        paid.refresh_from_db()
        self.assertTrue(paid.is_paid)

    def test_fresh_registration_is_created_with_proof_and_never_marked_paid_by_client(self):
        YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).delete()
        response = self.submit(self.profile)
        self.assertEqual(response.status_code, 201)
        record = YatraRegistrationInstallment.objects.get(registration__registered_for=self.profile)
        self.assertTrue(record.payment.proof)
        self.assertFalse(record.is_paid)

    def test_retry_of_successful_checkout_is_idempotent(self):
        first = self.submit(self.profile)
        second = self.submit(self.profile)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['payment_id'], second.data['payment_id'])
        self.assertEqual(Payment.objects.count(), 1)

    def test_failed_payment_rolls_back_new_registration(self):
        YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).delete()
        response = self.submit(self.profile, amount='1.00')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).exists())
        self.assertFalse(Payment.objects.exists())

    def test_failed_proof_upload_rolls_back_registration_and_payment(self):
        first = YatraRegistrationInstallment.objects.get(registration__registered_for=self.profile)
        rejected = Payment.objects.create(transaction_id='rejected-old', total_amount='100.00', uploaded_by=self.profile, proof='old.jpg', status='rejected')
        first.payment = rejected
        first.save()
        self.installment.end_date = date(2026, 1, 1)
        self.installment.save()
        with patch('django.core.files.storage.filesystem.FileSystemStorage._save', side_effect=OSError('storage failed')):
            with self.assertRaises(OSError):
                self.submit(self.profile)
        first.refresh_from_db()
        self.assertEqual(first.payment_id, rejected.pk)
        self.assertEqual(first.payment.status, 'rejected')
        self.assertEqual(Payment.objects.count(), 1)

    def test_storage_failure_rolls_back_registration_and_payment(self):
        YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).delete()
        with patch('django.core.files.storage.filesystem.FileSystemStorage._save', side_effect=OSError('storage failed')):
            with self.assertRaises(OSError):
                self.submit(self.profile)
        self.assertFalse(YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).exists())
        self.assertFalse(Payment.objects.exists())

    def test_batch_failure_rolls_back_every_registration(self):
        YatraRegistration.objects.filter(yatra=self.yatra).delete()
        self.yatra.capacity = 1
        self.yatra.save(update_fields=['capacity'])
        self.other.mentor = self.profile
        self.other.save(update_fields=['mentor'])
        profile_ids = [str(self.profile.pk), str(self.other.pk)]
        response = self.client.post(self.url, {
            'transaction_id': 'batch-transaction', 'total_amount': '200.00',
            'registration_installments': json.dumps([{'profile_id': pid, 'installments': ['First']} for pid in profile_ids]),
            'registrations': json.dumps({pid: {'form_fields': {}, 'installments_selected': ['First']} for pid in profile_ids}),
            'screenshot': SimpleUploadedFile('proof.png', b'proof', content_type='image/png'),
        }, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(YatraRegistration.objects.filter(yatra=self.yatra).exists())
        self.assertFalse(Payment.objects.exists())

    def test_missing_screenshot_cannot_create_registration(self):
        YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).delete()
        response = self.client.post(self.url, {'registrations': '{}', 'registration_installments': '[]'}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).exists())

    def test_closed_registration_cannot_create_registration_or_payment(self):
        YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).delete()
        self.yatra.is_registration_open = False
        self.yatra.save(update_fields=['is_registration_open'])
        response = self.submit(self.profile)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(YatraRegistration.objects.filter(yatra=self.yatra, registered_for=self.profile).exists())
        self.assertFalse(Payment.objects.exists())

    def test_old_payment_endpoint_cannot_create_unfinished_payment(self):
        response = self.client.post(f'/payments/{self.yatra.pk}/batch-payment-proof/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())
