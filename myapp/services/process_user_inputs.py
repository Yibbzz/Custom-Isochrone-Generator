import json

from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpRequest
from django.shortcuts import redirect
from django.contrib.gis.geos import GEOSGeometry

from ..forms import NetworkTypeForm, GeoJSONUploadForm, IsochroneForm 
from ..models import GeoData, BoxGeometry, MarkerGeometry, IsochronePreferences, Isochrone, NetworkType

def fetch_preferences(user: User) -> tuple:
    """
    Fetches or creates network and isochrone preferences for a given user.

    Args:
        user (User): The user for whom to fetch or create preferences.

    Returns:
        tuple: A tuple containing network preferences and isochrone preferences.
    """
    network_preferences, _ = NetworkType.objects.get_or_create(user=user)
    isochrone_preferences, _ = IsochronePreferences.objects.get_or_create(user=user)
    return network_preferences, isochrone_preferences


def fetch_forms(user: User) -> tuple:
    """
    Fetches forms for GeoJSON upload, network preferences, and isochrone settings.

    Args:
        user (User): The user for whom to fetch forms.

    Returns:
        tuple: A tuple containing the GeoJSON upload form, network preferences form, and isochrone settings form.
    """
    geo_upload_form = GeoJSONUploadForm()
    network_preferences, isochrone_preferences = fetch_preferences(user)
    network_type_form = NetworkTypeForm(instance=network_preferences)
    isochrone_form = IsochroneForm(instance=isochrone_preferences)
    return geo_upload_form, network_type_form, isochrone_form


def fetch_user_geojson_data(user: User):
    """
    Fetches GeoJSON data associated with a given user.

    Args:
        user (User): The user whose GeoJSON data is to be fetched.

    Returns:
        QuerySet: A queryset containing the GeoJSON data.
    """
    return GeoData.objects.filter(user=user)


def fetch_latest_geometries(user: User) -> tuple:
    """
    Fetches the latest geometries drawn, marker geometries, and isochrone geometries for a given user.

    Args:
        user (User): The user whose latest geometries are to be fetched.

    Returns:
        tuple: A tuple containing the latest drawn geometry, marker geometry, and isochrone geometries.
    """
    latest_drawn_geometry_query = BoxGeometry.objects.filter(user=user).order_by('-id').first()
    latest_marker_geometry_query = MarkerGeometry.objects.filter(user=user).order_by('-id').first()
    latest_isochrone_geometry = Isochrone.objects.filter(user=user)
    return latest_drawn_geometry_query, latest_marker_geometry_query, latest_isochrone_geometry


def process_geojson_file(request: HttpRequest) -> bool:
    """
    Processes an uploaded GeoJSON file.

    Args:
        request (HttpRequest): The HTTP request containing the file.

    Returns:
        bool: True if processing is successful, otherwise False.
    """
    geojson_file = request.FILES['file']
    max_file_size = 5242880  # 5MB in bytes
    if geojson_file.size > max_file_size:
        messages.error(request, 'File size should not exceed 5 MB.')
        return redirect('geojson_view')

    geo_upload_form = GeoJSONUploadForm(request.POST, request.FILES)
    if geo_upload_form.is_valid():
        try:
            geojson_data = json.load(geojson_file)
            GeoData.objects.filter(user=request.user).delete()
            for feature in geojson_data['features']:
                geometry_type = feature['geometry']['type']
                if geometry_type not in ['LineString', 'MultiLineString']:
                    messages.error(request, f'Invalid geometry type: {geometry_type}. Only LineString and MultiLineString are allowed.')
                    return redirect('geojson_view')

                geom = GEOSGeometry(json.dumps(feature['geometry']))
                if 'crs' in geojson_data and 'properties' in geojson_data['crs'] and 'name' in geojson_data['crs']['properties']:
                    try:
                        srid = int(geojson_data['crs']['properties']['name'].split(':')[-1])
                        geom.srid = srid
                        if geom.srid != 4326:
                            geom.transform(4326)
                            messages.info(request, 'Geometry transformed to EPSG:4326.')
                        GeoData.objects.create(user=request.user, geom=geom)
                    except ValueError:
                        GeoData.objects.create(user=request.user, geom=geom)
            return True
        except json.JSONDecodeError:
            messages.error(request, 'Invalid file format. Please upload a valid GeoJSON file.')
            return redirect('geojson_view')
    return False


def process_drawn_geometry(request: HttpRequest) -> bool:
    """
    Processes drawn geometry data submitted via a form.

    Args:
        request (HttpRequest): The HTTP request containing the geometry data.

    Returns:
        bool: True if processing is successful, otherwise False.
    """
    geometry_data = request.POST.get('geometry_data')
    if geometry_data:
        try:
            drawn_data = json.loads(geometry_data)
            if not drawn_data.get('geometry'):
                return HttpResponse('Empty geometry data', status=400)
            geom = GEOSGeometry(json.dumps(drawn_data['geometry']))
            BoxGeometry.objects.filter(user=request.user).delete()
            BoxGeometry.objects.create(user=request.user, geom=geom)
            return True
        except json.JSONDecodeError:
            messages.error(request, 'Invalid box data')
            return redirect('geojson_view')
    else:
        messages.error(request, 'No box drawn. Please draw a box and then upload.')
        return redirect('geojson_view')


def process_marker_data(request: HttpRequest) -> bool:
    """
    Processes marker data submitted via a form.

    Args:
        request (HttpRequest): The HTTP request containing the marker data.

    Returns:
        bool: True if processing is successful, otherwise False.
    """
    marker_data = request.POST.get('marker_data')
    if marker_data:
        try:
            marker_json = json.loads(marker_data)
            if not marker_json.get('geometry'):
                return HttpResponse('Empty marker data', status=400)
            geom = GEOSGeometry(json.dumps(marker_json['geometry']))
            MarkerGeometry.objects.filter(user=request.user).delete()
            MarkerGeometry.objects.create(user=request.user, geom=geom)
            return True
        except json.JSONDecodeError:
            messages.error(request, 'Invalid point data')
            return redirect('geojson_view')
    else:
        messages.error(request, 'No point placed. Place a new point and submit.')
        return redirect('geojson_view')


def process_forms(request: HttpRequest, network_preferences, isochrone_preferences) -> bool:
    """
    Processes forms for updating network preferences and isochrone settings.

    Args:
        request (HttpRequest): The HTTP request containing the form data.
        network_preferences: The network preferences instance to update.
        isochrone_preferences: The isochrone preferences instance to update.

    Returns:
        bool: True if any form is processed successfully, otherwise False.
    """
    form_processed = False
    network_type_form = NetworkTypeForm(request.POST, instance=network_preferences)
    if network_type_form.is_valid():
        network_type_form.save()
        messages.success(request, "Network type of inputted data has been updated.")
        form_processed = True

    isochrone_form = IsochroneForm(request.POST, instance=isochrone_preferences)
    if isochrone_form.is_valid():
        isochrone_form.save()
        messages.success(request, "Isochrone settings updated.")
        form_processed = True
    return form_processed