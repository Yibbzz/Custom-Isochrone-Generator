resource "kubernetes_role" "django_app" {
  metadata {
    name = "django-app-role"
  }

  rule {
    api_groups = [""]
    resources  = ["pods", "services"]
    verbs      = ["get", "watch", "list", "create", "update", "patch", "delete"]
  }

  rule {
    api_groups = ["apps", "extensions"]
    resources  = ["deployments"]
    verbs      = ["get", "list", "create", "update", "patch", "delete", "watch"]
  }
}

resource "kubernetes_role_binding" "django_app" {
  metadata {
    name = "django-app-rolebinding"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.django_app_service_account.metadata[0].name
    namespace = "default"
  }

  role_ref {
    kind      = "Role"
    name      = kubernetes_role.django_app.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}
