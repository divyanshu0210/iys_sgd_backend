from django.http import JsonResponse
from allauth.account.views import ConfirmEmailView # type: ignore


from django.shortcuts import redirect

class CustomConfirmEmailView(ConfirmEmailView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.confirm(request)
        return redirect("http://localhost:5173/email-verified")

