from django.db import connections

class CloseDBConnectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Close all DB connections after every request
        connections.close_all()
        return response
