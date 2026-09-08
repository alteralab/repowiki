terraform {
  backend "s3" {
    bucket = "state"
    key    = "prod/terraform.tfstate"
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"
  cidr    = var.cidr
}

resource "aws_instance" "web" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  tags = {
    Name = "web"
  }
}
