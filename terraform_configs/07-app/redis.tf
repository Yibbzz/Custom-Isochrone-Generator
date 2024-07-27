resource "kubernetes_deployment" "redis" {
  metadata {
    name = "redis"
  }
  spec {
    selector {
      match_labels = {
        app = "redis"
      }
    }
    replicas = 1
    template {
      metadata {
        labels = {
          app = "redis"
        }
      }
      spec {
        container {
          name  = "redis"
          image = "redis:alpine"
          port {
            container_port = 6379
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "redis" {
  metadata {
    name = "redis"
  }
  spec {
    port {
      port        = 6379
      target_port = 6379
    }
    selector = {
      app = "redis"
    }
  }
}
