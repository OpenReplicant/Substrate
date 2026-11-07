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
  type        = string
  default     = "localhost/knowledge-kernel-db:local"
  description = "kernel's Postgres image: pgvector, pg_cron, pgmq, pgGraph (kernel D-94)"
}
variable "caddy_image" {
  type        = string
  default     = "localhost/substrate-caddy:local"
  description = "the front door, with any plugins in deploy/caddy/plugins.txt (S-20)"
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
variable "otel_image" {
  type    = string
  default = "docker.io/otel/opentelemetry-collector-contrib:0.163.2"
}
variable "otel_grpc_port" {
  type    = number
  default = 4317
}
variable "otel_http_port" {
  type    = number
  default = 4318
}
variable "console_port" {
  type    = number
  default = 8100
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
        # as kernel's compose: pg_cron and pgGraph load at start (kernel D-94)
        args = ["postgres", "-c", "listen_addresses=127.0.0.1", "-c", "port=${var.db_port}",
        "-c", "shared_preload_libraries=pg_cron,graph", "-c", "cron.database_name=kk"]
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

    # The front door (S-20): substrate's Caddyfile (kernel's routes plus /console), the same file compose uses,
    # with the addresses that differ under host networking given as environment.
    task "caddy" {
      driver = var.driver
      config {
        image        = var.caddy_image
        network_mode = "host"
        command      = "caddy"
        args         = ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
        volumes      = ["${var.root}/deploy/caddy/Caddyfile:/etc/caddy/Caddyfile:ro"]
      }
      env {
        KK_SITE          = "http://127.0.0.1:${var.ui_port}"
        CADDY_BIND       = "127.0.0.1"
        KERNEL_UPSTREAM  = "127.0.0.1:${var.kernel_port}"
        CONSOLE_UPSTREAM = "127.0.0.1:${var.console_port}"
        # spans to the collector (S-28)
        OTEL_SERVICE_NAME           = "front-door"
        OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:${var.otel_http_port}"
        OTEL_EXPORTER_OTLP_PROTOCOL = "http/protobuf"
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

  # ------------------------------------------------------------------ the console (S-22)
  group "console" {
    network {
      port "http" {
        static = var.console_port
      }
    }

    task "console" {
      driver = var.driver
      config {
        image        = var.kernel_image
        network_mode = "host"
        command      = "python3"
        args         = ["/console/server.py"]
        volumes = [
          "${var.root}/services/console:/console:ro",
          "${var.root}:/substrate:ro",
        ]
      }
      env {
        CONSOLE_HOST     = "127.0.0.1"
        CONSOLE_PORT     = "${var.console_port}"
        KERNEL_URL       = "http://127.0.0.1:${var.kernel_port}"
        BIFROST_URL      = "http://127.0.0.1:${var.bifrost_port}"
        BACKSTAGE_URL    = "http://127.0.0.1:${var.backstage_port}"
        PROMETHEUS_URL   = "http://127.0.0.1:${var.prometheus_port}"
        NOMAD_ADDR       = "http://127.0.0.1:4646"
        BUS_URL          = "postgresql://substrate_bus@127.0.0.1:${var.db_port}/substrate"
        RUNTIME          = "nomad"
        CONTAINER_ENGINE = var.driver
      }
      template {
        data        = <<-EOT
          {{ with nomadVar "nomad/jobs/substrate/console" }}{{ range $k, $v := . }}
          {{ $k }}={{ $v }}
          {{ end }}{{ end }}
        EOT
        destination = "secrets/console.env"
        env         = true
      }
      service {
        name     = "console"
        provider = "nomad"
        port     = "http"
        check {
          type     = "http"
          path     = "/"
          interval = "15s"
          timeout  = "3s"
        }
      }
      resources {
        cpu    = 200
        memory = 192
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
        APP_HOST           = "127.0.0.1"
        APP_PORT           = "${var.bifrost_port}"
        OTEL_COLLECTOR_URL = "http://127.0.0.1:${var.otel_http_port}/v1/traces"
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
        # zero-code OpenTelemetry, installed in the image (S-28)
        NODE_OPTIONS                        = "--require @opentelemetry/auto-instrumentations-node/register"
        OTEL_SERVICE_NAME                   = "map-view"
        OTEL_EXPORTER_OTLP_ENDPOINT         = "http://127.0.0.1:${var.otel_http_port}"
        OTEL_EXPORTER_OTLP_PROTOCOL         = "http/protobuf"
        OTEL_TRACES_EXPORTER                = "otlp"
        OTEL_METRICS_EXPORTER               = "none"
        OTEL_LOGS_EXPORTER                  = "none"
        OTEL_NODE_DISABLED_INSTRUMENTATIONS = "fs,dns,net"
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
      port "otlp_grpc" {
        static = var.otel_grpc_port
      }
      port "otlp_http" {
        static = var.otel_http_port
      }
      port "otel_prom" {
        static = 8889
      }
    }

    # The OpenTelemetry collector (S-28), with the same config as compose (deploy/otel/collector.yaml).
    task "otel-collector" {
      driver = var.driver
      config {
        image        = var.otel_image
        network_mode = "host"
        args         = ["--config=/etc/otelcol-contrib/config.yaml"]
        volumes = [
          "${var.root}/deploy/otel/collector.yaml:/etc/otelcol-contrib/config.yaml:ro",
          "${var.root}/.state/otel:/otel",
        ]
      }
      env {
        OTEL_LISTEN_HOST = "127.0.0.1"
      }
      service {
        name     = "otel-collector"
        provider = "nomad"
        port     = "otel_prom"
        tags     = ["metrics"]
        check {
          type     = "http"
          path     = "/metrics"
          port     = "otel_prom"
          interval = "15s"
          timeout  = "3s"
        }
      }
      resources {
        cpu    = 200
        memory = 256
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
