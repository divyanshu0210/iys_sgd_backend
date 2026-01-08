from rest_framework import serializers
from .models import *
from payment.serializers import PaymentSerializer

class YatraFormFieldSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = YatraFormField
        fields = ['name', 'label', 'field_type', 'options', 'is_required']

    def get_options(self, obj):
        return obj.get_options_list()

class YatraInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = YatraInstallment
        fields = ['label', 'amount']

class YatraSerializer(serializers.ModelSerializer):
    form_fields = YatraFormFieldSerializer(many=True, read_only=True)
    installments = YatraInstallmentSerializer(many=True, read_only=True)

    class Meta:
        model = Yatra
        fields = [
            'id', 'title', 'description', 'start_date', 'end_date',
            'location', 'capacity', 'is_registration_open','payment_upi_id',    
            'form_fields', 'installments' , 'substitution_fee', 'cancellation_fee',
            'is_rcs_download_open','is_substitution_open','is_cancellation_open',  'close_yatra',
             'payment_refund_date',           # ✅ NEW
            'accept_full_payment_only_date',        # ✅ NEW
        ]

class AccommodationSerializer(serializers.ModelSerializer):
    class Meta:
        model = YatraAccommodation
        fields = "__all__"

class JourneySerializer(serializers.ModelSerializer):
    class Meta:
        model = YatraJourney
        fields = "__all__"

