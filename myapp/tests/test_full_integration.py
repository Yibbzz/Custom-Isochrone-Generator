# tests/test_full_integration.py
import os
import json
import time
import shutil
import pytest
import geopandas as gpd
from shapely.geometry import shape
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry

from myapp.models import (
    GeoData, BoxGeometry, MarkerGeometry,
    IsochronePreferences, UserRoutingPod, NetworkType
)

# ---------------------------------------------------------------------------
# Test scenarios — (name, bbox_wkt, marker_point_wkt, transport_mode)
# Pick areas small enough that osmnx fetches fast (~500m squares)
# ---------------------------------------------------------------------------
TEST_SCENARIOS = [
    {
        "name": "central_london",
        "bbox_wkt": "POLYGON((-0.132 51.509, -0.118 51.509, -0.118 51.516, -0.132 51.516, -0.132 51.509))",
        "marker_wkt": "POINT(-0.125 51.512)",
        "transport_mode": "car",
        "buckets": 1,
        "time_limit": 5,
    },
    {
        "name": "london_bridge",
        "bbox_wkt": "POLYGON((-0.092 51.503, -0.078 51.503, -0.078 51.510, -0.092 51.510, -0.092 51.503))",
        "marker_wkt": "POINT(-0.085 51.506)",
        "transport_mode": "car",
        "buckets": 2,
        "time_limit": 8,
    },
]

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "generated_osm")


def generate_osm_fixture(scenario: dict, user_id: int) -> str:
    """
    Runs the OSM generation pipeline for a scenario and writes the .osm file.
    Returns the path to the generated file.
    """
    from myapp.utils.osm_conversion import (
        get_osm_data_from_bbox,
        combine_custom_lines_with_osm_edges,
        create_points_from_gdf,
        split_lines_with_buffered_points,
        remove_duplicates_and_combine_nodes,
        filter_split_lines,
        assign_point_ids_to_lines,
        update_and_finalize_lines_gdf,
        check_line_node_consistency,
        convert_to_wgs84_and_add_xy,
        write_osm_xml,
        configure_osmnx_cache,
    )
    import pandas as pd
    from shapely.geometry import shape as shapely_shape

    configure_osmnx_cache()

    bbox_geom = GEOSGeometry(scenario["bbox_wkt"])
    bbox_gdf = gpd.GeoDataFrame(
        [{"geometry": shapely_shape(json.loads(bbox_geom.geojson))}],
        crs="EPSG:4326"
    )

    # Empty custom data — we're testing OSM-only path here
    custom_gdf = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs="EPSG:4326")

    nodes_gdf, edges_gdf = get_osm_data_from_bbox(bbox_gdf)
    combined_gdf = combine_custom_lines_with_osm_edges(custom_gdf, edges_gdf)
    custom_points_gdf = create_points_from_gdf(combined_gdf)
    split_lines_gdf = split_lines_with_buffered_points(combined_gdf, custom_points_gdf)
    combined_points_gdf = remove_duplicates_and_combine_nodes(custom_points_gdf, nodes_gdf)
    osm_split_lines_gdf = filter_split_lines(split_lines_gdf)
    updated_lines = assign_point_ids_to_lines(osm_split_lines_gdf, combined_points_gdf)
    final_lines = update_and_finalize_lines_gdf(split_lines_gdf, updated_lines)
    final_lines = check_line_node_consistency(final_lines, combined_points_gdf)
    combined_points_gdf = convert_to_wgs84_and_add_xy(combined_points_gdf)

    os.makedirs(FIXTURE_DIR, exist_ok=True)
    out_path = os.path.join(FIXTURE_DIR, f"{scenario['name']}_{user_id}.osm")
    write_osm_xml(combined_points_gdf, final_lines, out_path)

    return out_path


class OsmGenerationTest(TestCase):
    """
    Tests the OSM generation pipeline in isolation — no K8s, no GraphHopper.
    Verifies the .osm file is well-formed XML with nodes and ways.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.makedirs(FIXTURE_DIR, exist_ok=True)

    def _assert_osm_file_valid(self, osm_path: str):
        import xml.etree.ElementTree as ET
        self.assertTrue(os.path.exists(osm_path), f"OSM file not created: {osm_path}")
        tree = ET.parse(osm_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "osm")
        nodes = root.findall("node")
        ways = root.findall("way")
        self.assertGreater(len(nodes), 0, "OSM file has no nodes")
        self.assertGreater(len(ways), 0, "OSM file has no ways")

        # Every way's nd refs should point to a real node id
        node_ids = {n.get("id") for n in nodes}
        for way in ways:
            for nd in way.findall("nd"):
                self.assertIn(nd.get("ref"), node_ids,
                              f"Way references missing node {nd.get('ref')}")

    def test_osm_generation_central_london(self):
        path = generate_osm_fixture(TEST_SCENARIOS[0], user_id=9001)
        self._assert_osm_file_valid(path)

    def test_osm_generation_london_bridge(self):
        path = generate_osm_fixture(TEST_SCENARIOS[1], user_id=9002)
        self._assert_osm_file_valid(path)

    def test_osm_generation_with_custom_network_tags(self):
        """Checks that custom highway tags are written into ways correctly."""
        from myapp.utils.osm_conversion import (
            get_osm_data_from_bbox, combine_custom_lines_with_osm_edges,
            create_points_from_gdf, split_lines_with_buffered_points,
            remove_duplicates_and_combine_nodes, filter_split_lines,
            assign_point_ids_to_lines, update_and_finalize_lines_gdf,
            check_line_node_consistency, convert_to_wgs84_and_add_xy,
            update_gdf_tags, write_osm_xml, configure_osmnx_cache,
        )
        import xml.etree.ElementTree as ET
        import pandas as pd
        from shapely.geometry import shape as shapely_shape

        configure_osmnx_cache()
        scenario = TEST_SCENARIOS[0]
        bbox_geom = GEOSGeometry(scenario["bbox_wkt"])
        bbox_gdf = gpd.GeoDataFrame(
            [{"geometry": shapely_shape(json.loads(bbox_geom.geojson))}], crs="EPSG:4326"
        )
        custom_gdf = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs="EPSG:4326")

        nodes_gdf, edges_gdf = get_osm_data_from_bbox(bbox_gdf)
        combined_gdf = combine_custom_lines_with_osm_edges(custom_gdf, edges_gdf)
        custom_points_gdf = create_points_from_gdf(combined_gdf)
        split_lines_gdf = split_lines_with_buffered_points(combined_gdf, custom_points_gdf)
        combined_points_gdf = remove_duplicates_and_combine_nodes(custom_points_gdf, nodes_gdf)
        osm_split = filter_split_lines(split_lines_gdf)
        updated = assign_point_ids_to_lines(osm_split, combined_points_gdf)
        final = update_and_finalize_lines_gdf(split_lines_gdf, updated)
        final = check_line_node_consistency(final, combined_points_gdf)
        combined_points_gdf = convert_to_wgs84_and_add_xy(combined_points_gdf)

        network_tags = {"highway": "residential", "maxspeed": "20 mph"}
        # Inject a fake custom row so update_gdf_tags has something to act on
        if "custom" not in final.columns:
            final["custom"] = "no"
        final.loc[final.index[0], "custom"] = "yes"
        final = update_gdf_tags(final, "custom", network_tags)

        out_path = os.path.join(FIXTURE_DIR, "custom_tags_test.osm")
        write_osm_xml(combined_points_gdf, final, out_path)

        tree = ET.parse(out_path)
        root = tree.getroot()
        # Find at least one way that has our custom tag
        found_tag = any(
            way.find("tag[@k='highway'][@v='residential']") is not None
            for way in root.findall("way")
        )
        self.assertTrue(found_tag, "No way with custom highway=residential tag found")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if os.path.exists(FIXTURE_DIR):
            shutil.rmtree(FIXTURE_DIR)


class FullIsochroneIntegrationTest(TestCase):
    """
    Requires mirrord (local) or a running cluster (CI).
    Generates real OSM data, spins up GraphHopper, queries it.
    Run with: mirrord exec -f .mirrord/mirrord.json -- python manage.py test myapp.tests.test_full_integration.FullIsochroneIntegrationTest
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.makedirs(FIXTURE_DIR, exist_ok=True)
        # Generate OSM fixtures once for all test methods — osmnx fetches are slow
        cls.scenario_osm_paths = {}
        for scenario in TEST_SCENARIOS:
            # Use a high user_id range that won't clash with real users
            uid = 9000 + TEST_SCENARIOS.index(scenario)
            path = generate_osm_fixture(scenario, uid)
            cls.scenario_osm_paths[scenario["name"]] = path

    def _run_scenario(self, scenario: dict):
        from myapp.services.create_routing_pod import (
            create_or_update_deployment_and_service,
            is_user_pod_running,
        )
        from myapp.services.prepare_isochrone_data import (
            check_marker_geometry,
            get_user_isochrone_preferences,
            prepare_marker_geodata,
        )
        from myapp.services.routing_queries import handle_isochrone_creation

        user = User.objects.create_user(
            username=f"integtest_{scenario['name']}", password="pass"
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        user_id = user.id

        # Seed DB
        BoxGeometry.objects.create(user=user, geom=GEOSGeometry(scenario["bbox_wkt"]))
        MarkerGeometry.objects.create(user=user, geom=GEOSGeometry(scenario["marker_wkt"]))
        IsochronePreferences.objects.create(
            user=user,
            mode_selection=scenario["transport_mode"],
            buckets=scenario["buckets"],
            time_limit=scenario["time_limit"],
        )
        NetworkType.objects.create(user=user, selection="residential")

        # Copy the pre-generated OSM fixture to the expected path
        osm_dest = f"/webapp/myapp/media/user_osm_files/{user_id}.osm"
        os.makedirs(os.path.dirname(osm_dest), exist_ok=True)
        shutil.copy(cls.scenario_osm_paths[scenario["name"]], osm_dest)

        # Spin up GraphHopper
        create_or_update_deployment_and_service(user_id, request)
        running = is_user_pod_running(user_id, request, timeout_immediately=False)
        self.assertTrue(running, f"[{scenario['name']}] GraphHopper pod never reached Running")

        self._wait_for_graphhopper_http(user, timeout=300)

        # Run isochrone creation
        check_marker_geometry(user)
        isochrone_params = get_user_isochrone_preferences(user)
        point_coordinates = prepare_marker_geodata(user)
        response = handle_isochrone_creation(user, isochrone_params, point_coordinates)

        data = json.loads(response.content)
        self.assertEqual(data["status"], "success", f"[{scenario['name']}] {data}")
        iso = json.loads(data["iso_json"])
        self.assertEqual(
            len(iso["features"]), scenario["buckets"],
            f"[{scenario['name']}] expected {scenario['buckets']} bucket(s)"
        )

        # Polygon sanity checks
        for feature in iso["features"]:
            geom = shape(feature["geometry"])
            self.assertEqual(geom.geom_type, "Polygon")
            self.assertGreater(geom.area, 0.000001,
                               f"[{scenario['name']}] isochrone polygon suspiciously small")

        return user_id

    def test_central_london_isochrone(self):
        self._run_scenario(TEST_SCENARIOS[0])

    def test_london_bridge_isochrone(self):
        self._run_scenario(TEST_SCENARIOS[1])

    def test_multi_bucket_has_increasing_areas(self):
        """The outer bucket polygon should be larger than the inner one."""
        scenario = TEST_SCENARIOS[1]  # buckets=2
        from myapp.services.prepare_isochrone_data import (
            check_marker_geometry, get_user_isochrone_preferences, prepare_marker_geodata
        )
        from myapp.services.routing_queries import handle_isochrone_creation
        from myapp.services.create_routing_pod import (
            create_or_update_deployment_and_service, is_user_pod_running
        )

        user = User.objects.create_user(username="integtest_buckets", password="pass")
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        BoxGeometry.objects.create(user=user, geom=GEOSGeometry(scenario["bbox_wkt"]))
        MarkerGeometry.objects.create(user=user, geom=GEOSGeometry(scenario["marker_wkt"]))
        IsochronePreferences.objects.create(
            user=user, mode_selection="car", buckets=2, time_limit=10
        )
        NetworkType.objects.create(user=user, selection="residential")

        osm_dest = f"/webapp/myapp/media/user_osm_files/{user.id}.osm"
        os.makedirs(os.path.dirname(osm_dest), exist_ok=True)
        shutil.copy(cls.scenario_osm_paths[scenario["name"]], osm_dest)

        create_or_update_deployment_and_service(user.id, request)
        is_user_pod_running(user.id, request, timeout_immediately=False)
        self._wait_for_graphhopper_http(user)

        check_marker_geometry(user)
        params = get_user_isochrone_preferences(user)
        coords = prepare_marker_geodata(user)
        response = handle_isochrone_creation(user, params, coords)
        data = json.loads(response.content)
        iso = json.loads(data["iso_json"])

        areas = [shape(f["geometry"]).area for f in iso["features"]]
        self.assertGreater(areas[1], areas[0], "Outer bucket should cover more area than inner")

    def _wait_for_graphhopper_http(self, user, timeout=300):
        import requests as req
        pod_obj = UserRoutingPod.objects.get(user=user)
        url = f"http://{pod_obj.service_name}.default.svc.cluster.local:8989/health"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if req.get(url, timeout=5).status_code == 200:
                    return
            except req.ConnectionError:
                pass
            time.sleep(5)
        raise TimeoutError(f"GraphHopper never became ready at {url}")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        from kubernetes import client, config
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        core_v1 = client.CoreV1Api()

        # Clean up all test deployments
        for scenario in TEST_SCENARIOS:
            uid = 9000 + TEST_SCENARIOS.index(scenario)
            for name in [f"graphhopper-{uid}", f"graphhopper-{uid}-service"]:
                try:
                    apps_v1.delete_namespaced_deployment(f"graphhopper-{uid}", "default")
                    core_v1.delete_namespaced_service(f"graphhopper-{uid}-service", "default")
                except Exception:
                    pass

        # Clean up generated OSM files
        if os.path.exists(FIXTURE_DIR):
            shutil.rmtree(FIXTURE_DIR)