from django.shortcuts import render
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404

from yatra.serializers import *
from .models import *
from userProfile.serializers import ProfileSerializer
from .serializers import *
from userProfile.models import *
import uuid
from payment.models import *
from .models import YatraRegistration




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
    

class YatraRegistrationView(APIView):
    """
    Handle registration creation and management
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, yatra_id):
        """
        Get registration + eligibility status for all eligible profiles
        """
        yatra = get_object_or_404(Yatra, id=yatra_id)
        user_profile = request.user.profile

        # === GET APPROVED MENTEES ===
        approved_mentee_requests = MentorRequest.objects.filter(
            to_mentor=user_profile,
            is_approved=True
        ).select_related('from_user')

        mentees = [req.from_user for req in approved_mentee_requests]
        all_profiles = mentees.copy()

        # === Add self if approved ===
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

        # === Existing Registrations ===
        existing_registrations = YatraRegistration.objects.filter(
            yatra=yatra,
            registered_for__in=all_profiles
        ).select_related('registered_for').prefetch_related('installments__installment',
                                                            'accommodation_allocations__accommodation',
            'journey_allocations__journey',
            'custom_values__custom_field_value__custom_field')

        registration_map = {reg.registered_for_id: reg for reg in existing_registrations}

        # === Yatra Installments ===
        yatra_installments = yatra.installments.all()

        # === Serialize Profiles ===
        serializer = ProfileSerializer(all_profiles, many=True, context={'request': request})
        profiles_data = serializer.data

        # === Merge Eligibility + Registration Info ===
        for profile_data in profiles_data:
            profile_id = uuid.UUID(profile_data['id'])
            profile_obj = next((p for p in all_profiles if p.id == profile_id), None)
            registration = registration_map.get(profile_id)
            eligibility = eligibility_map.get(profile_id)

            # Eligibility fields
            profile_data.update({
                'is_eligible': eligibility.is_approved if eligibility else False,
                'is_self': profile_obj == user_profile,
                'approved_by': (
                    str(eligibility.approved_by.member_id)
                    if eligibility and eligibility.approved_by else None
                ),
            })

            # Registration fields
            if registration:
                paid_installments = []
                pending_installments = []

                for inst in registration.installments.all():
                    if inst.is_paid:
                        paid_installments.append(inst.installment.label)
                    else:
                        pending_installments.append(inst.installment.label)

                # Include installments not yet created
                existing_labels = [inst.installment.label for inst in registration.installments.all()]
                for yatra_inst in yatra_installments:
                    if yatra_inst.label not in existing_labels:
                        pending_installments.append(yatra_inst.label)

            
            if registration:
                installments_info = []

                for inst in yatra_installments:
                    reg_inst = registration.installments.filter(installment=inst).first()

                    if reg_inst:
                        if reg_inst.is_paid:
                            tag = "verified"
                        elif reg_inst.payment and reg_inst.verified_by:
                            tag = reg_inst.payment.status
                        elif reg_inst.payment and not reg_inst.verified_by:
                            tag = "verification pending"
                        else:
                            tag = "due"
                    else:
                        tag = "due"

                    installments_info.append({
                        'label': inst.label,
                        'amount': float(inst.amount),
                        'tag': tag
                    })  

                        # ========================
                # ACCOMMODATION SUMMARY
                # ========================
                accommodation_data = []
                for alloc in registration.accommodation_allocations.all():
                    # accommodation_data.append({
                    #     "accommodation": alloc.accommodation,
                    #     "room_number": alloc.room_number,
                    #     "bed_number": alloc.bed_number
                    # })
                    accommodation_data.append({
                        "accommodation": AccommodationSerializer(
                            alloc.accommodation, 
                            context={'request': request}
                        ).data,
                        "room_number": alloc.room_number,
                        "bed_number": alloc.bed_number
                    })


                # ========================
                # JOURNEY SUMMARY
                # ========================
                journey_data = []
                for j in registration.journey_allocations.all():
                    journey_data.append({
                         "journey": JourneySerializer(
                            j.journey, 
                            context={'request': request}
                        ).data,
                        "vehicle_number": j.vehicle_number,
                        "seat_number": j.seat_number,
                    })

                # ========================
                # CUSTOM FIELD SUMMARY
                # ========================
                custom_fields = []
                for v in registration.custom_values.all():
                    custom_fields.append({
                        "field": v.custom_field_value.custom_field.field_name,
                        "value": v.custom_field_value.value
                    })

                profile_data.update({
                    'is_registered': True,
                    'registration_id': str(registration.id),
                    'registration_status': registration.status,
                    'form_data': registration.form_data,
                    'paid_amount': float(registration.paid_amount),
                    'pending_amount': float(registration.pending_amount),
                    'installments_paid': paid_installments,
                    'installments_pending': pending_installments,
                    'installments_info': installments_info,

                    'accommodation': accommodation_data,
                    'journey': journey_data,
                    'custom_fields': custom_fields,
                })
            else:
                installments_info = [
                {'label': inst.label, 'amount': float(inst.amount), 'tag': 'due'}
                for inst in yatra_installments
            ]
                profile_data.update({
                    'is_registered': False,
                    'registration_status': "pending",
                    'form_data': {},
                    'paid_amount': 0,
                    'pending_amount': float(sum(inst.amount for inst in yatra_installments)),
                    'installments_paid': [],
                    'installments_pending': [inst.label for inst in yatra_installments],
                    'installments_info': installments_info,

                    'accommodation': [],
                    'journey': [],
                    'custom_fields': [],
                })

        return Response({
            'yatra': YatraSerializer(yatra, context={'request': request}).data,
            'profiles': profiles_data,
        })
    


    def post(self, request, yatra_id):
        """
        Create or update registrations for multiple profiles in one request.
        Expected format:
        {
            "<profile_id>": {
                "form_fields": {...},
                "installments_selected": [...],
                "installments_paid": [...],
                "installments_details": [...],
                "hasProof": false,
                "amount": 6500
            },
            ...
        }
        """
        yatra = get_object_or_404(Yatra, id=yatra_id)
        registrant = request.user.profile
        registrations_data = request.data  # dict of profile_id -> registration info

        if not isinstance(registrations_data, dict):
            return Response({'error': 'Invalid data format. Expected object of profile_id -> registration info.'},
                            status=status.HTTP_400_BAD_REQUEST)

        created_or_updated = []
        errors = []

        for profile_id, reg_data in registrations_data.items():
            try:
                profile = Profile.objects.get(id=profile_id)
            except Profile.DoesNotExist:
                errors.append(f'Invalid profile ID: {profile_id}')
                continue

            # --- Eligibility check ---
            if not self._check_eligibility(yatra, profile, registrant):
                errors.append(f'{profile} is not eligible for registration')
                continue

            # --- Extract fields ---
            form_fields = reg_data.get('form_fields', {})
            installments_selected = reg_data.get('installments_selected', [])
            installments_details = reg_data.get('installments_details', [])

            # --- Create or update registration ---
            registration, created_flag = YatraRegistration.objects.get_or_create(
                yatra=yatra,
                registered_for=profile,
                defaults={
                    'registered_by': registrant,
                    'form_data': form_fields,
                    'status': 'partial' if installments_selected else 'pending',
                }
            )

            if not created_flag:
                registration.form_data = form_fields
                registration.save()

            # --- Handle installments ---
            existing_labels = set(
                registration.installments.values_list('installment__label', flat=True)
            )

            for inst_label in installments_selected:
                try:
                    installment = YatraInstallment.objects.get(yatra=yatra, label=inst_label)
                except YatraInstallment.DoesNotExist:
                    errors.append(f'Invalid installment "{inst_label}" for profile {profile}')
                    continue

                reg_inst, _ = YatraRegistrationInstallment.objects.get_or_create(
                    registration=registration,
                    installment=installment
                )

                # Update payment-related details if provided
                matching_detail = next((i for i in installments_details if i['label'] == inst_label), None)
                if matching_detail:
                    reg_inst.is_paid = matching_detail.get('is_paid', reg_inst.is_paid)
                    reg_inst.save()

            created_or_updated.append(registration)

        # --- Return response ---
        return Response({
            'message': f'{len(created_or_updated)} registrations processed successfully',
            'errors': errors,
            'registrations': YatraRegistrationSerializer(created_or_updated, many=True).data
        }, status=status.HTTP_200_OK if created_or_updated else status.HTTP_400_BAD_REQUEST)

    
    
    def _check_eligibility(self, yatra, profile, registrant):
        """Check if profile is eligible for registration"""
        if profile == registrant:
            try:
                eligibility = YatraEligibility.objects.get(yatra=yatra, profile=profile)
                return eligibility.is_approved
            except YatraEligibility.DoesNotExist:
                return False
        else:
            if not MentorRequest.objects.filter(
                from_user=profile,
                to_mentor=registrant,
                is_approved=True
            ).exists():
                return False
            
            try:
                eligibility = YatraEligibility.objects.get(yatra=yatra, profile=profile)
                return eligibility.is_approved
            except YatraEligibility.DoesNotExist:
                return False

class YatraRegistrationDetailView(APIView):
    """
    GET /yatras/<yatra_id>/registrations/<profile_id>/
    → Returns form data, installments, and payment details
    """

    def get(self, request, yatra_id, profile_id):
        try:
            registration = YatraRegistration.objects.get(
                yatra_id=yatra_id,
                registered_for_id=profile_id
            )
            serializer = YatraRegistrationDetailSerializer(registration,context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        except YatraRegistration.DoesNotExist:
            # User not registered yet — return blank structure
            yatra = get_object_or_404(Yatra, id=yatra_id)
            installments = yatra.installments.all()
            installments_data = InstallmentSerializer(installments, many=True, context={'blank_mode': True}).data

            blank_data = {
                "id": None,
                "yatra": yatra.title,
                "registered_for": profile_id,
                "form_data": {},  # empty form
                "status": "not_registered",
                "registered_at": None,
                "updated_at": None,
                "installments": [
                    {
                        "id": None,
                        "label": inst.label,
                        "amount": inst.amount,
                        "is_paid": False,
                        "paid_at": None,
                        "verified_by": None,
                        "verified_at": None,
                        "notes": None,
                        "payment": None,
                    }
                    for inst in installments
                ],
            }
            return Response(blank_data, status=status.HTTP_200_OK)
