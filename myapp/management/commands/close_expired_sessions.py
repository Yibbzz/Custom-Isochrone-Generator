from django.core.management.base import BaseCommand
from kubernetes import client, config
from myapp.models import UserSessionStatus  
import os
from django.conf import settings
from django.db import models


class Command(BaseCommand):
    help = 'Closes Kubernetes Deployments and Services for users with expired sessions or who have logged out, and deletes associated .osm and .yaml files'

    def handle(self, *args: tuple, **kwargs: dict) -> None:
        print("Starting cleanup for users with expired sessions or logged out users...")

        # Load Kubernetes config
        # config.load_kube_config()  # For local testing
        config.load_incluster_config()

        apps_v1_api = client.AppsV1Api()
        core_v1_api = client.CoreV1Api()

        users_needing_cleanup = UserSessionStatus.objects.filter(
            models.Q(is_logged_in=False) | models.Q(session_expired=True)
        )

        # Updated media directory path
        osm_files_dir = os.path.join(settings.BASE_DIR, 'myapp', 'media', 'user_osm_files')

        for user_status in users_needing_cleanup:
            user_id = user_status.user_id
            deployment_name = f'graphhopper-{user_id}'
            service_name = f'graphhopper-{user_id}-service'

            # --- Delete Deployment ---
            try:
                apps_v1_api.delete_namespaced_deployment(
                    name=deployment_name, namespace="default", body=client.V1DeleteOptions()
                )
                print(f'Successfully deleted deployment for user {user_id}')
            except client.rest.ApiException as e:
                if e.status == 404:
                    print(f'Deployment not found for user {user_id}, may already be deleted.')
                else:
                    print(f'Error deleting deployment for user {user_id}: {e}')

            # --- Delete Service ---
            try:
                core_v1_api.delete_namespaced_service(
                    name=service_name, namespace="default", body=client.V1DeleteOptions()
                )
                print(f'Successfully deleted service for user {user_id}')
            except client.rest.ApiException as e:
                if e.status == 404:
                    print(f'Service not found for user {user_id}, may already be deleted.')
                else:
                    print(f'Error deleting service for user {user_id}: {e}')

            # --- Delete .osm and .yaml files ---
            osm_file_path = os.path.join(osm_files_dir, f'{user_id}.osm')
            yaml_file_path = os.path.join(osm_files_dir, f'{user_id}.yaml')

            for file_path in [osm_file_path, yaml_file_path]:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"Deleted file: {file_path}")
                    except Exception as e:
                        print(f"Error deleting file {file_path}: {e}")

        print("Finished cleanup for expired or logged-out users.")
