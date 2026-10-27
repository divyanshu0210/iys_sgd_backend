"""Application notification emails.

All functions in this module are deliberately fail-silent. Email delivery must
not roll back a successful profile, eligibility, or payment operation.
"""

from django.conf import settings

from helpers.mail import send_template_email


def _email_for(profile):
    user = getattr(profile, "user", None)
    return getattr(user, "email", None) if user else None


def _name(profile):
    return (
        profile.get_full_name()
        if profile and hasattr(profile, "get_full_name")
        else ""
    ) or (
        profile.full_name()
        if profile and hasattr(profile, "full_name")
        else ""
    ) or getattr(getattr(profile, "user", None), "username", "there")


def _send(subject, template_name, context, profile):
    recipient = _email_for(profile)
    if not recipient:
        return
    send_template_email(
        subject=subject,
        template_name=template_name,
        context={
            **context,
            "frontend_url": f"{getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173').rstrip('/')}/",
        },
        recipient=recipient,
        fail_silently=True,
    )


def _profile_image_url(profile):
    picture = getattr(profile, "profile_picture", None)
    if not picture:
        return None
    url = getattr(picture, "url", None)
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    public_base = getattr(settings, "PUBLIC_BACKEND_BASE_URL", "").rstrip("/")
    return f"{public_base}{url}" if public_base else None


def _reviewer_baces(reviewer):
    from django.db.models import Q
    from userProfile.models import Bace

    return list(
        Bace.objects.filter(is_active=True)
        .filter(Q(counsellor=reviewer) | Q(mentors=reviewer))
        .prefetch_related("mentors")
        .distinct()
    )


def _summary_groups_for_reviewer(reviewer, fallback_bace):
    from django.db.models import Q
    from userProfile.models import MentorRequest

    baces = _reviewer_baces(reviewer)
    if fallback_bace and fallback_bace not in baces:
        baces.append(fallback_bace)

    bace_ids = [bace.pk for bace in baces]
    scope = Q(requested_bace_id__in=bace_ids)
    if not bace_ids:
        scope = Q(requested_bace__isnull=True, to_mentor=reviewer)
    pending = MentorRequest.objects.filter(
        scope,
        is_approved=False,
        is_rejected=False,
    ).select_related("from_user__user", "requested_bace").order_by(
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
    reviewers = []
    bace = request_obj.requested_bace
    if bace:
        if bace.counsellor:
            reviewers.append(bace.counsellor)
        reviewers.extend(bace.mentors.all())
    if request_obj.to_mentor:
        reviewers.append(request_obj.to_mentor)

    sent_to = set()
    for reviewer in reviewers:
        recipient = _email_for(reviewer)
        if not recipient or recipient.lower() in sent_to:
            continue
        sent_to.add(recipient.lower())
        groups = _summary_groups_for_reviewer(reviewer, bace)
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


def notify_profile_review_update(request_obj, reviewer_who_acted):
    """Refresh every affected reviewer's queue after a profile is approved."""
    reviewers = []
    bace = request_obj.requested_bace
    if bace:
        if bace.counsellor:
            reviewers.append(bace.counsellor)
        reviewers.extend(bace.mentors.all())
    if request_obj.to_mentor:
        reviewers.append(request_obj.to_mentor)

    accepted_profile = request_obj.from_user
    accepted_name = _name(accepted_profile)
    accepted_profile_data = {
        "name": accepted_name,
        "image_url": _profile_image_url(accepted_profile),
        "initial": accepted_name[:1].upper() or "?",
    }

    sent_to = set()
    for reviewer in reviewers:
        recipient = _email_for(reviewer)
        if not recipient or recipient.lower() in sent_to:
            continue
        sent_to.add(recipient.lower())
        groups = _summary_groups_for_reviewer(reviewer, bace)
        total_pending = sum(len(group["profiles"]) for group in groups)
        _send(
            "Profiles waiting for Verification",
            "profile_verification_request.html",
            {
                "reviewer_name": _name(reviewer),
                "groups": groups,
                "total_pending": total_pending,
                "single_group": groups[0] if len(groups) == 1 else None,
                "accepted_profile": accepted_profile_data,
                "accepted_by": (
                    "You" if reviewer.pk == reviewer_who_acted.pk
                    else _name(reviewer_who_acted)
                ),
            },
            reviewer,
        )


def notify_mentor_request_decision(request_obj, approved, reviewer):
    _send(
        "Profile Verification",
        "profile_verification_result.html",
        {
            "mentee_name": _name(request_obj.from_user),
            "reviewer_name": _name(reviewer),
            "bace_name": (
                request_obj.requested_bace.name
                if request_obj.requested_bace
                else "the selected Bace"
            ),
            "approved": approved,
        },
        request_obj.from_user,
    )


def notify_yatra_approval_request(eligibility):
    """Tell every linked mentor/counsellor that Yatra approval is pending."""
    from django.db.models import Q
    from userProfile.models import Bace

    profile = eligibility.profile
    reviewers = []
    if profile.center:
        baces = Bace.objects.filter(is_active=True).filter(
            Q(name__iexact=profile.center)
            | Q(other_centers__name__iexact=profile.center)
        ).select_related("counsellor").prefetch_related("mentors").distinct()
        for bace in baces:
            if bace.counsellor:
                reviewers.append(bace.counsellor)
            reviewers.extend(bace.mentors.all())

    # Preserve the direct mentor/fallback reviewer for legacy or unmapped data.
    if eligibility.approved_by:
        reviewers.append(eligibility.approved_by)

    sent_to = set()
    for reviewer in reviewers:
        recipient = _email_for(reviewer)
        if not recipient or recipient.lower() in sent_to:
            continue
        sent_to.add(recipient.lower())
        _send(
            "Yatra approval request",
            "yatra_approval_request.html",
            {
                "reviewer_name": _name(reviewer),
                "profile_name": _name(profile),
                "yatra_name": eligibility.yatra.title,
            },
            reviewer,
        )


def notify_yatra_eligibility_decision(eligibility, approved, reviewer):
    _send(
        f"Yatra approval {'confirmed' if approved else 'declined'}",
        "yatra_approval_result.html",
        {
            "profile_name": _name(eligibility.profile),
            "reviewer_name": _name(reviewer),
            "yatra_name": eligibility.yatra.title,
            "approved": approved,
        },
        eligibility.profile,
    )


def notify_payment_submitted(payment):
    _send(
        "Payment proof submitted",
        "payment_submitted.html",
        {
            "profile_name": _name(payment.uploaded_by),
            "transaction_id": payment.transaction_id,
            "amount": payment.total_amount,
        },
        payment.uploaded_by,
    )


def notify_payment_result(payment, approved, reviewer):
    _send(
        "Payment approved" if approved else "Payment rejected",
        "payment_result.html",
        {
            "profile_name": _name(payment.uploaded_by),
            "transaction_id": payment.transaction_id,
            "amount": payment.total_amount,
            "approved": approved,
            "reviewer_name": _name(reviewer),
            "notes": payment.notes,
        },
        payment.uploaded_by,
    )
