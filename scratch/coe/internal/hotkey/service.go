package hotkey

import (
	"context"
)

type EventType string

const (
	Activated   EventType = "activated"
	Deactivated EventType = "deactivated"
)

type Event struct {
	Type EventType
}

type Service interface {
	Plan() string
	Events(context.Context) (<-chan Event, error)
}

type PlannedService struct {
	Description string
}

func (s PlannedService) Plan() string {
	return s.Description
}

func (s PlannedService) Events(ctx context.Context) (<-chan Event, error) {
	events := make(chan Event)
	go func() {
		<-ctx.Done()
		close(events)
	}()
	return events, nil
}
