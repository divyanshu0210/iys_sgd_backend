from django import forms

SMALL_TEXTAREA = forms.Textarea(attrs={'rows': 2, 'cols': 40})


from django import forms
from .models import (
    Yatra, YatraFormField, YatraJourney,
    YatraAccommodation, YatraCustomFieldValue
)
from .admin_forms import SMALL_TEXTAREA

class YatraForm(forms.ModelForm):
    class Meta:
        model = Yatra
        fields = "__all__"
        widgets = {
            'description': SMALL_TEXTAREA,
        }


class YatraFormFieldForm(forms.ModelForm):
    class Meta:
        model = YatraFormField
        fields = "__all__"
        widgets = {
            'options': SMALL_TEXTAREA,
        }


class YatraJourneyForm(forms.ModelForm):
    class Meta:
        model = YatraJourney
        fields = "__all__"
        widgets = {
            'remarks': SMALL_TEXTAREA,
        }


class YatraAccommodationForm(forms.ModelForm):
    class Meta:
        model = YatraAccommodation
        fields = "__all__"
        widgets = {
            'address': SMALL_TEXTAREA,
            'notes': SMALL_TEXTAREA,
        }


class YatraCustomFieldValueForm(forms.ModelForm):
    class Meta:
        model = YatraCustomFieldValue
        fields = "__all__"
        widgets = {
            'value': SMALL_TEXTAREA,
        }
