// Command mcp-router is Substrate's MCP router (S-203, S-205): `serve` is the network edge (an MCP server, a JSON API
// and a page for the desktop), `connect` is the connector that registers one backend MCP server and applies the calls
// the router queued for it. The rules (gates, who may call what, the record) live in Postgres, in schema env.
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
)

const version = "0.1.0"

func main() {
	log.SetFlags(log.LstdFlags | log.Lmsgprefix)
	log.SetPrefix("mcp-router: ")
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	var err error
	switch os.Args[1] {
	case "serve":
		err = runServe(ctx, os.Args[2:])
	case "connect":
		err = runConnect(ctx, os.Args[2:])
	case "version":
		fmt.Println(version)
	default:
		usage()
		os.Exit(2)
	}
	if err != nil && ctx.Err() == nil {
		log.Println("error:", err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: mcp-router serve | connect --name NAME (--stdio \"cmd args\" | --url URL) [--list-role ROLE] | version")
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
