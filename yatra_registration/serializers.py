
from rest_framework import serializers
from .models import *
from payment.serializers import PaymentSerializer


class YatraEligibilitySerializer(serializers.ModelSerializer):
    profile_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = YatraEligibility
        fields = ['id', 'yatra', 'profile', 'profile_name', 'approved_by', 'approved_by_name', 
                  'is_approved', 'notes', 'approved_at']
    
    def get_profile_name(self, obj):
        return f"{obj.profile.first_name or ''} {obj.profile.last_name or ''}".strip()
    
    def get_approved_by_name(self, obj):
        return f"{obj.approved_by.first_name or ''} {obj.approved_by.last_name or ''}".strip()



class YatraRegistrationSerializer(serializers.ModelSerializer):
    registered_for_name = serializers.SerializerMethodField()
    registered_by_name = serializers.SerializerMethodField()

    class Meta:
        model = YatraRegistration
        fields = [
            'id',
            'yatra',
            'registered_by',
            'registered_by_name',
            'registered_for',
            'registered_for_name',
            'status',
            'registered_at'
        ]

    def get_registered_for_name(self, obj):
        return f"{obj.registered_for.first_name or ''} {obj.registered_for.last_name or ''}".strip()

    def get_registered_by_name(self, obj):
        return f"{obj.registered_by.first_name or ''} {obj.registered_by.last_name or ''}".strip()


# -------------------------------
# //note: The following serializers are added for detailed views of YatraRegistration and its installments.
# it has nothing to do with the inline installments in admin.
# -------------------------------    
class InstallmentSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source='installment.label', read_only=True)
    amount = serializers.DecimalField(source='installment.amount', max_digits=10, decimal_places=2, read_only=True)
    payment = PaymentSerializer(read_only=True)

    class Meta:
        model = YatraRegistrationInstallment
        fields = [
            'id',
            'label',
            'amount',
            'is_paid',
            'paid_at',
            'verified_by',
            'verified_at',
            'notes',
            'payment',
        ]

class YatraRegistrationDetailSerializer(serializers.ModelSerializer):
    registered_for = serializers.StringRelatedField()
    yatra = serializers.StringRelatedField()
    installments = InstallmentSerializer(many=True, read_only=True)

    class Meta:
        model = YatraRegistration
        fields = [
            'id',
            'yatra',
            'registered_for',
            'form_data',
            'status',
            'registered_at',
            'updated_at',
            'installments',
        ]



