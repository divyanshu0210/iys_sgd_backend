from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from django.template.loader import render_to_string
from unittest.mock import patch

from payment.models import Payment
from userProfile.models import Profile
from yatra.models import Yatra, YatraInstallment
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
        self.user = User.objects.create_user(username="payment-owner")
        other_user = User.objects.create_user(username="payment-other")
        self.profile = Profile.objects.create(user=self.user, profile_verification_status="verified")
        self.other = Profile.objects.create(user=other_user, profile_verification_status="verified")
        self.yatra = Yatra.objects.create(
            title="Payment Yatra", description="Test", start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 2), location="Test", capacity=5,
        )
        self.installment = YatraInstallment.objects.create(yatra=self.yatra, label="First", amount="100.00")
        for profile in (self.profile, self.other):
            registration = YatraRegistration.objects.create(yatra=self.yatra, registered_for=profile, registered_by=profile)
            YatraRegistrationInstallment.objects.create(registration=registration, installment=self.installment)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/payments/{self.yatra.pk}/batch-payment-proof/"

    def submit(self, profile, amount="100.00", labels=None):
        return self.client.post(self.url, {
            "transaction_id": "transaction-1", "total_amount": amount,
            "registration_installments": [{"profile_id": str(profile.pk), "installments": labels if labels is not None else ["First"]}],
        }, format="json")

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
