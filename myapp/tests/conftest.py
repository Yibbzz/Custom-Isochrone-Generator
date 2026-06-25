import pytest, requests, time

BASE_URL = "http://isochrone-app-svc"  # K8s service name in temp namespace

def wait_for_service(url, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/health", timeout=5)
            if r.status_code == 200:
                return
        except requests.ConnectionError:
            pass
        time.sleep(3)
    raise TimeoutError(f"Service at {url} never became ready")

@pytest.fixture(scope="session", autouse=True)
def app_ready():
    wait_for_service(BASE_URL)