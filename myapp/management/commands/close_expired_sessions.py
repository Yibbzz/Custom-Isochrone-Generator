from django.core.management.base import BaseCommand
from kubernetes import client, config
from myapp.models import UserSessionStatus  
import os
from django.conf import settings
from django.db import models


class Command(BaseCommand):
    """
    Command to close Kubernetes Deployments and Services for users with expired sessions or who have logged out,
    and delete associated .osm files.

    This command interacts with the Kubernetes API to delete user-specific resources and performs file system cleanup.

    Attributes:
        help (str): Description of the command.
    """

    help = 'Closes Kubernetes Deployments and Services for users with expired sessions or who have logged out, and deletes associated .osm files'

    def handle(self, *args: tuple, **kwargs: dict) -> None:
        """
        Handle the command execution.

        Args:
            *args (tuple): Variable length argument list.
            **kwargs (dict): Arbitrary keyword arguments.
        """
        print("Starting cleanup for users with expired sessions or logged out users...")

        # Load Kubernetes config
        #config.load_kube_config() - if locally
        config.load_incluster_config()

        apps_v1_api = client.AppsV1Api()
        core_v1_api = client.CoreV1Api()

        users_needing_cleanup = UserSessionStatus.objects.filter(
            models.Q(is_logged_in=False) | models.Q(session_expired=True)
        )

        osm_files_dir = os.path.join(settings.BASE_DIR, 'media', 'user_osm_files')

        for user_status in users_needing_cleanup:
            user_id = user_status.user_id
            deployment_name = f'graphhopper-{user_id}'
            service_name = f'graphhopper-{user_id}-service'

            # Delete the Deployment
            try:
                apps_v1_api.delete_namespaced_deployment(name=deployment_name, namespace="default", body=client.V1DeleteOptions())
                print(f'Successfully deleted deployment for user {user_id}')
            except client.rest.ApiException as e:
                if e.status == 404:
                    print(f'Deployment not found for user {user_id}, it may have already been deleted.')
                else:
                    print(f'Error while handling deployment for user {user_id}: {e}')

            # Delete the Service
            try:
                core_v1_api.delete_namespaced_service(name=service_name, namespace="default", body=client.V1DeleteOptions())
                print(f'Successfully deleted service for user {user_id}')
            except client.rest.ApiException as e:
                if e.status == 404:
                    print(f'Service not found for user {user_id}, it may have already been deleted.')
                else:
                    print(f'Error while handling service for user {user_id}: {e}')

            # Delete the .osm file associated with the user
            osm_file_path = os.path.join(osm_files_dir, f'{user_id}.osm')
            if os.path.exists(osm_file_path):
                os.remove(osm_file_path)
                print(f'Successfully deleted .osm file for user {user_id}')

        print("Finished checking for expired sessions or logged out users.")
