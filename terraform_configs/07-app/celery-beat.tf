resource "kubernetes_deployment" "celery_beat" {

  depends_on = [
    kubernetes_persistent_volume_claim.efs_claim,
    kubernetes_persistent_volume.efs_pv,
    kubernetes_secret.my_rds_secret,
    kubernetes_deployment.redis
  ]

  metadata {
    name = "celery-beat"
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "celery-beat"
      }
    }

    template {
      metadata {
        labels = {
          app = "celery-beat"
        }
      }

      spec {
        container {
          name  = "celery-beat"
          image = "${data.terraform_remote_state.ecr.outputs.django_app_repository_uri}:latest"
          image_pull_policy = "Always"

          command = ["celery", "-A", "webproject", "beat", "--loglevel=info", "--scheduler", "django_celery_beat.schedulers:DatabaseScheduler"]

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
      }
    }
  }
}
