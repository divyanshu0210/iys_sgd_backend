from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

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
