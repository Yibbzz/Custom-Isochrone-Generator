
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.serializers import serialize
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.shortcuts import render, redirect

from .forms import NetworkTypeForm, IsochroneForm, CustomAuthForm
from .models import GeoData, BoxGeometry, Isochrone, UserRoutingPod

from .utils.osm_conversion import run_all

from .services.process_user_inputs import (
    fetch_preferences,
    fetch_forms,
    fetch_user_geojson_data,
    fetch_latest_geometries,
    process_geojson_file,
    process_drawn_geometry,
    process_marker_data,
    process_forms
)
from .services.prepare_docker_data import (
    get_or_create_user_previous_inputs,
    fetch_latest_user_inputs,
    check_if_inputs_changed,
    update_previous_inputs,
    get_network_tags,
    get_geodata_gdfs,
    prepare_folders
)
from .services.prepare_isochrone_data import (
    check_marker_geometry,
    get_user_isochrone_preferences,
    prepare_marker_geodata
)
from .services.routing_queries import handle_isochrone_creation

from .services.create_routing_pod import (
    create_or_update_deployment_and_service,
    is_user_pod_running
)

def login_view(request):
    """user 
    Handles user login. Processes POST requests to authenticate and log in a user. On successful login,
    resets the failed login attempts counter and redirects to the geojson page. On failure, increments the
    failed login attempts counter.

    Args:
        request (HttpRequest): The HTTP request object, containing request data and session information.

    Returns:
        HttpResponse: Renders the login page with the authentication form and failed attempts count.
        HttpResponseRedirect: Redirects to the geojson page on successful login.
    """
    
    if request.method == 'POST':
        form = CustomAuthForm(data=request.POST, request=request)  # Pass request to form
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                request.session['failed_attempts'] = 0  # Reset on successful login
                return redirect('/geojson/')  
            else:
                # Increment failed attempts count
                request.session['failed_attempts'] = request.session.get('failed_attempts', 0) + 1
                print("Failed login, incremented to:", request.session['failed_attempts'])  # Check incrementation
        else:
            # Increment failed attempts count
            request.session['failed_attempts'] = request.session.get('failed_attempts', 0) + 1
            print("Failed login, incremented to:", request.session['failed_attempts'])  # Check incrementation
    else:
        form = CustomAuthForm(request=request)  # Initialize form with request

    return render(request, 'login.html', {'form': form, 'failed_attempts': request.session.get('failed_attempts', 0)})

def register(request):
    """
    Handles user registration. Processes POST requests to create a new user. On successful registration,
    redirects to the login page. Otherwise, renders the registration form.

    Args:
        request (HttpRequest): The HTTP request object, containing request data.

    Returns:
        HttpResponse: Renders the registration page with the registration form.
        HttpResponseRedirect: Redirects to the login page on successful registration.
    """
    if request.method == 'POST':
        reg_form = UserCreationForm(request.POST)
        if reg_form.is_valid():
            reg_form.save()
            return redirect('login')
    else:
        reg_form = UserCreationForm()  # Use reg_form instead of form

    return render(request, 'register.html', {'reg_form': reg_form})


@login_required
def geojson_view(request: HttpRequest) -> HttpResponse:
    """
    Handles the GeoJSON view, processing forms and rendering the response.

    Args:
        request (HttpRequest): The HTTP request.

    Returns:
        HttpResponse: The HTTP response rendering the view.
    """
    network_preferences, isochrone_preferences = fetch_preferences(request.user)
    geo_upload_form, network_type_form, isochrone_form = fetch_forms(request.user)
    user_geojson_data = fetch_user_geojson_data(request.user)
    latest_drawn_geometry_query, latest_marker_geometry_query, latest_isochrone_geometry = fetch_latest_geometries(request.user)

    network_type_string = f"Current Road Type of Custom Data: {network_preferences.get_selection_display()}"
    if network_preferences.mph:
        network_type_string += f", Speed: {network_preferences.mph} mph"
    isochrone_string = f"Current Isochrone Mode: {isochrone_preferences.mode_selection}, " \
                       f"Buckets: {isochrone_preferences.buckets}, " \
                       f"Time Limit: {isochrone_preferences.time_limit} minutes"

    user_geojson_data_query = None

    if request.method == 'POST':
        form_processed = False
        if 'file' in request.FILES:
            form_processed = process_geojson_file(request)
        elif 'geometry_data' in request.POST:
            form_processed = process_drawn_geometry(request)
        elif 'marker_data' in request.POST:
            form_processed = process_marker_data(request)

        form_processed = process_forms(request, network_preferences, isochrone_preferences) or form_processed
        if form_processed:
            return redirect('geojson_view')

        user_geojson_data_query = GeoData.objects.filter(user=request.user).order_by('-id').first()
        if user_geojson_data_query:
            user_geojson_data = [user_geojson_data_query]

    if not user_geojson_data_query:
        user_geojson_data = fetch_user_geojson_data(request.user)

    return render(request, 'home.html', {
        'geo_upload_form': geo_upload_form,
        'network_form': NetworkTypeForm(instance=network_preferences) if network_preferences else NetworkTypeForm(),
        'isochrone_form': IsochroneForm(instance=isochrone_preferences) if isochrone_preferences else IsochroneForm(),
        'network_type_string': network_type_string,
        'isochrone_string': isochrone_string,
        'all_geojson_data': serialize('geojson', user_geojson_data, geometry_field='geom', fields=('id',)),
        'latest_drawn_geometry': serialize('geojson', [latest_drawn_geometry_query], geometry_field='geom', fields=('id',)) if latest_drawn_geometry_query else None,
        'latest_marker_geometry': serialize('geojson', [latest_marker_geometry_query], geometry_field='geom', fields=('id',)) if latest_marker_geometry_query else None,
        'latest_isochrone_geometry': serialize('geojson', latest_isochrone_geometry, geometry_field='geom', fields=('id',)) if latest_isochrone_geometry.exists() else None
    })


@login_required
def integrate_data_and_run_docker(request: HttpRequest) -> JsonResponse:
    """
    Integrates user data, runs Docker if necessary, and updates the user's deployment and service.

    Args:
        request (HttpRequest): The HTTP request.

    Returns:
        JsonResponse: A JSON response indicating the status of the operation.
    """
    user = request.user

    user_pod_obj, _ = UserRoutingPod.objects.get_or_create(user=user)
    previous_inputs = get_or_create_user_previous_inputs(user)

    last_geodata, last_box_geometry, last_network_type = fetch_latest_user_inputs(user)
    inputs_changed = check_if_inputs_changed(previous_inputs, last_geodata, last_box_geometry, last_network_type)

    update_previous_inputs(previous_inputs, last_geodata, last_box_geometry, last_network_type)

    user_id = user.id
    container_running = is_user_pod_running(user_id, request, True)

    if inputs_changed or not container_running:
        if user.is_authenticated:
            user_id = user.id

        has_geo_data = GeoData.objects.filter(user=user).exists()
        has_box_geometry = BoxGeometry.objects.filter(user=user).exists()

        if not has_geo_data and not has_box_geometry:
            return JsonResponse({"error": "You need to upload a geojson file and draw and upload a bounding box."}, status=400)
        elif not has_geo_data:
            return JsonResponse({"error": "You need to upload geojson file."}, status=400)
        elif not has_box_geometry:
            return JsonResponse({"error": "You need to draw and upload a bounding box."}, status=400)

        user_pod_obj.button_activate = False
        user_pod_obj.save()

        network_tags = get_network_tags(user)

        gdf_qs, gdf_drawn = get_geodata_gdfs(user)
        output_osm_path, output_yaml_path = prepare_folders(user_id)

        run_all(gdf_drawn, gdf_qs, output_osm_path, network_tags)
        create_or_update_deployment_and_service(user_id, request)
        is_user_pod_running(user_id, request, False)

    return JsonResponse({'status': 'success'})


@login_required
def container_button_activate(request):
    """
    Checks if the container button is activated for the logged-in user.

    Args:
        request (HttpRequest): The HTTP request object.

    Returns:
        JsonResponse: A JSON response indicating whether the container button is activated.
    """
    try:
        user_port_obj = UserRoutingPod.objects.get(user=request.user)
        return JsonResponse({'isRunning': user_port_obj.button_activate})
    except UserRoutingPod.DoesNotExist:
        return JsonResponse({'isRunning': False})

@login_required
def container_status_update(request):
    """
    Updates the container status for the logged-in user.

    Args:
        request (HttpRequest): The HTTP request object.

    Returns:
        JsonResponse: A JSON response indicating the running status of the container.
    """
    if isinstance(request.user, AnonymousUser):
        return JsonResponse({'is_running': False})
    container_status = UserRoutingPod.objects.filter(user=request.user).first()
    if container_status:
        return JsonResponse({'is_running': container_status.is_running})
    else:
        return JsonResponse({'is_running': False})
    

@login_required
def create_isochrone(request: HttpRequest) -> JsonResponse:
    """
    Main function to handle the creation of isochrones.

    Args:
        request (HttpRequest): The HTTP request.

    Returns:
        JsonResponse: A JSON response indicating the success or failure of the operation.
    """
    try:
        check_marker_geometry(request.user)
        isochrone_params = get_user_isochrone_preferences(request.user)
        point_coordinates = prepare_marker_geodata(request.user)
        return handle_isochrone_creation(request.user, isochrone_params, point_coordinates)
    except ValidationError as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def export_isochrones(request):
    """
    Exports isochrone data for the logged-in user as a GeoJSON file.

    Args:
        request (HttpRequest): The HTTP request object.

    Returns:
        HttpResponse: A HTTP response with the GeoJSON data as an attachment, 
                      or a plain text response if no data is available.
    """
    isochrones = Isochrone.objects.filter(user=request.user)
    if isochrones.exists():
        geojson_data = serialize('geojson', isochrones, geometry_field='geom', fields=('id',))
        response = HttpResponse(geojson_data, content_type="application/json")
        response['Content-Disposition'] = 'attachment; filename="isochrones.geojson"'
        return response
    else:
        return HttpResponse("No isochrone data available. Please go back and generate an isochrone.", content_type="text/plain")

@login_required
def how_to_view(request):
    """
    Renders the 'how_to.html' template.

    Args:
        request (HttpRequest): The HTTP request object.

    Returns:
        HttpResponse: A HTTP response rendering the 'how_to.html' template.
    """
    return render(request, 'how_to.html')