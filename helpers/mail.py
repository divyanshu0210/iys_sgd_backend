from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings


def send_template_email(subject, template_name, context, recipient, fail_silently=False):
    """
    Render an HTML email template and send it.
    Falls back to strip_tags plain text automatically.
    Pass fail_silently=True for non-critical emails (welcome, notifications).
    Leave False (default) for critical emails (password reset) so errors surface.
    """
    html_body = render_to_string(f"emails/{template_name}", context)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=_html_to_text(html_body),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=fail_silently)


def _html_to_text(html):
    """Very light HTML stripper for the plain-text fallback."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
