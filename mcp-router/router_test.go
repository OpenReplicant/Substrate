package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const secret = "0123456789abcdef0123456789abcdef" // a test fixture, not a secret gitleaks:allow

var t0 = time.Unix(1_800_000_000, 0)

func TestVerifyToken(t *testing.T) {
	good := mintToken("agent_a", secret, time.Hour, t0)
	if r, err := verifyToken(good, secret, t0.Add(time.Minute)); err != nil || r != "agent_a" {
		t.Fatalf("good token: %q %v", r, err)
	}
	if _, err := verifyToken(good, secret+"x", t0); err == nil {
		t.Error("wrong secret accepted")
	}
	if _, err := verifyToken(good, secret, t0.Add(2*time.Hour)); err == nil {
		t.Error("expired token accepted")
	}
	if _, err := verifyToken(mintToken("", secret, time.Hour, t0), secret, t0); err == nil {
		t.Error("token without role accepted")
	}
	if _, err := verifyToken("a.b.c", secret, t0); err == nil {
		t.Error("garbage accepted")
	}
	if _, err := verifyToken(good, "", t0); err == nil {
		t.Error("empty secret accepted")
	}
	// alg none
	none := b64.EncodeToString([]byte(`{"alg":"none"}`)) + "." + strings.Split(good, ".")[1] + "."
	if _, err := verifyToken(none, secret, t0); err == nil {
		t.Error("alg none accepted")
	}
	// no exp
	body := b64.EncodeToString([]byte(`{"role":"x","iat":1}`))
	head := b64.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	if _, err := verifyToken(head+"."+body+"."+b64.EncodeToString(sign(head+"."+body, secret)), secret, t0); err == nil {
		t.Error("token without exp accepted")
	}
}

func TestPersonRole(t *testing.T) {
	for in, want := range map[string]string{"pete": "person_pete", "ann-lee": "person_ann_lee", "a_b9": "person_a_b9"} {
		if got, ok := personRole(in); !ok || got != want {
			t.Errorf("%q: %q %v", in, got, ok)
		}
	}
	for _, bad := range []string{"", "Pete", "a b", "a;b", "a'b", "../x", strings.Repeat("a", 41), "é"} {
		if _, ok := personRole(bad); ok {
			t.Errorf("%q accepted", bad)
		}
	}
	if !isPerson("person_x") || isPerson("person_") || isPerson("agent_x") {
		t.Error("isPerson")
	}
}

func firstText(t *testing.T, r *mcp.CallToolResult) string {
	t.Helper()
	if len(r.Content) == 0 {
		return ""
	}
	tc, ok := r.Content[0].(*mcp.TextContent)
	if !ok {
		t.Fatalf("content is %T", r.Content[0])
	}
	return tc.Text
}

func TestMapOutcome(t *testing.T) {
	res, done := mapOutcome(Outcome{ID: 1, Status: "applied",
		Result: []byte(`{"content":[{"type":"text","text":"hi"}],"structuredContent":{"n":1}}`)})
	if !done || res.IsError || firstText(t, res) != "hi" {
		t.Fatalf("applied: %+v", res)
	}
	if m, _ := res.StructuredContent.(map[string]any); m["n"] != float64(1) {
		t.Errorf("structuredContent lost: %v", res.StructuredContent)
	}
	res, _ = mapOutcome(Outcome{ID: 2, Status: "applied", Result: []byte(`{"content":[{"type":"text","text":"x"}],"isError":true}`)})
	if !res.IsError {
		t.Error("isError of an applied result not passed through")
	}
	res, done = mapOutcome(Outcome{ID: 3, Status: "failed", Result: []byte(`{"error":"boom"}`)})
	if !done || !res.IsError || !strings.Contains(firstText(t, res), "boom") {
		t.Errorf("failed: %+v", res)
	}
	res, _ = mapOutcome(Outcome{ID: 4, Status: "failed", Result: []byte(`{"content":[{"type":"text","text":"bad"}]}`)})
	if !res.IsError || firstText(t, res) != "bad" {
		t.Errorf("failed with content: %+v", res)
	}
	res, done = mapOutcome(Outcome{ID: 5, Status: "refused", DecidedBy: "person_ann", Reason: "no"})
	if !done || !res.IsError || firstText(t, res) != "refused by person_ann: no" {
		t.Errorf("refused: %q", firstText(t, res))
	}
	res, done = mapOutcome(Outcome{ID: 6, Status: "denied"})
	if !done || !res.IsError {
		t.Error("denied")
	}
	for _, s := range []string{"proposed", "queued"} {
		if _, done := mapOutcome(Outcome{Status: s}); done {
			t.Errorf("%s reported done", s)
		}
	}
	if got := firstText(t, waitingResult(9, "proposed")); !strings.Contains(got, "action 9 is proposed: it waits for a person's approval") {
		t.Errorf("waiting text: %s", got)
	}
}

// fakeStore stands for the database: a call is finished by the test.
type fakeStore struct {
	mu       sync.Mutex
	outcomes map[int64]*Outcome
	next     int64
	status   string
	gotBy    string
	gotArgs  string
}

func (f *fakeStore) Tools(context.Context) ([]ToolRow, error) {
	return []ToolRow{
		{Name: "echo_say", Server: "echo", Tool: "say", Description: "says", InputSchema: []byte(`{"type":"object"}`), Annotations: []byte(`{"readOnlyHint":true}`)},
		{Name: "bad_one", InputSchema: []byte(`{"type":"string"}`)}, // malformed: skipped, not fatal
	}, nil
}
func (f *fakeStore) Call(_ context.Context, tool string, args []byte, by string) (int64, string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.next++
	f.gotBy, f.gotArgs = by, string(args)
	f.outcomes[f.next] = &Outcome{ID: f.next, Tool: tool, Caller: by, Status: f.status}
	return f.next, f.status, nil
}
func (f *fakeStore) Outcome(_ context.Context, id int64) (*Outcome, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if o, ok := f.outcomes[id]; ok {
		c := *o
		return &c, nil
	}
	return nil, nil
}
func (f *fakeStore) ToolsJSON(context.Context) ([]byte, error)      { return []byte(`[]`), nil }
func (f *fakeStore) CallsJSON(context.Context, int) ([]byte, error) { return []byte(`[]`), nil }
func (f *fakeStore) Decide(_ context.Context, id int64, approve bool, person, reason string) error {
	return nil
}
func (f *fakeStore) finish(id int64, status string, result string) {
	f.mu.Lock()
	o := f.outcomes[id]
	o.Status, o.Result = status, []byte(result)
	f.mu.Unlock()
}

type tokenRT struct{ token string }

func (t tokenRT) RoundTrip(r *http.Request) (*http.Response, error) {
	r = r.Clone(r.Context())
	if t.token != "" {
		r.Header.Set("Authorization", "Bearer "+t.token)
	}
	return http.DefaultTransport.RoundTrip(r)
}

func newTestServer(t *testing.T, f *fakeStore, wait time.Duration) (*httptest.Server, *Server) {
	s := &Server{store: f, hub: NewHub(""), secret: secret, wait: wait, frameAncestors: "http://localhost:8080",
		loginStore: func(_ context.Context, role, pw string) bool { return role == "person_ann" && pw == "pw" }, now: time.Now}
	ts := httptest.NewServer(s.Handler())
	t.Cleanup(ts.Close)
	return ts, s
}

func connectClient(t *testing.T, url, token string) (*mcp.ClientSession, error) {
	c := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "0"}, nil)
	return c.Connect(context.Background(), &mcp.StreamableClientTransport{Endpoint: url + "/mcp",
		HTTPClient: &http.Client{Transport: tokenRT{token}}, DisableStandaloneSSE: true, MaxRetries: -1}, nil)
}

func TestMCPOverHTTP(t *testing.T) {
	f := &fakeStore{outcomes: map[int64]*Outcome{}, status: "queued"}
	ts, srv := newTestServer(t, f, 300*time.Millisecond)

	// no token: 401
	resp, err := http.Post(ts.URL+"/mcp", "application/json", strings.NewReader(`{}`))
	if err != nil || resp.StatusCode != 401 {
		t.Fatalf("no token: %v %v", resp, err)
	}
	resp.Body.Close()
	if r, _ := http.Get(ts.URL + "/healthz"); r.StatusCode != 200 {
		t.Error("healthz needs no auth")
	}

	cs, err := connectClient(t, ts.URL, mintToken("agent_a", secret, time.Minute, time.Now()))
	if err != nil {
		t.Fatal(err)
	}
	defer cs.Close()
	var names []string
	for tool, err := range cs.Tools(context.Background(), nil) {
		if err != nil {
			t.Fatal(err)
		}
		names = append(names, tool.Name)
	}
	if strings.Join(names, ",") != "echo_say,router_outcome" {
		t.Fatalf("tools: %v", names)
	}

	// a call that the test finishes while the router waits
	go func() {
		time.Sleep(100 * time.Millisecond)
		f.finish(1, "applied", `{"content":[{"type":"text","text":"pong"}]}`)
		srv.hub.fan(1, "applied")
	}()
	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "echo_say", Arguments: map[string]any{"a": 1}})
	if err != nil || res.IsError || firstText(t, res) != "pong" {
		t.Fatalf("call: %+v %v", res, err)
	}
	if f.gotBy != "agent_a" || f.gotArgs != `{"a":1}` {
		t.Errorf("store saw by=%q args=%q", f.gotBy, f.gotArgs)
	}

	// nothing finishes it: the waiting text
	res, err = cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "echo_say"})
	if err != nil || !res.IsError || !strings.Contains(firstText(t, res), "action 2 is queued: it waits") {
		t.Fatalf("timeout: %+v %v", res, err)
	}
	// router_outcome
	res, err = cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "router_outcome", Arguments: map[string]any{"action": 1}})
	var out map[string]any
	if err != nil || json.Unmarshal([]byte(firstText(t, res)), &out) != nil || out["status"] != "applied" {
		t.Fatalf("outcome: %+v %v", res, err)
	}
	// denied
	f.status = "denied"
	res, _ = cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "echo_say"})
	if !res.IsError || !strings.Contains(firstText(t, res), "denied") {
		t.Errorf("denied: %+v", res)
	}
}

func TestAPIAndHeaders(t *testing.T) {
	f := &fakeStore{outcomes: map[int64]*Outcome{}}
	ts, _ := newTestServer(t, f, time.Second)
	get := func(path, token string) *http.Response {
		req, _ := http.NewRequest("GET", ts.URL+path, nil)
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
		r, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		return r
	}
	if r := get("/api/tools", ""); r.StatusCode != 401 {
		t.Errorf("api without token: %d", r.StatusCode)
	}
	r := get("/", "")
	if r.StatusCode != 200 || !strings.Contains(r.Header.Get("Content-Security-Policy"), "frame-ancestors http://localhost:8080;") ||
		r.Header.Get("X-Content-Type-Options") != "nosniff" || r.Header.Get("Referrer-Policy") != "no-referrer" {
		t.Errorf("page: %d %v", r.StatusCode, r.Header)
	}
	for _, p := range []string{"/app.js", "/style.css"} {
		if r := get(p, ""); r.StatusCode != 200 {
			t.Errorf("%s: %d", p, r.StatusCode)
		}
	}
	// an agent role may read but not decide
	agent := mintToken("agent_a", secret, time.Minute, time.Now())
	if r := get("/api/calls?limit=5", agent); r.StatusCode != 200 {
		t.Errorf("calls: %d", r.StatusCode)
	}
	post := func(path, body, token string) *http.Response {
		req, _ := http.NewRequest("POST", ts.URL+path, strings.NewReader(body))
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
		r, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		return r
	}
	if r := post("/api/decide", `{"action":1,"approve":true}`, agent); r.StatusCode != 403 {
		t.Errorf("agent decide: %d", r.StatusCode)
	}
	person := mintToken("person_ann", secret, time.Minute, time.Now())
	if r := post("/api/decide", `{"action":1,"approve":true}`, person); r.StatusCode != 200 {
		t.Errorf("person decide: %d", r.StatusCode)
	}
	// login
	r = post("/api/login", `{"name":"ann","password":"pw"}`, "")
	var lj struct{ Token, Role string }
	json.NewDecoder(r.Body).Decode(&lj)
	if role, err := verifyToken(lj.Token, secret, time.Now()); r.StatusCode != 200 || err != nil || role != "person_ann" || lj.Role != role {
		t.Errorf("login: %d %+v", r.StatusCode, lj)
	}
	start := time.Now()
	if r := post("/api/login", `{"name":"ann","password":"wrong"}`, ""); r.StatusCode != 401 || time.Since(start) < time.Second {
		t.Errorf("bad login: %d after %v", r.StatusCode, time.Since(start))
	}
}

func TestHubFanOut(t *testing.T) {
	h := NewHub("")
	a, ca := h.Wait(7)
	b, cb := h.Wait(8)
	defer ca()
	defer cb()
	h.fan(7, "applied")
	select {
	case <-a:
	default:
		t.Error("waiter 7 not woken")
	}
	select {
	case <-b:
		t.Error("waiter 8 woken by 7")
	default:
	}
}
