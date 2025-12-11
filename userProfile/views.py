from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import *
from .serializers import *
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAdminUser, AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

# models.py
# ✅ Get base URL from settings
frontend_url = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173/")
home_url = f"{frontend_url.rstrip('/')}/"



class ProfileView(APIView):
    """
    GET:
    Retrieve the currently logged-in user's profile.

    POST:
    Create or update the user's profile.
    If the mentor field changes (by member_id), automatically sends a mentor request.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return the logged-in user's profile"""
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """Create or update profile; handle mentor requests automatically"""
        profile, created = Profile.objects.get_or_create(user=request.user)
        old_mentor = profile.mentor
     

        # ✅ Handle mentor change (by member_id)
        new_mentor_member_id = request.data.get('mentor')

        if new_mentor_member_id:
            try:
                new_mentor_member_id = int(new_mentor_member_id)
            except (TypeError, ValueError):
                return Response({"mentor": "Invalid mentor member_id."}, status=status.HTTP_400_BAD_REQUEST)

            # Only trigger if mentor actually changed
            if not old_mentor or old_mentor.member_id != new_mentor_member_id:
                new_mentor = get_object_or_404(Profile, member_id=new_mentor_member_id)

                # ✅ Prevent users from choosing themselves as mentor
                if new_mentor == profile:
                    return Response({"mentor": "You cannot assign yourself as mentor."},
                                    status=status.HTTP_400_BAD_REQUEST)
                profile.mentor = new_mentor
                # ✅ Create or update mentor request
                MentorRequest.objects.get_or_create(from_user=profile, to_mentor=new_mentor)

                # ✅ Send notification email to mentor
                # if new_mentor.user.email:
                #     send_mail(
                #         subject="New Mentee Request 💬",
                #         message=(
                #             f"Dear {new_mentor.first_name or new_mentor.user.username},\n\n"
                #             f"{profile.first_name or profile.user.username} has requested you to be their mentor.\n\n"
                #             f"Please review and respond to this mentorship request in your dashboard.\n\n"
                #             f"Visit your dashboard: {home_url}\n\n"
                #             f"Hare Krishna!"
                #         ),
                #         from_email=settings.DEFAULT_FROM_EMAIL,
                #         recipient_list=[new_mentor.user.email],
                #         fail_silently=True,
                #     )

            serializer = ProfileSerializer(profile, data=request.data, partial=True, context={'request': request})
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            updated_profile = serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        
class ProfilePictureUploadView(APIView):
    """
    Upload or update profile picture.
    POST: Upload a new profile picture for the logged-in user.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        profile = request.user.profile
        image = request.data.get('profile_picture')

        if not image:
            return Response({'error': 'No image file provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Remove old image if exists
        if profile.profile_picture:
            profile.profile_picture.delete(save=False)

        # Assign new image and save
        profile.profile_picture = image
        profile.save()

        serializer = ProfileSerializer(profile, context={'request': request})
        return Response({
            "message": "Profile picture uploaded successfully.",
            "profile": serializer.data
        }, status=status.HTTP_200_OK)
    

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
        approved_requests = MentorRequest.objects.filter(
            to_mentor=mentor_profile,
            is_approved=True
        ).select_related('from_user__user')

        approved_mentees_data = [
            ProfileSerializer(req.from_user, context={'request': request}).data
            for req in approved_requests
        ]

        # =================================================================
        # 2. PENDING REQUESTS (from MentorRequest, not approved yet)
        # =================================================================
        pending_requests = MentorRequest.objects.filter(
            to_mentor=mentor_profile,
            is_approved=False
        ).select_related('from_user__user')

        pending_requests_data = [
            {
                "id": req.id,
                "from_user": ProfileSerializer(req.from_user, context={'request': request}).data,
                "message": req.message,
                "created_at": req.created_at,
            }
            for req in pending_requests
        ]

        # =================================================================
        # 3. STATS
        # =================================================================
        stats = {
            "total_mentees": approved_requests.count(),
            "pending_requests": pending_requests.count(),
        }

        # =================================================================
        # 4. RESPONSE
        # =================================================================
        return Response({
            "mentor_profile": ProfileSerializer(mentor_profile, context={'request': request}).data,
            "approved_mentees": approved_mentees_data,
            "pending_requests": pending_requests_data,
            "stats": stats,
        }, status=status.HTTP_200_OK)


    def post(self, request):
        """
        POST:
        Approve a mentor request and notify the mentee by email.
        """
        request_id = request.data.get('request_id')
        mentor_profile = request.user.profile
        print(request_id,'printing req id ...................................')
        req = get_object_or_404(MentorRequest, id=request_id, to_mentor=mentor_profile)


        req.is_approved = True
        req.save()

        # Assign mentee officially
        mentee = req.from_user
        mentee.mentor = mentor_profile
        mentee.user_type = 'devotee'  # Update user_type to 'devotee'
        mentee.save()

        # ✅ Send email notification to mentee
        mentee_email = mentee.user.email
        # if mentee_email:
        #     send_mail(
        #         subject="Mentor Request Approved ✅",
        #         message=(
        #             f"Dear {mentee.first_name or mentee.user.username},\n\n"
        #             f"Your mentor request to {mentor_profile.first_name or mentor_profile.user.username} has been approved.\n\n"
        #             f"You are now connected as a mentee.\n\n"
        #             f"Visit your dashboard: {home_url}\n\n"
        #             f"Hare Krishna!"
        #         ),
        #         from_email=settings.DEFAULT_FROM_EMAIL,
        #         recipient_list=[mentee_email],
        #         fail_silently=True,
        #     )

        return Response({"message": "Mentee request approved successfully."}, status=status.HTTP_200_OK)

    # DELETE: Reject request (request_id from URL)
    def delete(self, request, request_id=None):
        if not request_id:
            return Response({"error": "request_id is required in URL"}, status=status.HTTP_400_BAD_REQUEST)

        mentor_profile = request.user.profile

        try:
            req = MentorRequest.objects.get(
                id=request_id,
                to_mentor=mentor_profile,
                is_approved=False
            )
        except MentorRequest.DoesNotExist:
            return Response({"error": "Request not found or already processed"}, status=status.HTTP_404_NOT_FOUND)

        mentee = req.from_user
        mentee_email = mentee.user.email

        # 2. Clear the mentor reference from the mentee's Profile
        # -----------------------------------------------------------------
        if mentee.mentor == mentor_profile:
            mentee.mentor = None
            mentee.user_type = 'guest'  # Revert user_type to 'seeker'
            mentee.save(update_fields=["mentor", "user_type"])

        # Delete request
        req.delete()

        # Send rejection email
        # if mentee_email:
        #     send_mail(
        #         subject="Mentor Request Update",
        #         message=(
        #             f"Dear {mentee.first_name or mentee.user.username},\n\n"
        #             f"Your mentor request to {mentor_profile.first_name or mentor_profile.user.username} "
        #             f"was not accepted at this time.\n\n"
        #             f"Please feel free to request another mentor.\n\n"
        #             f"Visit profile: {home_url}\n\n"
        #             f"Hare Krishna!"
        #         ),
        #         from_email=settings.DEFAULT_FROM_EMAIL,
        #         recipient_list=[mentee_email],
        #         fail_silently=True,
        #     )

        return Response({"message": "Request rejected."}, status=status.HTTP_200_OK)
    

# api/views.py
import base64
import requests
from django.http import JsonResponse

def proxy_image(request):
    url = request.GET.get("url")
    if not url:
        return JsonResponse({"error": "Missing URL"}, status=400)

    try:
        r = requests.get(url)
        encoded = base64.b64encode(r.content).decode()
        return JsonResponse({"base64": encoded})
    except:
        return JsonResponse({"error": "Fetch Failed"}, status=400)


