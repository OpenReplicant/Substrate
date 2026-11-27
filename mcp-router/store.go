package main

import (
	"context"
	"errors"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

// ToolRow is env.mcp_tools()'s row.
type ToolRow struct {
	Name, Server, Tool, Title, Description string
	InputSchema, OutputSchema, Annotations []byte
	Gate                                   string
}

// Store is what serve needs from the database (the router login's functions).
type Store interface {
	Tools(ctx context.Context) ([]ToolRow, error)
	Call(ctx context.Context, tool string, args []byte, by string) (id int64, status string, err error)
	Outcome(ctx context.Context, id int64) (*Outcome, error)
	ToolsJSON(ctx context.Context) ([]byte, error)
	CallsJSON(ctx context.Context, limit int) ([]byte, error)
}

type pgStore struct{ pool *pgxpool.Pool }

// pgMessage is the database's own message without the "env: " prefix and context, safe to show a caller.
func pgMessage(err error) string {
	var pe *pgconn.PgError
	if errors.As(err, &pe) {
		return strings.TrimPrefix(pe.Message, "env: ")
	}
	return "database error"
}

func (s pgStore) Tools(ctx context.Context) ([]ToolRow, error) {
	rows, err := s.pool.Query(ctx, `select name, server, tool, coalesce(title,''), coalesce(description,''),
		input_schema, output_schema, annotations, gate from env.mcp_tools()`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ToolRow
	for rows.Next() {
		var t ToolRow
		if err := rows.Scan(&t.Name, &t.Server, &t.Tool, &t.Title, &t.Description, &t.InputSchema, &t.OutputSchema,
			&t.Annotations, &t.Gate); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

func (s pgStore) Call(ctx context.Context, tool string, args []byte, by string) (int64, string, error) {
	var id int64
	var status string
	err := s.pool.QueryRow(ctx, `select action, status from env.mcp_call($1, $2::jsonb, $3)`, tool, string(args), by).Scan(&id, &status)
	return id, status, err
}

func (s pgStore) Outcome(ctx context.Context, id int64) (*Outcome, error) {
	var o Outcome
	err := s.pool.QueryRow(ctx, `select id, tool, caller, status, result, coalesce(reason,''), coalesce(decided_by,'')
		from env.mcp_outcome($1)`, id).Scan(&o.ID, &o.Tool, &o.Caller, &o.Status, &o.Result, &o.Reason, &o.DecidedBy)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return &o, err
}

func (s pgStore) json(ctx context.Context, sql string, args ...any) ([]byte, error) {
	var b []byte
	err := s.pool.QueryRow(ctx, sql, args...).Scan(&b)
	return b, err
}

func (s pgStore) ToolsJSON(ctx context.Context) ([]byte, error) {
	return s.json(ctx, `select coalesce(jsonb_agg(t), '[]'::jsonb) from env.mcp_tools() t`)
}

func (s pgStore) CallsJSON(ctx context.Context, limit int) ([]byte, error) {
	return s.json(ctx, `select coalesce(jsonb_agg(c order by c.id desc), '[]'::jsonb) from env.mcp_calls($1) c`, limit)
}
