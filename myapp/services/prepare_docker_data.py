import json
import os
import shutil
import geopandas as gpd
from shapely.geometry import shape
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from ..models import GeoData, BoxGeometry, NetworkType, UserPreviousInputs

def get_field_names(model_name):
    # Get the model fields
    fields = model_name._meta.get_fields()

    # Extract field names
    field_names = [field.name for field in fields if hasattr(field, 'name')]

    return field_names


def get_or_create_user_previous_inputs(user: User) -> UserPreviousInputs:
    """
    Retrieves or creates a UserPreviousInputs instance for the given user.

    Args:
        user (User): The user for whom to retrieve or create the instance.

    Returns:
        UserPreviousInputs: The retrieved or created UserPreviousInputs instance.
    """
    previous_inputs, created = UserPreviousInputs.objects.get_or_create(user=user)
    print("Previous Inputs Created:", created)
    print("Previous GeoData ID:", previous_inputs.last_geodata_id)
    print("Previous BoxGeometry ID:", previous_inputs.last_box_geometry_id)
    print("Previous NetworkType ID:", previous_inputs.last_network_type_id)
    return previous_inputs


def fetch_latest_user_inputs(user: User) -> tuple:
    """
    Fetches the latest GeoData, BoxGeometry, and NetworkType instances for the given user.

    Args:
        user (User): The user for whom to fetch the latest inputs.

    Returns:
        tuple: A tuple containing the latest GeoData, BoxGeometry, and NetworkType instances.
    """
    last_geodata = GeoData.objects.filter(user=user).order_by('-id').first()
    last_box_geometry = BoxGeometry.objects.filter(user=user).order_by('-id').first()
    last_network_type = NetworkType.objects.filter(user=user).first()

    print("Current GeoData ID:", last_geodata.id if last_geodata else 'None')
    print("Current BoxGeometry ID:", last_box_geometry.id if last_box_geometry else 'None')
    print("Current NetworkType ID:", last_network_type.id if last_network_type else 'None')

    return last_geodata, last_box_geometry, last_network_type


def check_if_inputs_changed(previous_inputs: UserPreviousInputs, last_geodata, last_box_geometry, last_network_type) -> bool:
    """
    Checks if the user inputs have changed.

    Args:
        previous_inputs (UserPreviousInputs): The previous inputs of the user.
        last_geodata (GeoData): The latest GeoData instance.
        last_box_geometry (BoxGeometry): The latest BoxGeometry instance.
        last_network_type (NetworkType): The latest NetworkType instance.

    Returns:
        bool: True if the inputs have changed, otherwise False.
    """
    inputs_changed = (
        (last_geodata and last_geodata.id != previous_inputs.last_geodata_id) or
        (last_box_geometry and last_box_geometry.id != previous_inputs.last_box_geometry_id) or
        (last_network_type and last_network_type.id != previous_inputs.last_network_type_id)
    )
    print("Inputs Changed:", inputs_changed)
    return inputs_changed


def update_previous_inputs(previous_inputs: UserPreviousInputs, last_geodata, last_box_geometry, last_network_type):
    """
    Updates the UserPreviousInputs instance with the latest inputs.

    Args:
        previous_inputs (UserPreviousInputs): The previous inputs of the user.
        last_geodata (GeoData): The latest GeoData instance.
        last_box_geometry (BoxGeometry): The latest BoxGeometry instance.
        last_network_type (NetworkType): The latest NetworkType instance.
    """
    previous_inputs.last_geodata = last_geodata
    previous_inputs.last_box_geometry = last_box_geometry
    previous_inputs.last_network_type = last_network_type
    previous_inputs.save()


def get_network_tags(user: User) -> dict:
    """
    Retrieves the network tags based on the user's preferences.

    Args:
        user (User): The user whose network preferences are to be retrieved.

    Returns:
        dict: A dictionary containing the network tags.
    """
    network_tags = {}
    try:
        user_preferences = NetworkType.objects.get(user=user)
        selected_preference = user_preferences.selection
        mph_value = user_preferences.mph  # This will be None if not set

        if selected_preference == 'motorway':
            network_tags['highway'] = 'motorway'
            if mph_value:
                network_tags['maxspeed'] = f"{mph_value} mph"
        elif selected_preference == 'residential':
            network_tags['highway'] = 'residential'
            if mph_value:
                network_tags['maxspeed'] = f"{mph_value} mph"
        elif selected_preference == 'path':
            network_tags['highway'] = 'path'
            # Paths typically don't have maxspeed, so it's not set here
    except NetworkType.DoesNotExist:
        pass

    return network_tags


def get_geodata_gdfs(user: User) -> tuple:
    """
    Converts the user's GeoData and BoxGeometry to GeoDataFrames.

    Args:
        user (User): The user whose data is to be converted.

    Returns:
        tuple: A tuple containing the GeoDataFrame for GeoData and BoxGeometry.
    """
    geodata_qs = GeoData.objects.filter(user=user)
    geodata_drawn = BoxGeometry.objects.filter(user=user)

    field_names_qs = get_field_names(GeoData)

    geodata_dicts_qs = list(geodata_qs.values(*field_names_qs))
    geodata_dicts_drawn = list(geodata_drawn.values())

    for item in geodata_dicts_qs:
        geom = GEOSGeometry(item['geom']).geojson
        item['geom'] = shape(json.loads(geom))

    for item in geodata_dicts_drawn:
        geom = GEOSGeometry(item['geom']).geojson
        item['geom'] = shape(json.loads(geom))

    gdf_qs = gpd.GeoDataFrame(geodata_dicts_qs, crs='4326', geometry='geom')
    gdf_drawn = gpd.GeoDataFrame(geodata_dicts_drawn, crs='4326', geometry='geom')

    gdf_qs = gdf_qs.rename_geometry('geometry')
    gdf_drawn = gdf_drawn.rename_geometry('geometry')

    print('loaded in gdfs')
    return gdf_qs, gdf_drawn


def prepare_folders(user_id: int) -> tuple:
    """
    Prepares the folders and file paths for the user's data.

    Args:
        user_id (int): The ID of the user.

    Returns:
        tuple: A tuple containing the paths for the OSM file and YAML file.
    """
    webapp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    osm_folder = os.path.join(webapp_dir, 'media', 'user_osm_files')
    yaml_folder = os.path.join(webapp_dir, 'media', 'user_osm_files')

    os.makedirs(osm_folder, exist_ok=True)
    os.makedirs(yaml_folder, exist_ok=True)

    output_osm_path = os.path.join(osm_folder, f"{user_id}.osm")
    output_yaml_path = os.path.join(yaml_folder, f"{user_id}.yaml")

    master_yaml_path = os.path.join(yaml_folder, 'master.yaml')
    shutil.copyfile(master_yaml_path, output_yaml_path)

    return output_osm_path, output_yaml_path