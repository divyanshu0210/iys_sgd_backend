from django.utils import timezone


def payment_block_reason(registration, installment, on_date=None):
    """Check deadlines and unresolved earlier installments for a new proof."""
    on_date = on_date or timezone.localdate()
    installments = list(registration.phase.installments.all()) if registration.phase_id else list(registration.yatra.installments.filter(phase__isnull=True))
    records = {r.installment_id: r for r in registration.installments.select_related('payment')}
    for item in installments:
        record = records.get(item.pk)
        payment = record.payment if record and record.payment_id else None
        paid = bool(record and record.is_paid)
        submitted = bool(payment and payment.proof and payment.status != 'rejected')
        retry = bool(payment and payment.proof and payment.status == 'rejected')
        if item.pk == installment.pk:
            if item.end_date and item.end_date < on_date and not retry and not paid and not submitted:
                return f'The deadline for {item.label} has passed.'
            return None
        if not paid and not submitted:
            if retry:
                return f'Resubmit rejected proof for {item.label} first.'
            if item.end_date and item.end_date < on_date:
                return f'The deadline for {item.label} has passed.'
    return 'Invalid installment for this phase.'
