from django.template.loader import render_to_string
from django.conf import settings
from anymail.message import AnymailMessage
import logging

logger = logging.getLogger(__name__)


def send_template_email(subject, template_name, context, recipient, fail_silently=False):
    html_body = render_to_string(f"emails/{template_name}", context)
    plain_body = _html_to_text(html_body)

    # Try primary backend (Brevo)
    try:
        _send(subject, html_body, plain_body, recipient, 'anymail.backends.brevo.EmailBackend')
        return
    except Exception as e:
        logger.warning("Primary email backend (Brevo) failed: %s", e)

    # Fallback backend (Resend)
    try:
        _send(subject, html_body, plain_body, recipient, 'anymail.backends.resend.EmailBackend')
        return
    except Exception as e:
        logger.error("Fallback email backend (Resend) also failed: %s", e)
        if not fail_silently:
            raise


def _send(subject, html_body, plain_body, recipient, backend):
    from django.core.mail import get_connection
    connection = get_connection(backend=backend)
    msg = AnymailMessage(
        subject=subject,
        body=plain_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        connection=connection,
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send()


def _html_to_text(html):
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
