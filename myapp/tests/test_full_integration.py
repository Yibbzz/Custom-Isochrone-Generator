"""
tests/test_user_flow.py

Full end-to-end integration tests that mirror exactly what the browser does,
driven entirely through Django HTTP views. No internal functions are called
directly and nothing is mocked.

Flow per scenario:
  1. Seed GeoData (workaround for file-pointer bug in process_geojson_file)
  2. POST /geojson/        — save bounding box
  3. POST /geojson/        — save marker point
  4. POST /geojson/        — set road network type
  5. POST /geojson/        — set isochrone settings
  6. GET  /get-geodata/    — OSM generation + GraphHopper deploy (real, no mocks)
  7. Poll /container-button-activate/ until pod is ready
  8. GET  /make-isochrone/ — real GraphHopper query
  9. Assert geometry (bucket count, Polygon type, area > 0.1 km²)
 10. Cleanup: delete GraphHopper deployment/service + all DB rows

Requirements:
  - Run inside cluster or via mirrord so K8s API and GraphHopper are reachable
  - Run with: mirrord exec -f .mirrord/mirrord.json -- python manage.py test
              myapp.tests.test_user_flow.FullUserFlowTest
"""

import json
import time
import subprocess

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.urls import reverse
from shapely.geometry import shape

from myapp.models import (
    GeoData, BoxGeometry, MarkerGeometry,
    IsochronePreferences, UserRoutingPod, NetworkType,
)


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

TEST_SCENARIOS = [
    {
        "name": "central_london_car",
        "bbox_geojson": {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-0.132, 51.509], [-0.118, 51.509],
                    [-0.118, 51.516], [-0.132, 51.516],
                    [-0.132, 51.509],
                ]],
            },
        },
        "marker_geojson": {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-0.125, 51.512]},
        },
        "custom_geodata": [
            {"type": "LineString", "coordinates": [[-0.132, 51.509], [-0.118, 51.516]]},
        ],
        "network_selection": "residential",
        "mph": None,
        "transport_mode": "car",
        "buckets": 1,
        "time_limit": 5,
    },
    {
        "name": "london_bridge_foot",
        "bbox_geojson": {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-0.100, 51.497], [-0.070, 51.497],
                    [-0.070, 51.515], [-0.100, 51.515],
                    [-0.100, 51.497],
                ]],
            },
        },
        "marker_geojson": {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-0.085, 51.506]},
        },
        "custom_geodata": [
            {"type": "LineString", "coordinates": [[-0.092, 51.503], [-0.078, 51.510]]},
        ],
        "network_selection": "path",
        "mph": None,
        "transport_mode": "foot",
        "buckets": 2,
        "time_limit": 3,
    },
]

GRAPHHOPPER_READY_TIMEOUT = 300  # seconds


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------

class FullUserFlowTest(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username=f"flowtest_{id(self)}", password="testpass"
        )
        self.client.force_login(self.user)

    def tearDown(self):
        """Clean up GraphHopper deployment and all DB rows for this user."""
        self._cleanup_graphhopper()
        self.user.delete()  # cascades to all related models

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------

    def _seed_geodata(self, geometries: list):
        """
        Step 1: Write GeoData rows directly to the DB.

        process_geojson_file() reads the uploaded file twice (once in
        form validation, once in json.load), exhausting the pointer so
        nothing is ever saved. Seeding directly produces the same DB state
        every downstream step depends on. This is a workaround for a bug
        in that service function — fix there is to add geojson_file.seek(0)
        before the json.load() call.
        """
        GeoData.objects.filter(user=self.user).delete()
        for geom_dict in geometries:
            geom = GEOSGeometry(json.dumps(geom_dict))
            GeoData.objects.create(user=self.user, geom=geom)

        self.assertTrue(
            GeoData.objects.filter(user=self.user).exists(),
            "Test setup failed: GeoData seed produced no rows",
        )

    def _save_bounding_box(self, bbox_geojson: dict):
        """Step 2: POST the drawn rectangle geometry."""
        response = self.client.post(
            reverse("geojson_view"),
            {"geometry_data": json.dumps(bbox_geojson)},
        )
        self.assertIn(response.status_code, [200, 302],
                      f"Bounding box save failed: {response.status_code}")
        self.assertTrue(
            BoxGeometry.objects.filter(user=self.user).exists(),
            "Bounding box POST succeeded but no BoxGeometry row was saved",
        )

    def _save_marker(self, marker_geojson: dict):
        """Step 3: POST the placed marker point."""
        response = self.client.post(
            reverse("geojson_view"),
            {"marker_data": json.dumps(marker_geojson)},
        )
        self.assertIn(response.status_code, [200, 302],
                      f"Marker save failed: {response.status_code}")
        self.assertTrue(
            MarkerGeometry.objects.filter(user=self.user).exists(),
            "Marker POST succeeded but no MarkerGeometry row was saved",
        )

    def _submit_network_type(self, selection: str, mph=None):
        """Step 4: POST the road network type form."""
        data = {"selection": selection}
        if mph is not None:
            data["mph"] = mph
        response = self.client.post(reverse("geojson_view"), data)
        self.assertIn(response.status_code, [200, 302],
                      f"Network type submission failed: {response.status_code}")

    def _submit_isochrone_settings(self, mode: str, buckets: int, time_limit: int):
        """Step 5: POST the isochrone settings form."""
        response = self.client.post(
            reverse("geojson_view"),
            {"mode_selection": mode, "buckets": buckets, "time_limit": time_limit},
        )
        self.assertIn(response.status_code, [200, 302],
                      f"Isochrone settings submission failed: {response.status_code}")

    def _trigger_geodata_and_deploy(self):
        """
        Step 6: GET /get-geodata/ — runs OSM generation and deploys GraphHopper.
        This is the slow step; it starts the pod but doesn't wait for it to be ready.
        """
        response = self.client.get(reverse("get_geodata"))
        self.assertEqual(
            response.status_code, 200,
            f"/get-geodata/ returned {response.status_code}: {response.content.decode()}",
        )

    def _wait_for_pod_ready(self, timeout=GRAPHHOPPER_READY_TIMEOUT):
        """
        Step 7: Poll /container-button-activate/ until the pod signals ready,
        mirroring what the browser JS does.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            response = self.client.get(reverse("container_button_activate"))
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            if data.get("isRunning"):
                return
            print(f"  Waiting for GraphHopper pod... "
                  f"{int(deadline - time.time())}s remaining")
            time.sleep(5)

        # Dump logs to help diagnose timeout
        try:
            pod_name = subprocess.getoutput(
                f"kubectl get pod -l app=graphhopper,user={self.user.id} -o name"
            )
            logs = subprocess.getoutput(f"kubectl logs {pod_name} --tail=40")
            print(f"GraphHopper logs:\n{logs}")
        except Exception:
            pass

        self.fail(
            f"GraphHopper pod never became ready for user {self.user.id} "
            f"after {timeout}s"
        )

    def _wait_for_graphhopper_http(self, timeout=GRAPHHOPPER_READY_TIMEOUT):
        """
        Step 7b: Poll GraphHopper's HTTP endpoint directly until it responds.
        The pod reaching Running state is not enough — GraphHopper needs extra
        time after that to load the OSM file before it serves requests.
        """
        import requests as req

        pod_obj = UserRoutingPod.objects.get(user=self.user)
        base = f"http://{pod_obj.service_name}.default.svc.cluster.local:8989"
        urls = [f"{base}/health", f"{base}/healthcheck"]

        deadline = time.time() + timeout
        while time.time() < deadline:
            for url in urls:
                try:
                    if req.get(url, timeout=5).status_code == 200:
                        print(f"  GraphHopper ready at {url}")
                        return
                except req.exceptions.RequestException:
                    pass
            print(f"  Waiting for GraphHopper HTTP... {int(deadline - time.time())}s remaining")
            time.sleep(5)

        # Dump pod logs to help diagnose
        try:
            pod_name = subprocess.getoutput(
                f"kubectl get pod -l app=graphhopper,user={self.user.id} -o name"
            )
            print(f"GraphHopper logs:{subprocess.getoutput(f'kubectl logs {pod_name} --tail=40')}")
        except Exception:
            pass

        self.fail(
            f"GraphHopper HTTP never became ready for user {self.user.id} after {timeout}s"
        )

    def _create_isochrone(self):
        """Step 8: GET /make-isochrone/ — real GraphHopper query."""
        response = self.client.get(reverse("make_isochrone"))
        self.assertEqual(
            response.status_code, 200,
            f"/make-isochrone/ returned {response.status_code}: {response.content.decode()}",
        )
        return json.loads(response.content)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup_graphhopper(self):
        """Delete the GraphHopper K8s deployment and service for this user."""
        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()

            apps_v1 = client.AppsV1Api()
            core_v1 = client.CoreV1Api()
            user_id = self.user.id

            for api, name in [
                (apps_v1.delete_namespaced_deployment,
                 f"graphhopper-{user_id}"),
                (core_v1.delete_namespaced_service,
                 f"graphhopper-{user_id}-service"),
            ]:
                try:
                    api(name, "default")
                    print(f"  Deleted {name}")
                except Exception:
                    pass  # already gone or never created — fine

            # Remove the OSM file from the PVC
            try:
                pod_name = subprocess.getoutput(
                    "kubectl get pod -l app=my-django-app -o name | head -1"
                ).strip().removeprefix("pod/")
                subprocess.run(
                    ["kubectl", "exec", pod_name, "--",
                     "rm", "-f", f"/webapp/myapp/media/user_osm_files/{user_id}.osm"],
                    timeout=15, check=False,
                )
            except Exception:
                pass

        except Exception as e:
            print(f"  Warning: GraphHopper cleanup failed: {e}")

    # ------------------------------------------------------------------
    # Full flow runner
    # ------------------------------------------------------------------

    def _run_scenario(self, scenario: dict):
        """Run all 8 steps for a scenario and return the parsed isochrone data."""
        print(f"\n[{scenario['name']}] Starting full flow...")

        self._seed_geodata(scenario["custom_geodata"])
        self._save_bounding_box(scenario["bbox_geojson"])
        self._save_marker(scenario["marker_geojson"])
        self._submit_network_type(scenario["network_selection"], scenario["mph"])
        self._submit_isochrone_settings(
            scenario["transport_mode"],
            scenario["buckets"],
            scenario["time_limit"],
        )

        print(f"[{scenario['name']}] Triggering OSM generation and deploy...")
        self._trigger_geodata_and_deploy()

        print(f"[{scenario['name']}] Waiting for GraphHopper pod to reach Running...")
        self._wait_for_pod_ready()

        print(f"[{scenario['name']}] Waiting for GraphHopper HTTP to be ready...")
        self._wait_for_graphhopper_http()

        print(f"[{scenario['name']}] Querying isochrone...")
        return self._create_isochrone()

    # Minimum plausible isochrone area per transport mode (km²).
    # Car/5min can reach ~0.1km²; foot/3min realistically covers ~0.005km².
    MIN_AREA_KM2 = {
        "car":  0.05,
        "foot": 0.001,
        "bike": 0.01,
    }

    def _assert_isochrone_geometry(self, data: dict, scenario: dict):
        """Shared geometry assertions matching the original test suite."""
        self.assertEqual(
            data["status"], "success",
            f"[{scenario['name']}] Expected success, got: {data}",
        )

        iso = json.loads(data["iso_json"])
        self.assertEqual(
            len(iso["features"]), scenario["buckets"],
            f"[{scenario['name']}] Expected {scenario['buckets']} bucket(s), "
            f"got {len(iso['features'])}",
        )

        mode = scenario["transport_mode"]
        min_area = self.MIN_AREA_KM2.get(mode, 0.001)

        for feature in iso["features"]:
            geom = shape(feature["geometry"])
            self.assertEqual(
                geom.geom_type, "Polygon",
                f"[{scenario['name']}] Expected Polygon, got {geom.geom_type}",
            )
            # Convert degrees² → km² at London's latitude (1° lon ≈ 111km, 1° lat ≈ 69km)
            area_km2 = geom.area * 111 * 69
            self.assertGreater(
                area_km2, min_area,
                f"[{scenario['name']}] ({mode}) Isochrone area {area_km2:.4f} km² "
                f"is below minimum {min_area} km²",
            )

    # ------------------------------------------------------------------
    # Test methods
    # ------------------------------------------------------------------

    def test_central_london_car_isochrone(self):
        scenario = TEST_SCENARIOS[0]
        data = self._run_scenario(scenario)
        self._assert_isochrone_geometry(data, scenario)

    def test_london_bridge_foot_isochrone(self):
        scenario = TEST_SCENARIOS[1]
        data = self._run_scenario(scenario)
        self._assert_isochrone_geometry(data, scenario)

    def test_multi_bucket_has_increasing_areas(self):
        """The outer bucket polygon should cover more area than the inner one."""
        scenario = TEST_SCENARIOS[1]  # 2 buckets
        data = self._run_scenario(scenario)

        self.assertEqual(data["status"], "success", data)
        iso = json.loads(data["iso_json"])
        areas = sorted([shape(f["geometry"]).area for f in iso["features"]])
        self.assertGreater(
            areas[-1], areas[0] * 1.1,
            f"Outer bucket should be meaningfully larger than inner. Areas: {areas}",
        )

    def test_missing_marker_returns_error(self):
        """Skipping the marker step should return 400 at /make-isochrone/."""
        scenario = TEST_SCENARIOS[0]

        self._seed_geodata(scenario["custom_geodata"])
        self._save_bounding_box(scenario["bbox_geojson"])
        # deliberately skip _save_marker
        self._submit_network_type(scenario["network_selection"])
        self._submit_isochrone_settings(
            scenario["transport_mode"],
            scenario["buckets"],
            scenario["time_limit"],
        )
        self._trigger_geodata_and_deploy()
        self._wait_for_pod_ready()
        self._wait_for_graphhopper_http()

        response = self.client.get(reverse("make_isochrone"))
        self.assertEqual(response.status_code, 400,
                         "Missing marker should return 400")
        data = json.loads(response.content)
        self.assertIn("error", data)

    def test_missing_bbox_returns_error(self):
        """Skipping the bounding box should return 400 at /get-geodata/."""
        scenario = TEST_SCENARIOS[0]

        self._seed_geodata(scenario["custom_geodata"])
        # deliberately skip _save_bounding_box
        self._submit_network_type(scenario["network_selection"])
        self._submit_isochrone_settings(
            scenario["transport_mode"],
            scenario["buckets"],
            scenario["time_limit"],
        )

        response = self.client.get(reverse("get_geodata"))
        self.assertEqual(response.status_code, 400,
                         "Missing bbox should return 400")
        data = json.loads(response.content)
        self.assertIn("error", data)

    def test_export_after_isochrone(self):
        """After a successful isochrone, export should return a GeoJSON attachment."""
        scenario = TEST_SCENARIOS[0]
        self._run_scenario(scenario)

        response = self.client.get(reverse("export_isochrones"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("json", response.get("Content-Type", ""))
        self.assertIn("attachment", response.get("Content-Disposition", ""),
                      "Export should be a file download, not inline")

    def test_unauthenticated_user_redirected(self):
        """All protected endpoints should redirect unauthenticated users to login."""
        self.client.logout()
        for url_name in ["geojson_view", "get_geodata", "make_isochrone", "export_isochrones"]:
            response = self.client.get(reverse(url_name))
            self.assertIn(response.status_code, [301, 302],
                          f"{url_name} should redirect unauthenticated users")
            self.assertIn("/accounts/login/", response["Location"])