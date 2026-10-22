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
        fields = ['label', 'amount', 'order', 'start_date']


class RegistrationPhaseSerializer(serializers.ModelSerializer):
    installments = YatraInstallmentSerializer(many=True, read_only=True)

    class Meta:
        model = RegistrationPhase
        fields = ['id', 'name', 'start_date', 'end_date', 'installments']

class YatraContactCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = YatraContactCategory
        fields = ['id', 'title', 'numbers','order', 'show_in_rcs']

class YatraImportantNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = YatraImportantNote
        fields = ['id', 'note', 'order', 'show_in_rcs']


class RegistrationPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrationPolicy
        fields = ['requires_approval', 'min_chanting_rounds']


class YatraSerializer(serializers.ModelSerializer):
    form_fields = YatraFormFieldSerializer(many=True, read_only=True)
    installments = serializers.SerializerMethodField()
    registration_phases = RegistrationPhaseSerializer(many=True, read_only=True)
    contact_categories  = YatraContactCategorySerializer(many=True, read_only=True)
    important_notes = YatraImportantNoteSerializer(many=True,read_only=True)
    registration_policy = RegistrationPolicySerializer(read_only=True)

    class Meta:
        model = Yatra
        fields = [
            'id', 'title', 'description', 'start_date', 'end_date',
            'location', 'capacity', 'is_registration_open','payment_upi_id',
            'form_fields', 'installments', 'registration_phases', 'substitution_fee', 'cancellation_fee',
            'is_rcs_download_open','is_substitution_open','is_cancellation_open',  'close_yatra',
             'payment_refund_date',
            'contact_categories',
            'important_notes',
            'registration_policy',
            'poster',
        ]

    def get_installments(self, obj):
        # The top-level list is reserved for pre-phase/legacy installments.
        # Phase installments are exposed only under their RegistrationPhase,
        # preventing consumers from accidentally mixing phases.
        legacy_installments = obj.installments.filter(phase__isnull=True)
        return YatraInstallmentSerializer(legacy_installments, many=True).data

class AccommodationSerializer(serializers.ModelSerializer):
    class Meta:
        model = YatraAccommodation
        fields = "__all__"

class JourneySerializer(serializers.ModelSerializer):
    class Meta:
        model = YatraJourney
        fields = "__all__"

