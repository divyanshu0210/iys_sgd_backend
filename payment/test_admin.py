from datetime import timedelta
from unittest import skipUnless
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from payment.models import Payment
from userProfile.models import Profile
from yatra.models import Yatra, YatraInstallment
from yatra_registration.models import YatraEligibility, YatraRegistration, YatraRegistrationInstallment
from yatra_substitution.models import SubstitutionRequest


@skipUnless(apps.is_installed("django.contrib.admin"), "Requires admin settings")
class PaymentAdminShowAllTests(TestCase):
    def setUp(self):
        user = User.objects.create_superuser("payment-admin", "admin@example.com", "password")
        self.client.force_login(user)
        profile, _ = Profile.objects.get_or_create(user=user)
        today = timezone.localdate()
        for title, closed in (("Active", False), ("Past", True)):
            yatra = Yatra.objects.create(
                title=title, description="Test", location="Test", capacity=5,
                start_date=today, end_date=today + timedelta(days=1), close_yatra=closed,
            )
            registration = YatraRegistration.objects.create(yatra=yatra, registered_by=profile, registered_for=profile)
            YatraEligibility.objects.create(yatra=yatra, profile=profile, approved_by=profile, is_approved=True)
            SubstitutionRequest.objects.create(registration=registration, initiator=profile, target_profile=profile, two_digit_code="123456")
            installment = YatraInstallment.objects.create(yatra=yatra, label="Payment", amount=100)
            payment = Payment.objects.create(uploaded_by=profile, transaction_id=title, total_amount=100, status="rejected")
            YatraRegistrationInstallment.objects.create(registration=registration, installment=installment, payment=payment)
        self.url = reverse("admin:payment_payment_changelist")

    def test_show_all_is_preserved_when_filtering_and_paginating(self):
        self.assertEqual(self.client.get(self.url).context["cl"].result_count, 1)
        response = self.client.get(self.url, {"show_all": "1"})
        self.assertEqual(response.context["cl"].result_count, 2)
        filter_url = response.context["cl"].get_query_string({"status__exact": "rejected"})
        self.assertIn("show_all=1", filter_url)
        filtered = self.client.get(self.url + filter_url)
        self.assertEqual(filtered.context["cl"].result_count, 2)
        self.assertContains(filtered, "Show active Yatras only")
        self.assertIn("show_all=1", filtered.context["cl"].get_query_string({"p": 2}))

    def test_image_proof_has_hover_preview_and_other_files_keep_link(self):
        from django.contrib import admin
        from payment.admin import PaymentAdmin

        payment_admin = PaymentAdmin(Payment, admin.site)
        image = SimpleNamespace(proof=SimpleNamespace(name='payment_proofs/test.PNG', url='https://example.com/test.PNG'))
        preview = payment_admin.proof_preview(image)
        self.assertIn('payment-proof-preview__image', preview)
        self.assertIn('https://example.com/test.PNG', preview)
        self.assertIn('loading="lazy"', preview)
        document = SimpleNamespace(proof=SimpleNamespace(name='payment_proofs/test.pdf', url='https://example.com/test.pdf'))
        self.assertIn('test.pdf', payment_admin.proof_preview(document))
        self.assertNotIn('<img', payment_admin.proof_preview(document))
        self.assertEqual(payment_admin.proof_preview(SimpleNamespace(proof=None)), '—')
        self.assertContains(self.client.get(self.url), 'payment/css/proof_preview.css')

    def test_show_all_toggle_preserves_existing_filter(self):
        response = self.client.get(self.url, {"status__exact": "rejected"})
        self.assertContains(response, 'name="status__exact" value="rejected"')

    def test_show_all_persists_in_other_yatra_admins(self):
        cases = (
            ("admin:yatra_registration_yatraregistration_changelist", "status__exact", "pending"),
            ("admin:yatra_registration_yatraeligibility_changelist", "is_approved__exact", "1"),
            ("admin:yatra_substitution_substitutionrequest_changelist", "created_at__isnull", "False"),
        )
        for url_name, filter_name, filter_value in cases:
            with self.subTest(admin=url_name):
                url = reverse(url_name)
                self.assertEqual(self.client.get(url).context["cl"].result_count, 1)
                response = self.client.get(url, {"show_all": "1"})
                self.assertEqual(response.context["cl"].result_count, 2)
                filter_url = response.context["cl"].get_query_string({filter_name: filter_value})
                self.assertIn("show_all=1", filter_url)
                filtered = self.client.get(url + filter_url)
                self.assertEqual(filtered.status_code, 200)
                self.assertEqual(filtered.context["cl"].result_count, 2)
                self.assertContains(filtered, "Show active Yatras only")
                self.assertIn("show_all=1", filtered.context["cl"].get_query_string({"p": 2}))

    def test_registration_toolbar_shows_actions_for_selected_yatra(self):
        yatra = Yatra.objects.get(title="Active")
        url = reverse("admin:yatra_registration_yatraregistration_changelist")
        response = self.client.get(url, {"yatra": str(yatra.pk)})
        self.assertContains(response, "Show All")
        self.assertContains(response, "Export All Data as Excel")
        self.assertContains(response, "Manage Travel &amp; Accommodation")
        self.assertContains(response, reverse("admin:yatra_registration_bulk_edit", args=[yatra.pk]))
        self.assertNotContains(self.client.get(url), "Manage Travel &amp; Accommodation")
        self.assertNotContains(self.client.get(self.url), "Manage Travel &amp; Accommodation")
