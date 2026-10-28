from unittest.mock import patch
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from userProfile.notifications import _summary_groups_for_reviewer, notify_profile_review_batch
from userProfile.models import Bace, MentorRequest, OtherCenter, Profile
from userProfile.scopes import profiles_for_reviewer, reviewer_request_scope, reviewers_for_profile


class ProfileReviewBatchTests(TestCase):
    def setUp(self):
        def profile(username):
            user = User.objects.create_user(username=username, email=f"{username}@example.com")
            return Profile.objects.create(user=user, first_name=username)

        self.reviewer = profile("reviewer")
        self.first_counsellor = profile("counsellor_a")
        self.second_counsellor = profile("counsellor_b")
        self.first_bace = Bace.objects.create(name="Test A", counsellor=self.first_counsellor)
        self.second_bace = Bace.objects.create(name="Test B", counsellor=self.second_counsellor)
        self.first_bace.mentors.add(self.reviewer)
        self.second_bace.mentors.add(self.reviewer)
        self.first = profile("first")
        self.second = profile("second")
        self.first.center = self.first_bace.name
        self.first.save(update_fields=["center"])
        self.second.center = self.second_bace.name
        self.second.save(update_fields=["center"])
        self.requests = [
            MentorRequest.objects.create(from_user=self.first, to_mentor=self.first_counsellor, requested_bace=self.first_bace),
            MentorRequest.objects.create(from_user=self.second, to_mentor=self.second_counsellor, requested_bace=self.second_bace),
        ]

    def test_email_summary_uses_the_same_scope_as_review_page(self):
        groups = _summary_groups_for_reviewer(self.first_counsellor)
        self.assertEqual([p["name"] for group in groups for p in group["profiles"]], ["first"])
        self.assertEqual(sum(len(group["profiles"]) for group in _summary_groups_for_reviewer(self.reviewer)), 2)

    def test_yatra_scope_only_includes_verified_profiles(self):
        for request in self.requests:
            request.is_approved = True
            request.save(update_fields=["is_approved"])
        self.first.profile_verification_status = "verified"
        self.first.save(update_fields=["profile_verification_status"])
        self.second.profile_verification_status = "pending"
        self.second.save(update_fields=["profile_verification_status"])
        self.assertEqual(list(profiles_for_reviewer(self.reviewer)), [self.first.pk])
        self.assertEqual(list(profiles_for_reviewer(self.second_counsellor)), [])

    def test_current_center_and_mentor_control_access_not_old_request(self):
        self.first.center = self.second_bace.name.lower()
        self.first.mentor = self.reviewer
        self.first.profile_verification_status = "verified"
        self.first.save(update_fields=["center", "mentor", "profile_verification_status"])
        self.assertFalse(MentorRequest.objects.filter(reviewer_request_scope(self.first_counsellor), pk=self.requests[0].pk).exists())
        self.assertTrue(MentorRequest.objects.filter(reviewer_request_scope(self.second_counsellor), pk=self.requests[0].pk).exists())
        self.assertTrue(profiles_for_reviewer(self.reviewer).filter(pk=self.first.pk).exists())
        self.assertEqual(set(reviewers_for_profile(self.first).values_list("pk", flat=True)), {self.second_counsellor.pk, self.reviewer.pk})

    def test_verified_profile_without_request_is_visible_to_current_mentor(self):
        self.requests[0].delete()
        self.first.center = None
        self.first.mentor = self.reviewer
        self.first.profile_verification_status = "verified"
        self.first.save(update_fields=["center", "mentor", "profile_verification_status"])
        self.assertTrue(profiles_for_reviewer(self.reviewer).filter(pk=self.first.pk).exists())
        self.assertEqual(list(reviewers_for_profile(self.first).values_list("pk", flat=True)), [self.reviewer.pk])

    @patch("userProfile.views.notify_profile_review_batch")
    @patch("userProfile.views.notify_mentor_request_decision")
    def test_current_bace_can_approve_old_request_and_becomes_counsellor(self, user_mail, reviewer_mail):
        self.first.center = self.second_bace.name
        self.first.save(update_fields=["center"])
        client = APIClient()
        client.force_authenticate(self.second_counsellor.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post("/api/mentor/requests/", {
                "request_ids": [str(self.requests[0].pk)], "action": "connect",
            }, format="json")
        self.assertEqual(response.status_code, 200)
        self.first.refresh_from_db()
        self.assertEqual(self.first.mentor, self.second_counsellor)
        self.assertEqual(user_mail.call_count, 1)
        self.assertEqual(reviewer_mail.call_count, 1)

    def test_others_and_alias_are_consistent_for_lists_and_recipients(self):
        others, _ = Bace.objects.get_or_create(name="Others")
        others.counsellor = self.first_counsellor
        others.is_active = True
        others.save(update_fields=["counsellor", "is_active"])
        OtherCenter.objects.create(name="External Center", bace=self.second_bace)
        self.first.center = "unlisted center"
        self.first.profile_verification_status = "verified"
        self.first.save(update_fields=["center", "profile_verification_status"])
        self.assertTrue(profiles_for_reviewer(self.first_counsellor).filter(pk=self.first.pk).exists())
        self.assertTrue(reviewers_for_profile(self.first).filter(pk=self.first_counsellor.pk).exists())
        self.first.center = "external center"
        self.first.save(update_fields=["center"])
        self.assertFalse(profiles_for_reviewer(self.first_counsellor).filter(pk=self.first.pk).exists())
        self.assertTrue(profiles_for_reviewer(self.second_counsellor).filter(pk=self.first.pk).exists())
        self.assertTrue(reviewers_for_profile(self.first).filter(pk=self.second_counsellor.pk).exists())

    @patch("userProfile.notifications._send")
    def test_batch_summary_groups_profiles_by_reviewer(self, send):
        notify_profile_review_batch(self.requests, self.reviewer, True)
        summaries = {
            call.args[3].user.username: [p["name"] for p in call.args[2]["accepted_profiles"]]
            for call in send.call_args_list
        }
        self.assertEqual(summaries, {
            "counsellor_a": ["first"],
            "counsellor_b": ["second"],
            "reviewer": ["first", "second"],
        })

    @patch("userProfile.views.notify_profile_review_batch")
    @patch("userProfile.views.notify_mentor_request_decision")
    def test_batch_approves_together_and_schedules_notifications(self, user_mail, reviewer_mail):
        client = APIClient()
        client.force_authenticate(self.reviewer.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post("/api/mentor/requests/", {
                "request_ids": [str(req.pk) for req in self.requests], "action": "connect",
            }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(user_mail.call_count, 2)
        self.assertEqual(reviewer_mail.call_count, 1)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.mentor, self.first_counsellor)
        self.assertEqual(self.second.mentor, self.second_counsellor)

    def test_batch_rejects_unavailable_requests_without_changing_any(self):
        client = APIClient()
        client.force_authenticate(self.reviewer.user)
        self.requests[1].is_rejected = True
        self.requests[1].save(update_fields=["is_rejected"])
        response = client.post("/api/mentor/requests/", {
            "request_ids": [str(req.pk) for req in self.requests], "action": "connect",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.requests[0].refresh_from_db()
        self.assertFalse(self.requests[0].is_approved)

    @patch("userProfile.views.notify_profile_review_batch")
    @patch("userProfile.views.notify_mentor_request_decision")
    def test_batch_rejections_schedule_notifications(self, user_mail, reviewer_mail):
        client = APIClient()
        client.force_authenticate(self.reviewer.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post("/api/mentor/requests/", {
                "request_ids": [str(req.pk) for req in self.requests], "action": "reject",
            }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(user_mail.call_count, 2)
        self.assertEqual(reviewer_mail.call_count, 1)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.profile_verification_status, "rejected")
        self.assertEqual(self.second.profile_verification_status, "rejected")


class ProfilePictureReplacementTests(TestCase):
    def setUp(self):
        self.storage = InMemoryStorage()
        field = Profile._meta.get_field("profile_picture")
        self.storage_patch = patch.object(field, "storage", self.storage)
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        user = User.objects.create_user(username="photo-user")
        self.profile = Profile.objects.create(
            user=user, center="Photo Test Bace", profile_verification_status="verified",
        )
        Bace.objects.create(name="Photo Test Bace")
        image = BytesIO()
        Image.new("RGB", (2, 2), color="red").save(image, format="PNG")
        self.image_bytes = image.getvalue()
        self.profile.profile_picture.save("photo.png", ContentFile(self.image_bytes), save=True)
        self.old_name = self.profile.profile_picture.name
        self.client = APIClient()
        self.client.force_authenticate(user)

    def upload(self, content=None):
        return self.client.post("/api/profile/", {
            "profile_picture": SimpleUploadedFile(
                "photo.png", self.image_bytes if content is None else content,
                content_type="image/png",
            ),
        }, format="multipart")

    def test_replacement_deletes_old_file_after_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertNotEqual(self.old_name, self.profile.profile_picture.name)
        self.assertTrue(self.storage.exists(self.old_name))
        self.assertTrue(self.storage.exists(self.profile.profile_picture.name))
        for callback in callbacks:
            callback()
        self.assertFalse(self.storage.exists(self.old_name))
        self.assertTrue(self.storage.exists(self.profile.profile_picture.name))

    def test_invalid_upload_keeps_old_file(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.upload(b"not an image")
        self.assertEqual(response.status_code, 400)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_picture.name, self.old_name)
        self.assertTrue(self.storage.exists(self.old_name))

    def test_shared_old_file_is_not_deleted(self):
        other_user = User.objects.create_user(username="other-photo-user")
        Profile.objects.create(user=other_user, profile_picture=self.old_name)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.storage.exists(self.old_name))
