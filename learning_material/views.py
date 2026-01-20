# content/views.py
from rest_framework.generics import ListAPIView
from .models import Resource
from .serializers import ResourceSerializer
from .pagination import ResourcePagination

class ResourceListAPIView(ListAPIView):
    serializer_class = ResourceSerializer
    pagination_class = ResourcePagination

    def get_queryset(self):
        qs = Resource.objects.filter(is_active=True)

        params = self.request.query_params

        if params.get('yatra'):
            qs = qs.filter(yatra_id=params['yatra'])

        if params.get('event'):
            qs = qs.filter(event_id=params['event'])

        if params.get('language'):
            qs = qs.filter(language=params['language'])

        if params.get('category'):
            qs = qs.filter(category=params['category'])

        if params.get('type'):
            qs = qs.filter(resource_type=params['type'])

        return qs.order_by('order', '-created_at')
