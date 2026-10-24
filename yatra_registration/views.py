from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from yatra.serializers import *
from yatra_substitution.models import SubstitutionRequest
from .models import *
from userProfile.serializers import *
from .serializers import *
from userProfile.models import *
from payment.models import *
from .models import YatraRegistration
from django.db.models import (
    F, Value, CharField, OuterRef, Exists, Q
)
from django.db.models.functions import Concat, Lower
from django.utils import timezone
from uuid import UUID
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator


def active_registration_phase(yatra, on_date=None):
    """Return the most recently started phase active on the given date."""
    on_date = on_date or timezone.localdate()
    return (
        yatra.registration_phases
        .filter(start_date__lte=on_date)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=on_date))
        .order_by("-start_date", "-id")
        .first()
    )


def phase_for_registration(yatra, registration=None):
    """Keep an existing registration on its original phase forever."""
    if registration and registration.phase_id:
        has_phase_installment = registration.installments.filter(
            installment__phase_id=registration.phase_id
        ).exists()
        if has_phase_installment:
            return registration.phase

        # A registration row without a phase installment has not actually
        # started that phase. It may move to the currently active phase.
        return active_registration_phase(yatra)

    if registration:
        existing_phase = (
            registration.installments
            .filter(installment__phase__isnull=False)
            .select_related("installment__phase")
            .first()
        )
        if existing_phase:
            return existing_phase.installment.phase

        # Legacy registrations without phase-specific installments stay on
        # the legacy installment set instead of moving into a new phase.
        return None

    return active_registration_phase(yatra)


def installments_for_phase(yatra, phase=None):
    queryset = phase.installments if phase else yatra.installments.filter(phase__isnull=True)
    return list(queryset.all())


def phase_payload(phase):
    return RegistrationPhaseSummarySerializer(phase).data if phase else None


def profiles_for_reviewer(reviewer):
    """Return verified profiles from every Bace this reviewer manages."""
    reviewer_baces = Bace.objects.filter(
        is_active=True,
    ).filter(
        Q(mentors=reviewer) | Q(counsellor=reviewer)
    ).distinct()
    reviewer_bace_ids = reviewer_baces.values_list("id", flat=True)
    reviewer_bace_names = reviewer_baces.values_list("name", flat=True)
    other_center_names = OtherCenter.objects.filter(
        bace_id__in=reviewer_bace_ids,
        is_active=True,
    ).values_list("name", flat=True)
    reviewer_ids = Profile.objects.filter(
        Q(mentor_baces__in=reviewer_baces)
        | Q(counselled_baces__in=reviewer_baces)
    ).values_list("id", flat=True)
    approved_request_ids = MentorRequest.objects.filter(
        is_approved=True,
    ).filter(
        Q(requested_bace_id__in=reviewer_bace_ids)
        | (
            Q(to_mentor_id=reviewer)
            | (
                Q(to_mentor_id__in=reviewer_ids)
                & (
                    Q(from_user__center__in=reviewer_bace_names)
                    | Q(from_user__center__in=other_center_names)
                )
            )
        )
    ).values_list("from_user_id", flat=True)

    return Profile.objects.filter(
        id__in=approved_request_ids,
        profile_verification_status="verified",
    ).values_list("id", flat=True).distinct()




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
        mentee_ids = list(profiles_for_reviewer(mentor))

        # Always include self
        profile_ids = mentee_ids + [mentor.id]

        # =====================================================
        # 2. FETCH ALL PROFILES IN ONE QUERY
        # =====================================================
        profiles_qs = (
            Profile.objects
            .filter(id__in=profile_ids)
            .select_related('user', 'mentor')
            .order_by(Lower('first_name'), Lower('last_name'), 'id')
        )

        # Return profiles alphabetically, with the logged-in user's profile last.
        profiles = sorted(
            profiles_qs,
            key=lambda profile: (
                profile.id == mentor.id,
                (profile.first_name or "").lower(),
                (profile.last_name or "").lower(),
                str(profile.id),
            ),
        )

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
        # 6. POLICY: if requires_approval=False, mark all as approved
        # =====================================================
        policy = getattr(yatra, 'registration_policy', None)
        requires_approval = policy.requires_approval if policy else True

        if not requires_approval:
            for idx in range(len(profiles_data)):
                profiles_data[idx].update({
                    'is_approved': True,
                    'approved_by': None,
                    'approved_at': None,
                    'is_self': profiles[idx].id == mentor.id,
                })

        # =====================================================
        # 7. RESPONSE
        # =====================================================
        return Response({
            'yatra': {
                'id': str(yatra.id),
                'title': yatra.title,
                'requires_approval': requires_approval,
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

            # The profile may have no MentorRequest if the reviewer was
            # assigned to the Bace after the profile was verified.
            if not profiles_for_reviewer(devotee).filter(id=profile.id).exists():
                errors.append(f'{profile.get_full_name()} is not in a Center managed by you')
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
                mentees = list(profiles_for_reviewer(user_profile))
                profile_ids = list(mentees)

                # =====================================================
                # POLICY CHECK
                # =====================================================
                policy = getattr(yatra, 'registration_policy', None)
                requires_approval = policy.requires_approval if policy else True
                min_rounds = policy.min_chanting_rounds if policy else 0

                # =====================================================
                # ADD SELF IF ELIGIBLE
                # =====================================================
                if not requires_approval or YatraEligibility.objects.filter(
                    yatra=yatra,
                    profile=user_profile,
                    is_approved=True
                ).exists():
                    profile_ids.insert(0, user_profile.id)

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
                    .order_by(Lower('first_name'), Lower('last_name'), 'id')
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

                profiles_data = ProfileFastSerializer(profiles_qs, many=True).data

                # profile_map = {p['id']: p for p in profiles_data}
                profile_map = {UUID(p['id']): p for p in profiles_data}

                # =====================================================
                # ELIGIBILITY MAP
                # =====================================================
                eligibilities = (
                    YatraEligibility.objects
                    .filter(yatra=yatra, profile_id__in=profile_ids)
                    .select_related('approved_by')
                )
                eligibility_map = {e.profile_id: e for e in eligibilities}

                # =====================================================
                # REGISTRATIONS (FULLY PREFETCHED)
                # =====================================================
                registrations = (
                    YatraRegistration.objects
                    .filter(yatra=yatra, registered_for_id__in=profile_ids)
                    .select_related('registered_for', 'phase')
                    .prefetch_related(
                        'installments__installment',
                        'installments__payment',
                        'installments__verified_by',
                        'accommodation_allocations__accommodation',
                        'journey_allocations__journey',
                        'custom_values__custom_field_value__custom_field',
                    )
                )

                registration_map = {r.registered_for_id: r for r in registrations}
                legacy_installments = installments_for_phase(yatra)
                phase_installments = {
                    phase.id: list(phase.installments.all())
                    for phase in yatra.registration_phases.all()
                }

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

                # =====================================================
                # MERGE ALL DATA
                # =====================================================
                for pid in profile_ids:
                    pdata = profile_map.get(pid)
                    if not pdata:
                        print("⚠️ WARNING: profile missing in profile_map", pid)
                        continue

                    eligibility = eligibility_map.get(pid)
                    registration = registration_map.get(pid)
                    registration_phase = phase_for_registration(yatra, registration)
                    profile_installments = (
                        phase_installments.get(registration_phase.id, [])
                        if registration_phase
                        else legacy_installments
                    )

                    pdata.update({
                        'is_eligible': True if not requires_approval else (eligibility.is_approved if eligibility else False),
                        'is_self': pid == user_profile.id,
                        'registration_phase': phase_payload(registration_phase),
                        'approved_by': (
                            str(eligibility.approved_by.member_id)
                            if eligibility and eligibility.approved_by else None
                        ),
                    })

                    if registration:
                        reg_installments = list(registration.installments.all())
                        inst_map = {i.installment_id: i for i in reg_installments}

                        paid, pending = [], []
                        for inst in reg_installments:
                            (paid if inst.is_paid else pending).append(inst.installment.label)

                        for inst in profile_installments:
                            if inst.label not in paid and inst.label not in pending:
                                pending.append(inst.label)

                        installments_info = []
                        for inst in profile_installments:
                            ri = inst_map.get(inst.id)
                            tag = calculate_installment_tag(ri) if ri else "due"

                            installments_info.append({
                                "label": inst.label,
                                "amount": float(inst.amount),
                                "order": inst.order,
                                "start_date": inst.start_date,
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
                        pdata.update({
                            'is_registered': False,
                            'registration_status': "pending",
                            'form_data': {},
                            'paid_amount': 0,
                            'pending_amount': float(sum(i.amount for i in profile_installments)),
                            'installments_paid': [],
                            'installments_pending': [i.label for i in profile_installments],
                            'installments_info': [
                                {
                                    'label': i.label,
                                    'amount': float(i.amount),
                                    'order': i.order,
                                    'start_date': i.start_date,
                                    'tag': 'due',
                                }
                                for i in profile_installments
                            ],
                            'accommodation': [],
                            'journey': [],
                            'custom_fields': [],
                            'is_substitution': False,
                            'pending_substitution_fees': None,
                        })

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

        policy = getattr(yatra, 'registration_policy', None)
        requires_approval = policy.requires_approval if policy else True

        created_or_updated = []
        errors = []
        today = timezone.localdate()

        for profile_id, reg_data in registrations_data.items():
            try:
                profile = Profile.objects.get(id=profile_id)
            except Profile.DoesNotExist:
                errors.append(f'Invalid profile ID: {profile_id}')
                continue

            existing_registration = (
                YatraRegistration.objects
                .filter(yatra=yatra, registered_for=profile)
                .select_related('phase')
                .first()
            )
            registration_phase = phase_for_registration(yatra, existing_registration)
            if existing_registration is None:
                registration_phase = active_registration_phase(yatra)

            if (
                existing_registration
                and registration_phase
                and registration_phase.end_date
                and registration_phase.end_date < today
                and existing_registration.installments.filter(is_paid=False).exists()
            ):
                errors.append(
                    f'Registration has closed for {profile}; pending installments cannot be updated.'
                )
                continue

            phase_installments = installments_for_phase(yatra, registration_phase)
            valid_installments = {installment.label: installment for installment in phase_installments}

            # --- Eligibility check (skipped when requires_approval=False) ---
            if requires_approval and not self._check_eligibility(yatra, profile, registrant):
                errors.append(f'{profile} is not eligible for registration')
                continue

            # --- Extract fields ---
            form_fields = reg_data.get('form_fields', {})
            installments_selected = reg_data.get('installments_selected', [])
            installments_details = reg_data.get('installments_details', [])

            invalid_phase_installments = [
                label for label in installments_selected if label not in valid_installments
            ]
            if invalid_phase_installments:
                errors.append(
                    f'Invalid installment(s) for the selected registration phase: '
                    f'{", ".join(invalid_phase_installments)}'
                )
                continue

            existing_labels = set()
            if existing_registration:
                existing_labels = set(
                    existing_registration.installments.values_list(
                        'installment__label', flat=True
                    )
                )

            selected_labels = set(installments_selected)
            missing_order = []
            for index, installment in enumerate(phase_installments):
                if installment.label not in selected_labels:
                    continue
                missing_prerequisites = [
                    previous.label
                    for previous in phase_installments[:index]
                    if previous.label not in existing_labels
                    and previous.label not in selected_labels
                ]
                if missing_prerequisites:
                    missing_order.extend(missing_prerequisites)
            if missing_order:
                errors.append(
                    'Installments must be selected in order. Please select: '
                    f'{", ".join(dict.fromkeys(missing_order))}'
                )
                continue

            mandatory_indexes = [
                index
                for index, installment in enumerate(phase_installments)
                if installment.start_date and installment.start_date <= today
            ]
            required_labels = set()
            if mandatory_indexes:
                required_labels.update(
                    installment.label
                    for installment in phase_installments[: max(mandatory_indexes) + 1]
                )
            missing_required = sorted(required_labels - existing_labels - set(installments_selected))
            if missing_required:
                errors.append(
                    f'The following installments are mandatory: {", ".join(missing_required)}'
                )
                continue

            # --- Create or update registration ---
            registration, created_flag = YatraRegistration.objects.get_or_create(
                yatra=yatra,
                registered_for=profile,
                defaults={
                    'registered_by': registrant,
                    'phase': registration_phase,
                    'form_data': form_fields,
                    'status': 'partial' if installments_selected else 'pending',
                }
            )

            if not created_flag:
                registration.form_data = form_fields
                if registration.phase_id != getattr(registration_phase, 'id', None):
                    registration.phase = registration_phase
                registration.save()

            # --- Handle installments ---
            existing_labels = set(
                registration.installments.values_list('installment__label', flat=True)
            )

            for inst_label in installments_selected:
                try:
                    # Use the phase-scoped map validated above. Labels may
                    # legitimately repeat between different phases.
                    installment = valid_installments[inst_label]
                except YatraInstallment.DoesNotExist:
                    errors.append(f'Invalid installment "{inst_label}" for profile {profile}')
                    continue
                except KeyError:
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
            phase = active_registration_phase(yatra)
            installments = installments_for_phase(yatra, phase)
            installments_data = InstallmentSerializer(installments, many=True, context={'blank_mode': True}).data

            blank_data = {
                "id": None,
                "yatra": yatra.title,
                "registered_for": profile_id,
                "form_data": {},  # empty form
                "status": "not_registered",
                "registered_at": None,
                "updated_at": None,
                "phase": phase_payload(phase),
                "installments": [
                    {
                        "id": None,
                        "label": inst.label,
                        "amount": inst.amount,
                        "order": inst.order,
                        "start_date": inst.start_date,
                        "is_paid": False,
                        "tag": "due",
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


class TrackRCSDownloadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, registration_id):
        registration = get_object_or_404(
            YatraRegistration,
            id=registration_id
        )
        event, created = RCSDownloadEvent.objects.get_or_create(
            registration=registration
        )
        event.record_download()
        return Response(
            {
                "ok": True,
                "count": event.count,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

@method_decorator(staff_member_required, name="dispatch")
class MarkAttendanceView(View):

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
