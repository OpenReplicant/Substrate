package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

var serverName = regexp.MustCompile(`^[a-z][a-z0-9_]{0,30}$`)

type multiFlag []string

func (m *multiFlag) String() string     { return strings.Join(*m, " ") }
func (m *multiFlag) Set(v string) error { *m = append(*m, v); return nil }

// Backend is one MCP server a connector reaches, with its sessions (one, or one per caller role for http).
type Backend struct {
	name, transport string
	command         []string
	url             string
	secret          string
	listRole        string

	mu       sync.Mutex
	sessions map[string]*mcp.ClientSession // key: caller role ("" = shared)
}

func runConnect(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("connect", flag.ContinueOnError)
	name := fs.String("name", "", "server name (^[a-z][a-z0-9_]{0,30}$)")
	stdio := fs.String("stdio", "", "command line of a stdio server (split on spaces)")
	url := fs.String("url", "", "URL of a streamable HTTP server")
	listRole := fs.String("list-role", "", "role whose token lists the http server's tools")
	var extra multiFlag
	fs.Var(&extra, "arg", "an argument of the stdio command (repeatable)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if !serverName.MatchString(*name) {
		return errors.New("--name must match ^[a-z][a-z0-9_]{0,30}$")
	}
	if (*stdio == "") == (*url == "") {
		return errors.New("give exactly one of --stdio and --url")
	}
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		return errors.New("DATABASE_URL is required")
	}
	b := &Backend{name: *name, url: *url, secret: os.Getenv("KK_JWT_SECRET"), listRole: *listRole, sessions: map[string]*mcp.ClientSession{}}
	if *stdio != "" {
		b.transport = "stdio"
		b.command = append(strings.Fields(*stdio), extra...)
	} else {
		b.transport = "http"
	}
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return err
	}
	defer pool.Close()
	hub := NewHub(dsn)
	go hub.Run(ctx)
	c := &Connector{b: b, pool: pool, hub: hub, inflight: map[int64]bool{}, queues: map[string]bool{}}
	return c.run(ctx)
}

// ---- backend sessions

func (b *Backend) newClient() *mcp.Client {
	return mcp.NewClient(&mcp.Implementation{Name: "substrate-mcp-router-connector", Version: version},
		&mcp.ClientOptions{KeepAlive: 30 * time.Second})
}

type bearerTransport struct {
	role, secret string
	base         http.RoundTripper
}

// RoundTrip signs each request with a fresh five-minute token for the caller's role, so a cached session never
// outlives its token.
func (t bearerTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	r = r.Clone(r.Context())
	r.Header.Set("Authorization", "Bearer "+mintToken(t.role, t.secret, 5*time.Minute, time.Now()))
	return t.base.RoundTrip(r)
}

func (b *Backend) dial(ctx context.Context, role string) (*mcp.ClientSession, error) {
	var tr mcp.Transport
	if b.transport == "stdio" {
		cmd := exec.Command(b.command[0], b.command[1:]...)
		cmd.Stderr = os.Stderr
		tr = &mcp.CommandTransport{Command: cmd}
	} else {
		hc := &http.Client{}
		if b.secret != "" && role != "" {
			hc.Transport = bearerTransport{role: role, secret: b.secret, base: http.DefaultTransport}
		}
		tr = &mcp.StreamableClientTransport{Endpoint: b.url, HTTPClient: hc}
	}
	return b.newClient().Connect(ctx, tr, nil)
}

// session returns the cached session for a caller (the shared one for stdio and for http without identity).
func (b *Backend) session(ctx context.Context, caller string) (*mcp.ClientSession, string, error) {
	key := ""
	if b.transport == "http" && b.secret != "" {
		key = caller
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if cs := b.sessions[key]; cs != nil {
		return cs, key, nil
	}
	cs, err := b.dial(ctx, key)
	if err != nil {
		return nil, key, err
	}
	b.sessions[key] = cs
	return cs, key, nil
}

func (b *Backend) drop(key string, cs *mcp.ClientSession) {
	b.mu.Lock()
	if b.sessions[key] == cs {
		delete(b.sessions, key)
	}
	b.mu.Unlock()
	_ = cs.Close()
}

func (b *Backend) closeAll() {
	b.mu.Lock()
	defer b.mu.Unlock()
	for k, cs := range b.sessions {
		_ = cs.Close()
		delete(b.sessions, k)
	}
}

// call applies one tool call as the caller; a transport failure drops the session and retries once on a new one.
func (b *Backend) call(ctx context.Context, tool string, args json.RawMessage, caller string) (*mcp.CallToolResult, error) {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		cs, key, err := b.session(ctx, caller)
		if err != nil {
			return nil, err
		}
		var a any
		if len(args) > 0 {
			a = args
		}
		res, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: tool, Arguments: a})
		if err == nil {
			return res, nil
		}
		lastErr = err
		if ctx.Err() != nil || !errors.Is(err, mcp.ErrConnectionClosed) && !isTransportErr(err) {
			return nil, err
		}
		b.drop(key, cs)
	}
	return nil, lastErr
}

// isTransportErr is true for failures of the connection itself, not a JSON-RPC error the server answered.
func isTransportErr(err error) bool {
	s := err.Error()
	return strings.Contains(s, "connection closed") || strings.Contains(s, "EOF") || strings.Contains(s, "broken pipe") ||
		strings.Contains(s, "connection refused") || strings.Contains(s, "reset by peer")
}

// ---- the connector

type Connector struct {
	b    *Backend
	pool *pgxpool.Pool
	hub  *Hub

	mu       sync.Mutex
	inflight map[int64]bool
	queues   map[string]bool
}

type registered struct{ Tool, Actuator, Queue, Gate string }

// register lists the backend's tools and registers them; it returns the queues to serve.
func (c *Connector) register(ctx context.Context) error {
	cs, _, err := c.b.session(ctx, c.b.listRole)
	if err != nil {
		return err
	}
	var tools []*mcp.Tool
	for t, err := range cs.Tools(ctx, nil) {
		if err != nil {
			return fmt.Errorf("list tools: %w", err)
		}
		tools = append(tools, t)
	}
	tj, err := json.Marshal(tools)
	if err != nil {
		return err
	}
	if tools == nil {
		tj = []byte("[]")
	}
	info := map[string]any{}
	if ir := cs.InitializeResult(); ir != nil {
		info["serverInfo"], info["protocolVersion"], info["instructions"] = ir.ServerInfo, ir.ProtocolVersion, ir.Instructions
	}
	ij, _ := json.Marshal(info)
	target := map[string]any{"url": c.b.url}
	if c.b.transport == "stdio" {
		target = map[string]any{"command": c.b.command[0], "args": c.b.command[1:]}
	}
	tg, _ := json.Marshal(target)
	rows, err := c.pool.Query(ctx, `select tool, actuator, queue, gate from env.mcp_register($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6)`,
		c.b.name, c.b.transport, string(tg), string(ij), string(tj), "connector:"+c.b.name)
	if err != nil {
		return err
	}
	defer rows.Close()
	qs := map[string]bool{}
	n := 0
	for rows.Next() {
		var r registered
		if err := rows.Scan(&r.Tool, &r.Actuator, &r.Queue, &r.Gate); err != nil {
			return err
		}
		qs[r.Queue] = true
		n++
	}
	if err := rows.Err(); err != nil {
		return err
	}
	c.mu.Lock()
	c.queues = qs
	c.mu.Unlock()
	log.Printf("registered %s: %d tools, %d queues", c.b.name, n, len(qs))
	return nil
}

func (c *Connector) run(ctx context.Context) error {
	defer c.b.closeAll()
	backoff := time.Second
	reg := time.NewTicker(60 * time.Second)
	defer reg.Stop()
	registeredOK := false
	wake, cancel := c.hub.Any()
	defer cancel()
	poll := time.NewTicker(300 * time.Millisecond)
	defer poll.Stop()
	nextTry := time.Now()
	for ctx.Err() == nil {
		select {
		case <-ctx.Done():
			return nil
		case <-reg.C:
			registeredOK = false // register again (tool changes, a reconnect)
		case <-wake:
		case <-poll.C:
		}
		if !registeredOK {
			if time.Now().Before(nextTry) {
				continue
			}
			if err := c.register(ctx); err != nil {
				if ctx.Err() != nil {
					return nil
				}
				log.Printf("register %s: %v (retry in %s)", c.b.name, err, backoff)
				c.b.closeAll()
				nextTry = time.Now().Add(backoff)
				if backoff < 30*time.Second {
					backoff *= 2
				}
				continue
			}
			registeredOK, backoff = true, time.Second
		}
		c.drain(ctx)
	}
	return nil
}

type queued struct {
	MsgID int64
	Msg   struct {
		Action int64 `json:"action"`
		Input  struct {
			Server    string          `json:"server"`
			Tool      string          `json:"tool"`
			Arguments json.RawMessage `json:"arguments"`
		} `json:"input"`
		By string `json:"by"`
	}
}

// drain reads each registered queue once and starts a goroutine for each new message.
func (c *Connector) drain(ctx context.Context) {
	c.mu.Lock()
	qs := make([]string, 0, len(c.queues))
	for q := range c.queues {
		qs = append(qs, q)
	}
	c.mu.Unlock()
	for _, q := range qs {
		rows, err := c.pool.Query(ctx, `select msg_id, message from env.read($1, 60, 10)`, q)
		if err != nil {
			if ctx.Err() == nil {
				log.Printf("read %s: %s", q, pgMessage(err))
			}
			continue
		}
		var batch []queued
		for rows.Next() {
			var m queued
			var raw []byte
			if err := rows.Scan(&m.MsgID, &raw); err == nil && json.Unmarshal(raw, &m.Msg) == nil {
				batch = append(batch, m)
			}
		}
		rows.Close()
		for _, m := range batch {
			c.mu.Lock()
			busy := c.inflight[m.Msg.Action]
			c.inflight[m.Msg.Action] = true
			c.mu.Unlock()
			if !busy {
				go c.apply(ctx, q, m)
			}
		}
	}
}

func argKeys(args json.RawMessage) string {
	var m map[string]json.RawMessage
	if json.Unmarshal(args, &m) != nil {
		return ""
	}
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return strings.Join(keys, ",")
}

func (c *Connector) apply(ctx context.Context, queue string, m queued) {
	defer func() { c.mu.Lock(); delete(c.inflight, m.Msg.Action); c.mu.Unlock() }()
	start := time.Now()
	cctx, cancel := context.WithTimeout(ctx, 10*time.Minute)
	defer cancel()
	var result []byte
	ok := false
	res, err := c.b.call(cctx, m.Msg.Input.Tool, m.Msg.Input.Arguments, m.Msg.By)
	if err != nil {
		result, _ = json.Marshal(map[string]string{"error": err.Error()})
	} else {
		result, _ = json.Marshal(res)
		ok = !res.IsError
	}
	log.Printf("action=%d tool=%s caller=%s arg_keys=[%s] ok=%v ms=%d", m.Msg.Action, m.Msg.Input.Tool, m.Msg.By,
		argKeys(m.Msg.Input.Arguments), ok, time.Since(start).Milliseconds())
	if ctx.Err() != nil {
		return // shutting down: leave it queued; it is read again
	}
	if _, err := c.pool.Exec(ctx, `select env.done($1, $2::jsonb, $3)`, m.Msg.Action, string(result), ok); err != nil {
		msg := pgMessage(err)
		log.Printf("done action=%d: %s", m.Msg.Action, msg)
		if strings.Contains(msg, "is not queued") { // already settled: drop the message so it is not redelivered
			_, _ = c.pool.Exec(ctx, `select env.ack($1, array[$2::bigint])`, queue, m.MsgID)
		}
	}
}
