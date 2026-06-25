# tests/test_cleanup_commands.py
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.core.management import call_command
from datetime import timedelta

from myapp.models import UserSessionStatus, UserRoutingPod


class ClosePodsCommandTest(TestCase):
   """
   Tests for the close_expired_sessions management command.
   Mocks the K8s API so no cluster is needed.
   """

   def setUp(self):
      self.user_logged_out = User.objects.create_user(username="logged_out_user", password="pass")
      self.user_expired = User.objects.create_user(username="expired_user", password="pass")
      self.user_active = User.objects.create_user(username="active_user", password="pass")

      UserSessionStatus.objects.create(user=self.user_logged_out, is_logged_in=False, session_expired=False)
      UserSessionStatus.objects.create(user=self.user_expired, is_logged_in=True, session_expired=True)
      UserSessionStatus.objects.create(user=self.user_active, is_logged_in=True, session_expired=False)

      # Build the directory structure the command constructs:
      # os.path.join(BASE_DIR, 'myapp', 'media', 'user_osm_files')
      self.base_tmp = tempfile.mkdtemp()
      self.osm_dir_base = self.base_tmp
      self.osm_dir = os.path.join(self.base_tmp, 'myapp', 'media', 'user_osm_files')
      os.makedirs(self.osm_dir)

      for user in [self.user_logged_out, self.user_expired]:
         open(os.path.join(self.osm_dir, f"{user.id}.osm"), "w").close()
         open(os.path.join(self.osm_dir, f"{user.id}.yaml"), "w").close()

   def tearDown(self):
      shutil.rmtree(self.base_tmp)

   def _run_command(self, mock_apps_v1, mock_core_v1):
      with patch("myapp.management.commands.close_expired_sessions.config") as mock_config, \
            patch("myapp.management.commands.close_expired_sessions.client") as mock_client, \
            patch("myapp.management.commands.close_expired_sessions.settings") as mock_settings:

         mock_config.load_incluster_config.return_value = None
         mock_client.AppsV1Api.return_value = mock_apps_v1
         mock_client.CoreV1Api.return_value = mock_core_v1
         mock_client.V1DeleteOptions.return_value = MagicMock()
         mock_client.rest.ApiException = Exception
         mock_settings.BASE_DIR = self.osm_dir_base

         call_command("close_expired_sessions")

   def test_deletes_deployments_for_logged_out_and_expired_users(self):
      mock_apps = MagicMock()
      mock_core = MagicMock()
      self._run_command(mock_apps, mock_core)

      deleted_deployments = [
         c.kwargs['name']
         for c in mock_apps.delete_namespaced_deployment.call_args_list
      ]
      self.assertIn(f"graphhopper-{self.user_logged_out.id}", deleted_deployments)
      self.assertIn(f"graphhopper-{self.user_expired.id}", deleted_deployments)

   def test_does_not_delete_active_user_deployment(self):
      mock_apps = MagicMock()
      mock_core = MagicMock()
      self._run_command(mock_apps, mock_core)

      deleted_deployments = [
         c.kwargs['name']
         for c in mock_apps.delete_namespaced_deployment.call_args_list
      ]
      self.assertNotIn(f"graphhopper-{self.user_active.id}", deleted_deployments)

   def test_deletes_services_for_logged_out_and_expired_users(self):
      mock_apps = MagicMock()
      mock_core = MagicMock()
      self._run_command(mock_apps, mock_core)

      deleted_services = [
         c.kwargs['name']
         for c in mock_core.delete_namespaced_service.call_args_list
      ]
      self.assertIn(f"graphhopper-{self.user_logged_out.id}-service", deleted_services)
      self.assertIn(f"graphhopper-{self.user_expired.id}-service", deleted_services)

   def test_deletes_osm_and_yaml_files(self):
      mock_apps = MagicMock()
      mock_core = MagicMock()
      self._run_command(mock_apps, mock_core)

      for user in [self.user_logged_out, self.user_expired]:
         self.assertFalse(
               os.path.exists(os.path.join(self.osm_dir, f"{user.id}.osm")),
               f".osm file for user {user.id} should have been deleted"
         )
         self.assertFalse(
               os.path.exists(os.path.join(self.osm_dir, f"{user.id}.yaml")),
               f".yaml file for user {user.id} should have been deleted"
         )

   def test_active_user_files_untouched(self):
      open(os.path.join(self.osm_dir, f"{self.user_active.id}.osm"), "w").close()
      mock_apps = MagicMock()
      mock_core = MagicMock()
      self._run_command(mock_apps, mock_core)

      self.assertTrue(
         os.path.exists(os.path.join(self.osm_dir, f"{self.user_active.id}.osm")),
         "Active user's .osm file should NOT have been deleted"
      )

   def test_handles_already_deleted_deployment_gracefully(self):
      """404 from K8s should not crash the command."""
      mock_apps = MagicMock()
      mock_core = MagicMock()

      not_found = MagicMock()
      not_found.status = 404
      mock_apps.delete_namespaced_deployment.side_effect = not_found

      try:
         self._run_command(mock_apps, mock_core)
      except Exception as e:
         self.fail(f"Command raised unexpectedly on 404: {e}")

   def test_handles_missing_files_gracefully(self):
      """If .osm/.yaml files don't exist, the command should not crash."""
      for user in [self.user_logged_out, self.user_expired]:
         for ext in [".osm", ".yaml"]:
               path = os.path.join(self.osm_dir, f"{user.id}{ext}")
               if os.path.exists(path):
                  os.remove(path)

      mock_apps = MagicMock()
      mock_core = MagicMock()
      try:
         self._run_command(mock_apps, mock_core)
      except Exception as e:
         self.fail(f"Command raised unexpectedly on missing files: {e}")


class ExpiredSessionCommandTest(TestCase):
   """
   Tests for the check_expired_sessions management command.
   Pure Django — no K8s involved.
   """

   def setUp(self):
      self.user = User.objects.create_user(username="sessionuser", password="pass")

   def _create_session(self, user, expired=False):
      from django.contrib.sessions.backends.db import SessionStore
      store = SessionStore()
      store["_auth_user_id"] = str(user.id)
      store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
      store["_auth_user_hash"] = user.password
      if expired:
         store.set_expiry(-1)
      store.save()

      if expired:
         Session.objects.filter(session_key=store.session_key).update(
               expire_date=timezone.now() - timedelta(hours=1)
         )
      return store.session_key

   def test_expired_session_marks_user_session_expired(self):
      self._create_session(self.user, expired=True)
      call_command("check_expired_sessions")

      status = UserSessionStatus.objects.get(user=self.user)
      self.assertFalse(status.is_logged_in)
      self.assertTrue(status.session_expired)

   def test_expired_session_is_deleted_from_db(self):
      key = self._create_session(self.user, expired=True)
      call_command("check_expired_sessions")
      self.assertFalse(Session.objects.filter(session_key=key).exists())

   def test_active_session_not_affected(self):
      self._create_session(self.user, expired=False)
      call_command("check_expired_sessions")
      self.assertFalse(UserSessionStatus.objects.filter(user=self.user).exists())

   def test_multiple_expired_sessions_all_processed(self):
      user2 = User.objects.create_user(username="sessionuser2", password="pass")
      self._create_session(self.user, expired=True)
      self._create_session(user2, expired=True)
      call_command("check_expired_sessions")

      for u in [self.user, user2]:
         status = UserSessionStatus.objects.get(user=u)
         self.assertTrue(status.session_expired)

   def test_nonexistent_user_in_session_does_not_crash(self):
      """A session referencing a deleted user should be handled gracefully."""
      from django.contrib.sessions.backends.db import SessionStore
      store = SessionStore()
      store["_auth_user_id"] = "99999"
      store.save()
      Session.objects.filter(session_key=store.session_key).update(
         expire_date=timezone.now() - timedelta(hours=1)
      )
      try:
         call_command("check_expired_sessions")
      except Exception as e:
         self.fail(f"Command raised on missing user: {e}")


class CleanupPipelineIntegrationTest(TestCase):
   """
   Tests the full pipeline: session expires → check_expired_sessions marks it
   → close_expired_sessions deletes the deployment and files.
   Mocks K8s but uses real Django session/DB logic.
   """

   def setUp(self):
      self.user = User.objects.create_user(username="pipeline_user", password="pass")

      self.base_tmp = tempfile.mkdtemp()
      self.osm_dir = os.path.join(self.base_tmp, 'myapp', 'media', 'user_osm_files')
      os.makedirs(self.osm_dir)

      open(os.path.join(self.osm_dir, f"{self.user.id}.osm"), "w").close()
      open(os.path.join(self.osm_dir, f"{self.user.id}.yaml"), "w").close()

   def tearDown(self):
      shutil.rmtree(self.base_tmp)

   def test_full_cleanup_pipeline(self):
      from django.contrib.sessions.backends.db import SessionStore

      # 1. Create an expired session
      store = SessionStore()
      store["_auth_user_id"] = str(self.user.id)
      store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
      store["_auth_user_hash"] = self.user.password
      store.save()
      Session.objects.filter(session_key=store.session_key).update(
         expire_date=timezone.now() - timedelta(hours=1)
      )

      # 2. Run session check — marks user as expired
      call_command("check_expired_sessions")
      status = UserSessionStatus.objects.get(user=self.user)
      self.assertTrue(status.session_expired)

      # 3. Run pod cleanup — deletes deployment, service, files
      mock_apps = MagicMock()
      mock_core = MagicMock()

      with patch("myapp.management.commands.close_expired_sessions.config"), \
            patch("myapp.management.commands.close_expired_sessions.client") as mock_client, \
            patch("myapp.management.commands.close_expired_sessions.settings") as mock_settings:

         mock_client.AppsV1Api.return_value = mock_apps
         mock_client.CoreV1Api.return_value = mock_core
         mock_client.V1DeleteOptions.return_value = MagicMock()
         mock_client.rest.ApiException = Exception
         mock_settings.BASE_DIR = self.base_tmp

         call_command("close_expired_sessions")

      mock_apps.delete_namespaced_deployment.assert_called_once_with(
         name=f"graphhopper-{self.user.id}",
         namespace="default",
         body=mock_client.V1DeleteOptions.return_value
      )
      self.assertFalse(os.path.exists(os.path.join(self.osm_dir, f"{self.user.id}.osm")))
      self.assertFalse(os.path.exists(os.path.join(self.osm_dir, f"{self.user.id}.yaml")))