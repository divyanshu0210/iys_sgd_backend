# yatra_registration/admin_views.py

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.urls import reverse

from yatra.models import (
    Yatra, YatraAccommodation, YatraJourney,
    YatraCustomFieldValue, YatraCustomField
)
from .models import (
    YatraRegistration, RegistrationAccommodation,
    RegistrationJourney, RegistrationCustomFieldValue
)


@staff_member_required
def bulk_edit_view(request, yatra_id):
    yatra = get_object_or_404(Yatra, id=yatra_id)

    registrations = YatraRegistration.objects.filter(
        yatra=yatra,
        status__in=["partial", "paid", "attended"]
    ).select_related('registered_for').prefetch_related(
        'accommodation_allocations__accommodation',
        'journey_allocations__journey',
        'custom_values__custom_field_value__custom_field',
    )

    # Pre-build lookup for displaying selected custom field values
    custom_field_assignments = {}
    for reg in registrations:
        custom_field_assignments[reg.id] = {
            cfv.custom_field_value.custom_field_id: cfv.custom_field_value
            for cfv in reg.custom_values.all()
        }

    if request.method == "POST":
        selected_ids = request.POST.getlist("selected_regs")
        if not selected_ids:
            messages.warning(request, "No devotees selected.")
            return redirect(request.path)

        target_regs = registrations.filter(id__in=selected_ids)
        updated = 0

        # ------------------ Preload all possible objects ------------------
        # Existing accommodations and journeys for all selected registrations
        acc_allocs = RegistrationAccommodation.objects.filter(
            registration__in=target_regs
        ).select_related('accommodation')
        acc_alloc_map = {str(a.id): a for a in acc_allocs}

        journey_allocs = RegistrationJourney.objects.filter(
            registration__in=target_regs
        ).select_related('journey')
        journey_alloc_map = {str(j.id): j for j in journey_allocs}

        # All new accommodation/journey IDs in POST
        new_acc_ids = set()
        new_journey_ids = set()
        new_cf_val_ids = set()
        for key, val in request.POST.items():
            if key.startswith("new_acc_id_"):
                new_acc_ids.add(val)
            elif key.startswith("new_journey_id_"):
                new_journey_ids.add(val)
            elif key.startswith("cf_") and val:
                new_cf_val_ids.add(val)

        # Preload all new accommodation, journey, custom values
        acc_objs = YatraAccommodation.objects.filter(id__in=new_acc_ids)
        acc_obj_map = {str(a.id): a for a in acc_objs}

        journey_objs = YatraJourney.objects.filter(id__in=new_journey_ids)
        journey_obj_map = {str(j.id): j for j in journey_objs}

        cf_val_objs = YatraCustomFieldValue.objects.filter(id__in=new_cf_val_ids)
        cf_val_map = {str(c.id): c for c in cf_val_objs}

        with transaction.atomic():
            for reg in target_regs:
                changed = False

                # ------------------ ACCOMMODATIONS ------------------
                keep_acc_uuids = [
                    k.split('_')[-1] for k in request.POST if k.startswith(f'keep_acc_{reg.id}_')
                ]
                deleted_acc = reg.accommodation_allocations.exclude(id__in=keep_acc_uuids).delete()[0]
                if deleted_acc:
                    changed = True

                # Update existing allocations
                to_update_acc = []
                for key in request.POST:
                    if key.startswith("acc_room_"):
                        alloc_id = key.split("_")[-1]
                        if alloc_id not in keep_acc_uuids:
                            continue
                        alloc = acc_alloc_map.get(alloc_id)
                        if not alloc or alloc.registration_id != reg.id:
                            continue
                        new_room = request.POST.get(f"acc_room_{alloc_id}", "").strip() or None
                        new_bed = request.POST.get(f"acc_bed_{alloc_id}", "").strip() or None
                        if alloc.room_number != new_room or alloc.bed_number != new_bed:
                            alloc.room_number = new_room
                            alloc.bed_number = new_bed
                            to_update_acc.append(alloc)
                            changed = True
                if to_update_acc:
                    RegistrationAccommodation.objects.bulk_update(to_update_acc, ["room_number", "bed_number"])

                # Add new allocations
                new_acc_alloc_objs = []
                # For new accommodations
                for key, value in request.POST.items():
                    if key.startswith("new_acc_id_"):
                        # key = "new_acc_id_<reg_id>_<uid>"
                        rest = key[len("new_acc_id_"):]  # "<reg_id>_<uid>"
                        reg_in_key, uid = rest.split("_", 1)  # only split first "_"
                        if str(reg.id) != reg_in_key:
                            continue

                        acc_uuid = value
                        try:
                            # acc_obj = YatraAccommodation.objects.get(id=acc_uuid)
                            acc_obj = acc_obj_map.get(acc_uuid)
                        except YatraAccommodation.DoesNotExist:
                            continue

                        room = request.POST.get(f"new_acc_room_{reg.id}_{uid}", "").strip() or None
                        bed = request.POST.get(f"new_acc_bed_{reg.id}_{uid}", "").strip() or None

                        new_acc_alloc_objs.append(
                            RegistrationAccommodation(
                                registration=reg,
                                accommodation=acc_obj,
                                room_number=room,
                                bed_number=bed
                            )
                        )
                        changed = True


                if new_acc_alloc_objs:
                    RegistrationAccommodation.objects.bulk_create(new_acc_alloc_objs)

                # ------------------ JOURNEYS ------------------
                keep_journey_uuids = [
                    k.split("_")[-1] for k in request.POST if k.startswith(f"keep_journey_{reg.id}_")
                ]
                deleted_journey = reg.journey_allocations.exclude(id__in=keep_journey_uuids).delete()[0]
                if deleted_journey:
                    changed = True

                # Update existing allocations
                to_update_journey = []
                for key in request.POST:
                    if key.startswith("veh_"):
                        alloc_id = key.split("_")[-1]
                        if alloc_id not in keep_journey_uuids:
                            continue
                        alloc = journey_alloc_map.get(alloc_id)
                        if not alloc or alloc.registration_id != reg.id:
                            continue
                        new_veh = request.POST.get(f"veh_{alloc_id}", "").strip() or None
                        new_seat = request.POST.get(f"seat_{alloc_id}", "").strip() or None
                        if alloc.vehicle_number != new_veh or alloc.seat_number != new_seat:
                            alloc.vehicle_number = new_veh
                            alloc.seat_number = new_seat
                            to_update_journey.append(alloc)
                            changed = True
                if to_update_journey:
                    RegistrationJourney.objects.bulk_update(to_update_journey, ["vehicle_number", "seat_number"])

                # Add new journeys
                new_journey_alloc_objs = []
                # For new journeys
                for key, value in request.POST.items():
                    if key.startswith("new_journey_id_"):
                        rest = key[len("new_journey_id_"):]  # "<reg_id>_<uid>"
                        reg_in_key, uid = rest.split("_", 1)
                        if str(reg.id) != reg_in_key:
                            continue

                        journey_uuid = value
                        try:
                            # journey_obj = YatraJourney.objects.get(id=journey_uuid)
                            journey_obj = journey_obj_map.get(journey_uuid)
                        except YatraJourney.DoesNotExist:
                            continue

                        vehicle = request.POST.get(f"new_veh_{reg.id}_{uid}", "").strip() or None
                        seat = request.POST.get(f"new_seat_{reg.id}_{uid}", "").strip() or None

                        new_journey_alloc_objs.append(
                            RegistrationJourney(
                                registration=reg,
                                journey=journey_obj,
                                vehicle_number=vehicle,
                                seat_number=seat
                            )
                        )
                        changed = True

                if new_journey_alloc_objs:
                    RegistrationJourney.objects.bulk_create(new_journey_alloc_objs)

                # ------------------ CUSTOM FIELDS ------------------
                new_cf_vals = []
                for cf in yatra.custom_fields.all():
                    val_id = request.POST.get(f"cf_{cf.id}_{reg.id}")
                    current = reg.custom_values.filter(custom_field=cf).first()
                    current_val_id = str(current.custom_field_value_id) if current else None
                    if val_id != current_val_id:
                        if val_id:
                            value_obj = cf_val_map.get(val_id)
                            if value_obj:
                                new_cf_vals.append(
                                    RegistrationCustomFieldValue(
                                        registration=reg,
                                        custom_field=value_obj.custom_field,
                                        custom_field_value=value_obj
                                    )
                                )
                                changed = True
                        else:
                            reg.custom_values.filter(custom_field=cf).delete()
                            changed = True
                if new_cf_vals:
                    # Avoid duplicates
                    RegistrationCustomFieldValue.objects.bulk_create(new_cf_vals, ignore_conflicts=True)

                if changed:
                    updated += 1

        messages.success(request, f"Successfully updated {updated} devotee(s)!")
        return redirect(
            f"{reverse('admin:yatra_registration_yatraregistration_changelist')}?yatra__id__exact={yatra.id}"
        )

    # GET request — show form
    context = {
        'title': f"Bulk Edit — {yatra.title}",
        'yatra': yatra,
        'registrations': registrations,
        'accommodations': YatraAccommodation.objects.filter(yatra=yatra),
        'journeys': YatraJourney.objects.filter(yatra=yatra),
        'custom_fields': yatra.custom_fields.all().prefetch_related('values'),
        'custom_field_assignments': custom_field_assignments,
        'opts': YatraRegistration._meta,
    }

    return render(request, "admin/yatra_registration/bulk_edit.html", context)
