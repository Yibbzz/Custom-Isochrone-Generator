version: 0.2

phases:
  install:
    commands:
      - echo Installing dependencies...
      - apt-get update && apt-get install -y gzip

  pre_build:
    commands:
      - echo Logging in to Amazon ECR...
      - aws --version
      - $(aws ecr get-login --no-include-email --region ${region})
      - REPOSITORY_URI=${repository_uri}
      - GRAPHHOPPER_URI=${graphhopper_repository_uri}
      - COMMIT_HASH=$(echo $CODEBUILD_RESOLVED_SOURCE_VERSION | cut -c 1-7)
      - IMAGE_TAG=${COMMIT_HASH:=latest}
      - echo Extracting and loading Graphhopper Docker image from local tar file...
      - tar -xzf graphhopper.tar.gz  # Extract the tar.gz file
      - docker load -i graphhopper.tar  # Load the Docker image

  build:
    commands:
      - echo Build started on `date`
      - echo Building and tagging the Django Docker image...
      - docker build -t $REPOSITORY_URI:$IMAGE_TAG .
      - docker tag $REPOSITORY_URI:$IMAGE_TAG $REPOSITORY_URI:latest
      - echo Tagging Graphhopper Docker image...
      - docker tag graphhopper:8.0 $GRAPHHOPPER_URI:$IMAGE_TAG  # Ensure the tag matches the loaded image
      - docker tag graphhopper:8.0 $GRAPHHOPPER_URI:latest

  post_build:
    commands:
      - echo Build completed on `date`
      - echo Pushing the Docker images...
      - docker push $REPOSITORY_URI:$IMAGE_TAG
      - docker push $REPOSITORY_URI:latest
      - echo Pushing Graphhopper Docker image...
      - docker push $GRAPHHOPPER_URI:$IMAGE_TAG
      - docker push $GRAPHHOPPER_URI:latest
      - echo Writing image definitions file...
      - printf '[{"name":"django_app","imageUri":"%s"},{"name":"graphhopper","imageUri":"%s"}]' $REPOSITORY_URI:$IMAGE_TAG $GRAPHHOPPER_URI:$IMAGE_TAG > imagedefinitions.json
artifacts:
  files:
    - imagedefinitions.json
