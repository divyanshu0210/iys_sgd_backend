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


def _yatra_reviewers(eligibility):
    """Return the linked counsellors/mentors who review this profile's Yatra."""
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

    return reviewers


def _send_yatra_review_email(eligibility, reviewers, approved_profile=None, reviewer_who_acted=None):
    from yatra_registration.models import YatraEligibility

    pending_count = YatraEligibility.objects.filter(
        yatra_id=eligibility.yatra_id,
        is_approved=False,
    ).count()
    yatra_name = eligibility.yatra.title
    subject = f"{yatra_name}: Yatra Approval"

    sent_to = set()
    for reviewer in reviewers:
        recipient = _email_for(reviewer)
        if not recipient or recipient.lower() in sent_to:
            continue
        sent_to.add(recipient.lower())
        _send(
            subject,
            "yatra_approval_review.html",
            {
                "reviewer_name": _name(reviewer),
                "yatra_name": yatra_name,
                "pending_count": pending_count,
                "approved_profile_name": (
                    _name(approved_profile) if approved_profile else None
                ),
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


def notify_yatra_approval_update(eligibility, reviewer):
    """Refresh every linked reviewer's Yatra approval queue after approval."""
    _send_yatra_review_email(
        eligibility,
        _yatra_reviewers(eligibility),
        approved_profile=eligibility.profile,
        reviewer_who_acted=reviewer,
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
    yatra_name = _payment_yatra_name(payment)
    payment_rows = _payment_status_rows(payment)
    _send(
        f"{yatra_name}: Payment",
        "payment_status.html",
        {
            "profile_name": _name(payment.uploaded_by),
            "yatra_name": yatra_name,
            "transaction_id": payment.transaction_id,
            "amount": payment.total_amount,
            "status": "Submitted for review",
            "notes": None,
            "payment_rows": payment_rows,
            "next_step": _payment_next_step("Submitted for review", payment_rows),
        },
        payment.uploaded_by,
    )


def _payment_yatra_name(payment):
    installment = payment.installments.select_related(
        "registration__yatra"
    ).first()
    return (
        installment.registration.yatra.title
        if installment and installment.registration and installment.registration.yatra
        else "Yatra"
    )


def _payment_proof_url(payment):
    proof = getattr(payment, "proof", None)
    url = getattr(proof, "url", None) if proof else None
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    public_base = getattr(settings, "PUBLIC_BACKEND_BASE_URL", "").rstrip("/")
    return f"{public_base}{url}" if public_base else None


def _payment_status_rows(payment):
    """Build a complete installment status table for the user's registration."""
    linked = list(
        payment.installments.select_related(
            "registration__phase",
            "registration__yatra",
            "installment",
            "payment",
        )
    )
    registrations = {}
    for registration_installment in linked:
        registrations[registration_installment.registration_id] = (
            registration_installment.registration
        )

    rows = []
    for registration in registrations.values():
        if registration.phase_id:
            installment_options = registration.phase.installments.all()
        else:
            installment_options = registration.yatra.installments.filter(
                phase__isnull=True
            )
        submitted = {
            item.installment_id: item
            for item in registration.installments.select_related("payment")
        }

        for installment in installment_options:
            item = submitted.get(installment.id)
            payment_record = item.payment if item else None
            if item and item.is_paid:
                status = "Approved"
            elif payment_record and payment_record.status == "rejected":
                status = "Rejected"
            elif payment_record and payment_record.proof:
                status = "Under review"
            elif payment_record:
                status = "Payment started"
            else:
                status = "Not submitted"

            rows.append({
                "installment_name": installment.label,
                "amount": installment.amount,
                "proof_submitted": bool(payment_record and payment_record.proof),
                "proof_url": _payment_proof_url(payment_record) if payment_record else None,
                "transaction_id": payment_record.transaction_id if payment_record else None,
                "status": status,
            })
    return rows


def _payment_next_step(status, rows):
    has_more_to_pay = any(
        row["status"] in {"Not submitted", "Payment started"}
        for row in rows
    )
    all_verified = bool(rows) and all(
        row["status"] == "Approved" for row in rows
    )

    if status == "Submitted for review":
        if has_more_to_pay:
            return (
                "This payment is under review. If you have other installments "
                "to pay, you can proceed with them while you wait."
            )
        return "Please wait for confirmation for payments to be verified."
    if status == "Approved":
        if has_more_to_pay:
            return "You can proceed with any remaining installments shown above."
        if all_verified:
            return (
                "All your payments have been verified. Please stay updated with "
                "further Yatra details on your dashboard."
            )
        return "Please stay updated with further Yatra details on your dashboard."
    return (
        "Please review the notes, correct the issue if needed, and submit the "
        "payment proof again."
    )


def notify_payment_result(payment, approved, reviewer):
    yatra_name = _payment_yatra_name(payment)
    payment_rows = _payment_status_rows(payment)
    status = "Approved" if approved else "Rejected"
    _send(
        f"{yatra_name}: Payment",
        "payment_status.html",
        {
            "profile_name": _name(payment.uploaded_by),
            "yatra_name": yatra_name,
            "transaction_id": payment.transaction_id,
            "amount": payment.total_amount,
            "status": status,
            "notes": payment.notes,
            "payment_rows": payment_rows,
            "next_step": _payment_next_step(status, payment_rows),
        },
        payment.uploaded_by,
    )
