package main

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
)

const tokenTTL = 8 * time.Hour

// pgLogin checks a person's password by opening a connection as their role to the router's own host and database.
func pgLogin(ctx context.Context, dsn, role, password string) bool {
	cfg, err := pgx.ParseConfig(dsn)
	if err != nil {
		return false
	}
	cfg.User, cfg.Password = role, password
	cfg.ConnectTimeout = 5 * time.Second
	cfg.RuntimeParams = map[string]string{"application_name": "mcp-router-login"}
	conn, err := pgx.ConnectConfig(ctx, cfg)
	if err != nil {
		return false
	}
	_ = conn.Close(ctx)
	return true
}

func (s *Server) apiRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/login", s.login)
	mux.Handle("GET /api/tools", s.auth(http.HandlerFunc(s.apiTools)))
	mux.Handle("GET /api/calls", s.auth(http.HandlerFunc(s.apiCalls)))
	mux.Handle("POST /api/decide", s.auth(http.HandlerFunc(s.apiDecide)))
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(code)
	if b, ok := v.([]byte); ok {
		w.Write(b)
		return
	}
	_ = json.NewEncoder(w).Encode(v)
}

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	var in struct{ Name, Password string }
	if json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&in) != nil {
		writeJSON(w, 400, map[string]string{"error": "bad request"})
		return
	}
	role, ok := personRole(in.Name)
	if ok && in.Password != "" && s.loginStore(r.Context(), role, in.Password) {
		writeJSON(w, 200, map[string]string{"token": mintToken(role, s.secret, tokenTTL, s.now()), "role": role})
		return
	}
	select {
	case <-time.After(time.Second):
	case <-r.Context().Done():
		return
	}
	writeJSON(w, 401, map[string]string{"error": "sign-in failed"})
}

func (s *Server) apiTools(w http.ResponseWriter, r *http.Request) {
	b, err := s.store.ToolsJSON(r.Context())
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": pgMessage(err)})
		return
	}
	writeJSON(w, 200, b)
}

func (s *Server) apiCalls(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 {
		limit = 100
	}
	b, err := s.store.CallsJSON(r.Context(), limit)
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": pgMessage(err)})
		return
	}
	writeJSON(w, 200, b)
}

func (s *Server) apiDecide(w http.ResponseWriter, r *http.Request) {
	role, _ := r.Context().Value(roleKey{}).(string)
	if !isPerson(role) {
		writeJSON(w, 403, map[string]string{"error": "only a person decides"})
		return
	}
	var in struct {
		Action  int64  `json:"action"`
		Approve bool   `json:"approve"`
		Reason  string `json:"reason"`
	}
	if json.NewDecoder(http.MaxBytesReader(w, r.Body, 16384)).Decode(&in) != nil || in.Action <= 0 {
		writeJSON(w, 400, map[string]string{"error": "bad request"})
		return
	}
	if err := s.store.Decide(r.Context(), in.Action, in.Approve, role, in.Reason); err != nil {
		writeJSON(w, 400, map[string]string{"error": pgMessage(err)})
		return
	}
	writeJSON(w, 200, map[string]any{"ok": true})
}
