import os
os.environ['USE_PYGEOS'] = '0'
import geopandas as gpd
from shapely.geometry import Polygon
import requests

from django.core.serializers import serialize
from django.http import JsonResponse
from django.contrib.gis.geos import GEOSGeometry

from ..models import Isochrone


def handle_isochrone_creation(user, isochrone_params, point_coordinates) -> JsonResponse:
    """
    Handles the creation of isochrones for the user.

    Args:
        user (User): The user for whom to create isochrones.
        isochrone_params (dict): The isochrone parameters.
        point_coordinates (str): The coordinates of the point as a string.

    Returns:
        JsonResponse: A JSON response indicating the success or failure of the operation.
    """
    success, result = isochrone_query(
        isochrone_params['port'],
        isochrone_params['mode_selection'],
        isochrone_params['buckets'],
        isochrone_params['time_limit'],
        point_coordinates
    )

    if success:
        Isochrone.objects.filter(user=user).delete()

        for index, row in result.iterrows():
            geos_geom = GEOSGeometry(row['geometry'].wkt)
            Isochrone.objects.create(user=user, geom=geos_geom)

        iso_json = serialize('geojson', Isochrone.objects.filter(user=user), geometry_field='geom', fields=('id',))
        return JsonResponse({'status': 'success', 'iso_json': iso_json})

    return JsonResponse(result, status=400)

def isochrone_query(service_name: str, transport_mode: str, bucket_num: int, time: int, point_coordinates: str) -> tuple:
    """
    Perform an isochrone query to a GraphHopper service.

    Args:
        service_name (str): Name of the GraphHopper service.
        transport_mode (str): Mode of transport for the isochrone query.
        bucket_num (int): Number of time buckets for the isochrone query.
        time (int): Time limit for the isochrone query in minutes.
        point_coordinates (str): Coordinates of the starting point for the isochrone query.

    Returns:
        tuple: A boolean indicating success and a GeoDataFrame with the isochrone polygons.
    """

    print(service_name)
    time = time * 60  # Convert minutes to seconds
    url = f"http://{service_name}.default.svc.cluster.local:8989/isochrone"
    params = {
        "profile": transport_mode,
        "buckets": bucket_num,
        "point": point_coordinates,
        "time_limit": time
    }
    
    attempts = 0
    max_attempts = 100
    
    while attempts < max_attempts:
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                isochrone_json = response.json()
                polygons = []
                for feature in isochrone_json['polygons']:
                    coordinates = feature['geometry']['coordinates']
                    polygon = Polygon(coordinates[0])  # Assuming one set of coordinates
                    polygons.append({'geometry': polygon})
                iso_gdf = gpd.GeoDataFrame(polygons, crs='EPSG:4326')
                return True, iso_gdf
            break  # Break the loop if the request was successful
        except requests.ConnectionError as e:
            if attempts == max_attempts - 1:
                # If this was the last attempt, return an error
                return False, {"error": "Connection failed after retrying. Please try again later."}
        except requests.RequestException as e:
            # Handle other types of exceptions without retrying
            return False, {"error": f"Request failed: {e}"}
        attempts += 1  # Increment the attempt counter

    # Return False and an empty GeoDataFrame in case of failure not caught by exceptions
    empty_gdf = gpd.GeoDataFrame(columns=['geometry'], crs='EPSG:4326')
    return False, empty_gdf