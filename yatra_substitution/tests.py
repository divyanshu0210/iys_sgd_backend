from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from userProfile.models import Profile
from yatra.models import Yatra, YatraInstallment
from yatra_registration.models import YatraEligibility, YatraRegistration, YatraRegistrationInstallment
from yatra_substitution.models import SubstitutionRequest


class SubstitutionSecurityTests(TestCase):
    def setUp(self):
        source_user = User.objects.create_user(username="sub-source")
        target_user = User.objects.create_user(username="sub-target")
        self.source = Profile.objects.create(user=source_user, profile_verification_status="verified")
        self.target = Profile.objects.create(user=target_user, profile_verification_status="verified")
        self.yatra = Yatra.objects.create(
            title="Substitution Yatra", description="Test", start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 2), location="Test", capacity=10, is_substitution_open=True,
        )
        self.registration = YatraRegistration.objects.create(
            yatra=self.yatra, registered_for=self.source, registered_by=self.source, status="paid",
        )
        installment = YatraInstallment.objects.create(yatra=self.yatra, label="First", amount="100.00")
        YatraRegistrationInstallment.objects.create(
            registration=self.registration, installment=installment, is_paid=True, verified_by=self.source,
        )
        YatraEligibility.objects.create(yatra=self.yatra, profile=self.target, approved_by=self.source, is_approved=True)
        self.client = APIClient()

    def make_request(self, code="123456"):
        return SubstitutionRequest.objects.create(
            registration=self.registration, initiator=self.source, target_profile=self.target,
            two_digit_code=code, expires_at=timezone.now() + timedelta(minutes=30),
        )

    def test_code_is_hidden_from_target_and_guess_attempts_are_bounded(self):
        sub = self.make_request()
        self.client.force_authenticate(self.target.user)
        response = self.client.get("/yatra-transfers/substitution_requests/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("two_digit_code", response.data[0])
        url = f"/yatra-transfers/substitution_requests/{sub.pk}/respond/"
        for _ in range(5):
            self.assertEqual(self.client.post(url, {"action": "accept", "code": "000000"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"action": "accept", "code": "123456"}, format="json").status_code, 429)
        sub.refresh_from_db()
        self.assertEqual(sub.failed_code_attempts, 5)

    @patch("yatra_substitution.views.secrets.randbelow", return_value=42)
    def test_new_code_is_six_digits_and_substitution_flag_is_enforced(self, random_code):
        self.target.member_id = 987654
        self.target.save(update_fields=["member_id"])
        self.client.force_authenticate(self.source.user)
        url = f"/yatra-transfers/registrations/{self.registration.pk}/substitute/"
        self.yatra.is_substitution_open = False
        self.yatra.save(update_fields=["is_substitution_open"])
        self.assertEqual(self.client.post(url, {"target_profile_id": self.target.member_id}, format="json").status_code, 400)
        self.yatra.is_substitution_open = True
        self.yatra.save(update_fields=["is_substitution_open"])
        response = self.client.post(url, {"target_profile_id": self.target.member_id}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["two_digit_code"], "000042")

    def test_legacy_two_digit_code_still_works(self):
        sub = self.make_request("42")
        self.client.force_authenticate(self.target.user)
        response = self.client.post(
            f"/yatra-transfers/substitution_requests/{sub.pk}/respond/",
            {"action": "accept", "code": "42"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
