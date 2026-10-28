"""Payment notifications."""

from django.conf import settings

from helpers.notifications import _name, _send, _yatra_frontend_url


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
            "frontend_url": _payment_yatra_url(payment),
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


def _payment_yatra_url(payment):
    installment = payment.installments.select_related(
        "registration__yatra"
    ).first()
    return (
        _yatra_frontend_url(installment.registration.yatra_id)
        if installment
        else None
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
            "frontend_url": _payment_yatra_url(payment),
        },
        payment.uploaded_by,
    )

