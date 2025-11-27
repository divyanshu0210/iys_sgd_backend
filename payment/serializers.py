from rest_framework import serializers
from .models import *
from yatra.models import *
from rest_framework import serializers


class PaymentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField()
    processed_by = serializers.StringRelatedField()

    class Meta:
        model = Payment
        fields = [
            'id',
            'transaction_id',
            'total_amount',
            'proof',
            'uploaded_by',
            'uploaded_at',
            'status',
            'processed_by',
            'processed_at',
            'notes',
        ]

    
    def get_profile_picture_url(self, obj):
        request = self.context.get('request')
        if obj.proof and hasattr(obj.proof, 'url'):
            return request.build_absolute_uri(obj.proof.url) if request else obj.proof.url
        return None

import json

class RegistrationInstallmentSerializer(serializers.Serializer):
    profile_id = serializers.UUIDField()
    installments = serializers.ListField(child=serializers.CharField())

class BatchPaymentProofSerializer(serializers.Serializer):
    registration_installments = RegistrationInstallmentSerializer(many=True)
    transaction_id = serializers.CharField(required=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def to_internal_value(self, data):
        data = data.copy()
        reg_inst = data.get('registration_installments')
        if isinstance(reg_inst, str):
            try:
                data['registration_installments'] = json.loads(reg_inst)
            except json.JSONDecodeError:
                raise serializers.ValidationError({
                    "registration_installments": "Invalid JSON format"
                })
        return super().to_internal_value(data)
