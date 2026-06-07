package dbus

import (
	"context"
	"fmt"

	godbus "github.com/godbus/dbus/v5"
)

type TriggerCommand string

const (
	TriggerCommandToggle TriggerCommand = "toggle"
	TriggerCommandStart  TriggerCommand = "start"
	TriggerCommandStop   TriggerCommand = "stop"
	TriggerCommandStatus TriggerCommand = "status"
)

type triggerObject interface {
	CallWithContext(ctx context.Context, method string, flags godbus.Flags, args ...interface{}) *godbus.Call
}

func SendTrigger(ctx context.Context, command TriggerCommand) (TriggerResponse, error) {
	conn, err := godbus.ConnectSessionBus()
	if err != nil {
		return TriggerResponse{}, err
	}
	defer conn.Close()

	return sendTriggerWithObject(ctx, conn.Object(DictationServiceName, DictationObjectPath), command)
}

func sendTriggerWithObject(ctx context.Context, obj triggerObject, command TriggerCommand) (TriggerResponse, error) {
	method, err := triggerMethodName(command)
	if err != nil {
		return TriggerResponse{}, err
	}

	call := obj.CallWithContext(ctx, DictationInterface+"."+method, 0)
	if call.Err != nil {
		return TriggerResponse{}, call.Err
	}

	var resp TriggerResponse
	if err := call.Store(&resp.OK, &resp.Message, &resp.Active); err != nil {
		return TriggerResponse{}, err
	}
	return resp, nil
}

func triggerMethodName(command TriggerCommand) (string, error) {
	switch command {
	case TriggerCommandToggle:
		return "TriggerToggle", nil
	case TriggerCommandStart:
		return "TriggerStart", nil
	case TriggerCommandStop:
		return "TriggerStop", nil
	case TriggerCommandStatus:
		return "TriggerStatus", nil
	default:
		return "", fmt.Errorf("unsupported trigger command %q", command)
	}
}
