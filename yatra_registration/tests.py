from types import SimpleNamespace
from unittest.mock import patch
from datetime import date
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from userProfile.models import Bace, Profile
from yatra.models import Yatra
from yatra_registration.models import YatraEligibility
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

