from django.urls import path
from .views import *

urlpatterns = [
    path("registrations/<uuid:reg_id>/substitute/", create_substitution_request),
    path("substitution_requests/", list_substitution_requests),
    path("substitution_requests/<uuid:req_id>/respond/", respond_substitution_request),
     path(
        "registrations/<uuid:reg_id>/existing/",
        get_existing_substitution_request,
        name="existing-substitution-request"
    ),
]
