from django.template.loader import render_to_string
from django.conf import settings
from anymail.message import AnymailMessage
import logging

logger = logging.getLogger(__name__)


def send_template_email(subject, template_name, context, recipient, fail_silently=False):
    html_body = render_to_string(f"emails/{template_name}", context)
    plain_body = _html_to_text(html_body)

    if getattr(settings, 'EMAIL_PROVIDER', '').lower() in {'gmail', 'smtp'}:
        try:
            _send(subject, html_body, plain_body, recipient, settings.EMAIL_BACKEND)
            return
        except Exception:
            logger.exception("SMTP email delivery failed")
            if not fail_silently:
                raise
            return

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
    from html import unescape

    # Remove non-visible document sections before stripping HTML tags. Without
    # this, the CSS from the email's <style> block leaks into the plain-text
    # MIME part and some clients treat the message as trimmed content.
    html = re.sub(
        r"<(style|script)\b[^>]*>.*?</\1>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
