"""Profile verification notifications."""

from helpers.notifications import _email_for, _name, _profile_image_url, _send


def _summary_groups_for_reviewer(reviewer):
    from userProfile.models import MentorRequest
    from userProfile.scopes import reviewer_request_scope

    pending = MentorRequest.objects.filter(
        reviewer_request_scope(reviewer),
        is_approved=False,
        is_rejected=False,
    ).select_related("from_user__user", "requested_bace").distinct().order_by(
        "requested_bace__name", "created_at"
    )

    groups = {}
    for request_obj in pending:
        bace = request_obj.requested_bace
        label = bace.name if bace else "Pending profiles"
        if label.casefold() == "others":
            label = "Other centers"
        group = groups.setdefault(label, {"name": label, "profiles": []})
        profile = request_obj.from_user
        display_name = _name(profile)
        group["profiles"].append({
            "name": display_name,
            "image_url": _profile_image_url(profile),
            "initial": display_name[:1].upper() or "?",
        })

    result = list(groups.values())
    for group in result:
        group["visible_profiles"] = group["profiles"][:2]
        group["remaining_count"] = max(0, len(group["profiles"]) - 2)
    return result


def notify_new_profile_request(request_obj):
    """Send each eligible reviewer a summary of their pending profiles."""
    from userProfile.scopes import reviewers_for_profile

    reviewers = reviewers_for_profile(request_obj.from_user)

    sent_to = set()
    for reviewer in reviewers:
        recipient = _email_for(reviewer)
        if not recipient or recipient.lower() in sent_to:
            continue
        sent_to.add(recipient.lower())
        groups = _summary_groups_for_reviewer(reviewer)
        total_pending = sum(len(group["profiles"]) for group in groups)
        if not total_pending:
            continue
        _send(
            "Profiles waiting for Verification",
            "profile_verification_request.html",
            {
                "reviewer_name": _name(reviewer),
                "groups": groups,
                "total_pending": total_pending,
                "single_group": groups[0] if len(groups) == 1 else None,
            },
            reviewer,
        )


def notify_profile_review_batch(requests, reviewer_who_acted, approved, review_recipients=None):
    """Send one scoped decision summary to each affected reviewer."""
    from userProfile.scopes import reviewers_for_profile

    recipients = {}
    for request_obj in requests:
        reviewers = (
            review_recipients[request_obj.pk]
            if review_recipients is not None
            else reviewers_for_profile(request_obj.from_user)
        )
        for reviewer in reviewers:
            email = _email_for(reviewer)
            if not email:
                continue
            group = recipients.setdefault(email.lower(), {"reviewer": reviewer, "profiles": {}})
            profile = request_obj.from_user
            name = _name(profile)
            group["profiles"][profile.pk] = {
                "name": name,
                "image_url": _profile_image_url(profile),
                "initial": name[:1].upper() or "?",
            }

    for recipient in recipients.values():
        reviewer = recipient["reviewer"]
        groups = _summary_groups_for_reviewer(reviewer)
        total_pending = sum(len(group["profiles"]) for group in groups)
        _send(
            "Profiles waiting for Verification",
            "profile_verification_request.html",
            {
                "reviewer_name": _name(reviewer),
                "groups": groups,
                "total_pending": total_pending,
                "single_group": groups[0] if len(groups) == 1 else None,
                "accepted_profiles": list(recipient["profiles"].values()),
                "review_outcome": "accepted" if approved else "rejected",
                "reviewed_by": (
                    "You" if reviewer.pk == reviewer_who_acted.pk
                    else _name(reviewer_who_acted)
                ),
            },
            reviewer,
        )


def notify_mentor_request_decision(request_obj, approved, reviewer):
    from userProfile.utils import resolve_bace_for_center

    bace = resolve_bace_for_center(request_obj.from_user.center) if approved else None
    _send(
        "Profile Verification",
        "profile_verification_result.html",
        {
            "mentee_name": _name(request_obj.from_user),
            "reviewer_name": _name(reviewer),
            "bace_name": (
                bace.name
                if bace
                else "the selected Bace" if approved else None
            ),
            "approved": approved,
        },
        request_obj.from_user,
    )


