import os
os.environ['USE_PYGEOS'] = '0'
import geopandas as gpd
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon
import requests

from django.core.serializers import serialize
from django.http import JsonResponse
from django.contrib.gis.geos import GEOSGeometry

from ..models import Isochrone, GeoData, BoxGeometry


def _clipped_by_bbox(polygon, bbox_shapely, tol_degrees=0.0005):
    """
    Returns True if `polygon`'s boundary runs along the bbox boundary,
    which means GraphHopper had no OSM data beyond that point and the
    isochrone was truncated rather than naturally closing.

    This may need to be adjusted
    """
    if bbox_shapely is None:
        return False
    return polygon.boundary.distance(bbox_shapely.boundary) < tol_degrees


def handle_isochrone_creation(user, isochrone_params, point_coordinates) -> JsonResponse:
    # Validate custom geometry intersects the bbox before hitting GraphHopper
    bbox = BoxGeometry.objects.filter(user=user).first()
    if bbox:
        custom_lines = GeoData.objects.filter(user=user)
        non_intersecting = [
            str(line.id) for line in custom_lines
            if not bbox.geom.intersects(line.geom)
        ]
        if non_intersecting:
            return JsonResponse({
                "status": "error",
                "message": "Some of your custom geometry does not intersect with the selected area. "
                           "Please ensure all drawn lines fall within your bounding box."
            }, status=400)

    success, result = isochrone_query(
        isochrone_params['port'],
        isochrone_params['mode_selection'],
        isochrone_params['buckets'],
        isochrone_params['time_limit'],
        point_coordinates
    )

    if success:
        Isochrone.objects.filter(user=user).delete()

        bbox_shapely = shapely_wkt.loads(bbox.geom.wkt) if bbox else None
        clipped = False

        for index, row in result.iterrows():
            geos_geom = GEOSGeometry(row['geometry'].wkt)
            Isochrone.objects.create(user=user, geom=geos_geom)
            if _clipped_by_bbox(row['geometry'], bbox_shapely):
                clipped = True

        iso_json = serialize(
            'geojson',
            Isochrone.objects.filter(user=user).order_by('id'),  # insert order = sorted bucket order
            geometry_field='geom',
            fields=('id',)
        )

        response_payload = {'status': 'success', 'iso_json': iso_json}
        if clipped:
            response_payload['warning'] = (
                "The isochrone extends beyond the selected area boundary. "
                "For a complete result, try selecting a larger bounding box."
            )
        return JsonResponse(response_payload)

    if not isinstance(result, dict):
        result = {"error": f"Unexpected error result of type {type(result).__name__}: {result}"}
    return JsonResponse({"status": "error", **result}, status=400)


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
        tuple: A boolean indicating success and either a GeoDataFrame with the
        isochrone polygons (on success) or a dict describing the error (on failure).
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
                sorted_polygons = sorted(isochrone_json['polygons'], key=lambda f: f['properties']['bucket'])
                polygons = []
                for feature in sorted_polygons:
                    coordinates = feature['geometry']['coordinates']
                    polygon = Polygon(coordinates[0])
                    polygons.append({'geometry': polygon})
                iso_gdf = gpd.GeoDataFrame(polygons, crs='EPSG:4326')
                return True, iso_gdf

            # Non-200 response — surface GraphHopper's own error body if it has one
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            return False, {
                "error": f"GraphHopper returned status {response.status_code}",
                "detail": detail,
            }

        except requests.ConnectionError:
            if attempts == max_attempts - 1:
                # If this was the last attempt, return an error
                return False, {"error": "Connection failed after retrying. Please try again later."}
        except requests.RequestException as e:
            # Handle other types of exceptions without retrying
            return False, {"error": f"Request failed: {e}"}
        attempts += 1  # Increment the attempt counter

    # Return False and an error dict in case of failure not caught by exceptions above
    return False, {"error": "Isochrone query failed after retrying."}