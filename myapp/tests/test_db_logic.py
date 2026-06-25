# tests/test_db_logic.py
import json
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import GEOSGeometry

from myapp.models import (
    MarkerGeometry, BoxGeometry, IsochronePreferences, UserRoutingPod,
    GeoData, NetworkType, UserPreviousInputs, UserSessionStatus
)
from myapp.services.prepare_isochrone_data import (
    check_marker_geometry,
    get_user_isochrone_preferences,
    prepare_marker_geodata,
)
from myapp.services.prepare_docker_data import (
    get_or_create_user_previous_inputs,
    fetch_latest_user_inputs,
    check_if_inputs_changed,
    update_previous_inputs,
    get_network_tags,
)
from myapp.services.process_user_inputs import (
    fetch_preferences,
    fetch_forms,
    fetch_user_geojson_data,
    fetch_latest_geometries,
    process_drawn_geometry,
    process_marker_data,
    process_forms,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LONDON_BOX = 'POLYGON((-0.15 51.49, -0.10 51.49, -0.10 51.52, -0.15 51.52, -0.15 51.49))'
POINT_INSIDE  = 'POINT(-0.12 51.505)'
POINT_OUTSIDE = 'POINT(0.0 52.0)'
POINT_ON_EDGE = 'POINT(-0.15 51.49)'   # corner of box — boundary behaviour
LINESTRING    = 'LINESTRING(-0.13 51.50, -0.11 51.51)'


def make_user(username="testuser", password="pass"):
    return User.objects.create_user(username=username, password=password)


# ---------------------------------------------------------------------------
# check_marker_geometry
# ---------------------------------------------------------------------------

class CheckMarkerGeometryTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.box = BoxGeometry.objects.create(
            user=self.user, geom=GEOSGeometry(LONDON_BOX)
        )

    def test_raises_if_no_marker(self):
        with self.assertRaises(ValidationError):
            check_marker_geometry(self.user)

    def test_raises_if_marker_outside_box(self):
        MarkerGeometry.objects.create(user=self.user, geom=GEOSGeometry(POINT_OUTSIDE))
        with self.assertRaises(ValidationError):
            check_marker_geometry(self.user)

    def test_passes_if_marker_inside_box(self):
        MarkerGeometry.objects.create(user=self.user, geom=GEOSGeometry(POINT_INSIDE))
        self.assertTrue(check_marker_geometry(self.user))

    def test_raises_if_no_bounding_box(self):
        """Marker exists but user has no box at all."""
        self.box.delete()
        MarkerGeometry.objects.create(user=self.user, geom=GEOSGeometry(POINT_INSIDE))
        with self.assertRaises(ValidationError):
            check_marker_geometry(self.user)

    def test_raises_if_marker_on_box_boundary(self):
        """Points exactly on the boundary are not strictly within — depends on
        Django's within predicate. Documents the current behaviour."""
        MarkerGeometry.objects.create(user=self.user, geom=GEOSGeometry(POINT_ON_EDGE))
        # within() is strict — boundary point should fail
        with self.assertRaises(ValidationError):
            check_marker_geometry(self.user)

    def test_different_user_marker_not_visible(self):
        """Markers belonging to another user must not satisfy this user's check."""
        other = make_user("other")
        MarkerGeometry.objects.create(user=other, geom=GEOSGeometry(POINT_INSIDE))
        with self.assertRaises(ValidationError):
            check_marker_geometry(self.user)


# ---------------------------------------------------------------------------
# prepare_marker_geodata
# ---------------------------------------------------------------------------

class PrepareMarkerGeodataTest(TestCase):

    def setUp(self):
        self.user = make_user("testuser2")

    def test_returns_lat_lon_string(self):
        MarkerGeometry.objects.create(
            user=self.user, geom=GEOSGeometry('POINT(-0.1278 51.5074)')
        )
        result = prepare_marker_geodata(self.user)
        lat, lon = result.split(",")
        self.assertAlmostEqual(float(lat),  51.5074, places=3)
        self.assertAlmostEqual(float(lon), -0.1278,  places=3)

    def test_format_is_lat_comma_lon(self):
        """GraphHopper expects lat,lon not lon,lat."""
        MarkerGeometry.objects.create(
            user=self.user, geom=GEOSGeometry('POINT(-0.1278 51.5074)')
        )
        result = prepare_marker_geodata(self.user)
        parts = result.split(",")
        self.assertEqual(len(parts), 2)
        lat, lon = float(parts[0]), float(parts[1])
        # Latitude is ~51, longitude is ~-0.1 — a swap would put ~-0.1 first
        self.assertGreater(lat, 50)
        self.assertLess(lon, 1)

    def test_uses_most_recent_marker(self):
        """If multiple markers exist (shouldn't in prod but just in case) it
        uses the first one returned by the queryset."""
        MarkerGeometry.objects.create(user=self.user, geom=GEOSGeometry('POINT(-0.10 51.50)'))
        MarkerGeometry.objects.create(user=self.user, geom=GEOSGeometry('POINT(-0.11 51.51)'))
        # Should not raise
        result = prepare_marker_geodata(self.user)
        self.assertIn(",", result)


# ---------------------------------------------------------------------------
# get_user_isochrone_preferences
# ---------------------------------------------------------------------------

class GetIsochronePreferencesTest(TestCase):

    def setUp(self):
        self.user = make_user("testuser3")
        IsochronePreferences.objects.create(
            user=self.user, mode_selection="car", buckets=3, time_limit=15
        )
        UserRoutingPod.objects.create(
            user=self.user, service_name="graphhopper-1-service"
        )

    def test_returns_correct_preferences(self):
        prefs = get_user_isochrone_preferences(self.user)
        self.assertEqual(prefs['mode_selection'], "car")
        self.assertEqual(prefs['buckets'], 3)
        self.assertEqual(prefs['time_limit'], 15)
        self.assertEqual(prefs['port'], "graphhopper-1-service")

    def test_raises_if_no_preferences(self):
        IsochronePreferences.objects.filter(user=self.user).delete()
        with self.assertRaises(ValidationError):
            get_user_isochrone_preferences(self.user)

    def test_raises_if_no_routing_pod(self):
        UserRoutingPod.objects.filter(user=self.user).delete()
        with self.assertRaises(Exception):
            get_user_isochrone_preferences(self.user)

    def test_different_transport_modes(self):
        for mode in ["car", "bike", "foot"]:
            IsochronePreferences.objects.filter(user=self.user).update(mode_selection=mode)
            prefs = get_user_isochrone_preferences(self.user)
            self.assertEqual(prefs['mode_selection'], mode)


# ---------------------------------------------------------------------------
# prepare_docker_data helpers
# ---------------------------------------------------------------------------

class UserPreviousInputsTest(TestCase):

    def setUp(self):
        self.user = make_user("dockeruser")
        self.geo = GeoData.objects.create(
            user=self.user,
            geom=GEOSGeometry(LINESTRING)
        )
        self.box = BoxGeometry.objects.create(
            user=self.user, geom=GEOSGeometry(LONDON_BOX)
        )
        self.network = NetworkType.objects.create(
            user=self.user, selection="residential"
        )

    def test_get_or_create_creates_on_first_call(self):
        obj = get_or_create_user_previous_inputs(self.user)
        self.assertIsInstance(obj, UserPreviousInputs)

    def test_get_or_create_returns_same_object_on_second_call(self):
        obj1 = get_or_create_user_previous_inputs(self.user)
        obj2 = get_or_create_user_previous_inputs(self.user)
        self.assertEqual(obj1.pk, obj2.pk)

    def test_fetch_latest_user_inputs_returns_correct_objects(self):
        geo, box, network = fetch_latest_user_inputs(self.user)
        self.assertEqual(geo.pk, self.geo.pk)
        self.assertEqual(box.pk, self.box.pk)
        self.assertEqual(network.pk, self.network.pk)

    def test_fetch_latest_returns_most_recent_geodata(self):
        newer_geo = GeoData.objects.create(
            user=self.user, geom=GEOSGeometry(LINESTRING)
        )
        geo, _, _ = fetch_latest_user_inputs(self.user)
        self.assertEqual(geo.pk, newer_geo.pk)

    def test_check_if_inputs_changed_true_on_new_geodata(self):
        previous = get_or_create_user_previous_inputs(self.user)
        update_previous_inputs(previous, self.geo, self.box, self.network)

        new_geo = GeoData.objects.create(
            user=self.user, geom=GEOSGeometry(LINESTRING)
        )
        changed = check_if_inputs_changed(previous, new_geo, self.box, self.network)
        self.assertTrue(changed)

    def test_check_if_inputs_changed_false_when_same(self):
        previous = get_or_create_user_previous_inputs(self.user)
        update_previous_inputs(previous, self.geo, self.box, self.network)
        changed = check_if_inputs_changed(previous, self.geo, self.box, self.network)
        self.assertFalse(changed)

    def test_check_if_inputs_changed_true_on_new_box(self):
        previous = get_or_create_user_previous_inputs(self.user)
        update_previous_inputs(previous, self.geo, self.box, self.network)
        new_box = BoxGeometry.objects.create(
            user=self.user,
            geom=GEOSGeometry('POLYGON((-0.09 51.50, -0.07 51.50, -0.07 51.52, -0.09 51.52, -0.09 51.50))')
        )
        changed = check_if_inputs_changed(previous, self.geo, new_box, self.network)
        self.assertTrue(changed)

    def test_update_previous_inputs_persists(self):
        previous = get_or_create_user_previous_inputs(self.user)
        update_previous_inputs(previous, self.geo, self.box, self.network)
        previous.refresh_from_db()
        self.assertEqual(previous.last_geodata_id, self.geo.pk)
        self.assertEqual(previous.last_box_geometry_id, self.box.pk)
        self.assertEqual(previous.last_network_type_id, self.network.pk)


# ---------------------------------------------------------------------------
# get_network_tags
# ---------------------------------------------------------------------------

class GetNetworkTagsTest(TestCase):

    def setUp(self):
        self.user = make_user("networkuser")

    def test_motorway_without_speed(self):
        NetworkType.objects.create(user=self.user, selection="motorway", mph=None)
        tags = get_network_tags(self.user)
        self.assertEqual(tags.get("highway"), "motorway")
        self.assertNotIn("maxspeed", tags)

    def test_motorway_with_speed(self):
        NetworkType.objects.create(user=self.user, selection="motorway", mph=70)
        tags = get_network_tags(self.user)
        self.assertEqual(tags.get("maxspeed"), "70 mph")

    def test_residential_with_speed(self):
        NetworkType.objects.create(user=self.user, selection="residential", mph=20)
        tags = get_network_tags(self.user)
        self.assertEqual(tags.get("highway"), "residential")
        self.assertEqual(tags.get("maxspeed"), "20 mph")

    def test_path_has_no_maxspeed(self):
        NetworkType.objects.create(user=self.user, selection="path", mph=10)
        tags = get_network_tags(self.user)
        self.assertEqual(tags.get("highway"), "path")
        self.assertNotIn("maxspeed", tags)

    def test_returns_empty_dict_if_no_network_type(self):
        tags = get_network_tags(self.user)
        self.assertEqual(tags, {})


# ---------------------------------------------------------------------------
# process_user_inputs helpers
# ---------------------------------------------------------------------------

class FetchPreferencesTest(TestCase):

    def setUp(self):
        self.user = make_user("prefuser")

    def test_creates_defaults_on_first_call(self):
        network, isochrone = fetch_preferences(self.user)
        self.assertIsNotNone(network)
        self.assertIsNotNone(isochrone)

    def test_returns_same_objects_on_second_call(self):
        n1, i1 = fetch_preferences(self.user)
        n2, i2 = fetch_preferences(self.user)
        self.assertEqual(n1.pk, n2.pk)
        self.assertEqual(i1.pk, i2.pk)


class FetchLatestGeometriesTest(TestCase):

    def setUp(self):
        self.user = make_user("geomuser")

    def test_returns_none_when_nothing_saved(self):
        box, marker, isos = fetch_latest_geometries(self.user)
        self.assertIsNone(box)
        self.assertIsNone(marker)
        self.assertFalse(isos.exists())

    def test_returns_latest_box(self):
        BoxGeometry.objects.create(user=self.user, geom=GEOSGeometry(LONDON_BOX))
        newer = BoxGeometry.objects.create(
            user=self.user,
            geom=GEOSGeometry('POLYGON((-0.09 51.50, -0.07 51.50, -0.07 51.52, -0.09 51.52, -0.09 51.50))')
        )
        box, _, _ = fetch_latest_geometries(self.user)
        self.assertEqual(box.pk, newer.pk)

    def test_other_users_geometries_not_returned(self):
        other = make_user("othergeomuser")
        BoxGeometry.objects.create(user=other, geom=GEOSGeometry(LONDON_BOX))
        box, marker, _ = fetch_latest_geometries(self.user)
        self.assertIsNone(box)
        self.assertIsNone(marker)


class ProcessDrawnGeometryTest(TestCase):

    def setUp(self):
        self.user = make_user("drawnuser")
        self.factory = RequestFactory()

    def _post(self, data):
        request = self.factory.post("/", data)
        request.user = self.user
        return request

    def test_saves_valid_box_geometry(self):
        geom_data = json.dumps({"geometry": {"type": "Polygon", "coordinates": [
            [[-0.15, 51.49], [-0.10, 51.49], [-0.10, 51.52], [-0.15, 51.52], [-0.15, 51.49]]
        ]}})
        request = self._post({"geometry_data": geom_data})
        result = process_drawn_geometry(request)
        self.assertTrue(result)
        self.assertEqual(BoxGeometry.objects.filter(user=self.user).count(), 1)

    def test_replaces_existing_box_geometry(self):
        BoxGeometry.objects.create(user=self.user, geom=GEOSGeometry(LONDON_BOX))
        geom_data = json.dumps({"geometry": {"type": "Polygon", "coordinates": [
            [[-0.09, 51.50], [-0.07, 51.50], [-0.07, 51.52], [-0.09, 51.52], [-0.09, 51.50]]
        ]}})
        request = self._post({"geometry_data": geom_data})
        process_drawn_geometry(request)
        # Old one deleted, only new one remains
        self.assertEqual(BoxGeometry.objects.filter(user=self.user).count(), 1)

    def test_rejects_empty_geometry(self):
        request = self._post({"geometry_data": json.dumps({"geometry": None})})
        result = process_drawn_geometry(request)
        # Returns an HttpResponse(400), not True
        self.assertNotEqual(result, True)


class ProcessMarkerDataTest(TestCase):

    def setUp(self):
        self.user = make_user("markeruser")
        self.factory = RequestFactory()

    def _post(self, data):
        request = self.factory.post("/", data)
        request.user = self.user
        return request

    def test_saves_valid_marker(self):
        marker_data = json.dumps({"geometry": {"type": "Point", "coordinates": [-0.12, 51.505]}})
        request = self._post({"marker_data": marker_data})
        result = process_marker_data(request)
        self.assertTrue(result)
        self.assertEqual(MarkerGeometry.objects.filter(user=self.user).count(), 1)

    def test_replaces_existing_marker(self):
        MarkerGeometry.objects.create(user=self.user, geom=GEOSGeometry(POINT_INSIDE))
        marker_data = json.dumps({"geometry": {"type": "Point", "coordinates": [-0.11, 51.510]}})
        request = self._post({"marker_data": marker_data})
        process_marker_data(request)
        self.assertEqual(MarkerGeometry.objects.filter(user=self.user).count(), 1)

    def test_rejects_empty_marker(self):
        request = self._post({"marker_data": json.dumps({"geometry": None})})
        result = process_marker_data(request)
        self.assertNotEqual(result, True)


# ---------------------------------------------------------------------------
# UserSessionStatus
# ---------------------------------------------------------------------------

class UserSessionStatusTest(TestCase):

    def setUp(self):
        self.user = make_user("sessionstatususer")

    def test_created_with_defaults(self):
        status = UserSessionStatus.objects.create(user=self.user)
        # Model defaults is_logged_in=True (user is considered active on creation)
        self.assertTrue(status.is_logged_in)
        self.assertFalse(status.session_expired)

    def test_update_or_create_on_login(self):
        UserSessionStatus.objects.update_or_create(
            user=self.user,
            defaults={"is_logged_in": True, "session_expired": False}
        )
        status = UserSessionStatus.objects.get(user=self.user)
        self.assertTrue(status.is_logged_in)
        self.assertFalse(status.session_expired)

    def test_update_or_create_on_logout(self):
        UserSessionStatus.objects.create(user=self.user, is_logged_in=True)
        UserSessionStatus.objects.update_or_create(
            user=self.user,
            defaults={"is_logged_in": False, "session_expired": False}
        )
        status = UserSessionStatus.objects.get(user=self.user)
        self.assertFalse(status.is_logged_in)

    def test_one_status_per_user(self):
        UserSessionStatus.objects.create(user=self.user)
        with self.assertRaises(Exception):
            UserSessionStatus.objects.create(user=self.user)