package main

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Outcome is env.mcp_outcome's row.
type Outcome struct {
	ID        int64
	Tool      string
	Caller    string
	Status    string
	Result    []byte // jsonb, may be nil
	Reason    string
	DecidedBy string
}

func textResult(isErr bool, format string, a ...any) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		IsError: isErr,
		Content: []mcp.Content{&mcp.TextContent{Text: fmt.Sprintf(format, a...)}},
	}
}

// storedResult reads the backend's CallToolResult JSON as kept by env.done. ok is false when it is not one.
func storedResult(raw []byte) (*mcp.CallToolResult, bool) {
	s := strings.TrimSpace(string(raw))
	if s == "" || s == "null" || s[0] != '{' {
		return nil, false
	}
	var probe map[string]json.RawMessage
	if json.Unmarshal(raw, &probe) != nil {
		return nil, false
	}
	if _, c := probe["content"]; !c {
		if _, sc := probe["structuredContent"]; !sc {
			return nil, false
		}
	}
	var r mcp.CallToolResult
	if err := json.Unmarshal(raw, &r); err != nil {
		return nil, false
	}
	if r.Content == nil {
		r.Content = []mcp.Content{}
	}
	return &r, true
}

// mapOutcome turns a finished (or waiting) action into the answer to the caller. done is false while the action
// still waits (proposed or queued).
func mapOutcome(o Outcome) (res *mcp.CallToolResult, done bool) {
	switch o.Status {
	case "applied":
		if r, ok := storedResult(o.Result); ok {
			return r, true
		}
		if len(o.Result) == 0 || string(o.Result) == "null" {
			return textResult(false, "action %d applied", o.ID), true
		}
		return textResult(false, "%s", o.Result), true
	case "failed":
		if r, ok := storedResult(o.Result); ok {
			r.IsError = true
			return r, true
		}
		if len(o.Result) == 0 || string(o.Result) == "null" {
			return textResult(true, "action %d failed", o.ID), true
		}
		return textResult(true, "action %d failed: %s", o.ID, o.Result), true
	case "refused":
		return textResult(true, "refused by %s: %s", o.DecidedBy, o.Reason), true
	case "denied":
		return textResult(true, "action %d was denied: the tool's gate is deny", o.ID), true
	}
	return nil, false
}

func waitingResult(id int64, status string) *mcp.CallToolResult {
	return textResult(true, "action %d is %s: it waits for a person's approval in the desktop's Review (or its server); ask router_outcome with action %d", id, status, id)
}
