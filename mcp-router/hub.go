package main

import (
	"context"
	"encoding/json"
	"log"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
)

// Hub holds one dedicated connection LISTENing on env_action and fans each notification out: to whoever waits on that
// action id, and to anyone who wants every one (the connector). Many waits cost one map entry and one channel each.
type Hub struct {
	dsn  string
	mu   sync.Mutex
	byID map[int64]map[chan struct{}]struct{}
	any  map[chan struct{}]struct{}
}

func NewHub(dsn string) *Hub {
	return &Hub{dsn: dsn, byID: map[int64]map[chan struct{}]struct{}{}, any: map[chan struct{}]struct{}{}}
}

// Wait subscribes to an action id; the channel gets a token when it changes. Call cancel when done.
func (h *Hub) Wait(id int64) (<-chan struct{}, func()) {
	ch := make(chan struct{}, 1)
	h.mu.Lock()
	if h.byID[id] == nil {
		h.byID[id] = map[chan struct{}]struct{}{}
	}
	h.byID[id][ch] = struct{}{}
	h.mu.Unlock()
	return ch, func() {
		h.mu.Lock()
		delete(h.byID[id], ch)
		if len(h.byID[id]) == 0 {
			delete(h.byID, id)
		}
		h.mu.Unlock()
	}
}

// Any subscribes to every notification whose status is one of statuses (all when empty).
func (h *Hub) Any() (<-chan struct{}, func()) {
	ch := make(chan struct{}, 1)
	h.mu.Lock()
	h.any[ch] = struct{}{}
	h.mu.Unlock()
	return ch, func() { h.mu.Lock(); delete(h.any, ch); h.mu.Unlock() }
}

func poke(ch chan struct{}) {
	select {
	case ch <- struct{}{}:
	default:
	}
}

func (h *Hub) fan(id int64, status string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if id < 0 { // after a (re)connect: anything may have changed
		for _, set := range h.byID {
			for ch := range set {
				poke(ch)
			}
		}
	}
	for ch := range h.byID[id] {
		poke(ch)
	}
	if status == "queued" || id < 0 {
		for ch := range h.any {
			poke(ch)
		}
	}
}

// Run keeps the listening connection until ctx ends, reconnecting with a pause.
func (h *Hub) Run(ctx context.Context) {
	for ctx.Err() == nil {
		if err := h.listen(ctx); err != nil && ctx.Err() == nil {
			log.Println("listener:", err)
		}
		select {
		case <-ctx.Done():
		case <-time.After(2 * time.Second):
		}
	}
}

func (h *Hub) listen(ctx context.Context) error {
	conn, err := pgx.Connect(ctx, h.dsn)
	if err != nil {
		return err
	}
	defer conn.Close(context.Background())
	if _, err := conn.Exec(ctx, "listen env_action"); err != nil {
		return err
	}
	h.fan(-1, "") // wake everyone: events may have been missed
	for {
		n, err := conn.WaitForNotification(ctx)
		if err != nil {
			return err
		}
		var p struct {
			ID     int64  `json:"id"`
			Status string `json:"status"`
		}
		if json.Unmarshal([]byte(n.Payload), &p) == nil {
			h.fan(p.ID, p.Status)
		}
	}
}
