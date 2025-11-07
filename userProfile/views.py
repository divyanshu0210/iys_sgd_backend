from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Yatra, Profile, YatraRegistration, MentorRequest
from .serializers import YatraSerializer, ProfileSerializer, YatraRegistrationSerializer
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAdminUser, AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
# ✅ Get base URL from settings
frontend_url = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173/")
home_url = f"{frontend_url.rstrip('/')}/"

class YatraListView(APIView):
    """
    get:
    Retrieve a list of all available Yatras.

    Returns a list of Yatra objects with details such as title, description,
    dates, location, and capacity.

    post:
    Create a new Yatra entry.

    Expects JSON data like:
    ```
    {
        "title": "Spiritual Himalaya Yatra",
        "description": "A 7-day spiritual journey in the Himalayas.",
        "start_date": "2025-12-01",
        "end_date": "2025-12-08",
        "location": "Rishikesh, Uttarakhand",
        "capacity": 50
    }
    ```

    Returns the created Yatra object on success.
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]
    

    def get(self, request):
        yatras = Yatra.objects.all()
        serializer = YatraSerializer(yatras, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = YatraSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # creates a new Yatra in DB
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class YatraRegisterView(APIView):
    """
    get:
    Retrieve all profiles that the current user can register for a Yatra,
    along with whether each is already registered or not and their user type.
    """

    def get(self, request, yatra_id):
        user_profile = get_object_or_404(Profile, id=request.user.profile.id)
        mentees = Profile.objects.filter(mentor=user_profile)
        eligible = [user_profile] + list(mentees)

        # ✅ All profile IDs already registered for this yatra (by anyone)
        registered_ids = set(
            YatraRegistration.objects.filter(yatra_id=yatra_id)
            .values_list('registered_for_id', flat=True)
        )

        # ✅ Serialize all eligible profiles
        serializer = ProfileSerializer(eligible, many=True, context={'request': request})
        profiles_data = serializer.data

        # ✅ Add extra fields: is_registered + user_type
        for profile in profiles_data:
            profile['is_registered'] = profile['id'] in [str(rid) for rid in registered_ids]
            # user_type already exists in ProfileSerializer,
            # but ensuring it’s explicitly available even if serializer changes later
            profile['user_type'] = next(
                (p.user_type for p in eligible if str(p.id) == profile['id']), None
            )

        return Response(profiles_data, status=status.HTTP_200_OK)

    def post(self, request, yatra_id):
        yatra = get_object_or_404(Yatra, id=yatra_id)
        registrant = request.user.profile
        registered_for_ids = request.data.get('registered_for_ids', [])
        created = []

        for pid in registered_for_ids:
            profile = get_object_or_404(Profile, id=pid)

            # ✅ Only allow registering self or mentees
            if profile == registrant or profile.mentor == registrant:
                obj, _ = YatraRegistration.objects.get_or_create(
                    yatra=yatra,
                    registered_for=profile,
                    defaults={'registrant': registrant}
                )
                created.append(obj)

        serializer = YatraRegistrationSerializer(created, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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
        serializer = ProfileSerializer(profile, data=request.data, partial=True, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated_profile = serializer.save()

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

                # ✅ Create or update mentor request
                MentorRequest.objects.get_or_create(from_user=profile, to_mentor=new_mentor)

                # ✅ Send notification email to mentor
                if new_mentor.user.email:
                    send_mail(
                        subject="New Mentee Request 💬",
                        message=(
                            f"Dear {new_mentor.first_name or new_mentor.user.username},\n\n"
                            f"{profile.first_name or profile.user.username} has requested you to be their mentor.\n\n"
                            f"Please review and respond to this mentorship request in your dashboard.\n\n"
                            f"Visit your dashboard: {home_url}\n\n"
                            f"Hare Krishna!"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[new_mentor.user.email],
                        fail_silently=True,
                    )

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

    def get(self, request):
        """
        GET:
        List all pending mentee requests for the logged-in mentor, 
        including full mentee profile details.
        """
        mentor_profile = request.user.profile
        requests = MentorRequest.objects.filter(to_mentor=mentor_profile, is_approved=False)

        data = []
        for r in requests:
            # Serialize mentee's full profile
            mentee_profile_data = ProfileSerializer(
                r.from_user,  # from_user is a Profile object
                context={'request': request}
            ).data

            data.append({
                "id": r.id,
                "from_user": mentee_profile_data,   # full profile details here
                "message": r.message,
                "created_at": r.created_at,
            })

        return Response(data, status=status.HTTP_200_OK)

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
        mentee.save()

        # ✅ Send email notification to mentee
        mentee_email = mentee.user.email
        if mentee_email:
            send_mail(
                subject="Mentor Request Approved ✅",
                message=(
                    f"Dear {mentee.first_name or mentee.user.username},\n\n"
                    f"Your mentor request to {mentor_profile.first_name or mentor_profile.user.username} has been approved.\n\n"
                    f"You are now connected as a mentee.\n\n"
                    f"Visit your dashboard: {home_url}\n\n"
                    f"Hare Krishna!"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[mentee_email],
                fail_silently=True,
            )

        return Response({"message": "Mentee request approved successfully."}, status=status.HTTP_200_OK)

    def delete(self, request):
        """
        DELETE:
        Reject a mentor request and notify the mentee by email.
        """
        request_id = request.data.get('request_id')
        mentor_profile = request.user.profile
        req = get_object_or_404(MentorRequest, id=request_id, to_mentor=mentor_profile)


        mentee = req.from_user
        mentee_email = mentee.user.email

        # Delete request (rejected)
        req.delete()

        # ✅ Send rejection email
        if mentee_email:
            send_mail(
                subject="Mentor Request Rejected ❌",
                message=(
                    f"Dear {mentee.first_name or mentee.user.username},\n\n"
                    f"Your mentor request to {mentor_profile.first_name or mentor_profile.user.username} has been declined.\n\n"
                    f"You may choose another mentor from your profile settings.\n\n"
                    f"Visit your profile: {home_url}\n\n"
                    f"Hare Krishna!"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[mentee_email],
                fail_silently=True,
            )

        return Response({"message": "Mentee request rejected and notified."}, status=status.HTTP_200_OK)    
    
class MentorDashboardView(APIView):
    """
    GET:
    Return all mentorship-related data for the logged-in mentor.
    Includes approved mentees, pending requests, and basic stats.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mentor_profile = request.user.profile

        # ✅ Approved mentees (those whose mentor = current user)
        approved_mentees = Profile.objects.filter(mentor=mentor_profile)

        # ✅ Pending requests (not yet approved)
        pending_requests = MentorRequest.objects.filter(
            to_mentor=mentor_profile, is_approved=False
        )

        # ✅ Serialize everything
        mentor_data = ProfileSerializer(mentor_profile, context={'request': request}).data
        approved_mentees_data = ProfileSerializer(
            approved_mentees, many=True, context={'request': request}
        ).data

        pending_requests_data = []
        for req in pending_requests:
            mentee_data = ProfileSerializer(
                req.from_user, context={'request': request}
            ).data
            pending_requests_data.append({
                "id": req.id,
                "from_user": mentee_data,
                "message": req.message,
                "created_at": req.created_at,
            })

        # ✅ Stats
        stats = {
            "total_mentees": approved_mentees.count(),
            "pending_requests": pending_requests.count(),
        }

        return Response({
            "mentor_profile": mentor_data,
            "approved_mentees": approved_mentees_data,
            "pending_requests": pending_requests_data,
            "stats": stats,
        }, status=status.HTTP_200_OK)
