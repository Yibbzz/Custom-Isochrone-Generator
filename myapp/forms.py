from django import forms
from django.core.exceptions import ValidationError
from .models import NetworkType, IsochronePreferences
from django.contrib.auth.forms import AuthenticationForm
from captcha.fields import CaptchaField
import os

class CustomAuthForm(AuthenticationForm):
    access_code = forms.CharField(label="Access Code", required=True)

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super(CustomAuthForm, self).__init__(*args, **kwargs)
        if request:
            failed_attempts = request.session.get('failed_attempts', 0)
            if failed_attempts >= 3:
                self.fields['captcha'] = CaptchaField()

    def clean(self):
        cleaned_data = super().clean()
        access_code = cleaned_data.get("access_code")
        valid_code = os.getenv('ACCESS_CODE')
        if access_code != valid_code:
            raise ValidationError("Invalid access code provided.")
        return cleaned_data

class NetworkTypeForm(forms.ModelForm):
    class Meta:
        model = NetworkType
        fields = ['selection', 'mph']
        widgets = {
            'selection': forms.RadioSelect
        }

    def clean(self):
        cleaned_data = super().clean()
        selection = cleaned_data.get('selection')
        mph = cleaned_data.get('mph')

        # Check if selection requires mph to be a positive number
        if selection in ['motorway', 'residential']:
            # Raise error if mph is None, 0, or empty string
            if mph is None or mph <= 0:
                raise ValidationError({'mph': 'This field is required and must be greater than 0 for motorway and residential selections.'})

        return cleaned_data

class GeoJSONUploadForm(forms.Form):
    file = forms.FileField()

    def clean_file(self):
        file = self.cleaned_data['file']

        # Check file size
        max_upload_size = 5242880 # 5MB
        if file.size > max_upload_size:
            raise ValidationError(f'File size should not exceed {max_upload_size / 1024 / 1024} MB.')

        # Check file type
        if not file.name.endswith('.geojson'):
            raise ValidationError('Invalid file type. Please upload a GeoJSON file.')

        return file

class IsochroneForm(forms.ModelForm):
    MODE_CHOICES = [
        ('car', 'Car'),
        ('foot', 'Walk'),
        ('bike', 'Cycle'),
    ]

    # Overriding the mode_selection field to use custom choices and widget
    mode_selection = forms.ChoiceField(choices=MODE_CHOICES, widget=forms.RadioSelect)

    class Meta:
        model = IsochronePreferences
        fields = ['mode_selection', 'buckets', 'time_limit']
        labels = {
            'buckets': 'Buckets',
            'time_limit': 'Time Limit (minutes)',
        }

    def clean_time_limit(self):
        time_limit = self.cleaned_data['time_limit']
        return time_limit

    def clean_buckets(self):
        buckets = self.cleaned_data['buckets']
        return buckets