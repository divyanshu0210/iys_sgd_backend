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
            "frontend_url": context.get("frontend_url") or (
                f"{getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173').rstrip('/')}/"
            ),
        },
        recipient=recipient,
        fail_silently=True,
    )


def _yatra_frontend_url(yatra_id):
    base_url = getattr(
        settings, "FRONTEND_BASE_URL", "http://localhost:5173"
    ).rstrip("/")
    return f"{base_url}/yatra/{yatra_id}/register"


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
