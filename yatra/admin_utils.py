from django.utils import timezone
from django.db.models import Q


class ActiveYatraAdminMixin:
    """Default admin querysets to currently unclosed Yatras.

    Add ``?show_all=1`` to the changelist URL to include historical Yatras.
    Visibility ends on the configured refund date. If no refund date is set,
    visibility falls back to the Yatra end date.
    Subclasses may override ``admin_yatra_lookup`` for indirect relations.
    """

    admin_yatra_lookup = "yatra"

    def changelist_view(self, request, extra_context=None):
        # ``show_all`` is an admin UI toggle, not a model field lookup.
        # Remove it before Django's ChangeList processes query parameters.
        request.show_all_yatras = request.GET.get("show_all") == "1"
        request.GET = request.GET.copy()
        request.GET.pop("show_all", None)

        extra_context = extra_context or {}
        extra_context["show_all_yatras"] = request.show_all_yatras
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Apply the visibility filter only to changelist pages. A record
        # selected from "Show all" must remain openable on its change page.
        if not hasattr(request, "show_all_yatras") or request.show_all_yatras:
            return queryset

        lookup = self.admin_yatra_lookup
        refund_date_field = f"{lookup}__payment_refund_date"
        end_date_field = f"{lookup}__end_date"
        return queryset.filter(
            **{f"{lookup}__close_yatra": False}
        ).filter(
            Q(**{f"{refund_date_field}__gte": timezone.localdate()})
            | Q(**{f"{refund_date_field}__isnull": True,
                  f"{end_date_field}__gte": timezone.localdate()})
        ).distinct()
