from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Yatra, Profile, YatraRegistration, MentorRequest,YatraEligibility
from .serializers import YatraSerializer, ProfileSerializer, YatraRegistrationSerializer
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAdminUser, AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from .models import YatraRegistration
# utils.py
import qrcode
from django.conf import settings
from io import BytesIO
from django.core.files import File
from django.http import HttpResponse
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




# userProfile/views.py
class YatraRegisterView(APIView):
    """
    GET:
    Retrieve all profiles that the current user (mentor) can potentially register for a Yatra.
    Includes: self + mentees, with eligibility status for this Yatra, and current registration status.
    
    POST:
    Register eligible profiles (self + mentees) for the Yatra.
    Only approved profiles (via YatraEligibility) can be registered.
    Expects: {"registered_for_ids": [profile_id1, profile_id2, ...]}
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, yatra_id):
        yatra = get_object_or_404(Yatra, id=yatra_id)
        user_profile = request.user.profile

        # === GET APPROVED MENTEES FROM MentorRequest (NOT Profile.mentor) ===
        approved_mentee_requests = MentorRequest.objects.filter(
            to_mentor=user_profile,
            is_approved=True
        ).select_related('from_user')

        mentees = [req.from_user for req in approved_mentee_requests]
        all_profiles = mentees.copy()  # Start with mentees

        # === Add self only if approved by THEIR mentor ===
        try:
            self_eligibility = YatraEligibility.objects.get(
                yatra=yatra,
                profile=user_profile
            )
            if self_eligibility.is_approved:
                all_profiles = [user_profile] + all_profiles
        except YatraEligibility.DoesNotExist:
            pass

        # === Eligibility Map ===
        profile_ids = [p.id for p in all_profiles]
        eligibilities = YatraEligibility.objects.filter(
            yatra=yatra,
            profile__id__in=profile_ids
        ).select_related('approved_by')
        eligibility_map = {el.profile_id: el for el in eligibilities}

        # === Registered IDs ===
        registered_ids = set(
            YatraRegistration.objects.filter(yatra=yatra)
            .values_list('registered_for_id', flat=True)
        )

        # === Serialize full profiles ===
        serializer = ProfileSerializer(
            all_profiles,
            many=True,
            context={'request': request}
        )
        profiles_data = serializer.data

        # === Append extra fields ===
        for profile in all_profiles:
            profile_id = str(profile.id)
            el = eligibility_map.get(profile.id)

            for item in profiles_data:
                if item['id'] == profile_id:
                    item.update({
                        'is_eligible': el.is_approved if el else False,
                        'is_registered': profile.id in registered_ids,
                        'is_self': profile == user_profile,
                        'approved_by': (
                            str(el.approved_by.member_id)
                            if el and el.approved_by else None
                        ),
                    })
                    break

        return Response({
            'yatra': {
                'id': str(yatra.id),
                'title': yatra.title,
                'location': yatra.location,
                'start_date': yatra.start_date,
                'end_date': yatra.end_date,
                'description': yatra.description,
            },
            'profiles': profiles_data,
        }, status=200)

    def post(self, request, yatra_id):
        yatra = get_object_or_404(Yatra, id=yatra_id)
        registrant = request.user.profile
        registered_for_ids = request.data.get('registered_for_ids', [])

        if not registered_for_ids:
            return Response({'error': 'registered_for_ids required'}, status=400)

        created = []
        errors = []

        for pid in registered_for_ids:
            try:
                profile = Profile.objects.get(id=pid)
            except:
                errors.append(f'Invalid profile ID: {pid}')
                continue

            # === SELF: Must be approved by own mentor ===
            if profile == registrant:
                try:
                    el = YatraEligibility.objects.get(yatra=yatra, profile=profile)
                    if not el.is_approved:
                        errors.append(f'You are not approved for this Yatra')
                        continue
                except YatraEligibility.DoesNotExist:
                    errors.append(f'You are not approved for this Yatra')
                    continue
            else:
                # === MENTEE: Must be approved via MentorRequest AND YatraEligibility ===
                if not MentorRequest.objects.filter(
                    from_user=profile,
                    to_mentor=registrant,
                    is_approved=True
                ).exists():
                    errors.append(f'{profile} is not your approved mentee')
                    continue

                try:
                    el = YatraEligibility.objects.get(yatra=yatra, profile=profile)
                    if not el.is_approved:
                        errors.append(f'{profile} is not approved for this Yatra')
                        continue
                except YatraEligibility.DoesNotExist:
                    errors.append(f'{profile} has no approval for this Yatra')
                    continue

            # === Register ===
            obj, new = YatraRegistration.objects.get_or_create(
                yatra=yatra,
                registered_for=profile,
                defaults={'registrant': registrant, 'status': 'pending'}  # ← Changed to 'pending'
            )
            if new:
                created.append(obj)
            else:
                errors.append(f'{profile} already registered')

        if errors:
            return Response({'errors': errors}, status=400)

        serializer = YatraRegistrationSerializer(created, many=True)
        return Response({
            'message': f'Registered {len(created)} profiles (pending payment)',
            'registrations': serializer.data
        }, status=201)

    
# userProfile/views.py (add this new class)

class YatraEligibilityView(APIView):
    """
    GET /yatras/<yatra_id>/eligibility/:
    List all profiles (self + mentees) with their current eligibility status for this Yatra.
    
    POST /yatras/<yatra_id>/eligibility/:
    Approve/reject eligibility for profiles.
    Expects: {
        "profile_ids": [id1, id2, ...],
        "action": "approve" | "reject",
        "notes": "Optional notes for approval"
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, yatra_id):
        yatra = get_object_or_404(Yatra, id=yatra_id)
        mentor = request.user.profile

        # === 1. Get approved mentees from MentorRequest ===
        approved_requests = MentorRequest.objects.filter(
            to_mentor=mentor,
            is_approved=True
        ).select_related('from_user')
        mentees = [req.from_user for req in approved_requests]

        # === 2. Include self (mentor) in the list ===
        all_profiles = mentees + [mentor]  # self is always included

        # === 3. Build eligibility map ===
        profile_ids = [p.id for p in all_profiles]
        eligibilities = YatraEligibility.objects.filter(
            yatra=yatra,
            profile__id__in=profile_ids
        ).select_related('profile', 'approved_by')
        eligibility_map = {el.profile_id: el for el in eligibilities}

        serializer = ProfileSerializer(
        all_profiles,
        many=True,
        context={'request': request}
        )
        profiles_data = serializer.data

        # === 4. Build response data ===
        data = []
        for profile in all_profiles:
            profile_id = str(profile.id)
            el = eligibility_map.get(profile.id)

        # Append extra fields using index (safest)
        for idx, profile in enumerate(all_profiles):
            el = eligibility_map.get(profile.id)
            profiles_data[idx].update({
                'is_approved': el.is_approved if el else False,
                'approved_by': str(el.approved_by.member_id) if el and el.approved_by else None,
                'approved_at': el.approved_at.isoformat() if el and el.approved_at else None,
                'is_self': profile == mentor,
            })

        return Response({
        'yatra': {
            'id': str(yatra.id),
            'title': yatra.title,
        },
        'profiles': profiles_data,
        'total_mentees': len(mentees),
        'includes_self': True,
    }, status=200)

    def post(self, request, yatra_id):
        yatra = get_object_or_404(Yatra, id=yatra_id)
        devotee = request.user.profile
        profile_ids = request.data.get('profile_ids', [])
        action = request.data.get('action')

        if not profile_ids:
            return Response({'error': 'profile_ids is required'}, status=400)
        if action not in ['approve', 'unapprove','request_approval']:
            return Response({'error': 'Invalid action'}, status=400)

        updated = []
        errors = []

        # === HANDLE REQUEST APPROVAL (SELF) ===
        if action == 'request_approval':
            if not profile_ids or str(devotee.id) not in profile_ids:
                return Response({'error': 'You can only request approval for yourself.'}, status=400)
            # Must be self
            # --- Find mentor: 1. MentorRequest → 2. Profile.mentor ---
            mentor = None

            # 1. Try MentorRequest
            mentor_req = MentorRequest.objects.filter(
                from_user=devotee,
                is_approved=True
            ).first()

            if mentor_req:
                mentor = mentor_req.to_mentor
            else:
                # 2. Fallback: Profile.mentor field
                if devotee.mentor and devotee.is_approved:
                    mentor = devotee.mentor

            if not mentor:
                errors.append("You don't have an approved mentor to request from.")
            elif YatraEligibility.objects.filter(yatra=yatra, profile=devotee, is_approved=True).exists():
                errors.append("You are already approved for this Yatra.")
            elif YatraRegistration.objects.filter(yatra=yatra, registered_for=devotee).exists():
                errors.append("You are already registered for this Yatra.")
            else:
                eligibility, created = YatraEligibility.objects.get_or_create(
                    yatra=yatra,
                    profile=devotee,
                    defaults={'approved_by': mentor, 'is_approved': False}
                )
                eligibility.save()

                updated.append({
                    'profile_id': str(devotee.id),
                    'action': 'request_approval',
                    'status': 'pending',
                })

                    # TODO: Send email to mentor_request.to_mentor
                    # send_yatra_approval_request_email(mentor_request.to_mentor, mentor, yatra)

            if errors:
                return Response({'errors': errors}, status=400)
            return Response({
                'message': 'Approval request sent to your mentor.',
                'updated': updated
            }, status=200)

        for pid in profile_ids:
            try:
                profile = Profile.objects.get(id=pid)
            except Profile.DoesNotExist:
                errors.append(f'Invalid profile ID: {pid}')
                continue

            # BLOCK SELF-APPROVAL
            if profile == devotee:
                errors.append(
                    f"You cannot approve yourself. Please ask your mentor to approve you for this Yatra."
                )
                continue

            # Must be approved mentee via MentorRequest
            if not MentorRequest.objects.filter(
                from_user=profile,
                to_mentor=devotee,
                is_approved=True
            ).exists():
                errors.append(f'{profile.get_full_name()} is not your approved mentee')
                continue

            # Get or create eligibility
            eligibility, created = YatraEligibility.objects.get_or_create(
                yatra=yatra,
                profile=profile,
                defaults={'approved_by': devotee}
            )

            

            # === 4. UNAPPROVE: BLOCK IF ALREADY REGISTERED ===
            if action == 'unapprove':
                eligibility = YatraEligibility.objects.filter(
                yatra=yatra,
                profile=profile
                ).first()

                if not eligibility:
                    errors.append(f'{profile.get_full_name()} has no eligibility record to unapprove')
                    continue
                if YatraRegistration.objects.filter(
                    yatra=yatra,
                    registered_for=profile
                ).exists():
                    errors.append(
                        f"Cannot unapprove {profile.first_name}: "
                        "They are already registered for this Yatra."
                    )
                    continue

                # Only allow unapprove if currently approved
                if not eligibility.is_approved:
                    errors.append(f'{profile.first_name} is already not approved')
                    continue
                eligibility.delete()
                updated.append({
                'profile_id': str(profile.id),
                'action': 'unapprove',
                'status': 'removed'
                })
                continue

            if action == 'approve':
                eligibility, created = YatraEligibility.objects.get_or_create(
                    yatra=yatra,
                    profile=profile,
                    defaults={'approved_by': devotee, 'is_approved': True}
                )
            if not created:
                eligibility.is_approved = True
                eligibility.approved_by = devotee
                eligibility.save()

            updated.append({
                'profile_id': str(profile.id),
                'action': 'approve',
                'was_created': created,
                'is_approved': True
            })
            # eligibility.is_approved = (action == 'approve')
            # eligibility.approved_by = devotee
            # eligibility.save()

            updated.append({
                'profile_id': str(profile.id),
                'action': action,
                'was_created': created,
                'is_approved': eligibility.is_approved
            })

        if errors:
            return Response({'errors': errors, 'updated': updated}, status=400)

        return Response({
            'message': f'Updated eligibility for {len(updated)} devotee(s)',
            'updated': updated
        }, status=200)



# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from decimal import Decimal

class BatchPaymentProofView(APIView):
    @transaction.atomic
    def post(self, request, yatra_id):
        # 1. Extract data
        transaction_id = request.data.get('transaction_id')
        screenshot = request.FILES.get('screenshot')
        total_amount = Decimal(request.data.get('total_amount'))
        reg_ids = request.data.getlist('registration_ids')
        amounts = request.data.getlist('amounts')

        if len(reg_ids) != len(amounts):
            return Response({"error": "Mismatched IDs and amounts"}, status=400)

        # 2. Validate ownership
        registrations = YatraRegistration.objects.filter(
            id__in=reg_ids,
            yatra_id=yatra_id,
            registered_by=request.user
        )
        if registrations.count() != len(reg_ids):
            return Response({"error": "Invalid registrations"}, status=403)

        # 3. Validate total
        expected_total = sum(Decimal(a) for a in amounts)
        if expected_total != total_amount:
            return Response({"error": "Total mismatch"}, status=400)

        # 4. Create Batch Proof
        batch = BatchPaymentProof.objects.create(
            transaction_id=transaction_id,
            screenshot=screenshot,
            total_amount=total_amount,
            submitted_by=request.user
        )

        # 5. Allocate to each registration
        allocations = []
        for reg_id, amount in zip(reg_ids, amounts):
            reg = registrations.get(id=reg_id)
            allocations.append(
                BatchPaymentAllocation(
                    batch_proof=batch,
                    registration=reg,
                    amount_allocated=Decimal(amount)
                )
            )
        BatchPaymentAllocation.objects.bulk_create(allocations)

        return Response({
            "message": "Batch proof submitted. Awaiting verification.",
            "batch_id": batch.id
        }, status=201)


def generate_upi_qr(upi_id, amount, name, note="Yatra Payment"):
    upi_url = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR&tn={note}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()

def upi_qr_view(request):
    amount = request.GET.get('amount')
    reg_id = request.GET.get('reg')
    qr_img = generate_upi_qr("your-upi@bank", amount, "ISKCON Yatra", f"Reg: {reg_id}")
    return HttpResponse(qr_img, content_type="image/png")


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
            mentee.save(update_fields=["mentor"])

        # Delete request
        req.delete()

        # Send rejection email
        if mentee_email:
            send_mail(
                subject="Mentor Request Update",
                message=(
                    f"Dear {mentee.first_name or mentee.user.username},\n\n"
                    f"Your mentor request to {mentor_profile.first_name or mentor_profile.user.username} "
                    f"was not accepted at this time.\n\n"
                    f"Please feel free to request another mentor.\n\n"
                    f"Visit profile: {home_url}\n\n"
                    f"Hare Krishna!"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[mentee_email],
                fail_silently=True,
            )

        return Response({"message": "Request rejected."}, status=status.HTTP_200_OK)


