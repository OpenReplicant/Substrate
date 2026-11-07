# The substrate as one Nomad job (S-17): the same services as the compose runtime, scheduled by Nomad.
# Submitted by scripts/runtime/nomad.sh with -var values from .env. Secrets come from Nomad Variables, one per
# group with only what that group needs (nomad/jobs/substrate/<group>, written from .env by the same script),
# never from this file.
#
# Every task uses host networking and listens on 127.0.0.1 only, so tasks reach each other and a model
# server on this machine at 127.0.0.1, and nothing is exposed beyond this machine. Groups restart
# independently. Data lives in bind-mounted folders under .state/data/ (the Podman driver has no named
# volumes). Linux; on macOS use RUNTIME=compose.

variable "root" {
  type        = string
  description = "absolute path of the substrate checkout"
}
variable "driver" {
  type        = string
  default     = "podman"
  description = "podman or docker (CONTAINER_ENGINE)"
}
variable "kernel_image" {
  type    = string
  default = "localhost/knowledge-kernel:local"
}
variable "db_image" {
  type    = string
  default = "localhost/knowledge-kernel-db:local"
}
variable "caddy_image" {
  type = string
}
variable "bifrost_image" {
  type = string
}
variable "prometheus_image" {
  type = string
}
variable "backstage_image" {
  type    = string
  default = "localhost/substrate-backstage:local"
}
variable "serve_parts" {
  type        = string
  description = "what kk serve runs; read from kernel's compose default so the two runtimes match"
}
variable "db_port" {
  type    = number
  default = 5432
}
variable "kernel_port" {
  type    = number
  default = 8000
}
variable "ui_port" {
  type    = number
  default = 8080
}
variable "bifrost_port" {
  type    = number
  default = 8090
}
variable "backstage_port" {
  type    = number
  default = 7007
}
variable "prometheus_port" {
  type    = number
  default = 9090
}

job "substrate" {
  type = "service"

  # ------------------------------------------------------------------ kernel's Postgres
  group "db" {
    network {
      port "pg" {
        static = var.db_port
      }
    }

    task "postgres" {
      driver = var.driver
      config {
        image        = var.db_image
        network_mode = "host"
        args         = ["postgres", "-c", "listen_addresses=127.0.0.1", "-c", "port=${var.db_port}"]
        volumes      = ["${var.root}/.state/data/postgres:/var/lib/postgresql/data"]
      }
      env {
        POSTGRES_DB   = "kk"
        POSTGRES_USER = "postgres"
      }
      template {
        data        = <<-EOT
          {{ with nomadVar "nomad/jobs/substrate/db" }}{{ range $k, $v := . }}
          {{ $k }}={{ $v }}
          {{ end }}{{ end }}
        EOT
        destination = "secrets/db.env"
        env         = true
      }
      service {
        name     = "db"
        provider = "nomad"
        port     = "pg"
        check {
          type     = "tcp"
          interval = "10s"
          timeout  = "3s"
        }
      }
      resources {
        cpu    = 500
        memory = 512
      }
    }
  }

  # ------------------------------------------------------------------ kernel: init, kk serve, front door
  group "kernel" {
    network {
      port "kernel" {
        static = var.kernel_port
      }
      port "ui" {
        static = var.ui_port
      }
    }

    # kk init installs the kernel, its default modules and packs; it does nothing once installed. It
    # retries until Postgres (another group) accepts connections.
    task "init" {
      lifecycle {
        hook    = "prestart"
        sidecar = false
      }
      driver = var.driver
      config {
        image        = var.kernel_image
        network_mode = "host"
        command      = "sh"
        args         = ["-c", "until kk init; do echo waiting for postgres; sleep 3; done"]
      }
      template {
        data        = <<-EOT
          {{ with nomadVar "nomad/jobs/substrate/kernel" }}
          KK_ADMIN_URL=postgresql://postgres:{{ .POSTGRES_PASSWORD }}@127.0.0.1:${var.db_port}/kk
          KK_AUTHENTICATOR_PASSWORD={{ .KK_AUTHENTICATOR_PASSWORD }}
          {{ end }}
        EOT
        destination = "secrets/init.env"
        env         = true
      }
      resources {
        cpu    = 200
        memory = 256
      }
    }

    task "kernel" {
      driver = var.driver
      config {
        image        = var.kernel_image
        network_mode = "host"
        command      = "kk"
        args         = ["serve", "--host", "127.0.0.1", "--port", "${var.kernel_port}", "--only", var.serve_parts]
        volumes      = ["${var.root}/.state/artifacts:/store:ro"]
      }
      env {
        KK_ARTIFACTS = "/store"
      }
      template {
        data        = <<-EOT
          {{ with nomadVar "nomad/jobs/substrate/kernel" }}
          DATABASE_URL=postgresql://kk_authenticator:{{ .KK_AUTHENTICATOR_PASSWORD }}@127.0.0.1:${var.db_port}/kk
          KK_JWT_SECRET={{ .KK_JWT_SECRET }}
          {{ end }}
        EOT
        destination = "secrets/kernel.env"
        env         = true
      }
      service {
        name     = "kernel"
        provider = "nomad"
        port     = "kernel"
        check {
          type     = "http"
          path     = "/ui/views.json"
          interval = "15s"
          timeout  = "3s"
        }
      }
      resources {
        cpu    = 500
        memory = 768
      }
    }

    # Kernel's Caddy, routing 127.0.0.1:ui_port to kk serve, as in kernel's compose stack.
    task "caddy" {
      driver = var.driver
      config {
        image        = var.caddy_image
        network_mode = "host"
        command      = "caddy"
        args         = ["run", "--config", "/local/Caddyfile", "--adapter", "caddyfile"]
      }
      template {
        data        = <<-EOT
          http://127.0.0.1:${var.ui_port} {
          	encode zstd gzip
          	reverse_proxy 127.0.0.1:${var.kernel_port}
          }
        EOT
        destination = "local/Caddyfile"
      }
      service {
        name     = "caddy"
        provider = "nomad"
        port     = "ui"
      }
      resources {
        cpu    = 100
        memory = 64
      }
    }
  }

  # ------------------------------------------------------------------ model gateway (S-04, S-14)
  group "gateway" {
    network {
      port "http" {
        static = var.bifrost_port
      }
    }

    task "bifrost" {
      driver = var.driver
      config {
        image        = var.bifrost_image
        network_mode = "host"
        volumes = [
          "${var.root}/.state/data/bifrost:/app/data",
          "${var.root}/.state/bifrost/config.json:/app/data/config.json:ro",
        ]
      }
      env {
        APP_HOST = "127.0.0.1"
        APP_PORT = "${var.bifrost_port}"
      }
      template {
        data        = <<-EOT
          {{ with nomadVar "nomad/jobs/substrate/gateway" }}{{ range $k, $v := . }}
          {{ $k }}={{ $v }}
          {{ end }}{{ end }}
        EOT
        destination = "secrets/gateway.env"
        env         = true
      }
      service {
        name     = "bifrost"
        provider = "nomad"
        port     = "http"
        tags     = ["metrics"]
        check {
          type     = "http"
          path     = "/health"
          interval = "15s"
          timeout  = "3s"
        }
      }
      resources {
        cpu    = 500
        memory = 512
      }
    }
  }

  # ------------------------------------------------------------------ the map (S-12)
  group "map" {
    network {
      port "http" {
        static = var.backstage_port
      }
    }

    task "backstage" {
      driver = var.driver
      config {
        image        = var.backstage_image
        network_mode = "host"
        command      = "node"
        args = ["packages/backend", "--config", "app-config.yaml", "--config", "app-config.production.yaml",
        "--config", "app-config.substrate.yaml"]
        volumes = ["${var.root}/catalog-info.yaml:/substrate/catalog-info.yaml:ro"]
      }
      env {
        BACKSTAGE_PORT   = "${var.backstage_port}"
        BACKSTAGE_LISTEN = "127.0.0.1:${var.backstage_port}"
      }
      template {
        data        = <<-EOT
          {{ with nomadVar "nomad/jobs/substrate/map" }}{{ range $k, $v := . }}
          {{ $k }}={{ $v }}
          {{ end }}{{ end }}
        EOT
        destination = "secrets/map.env"
        env         = true
      }
      service {
        name     = "backstage"
        provider = "nomad"
        port     = "http"
        check {
          type     = "http"
          path     = "/.backstage/health/v1/readiness"
          interval = "15s"
          timeout  = "5s"
        }
      }
      resources {
        cpu    = 1000
        memory = 1536
      }
    }
  }

  # ------------------------------------------------------------------ telemetry (S-05)
  group "telemetry" {
    network {
      port "http" {
        static = var.prometheus_port
      }
    }

    task "prometheus" {
      driver = var.driver
      config {
        image        = var.prometheus_image
        network_mode = "host"
        args = ["--config.file=/local/prometheus.yml", "--storage.tsdb.path=/prometheus",
          "--storage.tsdb.retention.time=7d", "--web.listen-address=127.0.0.1:${var.prometheus_port}"]
        volumes = ["${var.root}/.state/data/prometheus:/prometheus"]
      }
      # Targets come from Nomad's own service catalog: every service tagged "metrics", plus Nomad itself.
      template {
        data        = <<-EOT
          global:
            scrape_interval: 15s
          scrape_configs:
            - job_name: nomad-services
              nomad_sd_configs:
                - server: http://127.0.0.1:4646
              relabel_configs:
                - source_labels: [__meta_nomad_tags]
                  regex: '.*,metrics,.*'
                  action: keep
                - source_labels: [__meta_nomad_service]
                  target_label: job
            - job_name: nomad
              metrics_path: /v1/metrics
              params:
                format: [prometheus]
              static_configs:
                - targets: ['127.0.0.1:4646']
        EOT
        destination = "local/prometheus.yml"
      }
      service {
        name     = "prometheus"
        provider = "nomad"
        port     = "http"
        check {
          type     = "http"
          path     = "/-/ready"
          interval = "15s"
          timeout  = "3s"
        }
      }
      resources {
        cpu    = 200
        memory = 256
      }
    }
  }
}
