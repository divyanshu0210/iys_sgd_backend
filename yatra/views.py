from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404
from .models import *
from userProfile.serializers import ProfileSerializer
from .serializers import *
from userProfile.models import *
import uuid
from payment.models import *
from yatra_registration.models import YatraEligibility, YatraRegistration


# Create your views here.
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
        data = serializer.data

        # The public list also serves authenticated users. Expose only a
        # boolean indicating whether this user has started this Yatra's
        # approval/registration process; do not expose private details.
        process_yatra_ids = set()
        if request.user.is_authenticated:
            profile_id = Profile.objects.filter(
                user=request.user
            ).values_list('id', flat=True).first()
            if profile_id:
                process_yatra_ids.update(
                    YatraEligibility.objects.filter(
                        profile_id=profile_id
                    ).values_list('yatra_id', flat=True)
                )
                process_yatra_ids.update(
                    YatraRegistration.objects.filter(
                        registered_for_id=profile_id
                    ).values_list('yatra_id', flat=True)
                )

        for item in data:
            item['registration_in_progress'] = item['id'] in process_yatra_ids

        return Response(data)

    def post(self, request):
        serializer = YatraSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # creates a new Yatra in DB
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

