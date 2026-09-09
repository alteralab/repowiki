provider "aws" {
  region = var.region
}

locals {
  name = "acceptance"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

module "network" {
  source = "../modules/network"
  cidr   = var.cidr
}

resource "aws_instance" "web" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.instance_type
  subnet_id     = module.network.subnet_id
  count         = var.count_hint
  tags          = { Name = local.name, Key = each.key }
  dynamic "ebs_block_device" {
    for_each = var.disks
    content {
      volume_size = ebs_block_device.value
    }
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
}

output "web_ip" {
  value = aws_instance.web.private_ip
}
