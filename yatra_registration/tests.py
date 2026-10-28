from types import SimpleNamespace
from unittest.mock import patch
from datetime import date
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from userProfile.models import Bace, Profile
from yatra.models import RegistrationPolicy, Yatra, YatraInstallment
from yatra_registration.models import YatraEligibility, YatraRegistration, YatraRegistrationInstallment
from yatra_registration.notifications import notify_yatra_approval_update


class YatraReviewerBatchNotificationTests(SimpleTestCase):
    @patch("yatra_registration.notifications._send_yatra_review_email")
    @patch("yatra_registration.notifications._yatra_reviewers")
    def test_batch_is_grouped_by_reviewer(self, find_reviewers, send_email):
        def reviewer(email):
            return SimpleNamespace(user=SimpleNamespace(email=email))

        mayapur = reviewer("mayapur@example.com")
        vrindavan = reviewer("vrindavan@example.com")
        shared = reviewer("shared@example.com")
        first = SimpleNamespace(profile_id=1, profile=SimpleNamespace(pk=1))
        second = SimpleNamespace(profile_id=2, profile=SimpleNamespace(pk=2))
        find_reviewers.side_effect = [
            [mayapur, shared, shared],
            [vrindavan, shared],
        ]

        notify_yatra_approval_update([first, second], shared, approved=False)

        self.assertEqual(send_email.call_count, 3)
        groups = {
            call.args[1][0].user.email: [p.pk for p in call.kwargs["approved_profiles"]]
            for call in send_email.call_args_list
        }
        self.assertEqual(groups, {
            "mayapur@example.com": [1],
            "vrindavan@example.com": [2],
            "shared@example.com": [1, 2],
        })
        for call in send_email.call_args_list:
            self.assertEqual(call.kwargs["approval_outcome"], "rejected")


class YatraEligibilityDecisionTests(TestCase):
    def setUp(self):
        reviewer_user = User.objects.create_user(username="yatra-reviewer", email="reviewer@example.com")
        profile_user = User.objects.create_user(username="yatra-member", email="member@example.com")
        self.reviewer = Profile.objects.create(user=reviewer_user, first_name="Reviewer")
        self.profile = Profile.objects.create(
            user=profile_user, first_name="Member", center="Origin Test Bace",
            mentor=self.reviewer, profile_verification_status="verified",
        )
        Bace.objects.create(name="Origin Test Bace", counsellor=self.reviewer)
        self.yatra = Yatra.objects.create(
            title="Test Yatra", description="Test", start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 2), location="Test", capacity=50,
        )
        self.url = f"/yatras/{self.yatra.pk}/eligibility/"
        self.client = APIClient()

    def act(self, actor, action):
        self.client.force_authenticate(actor.user)
        return self.client.post(self.url, {
            "profile_ids": [str(self.profile.pk)], "action": action,
        }, format="json")

    @patch("yatra_registration.views.notify_yatra_approval_update")
    @patch("yatra_registration.views.notify_yatra_eligibility_decision")
    def test_preapproval_is_silent_but_unapproval_notifies(self, user_mail, reviewer_mail):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.act(self.reviewer, "approve")
        self.assertEqual(response.status_code, 200)
        user_mail.assert_not_called()
        reviewer_mail.assert_not_called()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.act(self.reviewer, "unapprove")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(YatraEligibility.objects.filter(yatra=self.yatra, profile=self.profile).exists())
        user_mail.assert_called_once()
        reviewer_mail.assert_called_once()

    @patch("yatra_registration.views.notify_yatra_approval_request")
    @patch("yatra_registration.views.notify_yatra_approval_update")
    @patch("yatra_registration.views.notify_yatra_eligibility_decision")
    def test_user_request_approval_and_unapproval_notify(self, user_mail, reviewer_mail, request_mail):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.act(self.profile, "request_approval")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(YatraEligibility.objects.filter(yatra=self.yatra, profile=self.profile, is_approved=False).exists())
        request_mail.assert_called_once()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.act(self.reviewer, "approve")
        self.assertEqual(response.status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.act(self.reviewer, "unapprove")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(user_mail.call_count, 2)
        self.assertEqual(reviewer_mail.call_count, 2)

    @patch("yatra_registration.views.notify_yatra_approval_update")
    @patch("yatra_registration.views.notify_yatra_eligibility_decision")
    def test_existing_approval_unapproval_notifies(self, user_mail, reviewer_mail):
        YatraEligibility.objects.create(yatra=self.yatra, profile=self.profile, approved_by=self.reviewer, is_approved=True)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.act(self.reviewer, "unapprove")
        self.assertEqual(response.status_code, 200)
        user_mail.assert_called_once()
        reviewer_mail.assert_called_once()

    def test_unapprove_without_eligibility_does_not_create_one(self):
        response = self.act(self.reviewer, "unapprove")
        self.assertEqual(response.status_code, 400)
        self.assertIn("has no eligibility record", response.data["errors"][0])
        self.assertFalse(YatraEligibility.objects.filter(yatra=self.yatra, profile=self.profile).exists())


class RegistrationSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="registration-owner")
        self.other_user = User.objects.create_user(username="registration-other")
        self.profile = Profile.objects.create(user=self.user, first_name="Owner", profile_verification_status="verified")
        self.other = Profile.objects.create(user=self.other_user, first_name="Other", profile_verification_status="verified")
        self.yatra = Yatra.objects.create(
            title="Security Yatra", description="Test", start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 2), location="Test", capacity=2,
        )
        RegistrationPolicy.objects.create(yatra=self.yatra, requires_approval=False)
        self.installment = YatraInstallment.objects.create(yatra=self.yatra, label="First", amount="100.00")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/yatras/{self.yatra.pk}/register/"

    def payload(self, profile):
        return {str(profile.pk): {
            "form_fields": {}, "installments_selected": ["First"],
            "installments_details": [{"label": "First", "is_paid": True}],
        }}

    def test_client_cannot_mark_installment_paid(self):
        response = self.client.post(self.url, self.payload(self.profile), format="json")
        self.assertEqual(response.status_code, 200)
        installment = YatraRegistrationInstallment.objects.get(registration__registered_for=self.profile)
        self.assertFalse(installment.is_paid)
        self.assertIsNone(installment.verified_by)

    def test_open_yatra_does_not_allow_registering_unrelated_profile(self):
        response = self.client.post(self.url, self.payload(self.other), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(YatraRegistration.objects.filter(registered_for=self.other).exists())

    def test_registration_details_are_not_visible_to_unrelated_user(self):
        YatraRegistration.objects.create(yatra=self.yatra, registered_for=self.other, registered_by=self.other, form_data={"private": "value"})
        response = self.client.get(f"/yatras/{self.yatra.pk}/{self.other.pk}/registrations/")
        self.assertEqual(response.status_code, 403)

    def test_current_mentor_can_view_scoped_registration(self):
        self.other.mentor = self.profile
        self.other.save(update_fields=["mentor"])
        YatraRegistration.objects.create(yatra=self.yatra, registered_for=self.other, registered_by=self.other)
        response = self.client.get(f"/yatras/{self.yatra.pk}/{self.other.pk}/registrations/")
        self.assertEqual(response.status_code, 200)

    def test_closed_or_full_yatra_rejects_new_registration(self):
        self.yatra.is_registration_open = False
        self.yatra.save(update_fields=["is_registration_open"])
        self.assertEqual(self.client.post(self.url, self.payload(self.profile), format="json").status_code, 400)
        self.yatra.is_registration_open = True
        self.yatra.capacity = 0
        self.yatra.save(update_fields=["is_registration_open", "capacity"])
        self.assertEqual(self.client.post(self.url, self.payload(self.profile), format="json").status_code, 400)

    def test_cancellation_flag_is_enforced(self):
        YatraRegistration.objects.create(yatra=self.yatra, registered_for=self.profile, registered_by=self.profile)
        response = self.client.delete(self.url, {"profile_id": str(self.profile.pk)}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(YatraRegistration.objects.filter(registered_for=self.profile).exists())

