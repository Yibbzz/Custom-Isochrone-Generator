
resource "kubernetes_persistent_volume" "efs_pv" {
  metadata {
    name = "efs-pv"
  }
  spec {
    capacity = {
      storage = "5Gi"
    }
    volume_mode = "Filesystem"
    access_modes = ["ReadWriteMany"]
    persistent_volume_reclaim_policy = "Retain"
    storage_class_name = "efs-sc"
    persistent_volume_source {
      csi {
        driver = "efs.csi.aws.com"
        volume_handle = data.terraform_remote_state.post-eks.outputs.efs_id
      }
    }
  }
}

resource "kubernetes_persistent_volume_claim" "efs_claim" {
  metadata {
    name = "efs-claim"
  }
  spec {
    access_modes = ["ReadWriteMany"]
    storage_class_name = "efs-sc"
    resources {
      requests = {
        storage = "5Gi"
      }
    }
  }
}

resource "kubernetes_storage_class" "efs_sc" {
  metadata {
    name = "efs-sc"
  }
  storage_provisioner = "efs.csi.aws.com"
}
