package app

import (
	"fmt"
	"sync"

	dbusipc "coe/internal/ipc/dbus"
)

type dictationState struct {
	mu      sync.RWMutex
	nextID  uint64
	current dbusipc.Status
}

func newDictationState() *dictationState {
	return &dictationState{
		current: dbusipc.Status{
			State: "idle",
		},
	}
}

func (s *dictationState) Snapshot() dbusipc.Status {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.current
}

func (s *dictationState) Idle(detail string) dbusipc.Status {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.current = dbusipc.Status{
		State:  "idle",
		Detail: detail,
	}
	return s.current
}

func (s *dictationState) Recording(detail string) dbusipc.Status {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.nextID++
	s.current = dbusipc.Status{
		State:     "recording",
		SessionID: fmt.Sprintf("session-%06d", s.nextID),
		Detail:    detail,
	}
	return s.current
}

func (s *dictationState) Processing(detail string) dbusipc.Status {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.current.State = "processing"
	s.current.Detail = detail
	return s.current
}

func (s *dictationState) Completed(detail string) dbusipc.Status {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.current.State = "completed"
	s.current.Detail = detail
	return s.current
}

func (s *dictationState) Error(detail string) dbusipc.Status {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.current.State = "error"
	s.current.Detail = detail
	return s.current
}
