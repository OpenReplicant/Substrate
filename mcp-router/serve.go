package main

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

//go:embed web
var webFS embed.FS

type roleKey struct{}

// Server is the router's network edge.
type Server struct {
	store          Store
	hub            *Hub
	secret         string
	wait           time.Duration
	frameAncestors string
	loginStore     func(ctx context.Context, role, password string) bool
	now            func() time.Time
}

func runServe(ctx context.Context, _ []string) error {
	dsn := os.Getenv("DATABASE_URL")
	secret := os.Getenv("KK_JWT_SECRET")
	if dsn == "" || len(secret) < 32 {
		return errors.New("DATABASE_URL and KK_JWT_SECRET (at least 32 characters) are required")
	}
	waitSec, err := strconv.Atoi(envOr("WAIT_SECONDS", "15"))
	if err != nil || waitSec < 0 {
		return errors.New("WAIT_SECONDS must be a number")
	}
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return err
	}
	defer pool.Close()
	hub := NewHub(dsn)
	go hub.Run(ctx)
	s := &Server{
		store: pgStore{pool}, hub: hub, secret: secret, wait: time.Duration(waitSec) * time.Second,
		frameAncestors: envOr("FRAME_ANCESTORS", "http://127.0.0.1:8080 http://localhost:8080"),
		loginStore:     func(c context.Context, role, pw string) bool { return pgLogin(c, dsn, role, pw) },
		now:            time.Now,
	}
	addr := envOr("LISTEN", ":8090")
	srv := &http.Server{Addr: addr, Handler: s.Handler(), ReadHeaderTimeout: 10 * time.Second}
	go func() {
		<-ctx.Done()
		sc, c := context.WithTimeout(context.Background(), 5*time.Second)
		defer c()
		_ = srv.Shutdown(sc)
	}()
	log.Println("serving on", addr)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

// Handler builds every route.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprint(w, "ok") })
	mcpH := mcp.NewStreamableHTTPHandler(func(r *http.Request) *mcp.Server {
		role, _ := r.Context().Value(roleKey{}).(string)
		return s.mcpServer(r.Context(), role)
	}, &mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true})
	mux.Handle("/mcp", s.auth(mcpH))
	s.apiRoutes(mux)
	sub, _ := fs.Sub(webFS, "web")
	mux.Handle("/", http.FileServerFS(sub))
	return s.headers(mux)
}

func (s *Server) headers(next http.Handler) http.Handler {
	csp := "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors " +
		s.frameAncestors + "; base-uri 'none'; form-action 'self'; object-src 'none'"
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("Content-Security-Policy", csp)
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("Referrer-Policy", "no-referrer")
		next.ServeHTTP(w, r)
	})
}

// auth requires a valid Bearer token and puts its role in the request context.
func (s *Server) auth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		role, err := verifyToken(bearer(r.Header.Get("Authorization")), s.secret, s.now())
		if err != nil {
			w.Header().Set("WWW-Authenticate", `Bearer realm="mcp-router"`)
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), roleKey{}, role)))
	})
}

// mcpServer builds the server for one request from the tools registered right now, for the caller's role. The
// handler is stateless, so a session never outlives or outranks the token that opened it.
func (s *Server) mcpServer(ctx context.Context, role string) *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{Name: "substrate-mcp-router", Version: version}, &mcp.ServerOptions{
		Instructions: "Substrate's MCP router: tools are named <server>_<tool>. A call may wait for a person's approval; then ask router_outcome.",
	})
	rows, err := s.store.Tools(ctx)
	if err != nil {
		log.Println("tools:", pgMessage(err))
	}
	for _, t := range rows {
		s.addTool(srv, t, role)
	}
	srv.AddTool(&mcp.Tool{
		Name:        "router_outcome",
		Description: "The outcome of an action (a call that waited for approval or its server): status, result, who decided.",
		InputSchema: json.RawMessage(`{"type":"object","properties":{"action":{"type":"integer"}},"required":["action"]}`),
		Annotations: &mcp.ToolAnnotations{ReadOnlyHint: true},
	}, s.outcomeTool)
	return srv
}

func (s *Server) addTool(srv *mcp.Server, t ToolRow, role string) {
	defer func() { // one malformed registered tool must not take the listing down
		if r := recover(); r != nil {
			log.Printf("tool %s skipped: %v", t.Name, r)
		}
	}()
	tool := &mcp.Tool{Name: t.Name, Title: t.Title, Description: t.Description, InputSchema: json.RawMessage(t.InputSchema)}
	if len(t.InputSchema) == 0 {
		tool.InputSchema = json.RawMessage(`{"type":"object"}`)
	}
	if len(t.OutputSchema) > 0 && string(t.OutputSchema) != "null" {
		tool.OutputSchema = json.RawMessage(t.OutputSchema)
	}
	if len(t.Annotations) > 0 {
		var a mcp.ToolAnnotations
		if json.Unmarshal(t.Annotations, &a) == nil {
			tool.Annotations = &a
		}
	}
	name := t.Name
	srv.AddTool(tool, func(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return s.callTool(ctx, name, req.Params.Arguments, role), nil
	})
}

// callTool records the call for the caller and waits for its outcome.
func (s *Server) callTool(ctx context.Context, name string, args json.RawMessage, role string) *mcp.CallToolResult {
	if len(args) == 0 || string(args) == "null" {
		args = json.RawMessage(`{}`)
	}
	id, status, err := s.store.Call(ctx, name, args, role)
	if err != nil {
		return textResult(true, "%s", pgMessage(err))
	}
	if status == "denied" {
		return textResult(true, "action %d was denied: the tool's gate is deny", id)
	}
	return s.await(ctx, id, status)
}

// await waits up to s.wait for the action to end: it subscribes first, then reads, so no change is missed; a slow
// poll covers a lost notification.
func (s *Server) await(ctx context.Context, id int64, status string) *mcp.CallToolResult {
	ch, cancel := s.hub.Wait(id)
	defer cancel()
	deadline := time.NewTimer(s.wait)
	defer deadline.Stop()
	poll := time.NewTicker(2 * time.Second)
	defer poll.Stop()
	for {
		o, err := s.store.Outcome(ctx, id)
		if err != nil {
			return textResult(true, "%s", pgMessage(err))
		}
		if o != nil {
			status = o.Status
			if res, done := mapOutcome(*o); done {
				return res
			}
		}
		select {
		case <-ch:
		case <-poll.C:
		case <-deadline.C:
			return waitingResult(id, status)
		case <-ctx.Done():
			return waitingResult(id, status)
		}
	}
}

func (s *Server) outcomeTool(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	var in struct {
		Action int64 `json:"action"`
	}
	if err := json.Unmarshal(req.Params.Arguments, &in); err != nil || in.Action <= 0 {
		return textResult(true, "action must be an integer"), nil
	}
	o, err := s.store.Outcome(ctx, in.Action)
	if err != nil {
		return textResult(true, "%s", pgMessage(err)), nil
	}
	if o == nil {
		return textResult(true, "no such action %d", in.Action), nil
	}
	b, _ := json.Marshal(map[string]any{
		"action": o.ID, "tool": o.Tool, "caller": o.Caller, "status": o.Status, "result": rawOrNull(o.Result),
		"reason": o.Reason, "decided_by": o.DecidedBy,
	})
	return textResult(false, "%s", b), nil
}

func rawOrNull(b []byte) json.RawMessage {
	if len(b) == 0 {
		return json.RawMessage("null")
	}
	return b
}
