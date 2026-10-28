from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import *
from .serializers import *
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAdminUser, AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import api_view, permission_classes
from helpers.mail import send_template_email
from userProfile.notifications import (
    notify_new_profile_request,
    notify_mentor_request_decision,
    notify_profile_review_batch,
)
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models.functions import Lower
import logging
from userProfile.scopes import can_access_profile, profiles_for_reviewer, reviewer_request_scope, reviewers_for_profile
from userProfile.utils import resolve_bace_for_center

# models.py
# ✅ Get base URL from settings
frontend_url = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173/")
home_url = f"{frontend_url.rstrip('/')}/"
MAX_PROFILE_PHOTO_SIZE = 1 * 1024 * 1024
logger = logging.getLogger(__name__)


def _delete_replaced_profile_picture(storage, old_name):
    """Delete a replaced image only when no profile still references it."""
    try:
        if not Profile.objects.filter(profile_picture=old_name).exists():
            storage.delete(old_name)
    except Exception:
        logger.exception("Could not delete replaced profile picture: %s", old_name)


def create_bace_verification_requests(profile, bace):
    """Create one verification request owned by the Bace counsellor."""
    if not bace or not bace.counsellor or bace.counsellor == profile:
        return None

    now = timezone.now()

    # A profile changing Bace starts a fresh verification round.
    MentorRequest.objects.filter(
        from_user=profile,
        is_approved=False,
        is_rejected=False,
    ).exclude(requested_bace=bace).update(
        is_rejected=True,
        rejected_at=now,
    )

    # Reuse an already-pending counsellor-owned request, if present. A
    # rejected request is deliberately not reused: resubmission creates a
    # fresh request while preserving the previous rejection history.
    request_obj = MentorRequest.objects.filter(
        from_user=profile,
        to_mentor=bace.counsellor,
        requested_bace=bace,
        is_approved=False,
        is_rejected=False,
    ).order_by("created_at").first()
    created = request_obj is None
    if created:
        request_obj = MentorRequest.objects.create(
            from_user=profile,
            to_mentor=bace.counsellor,
            requested_bace=bace,
            is_approved=False,
            is_rejected=False,
        )

    # Consolidate any older mentor-owned pending rows for this same Bace.
    MentorRequest.objects.filter(
        from_user=profile,
        requested_bace=bace,
        is_approved=False,
        is_rejected=False,
    ).exclude(pk=request_obj.pk).update(
        is_rejected=True,
        rejected_at=now,
    )
    if created:
        transaction.on_commit(lambda: notify_new_profile_request(request_obj))
    return request_obj


class BaceListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        baces = Bace.objects.filter(is_active=True).select_related("counsellor").prefetch_related("mentors", "other_centers")
        return Response(BaceSerializer(baces, many=True, context={"request": request}).data)



class ProfileView(APIView):
    """
    GET:
    Retrieve the currently logged-in user's profile.

    POST:
    Create or update the user's profile.
    If the mentor field changes (by member_id), automatically sends a mentor request.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        """Return the logged-in user's profile"""
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request):
        """Create or update profile; handle mentor requests automatically"""
        profile, created = Profile.objects.select_for_update().get_or_create(user=request.user)
        old_mentor = profile.mentor
        old_picture_name = profile.profile_picture.name
        picture_storage = profile.profile_picture.storage
        requested_center = request.data.get("center", profile.center)

        # The frontend may show a broader list than the Baces configured in
        # admin. Anything not configured is grouped under the mandatory
        # fallback Bace named "Others".
        requested_bace = resolve_bace_for_center(requested_center)
        if requested_center and not requested_bace:
            return Response(
                {"center": "The fallback Bace 'Others' is not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        current_center = profile.center or ""

        if (
            profile.profile_verification_status in {"pending", "verified"}
            and requested_center != current_center
        ):
            return Response(
                {"center": "A profile under verification or already verified cannot change its Bace."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bace = requested_bace

        incoming_photo = request.FILES.get("profile_picture")
        if incoming_photo and incoming_photo.size > MAX_PROFILE_PHOTO_SIZE:
            return Response(
                {"profile_picture": "Photo must be 1 MB or smaller."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            profile.profile_verification_status != "verified"
            and not incoming_photo
            and not profile.profile_picture
        ):
            return Response(
                {"profile_picture": "A profile photo is required before submission."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            requested_center
            and bace
            and not bace.counsellor
            and profile.profile_verification_status != "verified"
        ):
            return Response(
                {"center": "This Bace does not have a counsellor assigned yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )
     

        # ✅ Handle mentor change (by member_id)
        # Mentors are assigned only through the Bace admin mapping; users cannot choose one.
        new_mentor_member_id = None

        if new_mentor_member_id:
            try:
                new_mentor_member_id = int(new_mentor_member_id)
            except (TypeError, ValueError):
                return Response({"mentor": "Invalid mentor member_id."}, status=status.HTTP_400_BAD_REQUEST)

            new_mentor = get_object_or_404(Profile, member_id=new_mentor_member_id)

            if new_mentor == profile:
                    return Response({"mentor": "You cannot assign yourself as mentor."},
                                    status=status.HTTP_400_BAD_REQUEST)
            
            if new_mentor.user_type != "mentor":
                return Response(
                    {"mentor": "Selected user is not a mentor."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Only trigger if mentor actually changed
            if not old_mentor or old_mentor.member_id != new_mentor_member_id:

                # ✅ Prevent users from choosing themselves as mentor
                
                profile.mentor = new_mentor
                # ✅ Create or update mentor request
                mentor_request, created = MentorRequest.objects.get_or_create(
                    from_user=profile,
                    to_mentor=new_mentor,
                )

                # ✅ Send notification email to mentor
                if created:
                    transaction.on_commit(
                        lambda: notify_new_profile_request(mentor_request)
                    )

        profile_data = request.data.copy()
        if requested_center:
            profile_data["center"] = requested_center
        serializer = ProfileSerializer(profile, data=profile_data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated_profile = serializer.save()

        if incoming_photo and old_picture_name and old_picture_name != updated_profile.profile_picture.name:
            transaction.on_commit(
                lambda: _delete_replaced_profile_picture(picture_storage, old_picture_name)
            )

        if requested_center and updated_profile.profile_verification_status != "verified":
            updated_profile.profile_verification_status = "pending"
            updated_profile.user_type = "guest"
            updated_profile.mentor = None
            updated_profile.save(update_fields=[
                "profile_verification_status",
                "user_type",
                "mentor",
            ])
            create_bace_verification_requests(updated_profile, bace)

        response_serializer = ProfileSerializer(updated_profile, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        
    

class MentorRequestView(APIView):
    permission_classes = [IsAuthenticated]

    """
    GET:
    Return all mentorship-related data for the logged-in mentor.
    
    - Approved mentees: From MentorRequest where is_approved=True
    - Pending requests: From MentorRequest where is_approved=False
    - Both include FULL mentee profile (via ProfileSerializer)
    - Includes stats
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mentor_profile = request.user.profile

        # =================================================================
        # 1. APPROVED MENTEES (from approved MentorRequest)
        # =================================================================
        approved_profiles = Profile.objects.filter(
            pk__in=profiles_for_reviewer(mentor_profile),
        ).select_related('user', 'mentor').order_by(
            Lower('first_name'), Lower('last_name'), 'id',
        )

        approved_mentees_data = [
            ProfileFastSerializer(profile, context={'request': request}).data
            for profile in approved_profiles
        ]

        # =================================================================
        # 2. PENDING REQUESTS (from MentorRequest, not approved yet)
        # =================================================================
        pending_requests = MentorRequest.objects.filter(
            reviewer_request_scope(mentor_profile),
            is_approved=False,
            is_rejected=False,
        ).select_related('from_user__user', 'from_user__mentor', 'requested_bace').distinct().order_by(
            Lower('from_user__first_name'),
            Lower('from_user__last_name'),
            'from_user_id',
        )

        pending_requests_data = [
            {
                "id": req.id,
                "from_user": ProfileFastSerializer(req.from_user, context={'request': request}).data,
                "message": req.message,
                "created_at": req.created_at,
                "bace": req.requested_bace.name if req.requested_bace else req.from_user.center,
            }
            for req in pending_requests
        ]

        # =================================================================
        # 3. STATS
        # =================================================================
        stats = {
            "total_mentees": len(approved_mentees_data),
            "pending_requests": len(pending_requests_data),
        }

        # =================================================================
        # 4. RESPONSE
        # =================================================================
        return Response({
            "mentor_profile": ProfileFastSerializer(mentor_profile, context={'request': request}).data,
            "approved_mentees": approved_mentees_data,
            "pending_requests": pending_requests_data,
            "stats": stats,
        }, status=status.HTTP_200_OK)


    def post(self, request):
        request_ids = request.data.get("request_ids")
        if request_ids is None and request.data.get("request_id"):
            request_ids = [request.data["request_id"]]
        return self.process(
            request, request_ids, request.data.get("action", "connect")
        )

    def delete(self, request, request_id=None):
        if not request_id:
            return Response({"error": "request_id is required in URL"}, status=400)
        return self.process(request, [request_id], "reject")

    def process(self, request, request_ids, action):
        from uuid import UUID

        if not isinstance(request_ids, list) or not request_ids or action not in {"connect", "reject"}:
            return Response({"detail": "Provide request_ids and an action of connect or reject."}, status=400)
        try:
            ids = list(dict.fromkeys(UUID(str(value)) for value in request_ids))
        except (TypeError, ValueError, AttributeError):
            return Response({"detail": "Invalid request ID."}, status=400)

        reviewer = request.user.profile
        approved = action == "connect"
        with transaction.atomic():
            requests = list(
                MentorRequest.objects.filter(
                    reviewer_request_scope(reviewer),
                    pk__in=ids,
                    is_approved=False,
                    is_rejected=False,
                ).select_related("from_user__user", "to_mentor__user", "requested_bace__counsellor__user")
                .select_for_update(of=("self",))
            )
            if len(requests) != len(ids):
                return Response({"detail": "Some requests are unavailable or already processed."}, status=400)
            current_baces = {req.pk: resolve_bace_for_center(req.from_user.center) for req in requests}
            if approved and any(bace and not bace.counsellor for bace in current_baces.values()):
                return Response({"detail": "A selected Bace has no counsellor assigned."}, status=400)
            if len({req.from_user_id for req in requests}) != len(requests):
                return Response({"detail": "Select only one pending request per profile."}, status=400)

            review_recipients = {
                req.pk: list(reviewers_for_profile(req.from_user)) for req in requests
            }
            for req in requests:
                mentee = req.from_user
                if approved:
                    current_mentor = mentee.mentor
                    req.is_approved = True
                    req.save(update_fields=["is_approved"])
                    bace = current_baces[req.pk]
                    mentee.mentor = bace.counsellor if bace else (current_mentor or reviewer)
                    mentee.user_type = "devotee"
                    mentee.profile_verification_status = "verified"
                else:
                    req.is_rejected = True
                    req.rejected_at = timezone.now()
                    req.rejected_by = reviewer
                    req.save(update_fields=["is_rejected", "rejected_at", "rejected_by"])
                    mentee.mentor = None
                    mentee.user_type = "guest"
                    mentee.profile_verification_status = "rejected"
                mentee.save(update_fields=["mentor", "user_type", "profile_verification_status"])
                MentorRequest.objects.filter(
                    from_user=mentee, requested_bace=req.requested_bace,
                    is_approved=False, is_rejected=False,
                ).exclude(pk=req.pk).update(
                    is_rejected=True, rejected_at=timezone.now(), rejected_by=reviewer,
                )

            for req in requests:
                transaction.on_commit(
                    lambda req=req: notify_mentor_request_decision(req, approved, reviewer)
                )
            transaction.on_commit(
                lambda: notify_profile_review_batch(requests, reviewer, approved, review_recipients)
            )

        return Response({"message": "Requests processed successfully.", "processed": len(requests)})
    

# api/views.py
import base64

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def proxy_image(request):
    """Read an authorized profile's stored photo without fetching arbitrary URLs."""
    from uuid import UUID
    try:
        profile_id = UUID(request.query_params.get("profile_id", ""))
    except (ValueError, TypeError, AttributeError):
        return Response({"error": "A valid profile_id is required."}, status=400)
    profile = get_object_or_404(Profile, pk=profile_id)
    if not can_access_profile(request.user.profile, profile):
        return Response({"error": "You cannot access this profile photo."}, status=403)
    if not profile.profile_picture:
        return Response({"error": "No profile photo found."}, status=404)
    try:
        # Bound reads even for older images that predate the upload size limit.
        with profile.profile_picture.open("rb") as image:
            content = image.read(5 * 1024 * 1024 + 1)
        if len(content) > 5 * 1024 * 1024:
            return Response({"error": "Profile photo is too large."}, status=400)
        return Response({"base64": base64.b64encode(content).decode("ascii")})
    except Exception:
        logger.exception("Could not read profile picture for profile %s", profile.pk)
        return Response({"error": "Unable to read profile photo."}, status=502)


