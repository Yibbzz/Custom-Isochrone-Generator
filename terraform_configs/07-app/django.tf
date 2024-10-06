locals {
  db_host = split(":", data.terraform_remote_state.post-eks.outputs.db_endpoint)[0]
}


resource "kubernetes_deployment" "my_django_app" {

  depends_on = [
    kubernetes_persistent_volume_claim.efs_claim,
    kubernetes_persistent_volume.efs_pv,
    kubernetes_secret.my_rds_secret,
    kubernetes_deployment.redis
  ]

  metadata {
    name = "my-django-app"
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "my-django-app"
      }
    }

    template {
      metadata {
        labels = {
          app = "my-django-app"
        }
      }

      spec {
        service_account_name = "django-app-service-account"

        init_container {
          name            = "init-webapp"
          image           = "${data.terraform_remote_state.ecr.outputs.django_app_repository_uri}:latest"
          image_pull_policy = "Always"
          command         = ["sh", "-c", "cp -r /webapp/media/user_osm_files/* /mnt/ && echo Files copied"]

          volume_mount {
            name       = "osm-volume"
            mount_path = "/mnt"
          }
        }

        init_container {
          name            = "migrate"
          image           = "${data.terraform_remote_state.ecr.outputs.django_app_repository_uri}:latest"
          image_pull_policy = "Always"
          command         = ["sh", "-c", "python manage.py makemigrations && python manage.py migrate"]

          env {
            name = "DB_USER"
            value_from {
              secret_key_ref {
                name = "my-rds-secret"
                key  = "username"
              }
            }
          }

          env {
            name = "DB_PASSWORD"
            value_from {
              secret_key_ref {
                name = "my-rds-secret"
                key  = "password"
              }
            }
          }

          env {
            name  = "DB_NAME"
            value = "postgresdb"
          }

          env {
            name  = "DB_HOST"
            value = local.db_host
          }

          env {
            name  = "DB_PORT"
            value = "5432"
          }
        }

        container {
          name            = "my-django-app"
          image           = "${data.terraform_remote_state.ecr.outputs.django_app_repository_uri}:latest"
          image_pull_policy = "Always"

          port {
            container_port = 8000
          }

          volume_mount {
            name       = "osm-volume"
            mount_path = "webapp/media/user_osm_files"
          }

          env {
            name = "DB_USER"
            value_from {
              secret_key_ref {
                name = "my-rds-secret"
                key  = "username"
              }
            }
          }

          env {
            name = "DB_PASSWORD"
            value_from {
              secret_key_ref {
                name = "my-rds-secret"
                key  = "password"
              }
            }
          }

          env {
            name  = "DB_NAME"
            value = "postgresdb"
          }

          env {
            name  = "DB_HOST"
            value = local.db_host
          }

          env {
            name  = "DB_PORT"
            value = "5432"
          }
        }

        volume {
          name = "osm-volume"

          persistent_volume_claim {
            claim_name = "efs-claim"
          }
        }
      }
    }
  }
}

resource "kubernetes_service_account" "django_app_service_account" {
  metadata {
    name = "django-app-service-account"
  }
}
