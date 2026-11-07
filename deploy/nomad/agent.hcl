# A single-node Nomad agent for substrate: server and client on this machine, everything on localhost
# (S-17). scripts/runtime/nomad.sh starts it with its data and plugin folders under .state/nomad/ and,
# for Podman, a second file naming this user's Podman socket.
#
# Nomad 2.0.7 (BUSL-1.1, S-17); the Podman driver is nomad-driver-podman 0.6.5 (MPL-2.0), Linux only.

datacenter = "dc1"
bind_addr  = "127.0.0.1"

advertise {
  http = "127.0.0.1"
  rpc  = "127.0.0.1"
  serf = "127.0.0.1"
}

server {
  enabled          = true
  bootstrap_expect = 1
}

client {
  enabled = true
  # Services register on loopback, where every task listens (host networking, S-17).
  network_interface = "{{ GetAllInterfaces | include \"flags\" \"loopback\" | attr \"name\" }}"
}

# Allocation and node metrics in Prometheus format at /v1/metrics?format=prometheus, scraped by the
# telemetry group and recorded by kernel's observer: restarts and resource use become claims.
telemetry {
  prometheus_metrics         = true
  publish_allocation_metrics = true
  publish_node_metrics       = true
}

# Plain processes on this machine (kk serve, Morphogen runs) when a job asks for them.
plugin "raw_exec" {
  config {
    enabled = true
  }
}

plugin "docker" {
  config {
    volumes {
      enabled = true
    }
  }
}

# The Podman driver's block is written by scripts/runtime/nomad.sh into .state/nomad/podman.hcl, with this
# user's socket (unix://$XDG_RUNTIME_DIR/podman/podman.sock when rootless) and volumes enabled.
