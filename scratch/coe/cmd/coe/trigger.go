package main

import (
	"context"
	"errors"
	"fmt"

	dbusipc "coe/internal/ipc/dbus"
)

var sendTrigger = dbusipc.SendTrigger

func runTrigger(ctx context.Context, args []string) error {
	if len(args) == 0 {
		return errors.New("usage: coe trigger <toggle|start|stop|status>")
	}

	command, err := parseTriggerCommand(args[0])
	if err != nil {
		return err
	}

	resp, err := sendTrigger(ctx, command)
	if err != nil {
		return fmt.Errorf("send trigger command over D-Bus: %w", err)
	}

	fmt.Printf("%s (active=%t)\n", resp.Message, resp.Active)
	if !resp.OK {
		return errors.New(resp.Message)
	}
	return nil
}

func parseTriggerCommand(arg string) (dbusipc.TriggerCommand, error) {
	switch arg {
	case "toggle":
		return dbusipc.TriggerCommandToggle, nil
	case "start":
		return dbusipc.TriggerCommandStart, nil
	case "stop":
		return dbusipc.TriggerCommandStop, nil
	case "status":
		return dbusipc.TriggerCommandStatus, nil
	default:
		return "", fmt.Errorf("unknown trigger command %q", arg)
	}
}
