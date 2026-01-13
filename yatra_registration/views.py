from django.http import JsonResponse
from django.shortcuts import render
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404

from yatra.serializers import *
from yatra_substitution.models import SubstitutionRequest
from .models import *
from userProfile.serializers import *
from .serializers import *
from userProfile.models import *
import uuid
from payment.models import *
from .models import YatraRegistration
from django.db.models import (
    F, Value, CharField, OuterRef, Exists
)
from django.db.models.functions import Concat
from uuid import UUID





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

    # def get(self, request, yatra_id):
    #     yatra = get_object_or_404(Yatra, id=yatra_id)
    #     mentor = request.user.profile

    #     # === 1. Get approved mentees from MentorRequest ===
    #     approved_requests = MentorRequest.objects.filter(
    #         to_mentor=mentor,
    #         is_approved=True
    #     ).select_related('from_user')
    #     mentees = [req.from_user for req in approved_requests]

    #     # === 2. Include self (mentor) in the list ===
    #     all_profiles = mentees + [mentor]  # self is always included

    #     # === 3. Build eligibility map ===
    #     profile_ids = [p.id for p in all_profiles]
    #     eligibilities = YatraEligibility.objects.filter(
    #         yatra=yatra,
    #         profile__id__in=profile_ids
    #     ).select_related('profile', 'approved_by')
    #     eligibility_map = {el.profile_id: el for el in eligibilities}

    #     serializer = ProfileFastSerializer(
    #     all_profiles,
    #     many=True,
    #     context={'request': request}
    #     )
    #     profiles_data = serializer.data

    #     # === 4. Build response data ===
    #     data = []
    #     for profile in all_profiles:
    #         profile_id = str(profile.id)
    #         el = eligibility_map.get(profile.id)

    #     # Append extra fields using index (safest)
    #     for idx, profile in enumerate(all_profiles):
    #         el = eligibility_map.get(profile.id)
    #         profiles_data[idx].update({
    #             'is_approved': el.is_approved if el else False,
    #             'approved_by': str(el.approved_by.member_id) if el and el.approved_by else None,
    #             'approved_at': el.approved_at.isoformat() if el and el.approved_at else None,
    #             'is_self': profile == mentor,
    #         })

    #     return Response({
    #     'yatra': {
    #         'id': str(yatra.id),
    #         'title': yatra.title,
    #     },
    #     'profiles': profiles_data,
    #     'total_mentees': len(mentees),
    #     'includes_self': True,
    # }, status=200)

    def get(self, request, yatra_id):
        yatra = get_object_or_404(Yatra, id=yatra_id)
        mentor = request.user.profile

        # =====================================================
        # 1. GET APPROVED MENTEE IDS (FAST)
        # =====================================================
        mentee_ids = list(
            MentorRequest.objects.filter(
                to_mentor=mentor,
                is_approved=True
            ).values_list('from_user_id', flat=True)
        )

        # Always include self
        profile_ids = mentee_ids + [mentor.id]

        # =====================================================
        # 2. FETCH ALL PROFILES IN ONE QUERY
        # =====================================================
        profiles_qs = (
            Profile.objects
            .filter(id__in=profile_ids)
            .select_related('user', 'mentor')
        )

        # Preserve original order (mentees first, self last)
        profile_order = {pid: idx for idx, pid in enumerate(profile_ids)}
        profiles = sorted(profiles_qs, key=lambda p: profile_order[p.id])

        # =====================================================
        # 3. FETCH ELIGIBILITY (MINIMAL)
        # =====================================================
        eligibilities = (
            YatraEligibility.objects
            .filter(yatra=yatra, profile_id__in=profile_ids)
            .select_related('approved_by')
            .only('profile_id', 'is_approved', 'approved_by', 'approved_at')
        )
        eligibility_map = {e.profile_id: e for e in eligibilities}

        # =====================================================
        # 4. SERIALIZE (FAST SERIALIZER)
        # =====================================================
        serializer = ProfileFastSerializer(
            profiles,
            many=True,
            context={'request': request}
        )
        profiles_data = serializer.data

        # =====================================================
        # 5. MERGE ELIGIBILITY DATA (O(N), NO DB)
        # =====================================================
        for idx, profile in enumerate(profiles):
            el = eligibility_map.get(profile.id)

            profiles_data[idx].update({
                'is_approved': el.is_approved if el else False,
                'approved_by': (
                    str(el.approved_by.member_id)
                    if el and el.approved_by else None
                ),
                'approved_at': (
                    el.approved_at.isoformat()
                    if el and el.approved_at else None
                ),
                'is_self': profile.id == mentor.id,
            })

        # =====================================================
        # 6. RESPONSE
        # =====================================================
        return Response({
            'yatra': {
                'id': str(yatra.id),
                'title': yatra.title,
            },
            'profiles': profiles_data,
            'total_mentees': len(mentee_ids),
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
            print("STEP 0: ENTER VIEW")
            # return Response({"detail": "This endpoint is under maintenance."}, status=200)

            try:
                yatra = get_object_or_404(Yatra, id=yatra_id)
                user_profile = request.user.profile
                print("STEP 1: yatra & user_profile OK", yatra.id, user_profile.id)

                # =====================================================
                # APPROVED MENTEES
                # =====================================================
                mentees = list(
                    MentorRequest.objects
                    .filter(to_mentor=user_profile, is_approved=True)
                    .values_list('from_user_id', flat=True)
                )
                print("STEP 2: mentees fetched", mentees)

                profile_ids = list(mentees)

                # =====================================================
                # ADD SELF IF ELIGIBLE
                # =====================================================
                if YatraEligibility.objects.filter(
                    yatra=yatra,
                    profile=user_profile,
                    is_approved=True
                ).exists():
                    profile_ids.insert(0, user_profile.id)

                print("STEP 3: profile_ids", profile_ids)

                # =====================================================
                # FAST PROFILE QUERY (ANNOTATED)
                # =====================================================
                approved_req = MentorRequest.objects.filter(
                    from_user=OuterRef('pk'),
                    is_approved=True
                )

                profiles_qs = (
                    Profile.objects
                    .filter(id__in=profile_ids)
                    .select_related('user', 'mentor')
                    .annotate(
                        full_name=Concat(
                            F('first_name'),
                            Value(' '),
                            F('last_name'),
                            output_field=CharField()
                        ),
                        mentor_name=Concat(
                            F('mentor__first_name'),
                            Value(' '),
                            F('mentor__last_name'),
                            output_field=CharField()
                        ),
                        is_profile_approved=Exists(approved_req),
                    )
                )

                print("STEP 4: profiles_qs COUNT =", profiles_qs.count())

                profiles_data = ProfileFastSerializer(profiles_qs, many=True).data
                print("STEP 5: profiles serialized", len(profiles_data))

                # profile_map = {p['id']: p for p in profiles_data}
                profile_map = {UUID(p['id']): p for p in profiles_data}

                print("STEP 6: profile_map keys", profile_map.keys())

                # =====================================================
                # ELIGIBILITY MAP
                # =====================================================
                eligibilities = (
                    YatraEligibility.objects
                    .filter(yatra=yatra, profile_id__in=profile_ids)
                    .select_related('approved_by')
                )
                eligibility_map = {e.profile_id: e for e in eligibilities}

                print("STEP 7: eligibility_map keys", eligibility_map.keys())

                # =====================================================
                # REGISTRATIONS (FULLY PREFETCHED)
                # =====================================================
                registrations = (
                    YatraRegistration.objects
                    .filter(yatra=yatra, registered_for_id__in=profile_ids)
                    .select_related('registered_for')
                    .prefetch_related(
                        'installments__installment',
                        'installments__payment',
                        'installments__verified_by',
                        'accommodation_allocations__accommodation',
                        'journey_allocations__journey',
                        'custom_values__custom_field_value__custom_field',
                    )
                )

                print("STEP 8: registrations COUNT =", registrations.count())

                registration_map = {r.registered_for_id: r for r in registrations}
                yatra_installments = list(yatra.installments.all())

                print("STEP 9: yatra_installments", [i.label for i in yatra_installments])

                # =====================================================
                # SUBSTITUTION REQUESTS (BULK)
                # =====================================================
                substitution_map = {
                    s.new_registration_id: s
                    for s in SubstitutionRequest.objects.filter(
                        new_registration__in=registrations,
                        status="accepted",
                        fee_collected=False
                    )
                }

                print("STEP 10: substitution_map keys", substitution_map.keys())

                # =====================================================
                # MERGE ALL DATA
                # =====================================================
                for pid in profile_ids:
                    print("STEP 11: processing profile", pid)

                    pdata = profile_map.get(pid)
                    if not pdata:
                        print("⚠️ WARNING: profile missing in profile_map", pid)
                        continue

                    eligibility = eligibility_map.get(pid)
                    registration = registration_map.get(pid)

                    pdata.update({
                        'is_eligible': eligibility.is_approved if eligibility else False,
                        'is_self': pid == user_profile.id,
                        'approved_by': (
                            str(eligibility.approved_by.member_id)
                            if eligibility and eligibility.approved_by else None
                        ),
                    })

                    if registration:
                        print("STEP 12: has registration", registration.id)

                        reg_installments = list(registration.installments.all())
                        inst_map = {i.installment_id: i for i in reg_installments}

                        paid, pending = [], []
                        for inst in reg_installments:
                            (paid if inst.is_paid else pending).append(inst.installment.label)

                        for inst in yatra_installments:
                            if inst.label not in paid and inst.label not in pending:
                                pending.append(inst.label)

                        installments_info = []
                        for inst in yatra_installments:
                            ri = inst_map.get(inst.id)
                            if ri:
                                if ri.is_paid:
                                    tag = "verified"
                                elif ri.payment and ri.verified_by:
                                    tag = ri.payment.status
                                elif ri.payment:
                                    tag = "verification pending"
                                else:
                                    tag = "due"
                            else:
                                tag = "due"

                            installments_info.append({
                                "label": inst.label,
                                "amount": float(inst.amount),
                                "tag": tag,
                            })

                        pdata.update({
                            'is_registered': True,
                            'registration_id': str(registration.id),
                            'registration_status': registration.status,
                            'form_data': registration.form_data,
                            # 'paid_amount': float(registration.paid_amount),
                            # 'pending_amount': float(registration.pending_amount),
                            'installments_paid': paid,
                            'installments_pending': pending,
                            'installments_info': installments_info,
                            'accommodation': [
                            {
                                "accommodation": AccommodationSerializer(
                                    a.accommodation, context={'request': request}
                                ).data,
                                "room_number": a.room_number,
                                "bed_number": a.bed_number,
                            }
                            for a in registration.accommodation_allocations.all()
                            ],
                            'journey': [
                                {
                                    "journey": JourneySerializer(
                                        j.journey, context={'request': request}
                                    ).data,
                                    "vehicle_number": j.vehicle_number,
                                    "seat_number": j.seat_number,
                                }
                                for j in registration.journey_allocations.all()
                            ],
                            'custom_fields': [
                                {
                                    "field": v.custom_field_value.custom_field.field_name,
                                    "value": v.custom_field_value.value,
                                }
                                for v in registration.custom_values.all()
                            ],
                        })

                        sub_req = substitution_map.get(registration.id)
                        pdata.update({
                            'is_substitution': bool(sub_req),
                            'pending_substitution_fees': (
                                {
                                    "cancellation_fee": float(yatra.cancellation_fee or 0),
                                    "substitution_fee": float(yatra.substitution_fee or 0),
                                    "total": float(
                                        (yatra.cancellation_fee or 0) +
                                        (yatra.substitution_fee or 0)
                                    ),
                                } if sub_req else None
                            )
                        })

                    else:
                        print("STEP 13: NOT registered", pid)
                        pdata.update({
                            'is_registered': False,
                            'registration_status': "pending",
                            'form_data': {},
                            'paid_amount': 0,
                            'pending_amount': float(sum(i.amount for i in yatra_installments)),
                            'installments_paid': [],
                            'installments_pending': [i.label for i in yatra_installments],
                            'installments_info': [
                                {'label': i.label, 'amount': float(i.amount), 'tag': 'due'}
                                for i in yatra_installments
                            ],
                            'accommodation': [],
                            'journey': [],
                            'custom_fields': [],
                            'is_substitution': False,
                            'pending_substitution_fees': None,
                        })

                print("STEP 14: RESPONSE READY")

                return Response({
                    "yatra": YatraSerializer(yatra, context={'request': request}).data,
                    "profiles": list(profile_map.values()),
                })

            except Exception as e:
                print("❌ ERROR OCCURRED:", type(e).__name__, str(e))
                raise

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

    def delete(self, request, yatra_id):
        """
        Cancel an existing registration.
        Expected input:
        {
            "profile_id": "<profile_uuid>"
        }
        """
        profile_id = request.data.get("profile_id")
        if not profile_id:
            return Response({"error": "profile_id is required"}, status=400)

        yatra = get_object_or_404(Yatra, id=yatra_id)
        profile = get_object_or_404(Profile, id=profile_id)
        requester = request.user.profile

        # ---- 1. Fetch registration ----
        try:
            registration = YatraRegistration.objects.get(
                yatra=yatra,
                registered_for=profile
            )
        except YatraRegistration.DoesNotExist:
            return Response({"error": "Registration not found"}, status=404)
        
        if registration.status == "attended":
            return Response(
                {"error": "Cannot cancel. Devotee has already attended the Yatra."},
                status=400
            )
        
        if registration.has_any_installment_under_verification():
            return Response(
                {
                    "error": "Cancellation is not allowed because an installment verification is pending."
                },
                status=400
    )
        
        active_substitution = (
            SubstitutionRequest.objects
            .filter(
                registration=registration,
                initiator=profile,
                status="pending",
                expires_at__gt=timezone.now()
            )
            .order_by("-created_at")
            .first()
        )

        if active_substitution:
            return Response(
                {
                    "error": "Cancellation not allowed while a substitution request is active. Try after the request is expired.",
                    "substitution_request_id": str(active_substitution.id)
                },
                status=400
            )

        # ---- 2. Check permission ----
        # Self cancel
        if requester == profile:
            allowed = True

        # Mentor cancel
        elif MentorRequest.objects.filter(
            from_user=profile,
            to_mentor=requester,
            is_approved=True
        ).exists():
            allowed = True

        # Admin cancel
        elif requester.user.is_staff:
            allowed = True

        else:
            return Response(
                {"error": "You are not allowed to cancel this registration."},
                status=403
            )
        
        # ---- 4. Mark registration as cancelled ----
        registration.status = "cancelled"
        registration.save()

        # ---- 5. Delete allocations ----
        # registration.accommodation_allocations.all().delete()
        # registration.journey_allocations.all().delete()
        # registration.custom_values.all().delete()

        return Response({
            "message": "Registration cancelled successfully.",
            "registration_id": str(registration.id),
            "status": "cancelled"
        }, status=200)
    
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


class MarkAttendanceView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, registration_id):
        try:
            reg = YatraRegistration.objects.get(id=registration_id)
        except YatraRegistration.DoesNotExist:
            return render(request, "attendance_result.html", {
                "title": "Invalid QR",
                "message": "No registration found.",
            })

        profile = reg.registered_for
        substitution = None

        # Already attended
        if reg.status == "attended":
            return render(request, "attendance_result.html", {
                "title": "QR Verification",
                "message": "Attendance already marked.",
                "profile": profile,
                "reg": reg,
            })

        # Not fully paid
        if reg.status != "paid":
            return render(request, "attendance_result.html", {
                "title": "QR Verification",
                "message": "Registration is not completed (payment pending).",
                "profile": profile,
                "reg": reg,
            })

        # Check for substitution
        substitution = SubstitutionRequest.objects.filter(
            target_profile=profile,
            new_registration=reg,
            status="accepted",
            fee_collected=False,
        ).first()

        if substitution:
            cancellation_fee = reg.yatra.cancellation_fee
            substitution_fee = reg.yatra.substitution_fee
            amount_to_collect = cancellation_fee + substitution_fee

            return render(request, "attendance_result.html", {
                "title": "Substitution Detected",
                "message": f"{profile.first_name} {profile.last_name} has been substituted.",
                "substitution": True,
                "amount_to_collect": amount_to_collect,
                "cancellation_fee": cancellation_fee,
                "substitution_fee": substitution_fee,
                "original_paid": reg.paid_amount,
                "substitution_id": substitution.id,
                "profile": profile,
                "reg": reg,
                "substitution_obj": substitution,  # optional, for extra info if needed
            })

        # Normal attendance marking
        reg.status = "attended"
        reg.save()

        return render(request, "attendance_result.html", {
            "title": "Attendance Marked",
            "message": f"{profile.first_name} {profile.last_name}'s attendance has been marked successfully.",
            "profile": profile,
            "reg": reg,
        })
    
    def post(self, request, registration_id):
        try:
            reg = YatraRegistration.objects.get(id=registration_id)
        except YatraRegistration.DoesNotExist:
            return JsonResponse({
                "success": False,
                "message": "Registration not found."
            })

        profile = reg.registered_for

        # Prevent re-attendance
        if reg.status == "attended":
            return JsonResponse({
                "success": True,
                "message": "Attendance already marked."
            })

        if reg.status != "paid":
            return JsonResponse({
                "success": False,
                "message": "Registration incomplete (payment pending)."
            })

        # Substitution case
        substitution = SubstitutionRequest.objects.filter(
            new_registration=reg,
            status="accepted",
            fee_collected=False,
        ).first()

        if substitution:
            substitution.fee_collected = True
            substitution.save()

        reg.status = "attended"
        reg.save()

        return JsonResponse({
            "success": True,
            "message": "Attendance marked successfully."
        })
