resource "kubernetes_secret" "my_rds_secret" {
  metadata {
    name = "my-rds-secret"
  }
  data = {
    username = data.terraform_remote_state.security.outputs.db_username
    password = data.terraform_remote_state.security.outputs.db_password
  }
  type = "Opaque"
}
