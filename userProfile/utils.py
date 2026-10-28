from userProfile.models import Bace, OtherCenter, Profile



CENTER_CODE_MAP = {
    "vrindavan bace": "1",
    "mayapur bace": "2",
    "giri govardhan bace": "3",
    "temple vta": "4",
    "temple brahmachari": "5",
}
DEFAULT_OTHER_CENTER_CODE = "6"
PENDING_APPROVAL_CODE = "7"


def resolve_bace_for_center(center):
    """Resolve a non-empty center to an active Bace.

    Configured Baces and aliases in ``OtherCenter`` are resolved directly.
    Any other non-empty center is grouped under the active ``Others`` Bace.
    A missing center remains unassigned rather than being silently grouped.
    """
    if not center:
        return None

    bace = Bace.objects.filter(
        name__iexact=center,
        is_active=True,
    ).first()
    if bace:
        return bace

    other_center = (
        OtherCenter.objects.filter(
            name__iexact=center,
            is_active=True,
            bace__is_active=True,
        )
        .select_related("bace")
        .first()
    )
    if other_center:
        return other_center.bace

    return Bace.objects.filter(
        name__iexact="Others",
        is_active=True,
    ).first()



def generate_member_id(*, year, center_code):
    prefix = f"{year}{center_code}"  # YYC

    start = int(f"{prefix}000")
    end = int(f"{prefix}999")

    last_profile = (
        Profile.objects
        .select_for_update()
        .filter(member_id__gte=start, member_id__lte=end)
        .order_by("-member_id")
        .first()
    )

    next_seq = (last_profile.member_id % 1000) + 1 if last_profile else 1

    if next_seq > 999:
        raise ValueError("Sequence overflow for this year and center")

    return int(f"{prefix}{next_seq:03d}")
