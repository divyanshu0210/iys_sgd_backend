"""Shared Bace and profile review access scopes."""

from django.db.models import Q

from userProfile.models import Bace, OtherCenter, Profile
from userProfile.utils import resolve_bace_for_center


def reviewer_baces(profile):
    """Return the active Baces managed by this counsellor or mentor."""
    return Bace.objects.filter(
        is_active=True,
    ).filter(
        Q(mentors=profile) | Q(counsellor=profile),
    ).distinct()


def _center_matches(names):
    matches = Q(pk__in=[])
    for name in names:
        matches |= Q(center__iexact=name)
    return matches


def reviewer_profile_scope(reviewer):
    """Match profiles by their current center's Bace or current mentor."""
    managed = list(reviewer_baces(reviewer))
    managed_ids = {bace.pk for bace in managed}
    baces = list(Bace.objects.filter(is_active=True))
    bace_names = {bace.name.casefold() for bace in baces}
    aliases = list(OtherCenter.objects.filter(is_active=True, bace__is_active=True))
    # An exact Bace name takes precedence over an OtherCenter alias.
    aliases = [alias for alias in aliases if alias.name.casefold() not in bace_names]
    managed_names = [bace.name for bace in managed]
    managed_names.extend(alias.name for alias in aliases if alias.bace_id in managed_ids)
    known_names = [bace.name for bace in baces] + [alias.name for alias in aliases]

    scope = Q(mentor=reviewer) | _center_matches(managed_names)
    if any(bace.name.casefold() == "others" for bace in managed):
        scope |= Q(center__isnull=False) & ~Q(center="") & ~_center_matches(known_names)
    return scope


def reviewer_request_scope(reviewer):
    """Apply current profile access to profile-verification requests."""
    return Q(from_user_id__in=Profile.objects.filter(reviewer_profile_scope(reviewer)).values("pk"))


def reviewers_for_profile(profile):
    """Return current Bace reviewers and the profile's current direct mentor."""
    bace = resolve_bace_for_center(profile.center)
    reviewer_ids = set()
    if bace:
        if bace.counsellor_id:
            reviewer_ids.add(bace.counsellor_id)
        reviewer_ids.update(bace.mentors.values_list("pk", flat=True))
    if profile.mentor_id:
        reviewer_ids.add(profile.mentor_id)
    return Profile.objects.filter(pk__in=reviewer_ids).select_related("user")


def profiles_for_reviewer(reviewer):
    """Return verified profile IDs within the current reviewer scope."""
    return Profile.objects.filter(
        reviewer_profile_scope(reviewer),
        profile_verification_status="verified",
    ).values_list("id", flat=True).distinct()
