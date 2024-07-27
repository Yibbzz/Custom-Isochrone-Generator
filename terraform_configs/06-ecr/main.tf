
resource "aws_ecr_repository" "django_app" {
  name                 = "django-app"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = false
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
  }
}

resource "aws_ecr_repository" "graphhopper" {
  name                 = "graphhopper"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = false
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
  }
}

resource "aws_s3_bucket_object" "buildspec_file" {
  bucket = "bucket-for-buildspecs"
  key    = "buildspec.yml"
  content = templatefile("${path.module}/buildspec.yml.tpl", {
    repository_uri = aws_ecr_repository.django_app.repository_url,
    graphhopper_repository_uri = aws_ecr_repository.graphhopper.repository_url,
    region = "eu-north-1"
  })
  content_type = "application/yaml"
}

resource "aws_codebuild_project" "django_app_build" {
  name         = "django-app"
  description  = "CodeBuild project for Django application."
  service_role = aws_iam_role.codebuild_service_role.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/amazonlinux2-aarch64-standard:2.0"
    type            = "ARM_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
  }

  source {
    type            = "GITHUB"
    location        = "https://github.com/Yibbzz/webapp.git"
    buildspec       = "s3://bucket-for-buildspecs/aws-buildspec.yml" 
    git_clone_depth = 1
    insecure_ssl    = false
    report_build_status = false
  }

  timeout_in_minutes         = 60
  queued_timeout_in_minutes  = 480

  encryption_key = aws_kms_key.codebuild_encryption.arn

  logs_config {
    cloud_watch_logs {
      status = "DISABLED"
    }
    s3_logs {
      status             = "DISABLED"
      encryption_enabled = false
    }
  }
}


resource "aws_codepipeline" "django_pipeline" {
  name     = "django-pipeline"
  role_arn = aws_iam_role.codepipeline_service_role.arn

  artifact_store {
    location = aws_s3_bucket.artifact_store.bucket
    type     = "S3"
  }

  stage {
    name = "Source"
    action {
      name             = "GitHub_Source"
      category         = "Source"
      owner            = "ThirdParty"
      provider         = "GitHub"
      output_artifacts = ["source_output"]
      version          = "1"
      configuration = {
        Owner      = "Yibbzz"
        Repo       = "webapp"
        Branch     = "main"
      }
    }
  }

  stage {
    name = "Build"
    action {
      name             = "Build"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      input_artifacts  = ["source_output"]
      output_artifacts = ["build_output"]
      version          = "1"
      configuration = {
        ProjectName = aws_codebuild_project.django_app_build.name
      }
    }
  }

  stage {
    name = "Deploy"
    action {
      name            = "Deploy_to_ECR"
      category        = "Deploy"
      owner           = "AWS"
      provider        = "ECR"
      input_artifacts = ["build_output"]
      version         = "1"
      configuration = {
        RepositoryName = aws_ecr_repository.django_app.name
        ImageTag       = "latest"
      }
    }
  }
}

resource "aws_s3_bucket" "artifact_store" {
  bucket = "my-pipeline-artifacts-2"
  versioning {
    enabled = true
  }
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
  public_access_block {
    block_public_acls   = true
    block_public_policy = true
    ignore_public_acls  = true
    restrict_public_buckets = true
  }
}

resource "aws_s3_bucket_policy" "artifact_store" {
  bucket = aws_s3_bucket.artifact_store.id
  policy = data.aws_iam_policy_document.artifact_store.json
}

data "aws_iam_policy_document" "artifact_store" {
  statement {
    effect    = "Allow"
    actions   = ["s3:*"]
    resources = [
      aws_s3_bucket.artifact_store.arn,
      "${aws_s3_bucket.artifact_store.arn}/*",
    ]
    principals {
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
      type        = "AWS"
    }
  }
}


resource "aws_iam_role" "codepipeline_service_role" {
  name               = "AWSCodePipelineServiceRole-eu-north-1-main-2"
  assume_role_policy = data.aws_iam_policy_document.codepipeline_assume_role.json
}

data "aws_iam_policy_document" "codepipeline_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["codepipeline.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild_service_role" {
  name               = "codebuild-django-aws-project-service-role"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json

  inline_policy {
    name   = "ecr-perms"
    policy = data.aws_iam_policy_document.ecr_perms.json
  }
}

data "aws_iam_policy_document" "codebuild_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "ecr_perms" {
  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:GetAuthorizationToken",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart"
    ]
    effect   = "Allow"
    resources = ["*"]
  }
}

resource "aws_kms_key" "codebuild_encryption" {
  description             = "KMS key for CodeBuild encryption"
  is_enabled              = true
  enable_key_rotation     = true
}

resource "aws_kms_alias" "codebuild_encryption_alias" {
  name          = "alias/codebuild_encryption_key"
  target_key_id = aws_kms_key.codebuild_encryption.key_id
}
