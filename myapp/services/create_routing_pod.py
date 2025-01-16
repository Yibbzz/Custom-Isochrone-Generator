import os
from datetime import datetime
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from django.http import HttpRequest
from ..models import UserRoutingPod

def load_kube_config():
    """
    Load Kubernetes configuration.
    """
    # config.load_kube_config()  # Uncomment if running locally 
    config.load_incluster_config()


def get_k8s_apis() -> tuple:
    """
    Get Kubernetes API clients.

    Returns:
        tuple: A tuple containing the AppsV1Api and CoreV1Api clients.
    """
    apps_v1_api = client.AppsV1Api()
    core_v1_api = client.CoreV1Api()
    return apps_v1_api, core_v1_api


def create_deployment_object(user_id: int, image: str) -> client.V1Deployment:
    """
    Create a Kubernetes deployment object.

    Args:
        user_id (int): The user ID for which the deployment is created.
        image (str): The Docker image to use in the deployment.

    Returns:
        client.V1Deployment: The V1Deployment object.
    """
    deployment_name = f"graphhopper-{user_id}"
    container_port = 8989

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(
            labels={"app": "graphhopper", "user": str(user_id)}
        ),
        spec=client.V1PodSpec(
            containers=[
                client.V1Container(
                    name="graphhopper",
                    image=image,
                    ports=[client.V1ContainerPort(container_port=container_port)],
                    volume_mounts=[
                        client.V1VolumeMount(
                            name="efs-claim", 
                            mount_path="/custom_osm"
                        )
                    ],
                    command=[
                        "./graphhopper.sh",
                        "-i",
                        f"/custom_osm/{user_id}.osm",
                        "-c",
                        "/custom_osm/master.yaml"
                    ],
                    # Security context that drops privileges, disables privilege escalation, etc.
                    # security_context=client.V1SecurityContext(
                    #     run_as_non_root=True,
                    #     run_as_user=1000,
                    #     run_as_group=1000,
                    #     allow_privilege_escalation=False,
                    #     capabilities=client.V1Capabilities(drop=["ALL"]),
                    #     read_only_root_filesystem=False
                    # )
                )
            ],
            volumes=[
                client.V1Volume(
                    name="efs-claim",
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name="efs-claim"
                    )
                )
            ]
        )
    )

    spec = client.V1DeploymentSpec(
        replicas=1,
        selector=client.V1LabelSelector(
            match_labels={"app": "graphhopper", "user": str(user_id)}
        ),
        template=template
    )

    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(name=deployment_name),
        spec=spec
    )
    
    return deployment



def create_or_update_deployment(apps_v1_api: client.AppsV1Api, deployment: client.V1Deployment, namespace: str):
    """
    Create or update a Kubernetes deployment.

    Args:
        apps_v1_api (client.AppsV1Api): The AppsV1Api client.
        deployment (client.V1Deployment): The deployment object to create or update.
        namespace (str): The namespace in which to create or update the deployment.
    """
    deployment_name = deployment.metadata.name
    try:
        apps_v1_api.create_namespaced_deployment(namespace=namespace, body=deployment)
        print(f"Deployment {deployment_name} created.")
    except ApiException as e:
        if e.status == 409:  # Deployment already exists, so update it
            existing_deployment = apps_v1_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            if not existing_deployment.spec.template.metadata.annotations:
                existing_deployment.spec.template.metadata.annotations = {}
            existing_deployment.spec.template.metadata.annotations['kubectl.kubernetes.io/restartedAt'] = datetime.now().isoformat()
            try:
                apps_v1_api.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=existing_deployment)
                print(f"Deployment {deployment_name} updated and new pods are being created.")
            except ApiException as e:
                print(f"Exception when updating deployment: {e}")
        else:
            print(f"Exception when creating/updating deployment: {e}")


def create_service_object(user_id: int, container_port: int) -> client.V1Service:
    """
    Create a Kubernetes service object.

    Args:
        user_id (int): The user ID for which the service is created.
        container_port (int): The port inside the container.

    Returns:
        client.V1Service: The V1Service object.
    """
    service_name = f"graphhopper-{user_id}-service"

    service_body = client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=client.V1ObjectMeta(name=service_name),
        spec=client.V1ServiceSpec(
            type="ClusterIP",
            selector={"app": "graphhopper", "user": str(user_id)},
            ports=[client.V1ServicePort(port=container_port, target_port=container_port, protocol="TCP")]
        )
    )

    return service_body


def create_or_update_service(core_v1_api: client.CoreV1Api, service: client.V1Service, namespace: str) -> bool:
    """
    Create or update a Kubernetes service.

    Args:
        core_v1_api (client.CoreV1Api): The CoreV1Api client.
        service (client.V1Service): The service object to create or update.
        namespace (str): The namespace in which to create or update the service.

    Returns:
        bool: True if the service was created or updated, False otherwise.
    """
    service_name = service.metadata.name
    try:
        core_v1_api.create_namespaced_service(namespace=namespace, body=service)
        print(f"Service {service.metadata.name} created with type ClusterIP")
        return True
    except ApiException as e:
        if e.status == 409:
            core_v1_api.replace_namespaced_service(name=service_name, namespace=namespace, body=service)
            print(f"Service {service_name} updated with type ClusterIP")
            return True
        else:
            print(f"Exception when creating/updating service: {e}")
            return False



def update_user_service(user_id: int, service_name: str):
    """
    Update the UserPort object with the new service name.

    Args:
        user_id (int): The user ID associated with the service.
        service_name (str): The name of the created or updated service.
    """
    UserRoutingPod.objects.update_or_create(user_id=user_id, defaults={'service_name': service_name})


def create_or_update_deployment_and_service(user_id: int, request: HttpRequest):
    """
    Main function to create or update deployment and service.

    Args:
        user_id (int): The user ID for which the deployment and service are created or updated.
        request (HttpRequest): The HTTP request object containing the user information.
    """
    load_kube_config()
    namespace = "default"
    apps_v1_api, core_v1_api = get_k8s_apis()
    image = os.getenv("IMAGE")

    deployment = create_deployment_object(user_id, image)
    create_or_update_deployment(apps_v1_api, deployment, namespace)

    service = create_service_object(user_id, container_port=8989)
    service_created_or_updated = create_or_update_service(core_v1_api, service, namespace)

    if service_created_or_updated:
        update_user_service(user_id, service.metadata.name)
    else:
        print("Service was not successfully created or updated. Skipping dependent operations.")


def is_user_pod_running(user_id: int, request: HttpRequest, timeout_immediately: bool) -> bool:
    """
    Checks if a pod associated with a user is running within a Kubernetes cluster.

    This function watches for pod events in the "default" namespace, filtering by a label selector
    that includes the user ID. It can either return immediately or wait for up to 5 minutes to see
    if the pod reaches the "Running" state.

    Args:
        user_id (int): The ID of the user whose pod status is being checked.
        request (HttpRequest): The Django HTTP request object, used to access the user.
        timeout_immediately (bool): If True, the function will return almost immediately if the pod is not found;
                                    if False, it will wait for up to 5 minutes.

    Returns:
        bool: True if the pod is running, False otherwise.
    """
    # Use in-cluster configuration
    config.load_incluster_config()

    # Set the API client
    core_v1_api = client.CoreV1Api()

    # Define namespace and label selector
    namespace = "default"
    label_selector = f"app=graphhopper,user={user_id}"

    # Initialize the watch
    w = watch.Watch()

    # Dynamically set the timeout for the watch based on the condition
    timeout_seconds = 1 if timeout_immediately else 300  # 1 second or 5 minutes

    # Start watching for Pod events with dynamic timeout
    for event in w.stream(core_v1_api.list_namespaced_pod, namespace=namespace, label_selector=label_selector, timeout_seconds=timeout_seconds):
        print(event['type'])
        if event['type'] in ['ADDED', 'MODIFIED']:
            pod = event['object']
            if pod.status.phase == "Running":
                print(f"Pod {pod.metadata.name} is running.")
                
                user_port_obj, created = UserRoutingPod.objects.update_or_create(
                    user=request.user,
                    defaults={'pod_name': pod.metadata.name, 'button_activate': True}
                )
                return True
        elif timeout_immediately:
            # If set for immediate timeout, check if the event type is not 'ADDED'
            print("Event type is not 'ADDED', returning False immediately.")
            return False

    # If the loop exits without finding the Pod in Running state
    print("Timeout reached, pod not in Running state.")
    return False