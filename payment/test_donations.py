import base64
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from payment.models import Donation, Payment
from userProfile.models import Profile


class DonationSubmitTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.storage = override_settings(STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                        "OPTIONS": {"location": self.media.name}},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        })
        self.storage.enable()
        self.addCleanup(self.storage.disable)
        self.client = APIClient()
        self.data = {
            "donor_name": "Test Donor", "address": "Test address",
            "mobile": "9876543210", "amount": "3500.00",
            "email": "donor@example.com", "transaction_id": "428317654230",
        }

    def screenshot(self):
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg==")
        return SimpleUploadedFile("proof.png", png, content_type="image/png")

    def test_public_donation_is_saved_with_screenshot(self):
        response = self.client.post("/payments/donations/", {**self.data, "screenshot": self.screenshot()}, format="multipart")
        self.assertEqual(response.status_code, 201)
        donation = Donation.objects.get(pk=response.data["id"])
        self.assertEqual(donation.amount, Decimal("3500.00"))
        self.assertEqual(donation.status, "under_review")
        self.assertTrue(donation.screenshot.storage.exists(donation.screenshot.name))
        self.assertNotIn("email", response.data)

    def test_duplicate_transaction_is_rejected(self):
        self.client.post("/payments/donations/", {**self.data, "screenshot": self.screenshot()}, format="multipart")
        response = self.client.post("/payments/donations/", {**self.data, "screenshot": self.screenshot()}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Donation.objects.count(), 1)

    def test_transaction_used_for_yatra_payment_is_rejected(self):
        user = User.objects.create_user(username="donation-payment-owner")
        profile = Profile.objects.create(user=user, first_name="Member")
        Payment.objects.create(uploaded_by=profile, transaction_id=self.data["transaction_id"],
                               total_amount=3500, status="rejected")

        response = self.client.post("/payments/donations/", {**self.data, "screenshot": self.screenshot()}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertIn("transaction_id", response.data)
        self.assertEqual(Donation.objects.count(), 0)

    def test_missing_or_invalid_image_and_amount_are_rejected(self):
        response = self.client.post("/payments/donations/", {**self.data, "amount": "0"}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Donation.objects.count(), 0)
