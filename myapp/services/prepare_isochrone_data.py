import json
import geopandas as gpd
from shapely.geometry import shape
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import GEOSGeometry
from ..models import BoxGeometry, MarkerGeometry, IsochronePreferences, UserRoutingPod


def check_marker_geometry(user) -> bool:
    """
    Check if the user has marker geometry and if it is within the bounding box.

    Args:
        user (User): The user for whom to check the marker geometry.

    Returns:
        bool: True if marker geometry exists and is valid, otherwise raises a ValidationError.
    """
    marker_geom = MarkerGeometry.objects.filter(user=user)

    if not marker_geom.exists():
        raise ValidationError('No point data available. Please select a point on the map within your bounding box and submit.')

    geodata_drawn = BoxGeometry.objects.filter(user=user)
    
    for marker in marker_geom:
        if not any(marker.geom.within(drawn.geom) for drawn in geodata_drawn):
            raise ValidationError("The marker point is not within the bounding box. Please either redraw the box or place it within.")
    
    return True

def get_user_isochrone_preferences(user) -> dict:
    """
    Retrieve the user's isochrone preferences.

    Args:
        user (User): The user for whom to retrieve isochrone preferences.

    Returns:
        dict: A dictionary containing the user's mode selection, buckets, and time limit.
    """
    user_preferences = IsochronePreferences.objects.filter(user=user).first()
    if not user_preferences:
        raise ValidationError("No mode selected. Please select a transport mode, buckets and time limit and submit.")
    
    user_pod = UserRoutingPod.objects.get(user=user)
    
    return {
        'mode_selection': user_preferences.mode_selection,
        'buckets': user_preferences.buckets,
        'time_limit': user_preferences.time_limit,
        'port': user_pod.service_name
    }

def prepare_marker_geodata(user) -> str:
    """
    Prepares the marker GeoDataFrame and retrieves the coordinates of the first point.

    Args:
        user (User): The user for whom to prepare the marker GeoDataFrame.

    Returns:
        str: The coordinates of the first point as a string in "latitude,longitude" format.
    """
    marker_geom = MarkerGeometry.objects.filter(user=user)
    geodata_dicts_marker = list(marker_geom.values())

    for item in geodata_dicts_marker:
        geom = GEOSGeometry(item['geom']).geojson  
        item['geom'] = shape(json.loads(geom))

    gdf_marker = gpd.GeoDataFrame(geodata_dicts_marker, crs='4326', geometry='geom')
    gdf_marker = gdf_marker.rename_geometry('geometry')
    first_point = gdf_marker.geometry.iloc[0]
    return f"{first_point.y},{first_point.x}"