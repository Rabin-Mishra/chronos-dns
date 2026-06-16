terraform {
  backend "s3" {
    bucket         = "chronos-dns-tf-state"
    key            = "dev/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "chronos-dns-tflocks"
    encrypt        = true
  }
}
