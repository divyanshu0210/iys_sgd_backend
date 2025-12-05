# admin_views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import  YatraRegistration, YatraJourney, YatraAccommodation
from yatra.models import Yatra
import uuid

def bulk_assign_details_view(request):
    yatras = Yatra.objects.all().order_by('-start_date')
    registrations = None

    if request.method == "POST":
        yatra_id = request.POST.get("yatra_id")
        selected_regs = request.POST.getlist("registration_ids")

        travel_id = request.POST.get("travel_id")
        accommodation_id = request.POST.get("accommodation_id")
        seat_number = request.POST.get("seat_number")
        room_number = request.POST.get("room_number")

        # ✔ Bulk update logic
        regs = YatraRegistration.objects.filter(id__in=selected_regs)

        for reg in regs:
            if travel_id:
                reg.journey_id = travel_id

            if accommodation_id:
                reg.accommodation_id = accommodation_id

            if seat_number:
                reg.seat_number = seat_number

            if room_number:
                reg.room_number = room_number

            reg.save()

        messages.success(request, "Bulk assignment completed successfully!")
        return redirect("admin:yatra_yatraregistration_changelist")

        # Initial GET
    yatra_id_str = request.GET.get("yatra")
    print("GET yatra param:", yatra_id_str)

    registrations = journeys = accommodations = []

    if yatra_id_str:
        try:
            yatra_uuid = uuid.UUID(yatra_id_str)
            yatra_instance = Yatra.objects.get(id=yatra_uuid)
            print("Found Yatra:", yatra_instance)

            registrations = YatraRegistration.objects.filter(yatra=yatra_instance).select_related('registered_for', 'registered_by')
            print(f"Registrations count: {registrations.count()}")
            print("Sample Registration:", registrations.first())

            journeys = YatraJourney.objects.filter(yatra=yatra_instance)
            print(f"Journeys count: {journeys.count()}")
            print("Sample Journey:", journeys.first())

            accommodations = YatraAccommodation.objects.filter(yatra=yatra_instance)
            print(f"Accommodations count: {accommodations.count()}")
            print("Sample Accommodation:", accommodations.first())

        except ValueError:
            print("Invalid UUID:", yatra_id_str)
        except Yatra.DoesNotExist:
            print("No Yatra found with ID:", yatra_id_str)
    else:
        journeys = accommodations = []

    return render(request, "admin/yatra_registration/bulk_assign_details.html", {
        "yatras": yatras,
        "registrations": registrations,
        "journeys": journeys,
        "accommodations": accommodations,
    })
