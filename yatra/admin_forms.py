from django import forms

SMALL_TEXTAREA = forms.Textarea(attrs={'rows': 2, 'cols': 40})


from django import forms
from .models import *
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

class YatraContactCategoryForm(forms.ModelForm):
    class Meta:
        model = YatraContactCategory
        fields = "__all__"
        widgets = {
            'numbers': forms.Textarea(attrs={
                'rows': 2,
                'cols': 50,
                "style": "width: 95%;",
                'placeholder': 'Comma-separated numbers, e.g. 1234567890, Dr. Ramesh:1234567891'
            }),
        }


class YatraImportantNoteForm(forms.ModelForm):
    class Meta:
        model = YatraImportantNote
        fields = "__all__"
        widgets = {
            "note": forms.Textarea(attrs={
                'rows': 2,
                'cols': 40,
                "style": "width: 95%;",
                "placeholder": "Enter point-wise note"
            })
        }


class PhaseInstallmentForm(forms.ModelForm):
    """Keep the first phase installment date tied to the phase start date."""

    class Meta:
        model = YatraInstallment
        fields = ['label', 'amount', 'order', 'start_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.phase_id:
            first = (
                YatraInstallment.objects
                .filter(phase_id=self.instance.phase_id)
                .order_by('order', 'id')
                .first()
            )
            is_first_existing = first and first.pk == self.instance.pk
            is_first_new = not self.instance.pk and first is None
            if is_first_existing or is_first_new:
                self.fields['start_date'].disabled = True
                self.initial['start_date'] = self.instance.phase.start_date

    def clean(self):
        cleaned = super().clean()
        phase = self.instance.phase if self.instance.phase_id else None
        if not phase:
            return cleaned

        other = (
            YatraInstallment.objects
            .filter(phase_id=phase.id)
            .exclude(pk=self.instance.pk)
            .order_by('order', 'id')
            .first()
        )
        order = cleaned.get('order', self.instance.order)
        if other is None or order <= other.order:
            cleaned['start_date'] = phase.start_date
        return cleaned
