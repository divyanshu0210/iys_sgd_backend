from userProfile.models import Profile



CENTER_CODE_MAP = {
    "vrindavan bace": "1",
    "mayapur bace": "2",
    "giri govardhan bace": "3",
    "temple vta": "4",
    "temple brahmachari": "5",
}
DEFAULT_OTHER_CENTER_CODE = "6"
PENDING_APPROVAL_CODE = "7"

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
