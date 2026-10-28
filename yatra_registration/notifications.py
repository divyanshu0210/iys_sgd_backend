"""Yatra approval notifications."""

from helpers.notifications import _email_for, _name, _profile_image_url, _send, _yatra_frontend_url


def _yatra_reviewers(eligibility):
    """Return the linked counsellors/mentors who review this profile's Yatra."""
    from userProfile.scopes import reviewers_for_profile

    if eligibility.profile.profile_verification_status != "verified":
        return []
    return reviewers_for_profile(eligibility.profile)


def _send_yatra_review_email(
    eligibility,
    reviewers,
    approved_profile=None,
    approved_profiles=None,
    reviewer_who_acted=None,
    approval_outcome="approved",
):
    from yatra_registration.models import YatraEligibility

    from userProfile.scopes import profiles_for_reviewer

    yatra_name = eligibility.yatra.title
    subject = f"{yatra_name}: Yatra Approval"
    profile_list = approved_profiles or ([approved_profile] if approved_profile else [])
    profile_rows = [
        {
            "name": _name(profile),
            "image_url": _profile_image_url(profile),
            "initial": (_name(profile)[:1] or "?").upper(),
        }
        for profile in profile_list
    ]

    sent_to = set()
    for reviewer in reviewers:
        recipient = _email_for(reviewer)
        if not recipient or recipient.lower() in sent_to:
            continue
        sent_to.add(recipient.lower())

        # Keep the email count consistent with the profiles visible to this
        # reviewer in the Yatra approval page.
        reviewer_profile_ids = profiles_for_reviewer(reviewer)
        pending_count = YatraEligibility.objects.filter(
            yatra_id=eligibility.yatra_id,
            profile_id__in=reviewer_profile_ids,
            is_approved=False,
        ).count()

        _send(
            subject,
            "yatra_approval_review.html",
            {
                "reviewer_name": _name(reviewer),
                "yatra_name": yatra_name,
                "pending_count": pending_count,
                "frontend_url": _yatra_frontend_url(eligibility.yatra_id),
                "approved_profiles": profile_rows,
                "approved_profile_name": (
                    _name(approved_profile) if approved_profile else None
                ),
                "approval_outcome": approval_outcome,
                "approved_by": (
                    "You"
                    if reviewer_who_acted and reviewer.pk == reviewer_who_acted.pk
                    else _name(reviewer_who_acted)
                    if reviewer_who_acted
                    else None
                ),
            },
            reviewer,
        )


def notify_yatra_approval_request(eligibility):
    """Tell every linked mentor/counsellor that a Yatra approval was requested."""
    _send_yatra_review_email(eligibility, _yatra_reviewers(eligibility))


def notify_yatra_approval_update(eligibilities, reviewer, approved=True):
    """Send each linked reviewer only their profiles from this decision batch."""
    recipients = {}
    for eligibility in eligibilities:
        for recipient in _yatra_reviewers(eligibility):
            email = _email_for(recipient)
            if not email:
                continue
            group = recipients.setdefault(
                email.lower(),
                {"reviewer": recipient, "eligibility": eligibility, "profiles": {}},
            )
            group["profiles"][eligibility.profile_id] = eligibility.profile

    for group in recipients.values():
        _send_yatra_review_email(
            group["eligibility"],
            [group["reviewer"]],
            approved_profiles=list(group["profiles"].values()),
            reviewer_who_acted=reviewer,
            approval_outcome="approved" if approved else "rejected",
        )


def notify_yatra_eligibility_decision(eligibility, approved, reviewer, withdrawn=False):
    decision = "rejected" if withdrawn else "confirmed" if approved else "declined"
    _send(
        f"Yatra approval {decision}",
        "yatra_approval_result.html",
        {
            "profile_name": _name(eligibility.profile),
            "reviewer_name": _name(reviewer),
            "yatra_name": eligibility.yatra.title,
            "approved": approved,
            "withdrawn": withdrawn,
            "frontend_url": _yatra_frontend_url(eligibility.yatra_id),
        },
        eligibility.profile,
    )


