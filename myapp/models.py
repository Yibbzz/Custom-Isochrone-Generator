from django.contrib.gis.db import models
from django.conf import settings

class GeoData(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    geom = models.GeometryField()

    def __str__(self):
        return f"GeoData for {self.user.username}"

class BoxGeometry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    geom = models.GeometryField()

    def __str__(self):
        return f"DrawnGeometry by {self.user.username}"

class MarkerGeometry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    geom = models.GeometryField()

    def __str__(self):
        return f"MarkerGeometry for {self.user.username}"

class Isochrone(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    geom = models.GeometryField()

    def __str__(self):
        return f"Isochrone for {self.user.username}"

class NetworkType(models.Model):
    SELECTION_CHOICES = [
        ('motorway', 'Motorway'),
        ('residential', 'Residential'),
        ('path', 'Path'),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    selection = models.CharField(
        max_length=50, 
        choices=SELECTION_CHOICES, 
        default='motorway'  
    )
    mph = models.IntegerField(default=20, null=True, blank=True)  

    def __str__(self):
        return f"{self.user.username}'s preferences"

class IsochronePreferences(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mode_selection = models.CharField(max_length=10, default='foot')
    buckets = models.IntegerField(default=1)
    time_limit = models.IntegerField(default=10)

    def __str__(self):
        return f"{self.user.username}'s Isochrone Preferences"

class UserRoutingPod(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    service_name = models.CharField(max_length=50)
    pod_name = models.CharField(max_length=255, blank=True, null=True)  
    button_activate = models.BooleanField(default=False)

    def __str__(self):
        return f"UserRoutingPod for {self.user.username} (service_name: {self.service_name}, Pod Name: {self.pod_name})"
    
class UserPreviousInputs(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_geodata = models.ForeignKey(GeoData, on_delete=models.SET_NULL, null=True, blank=True)
    last_box_geometry = models.ForeignKey(BoxGeometry, on_delete=models.SET_NULL, null=True, blank=True)
    last_network_type = models.ForeignKey(NetworkType, on_delete=models.SET_NULL, null=True, blank=True)
    last_container_name = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Previous Inputs for {self.user.username}"

class UserSessionStatus(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_logged_in = models.BooleanField(default=True)
    session_expired = models.BooleanField(default=False)  

    def __str__(self):
        status = 'Logged In' if self.is_logged_in else 'Logged Out'
        expired_status = "Session Expired" if self.session_expired else "Session Active"
        return f"{self.user.username} - {status}, {expired_status}"