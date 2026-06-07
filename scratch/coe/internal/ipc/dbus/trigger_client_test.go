package dbus

import (
	"context"
	"errors"
	"testing"

	godbus "github.com/godbus/dbus/v5"
)

type stubTriggerObject struct {
	method string
	call   *godbus.Call
}

func (s *stubTriggerObject) CallWithContext(_ context.Context, method string, _ godbus.Flags, _ ...interface{}) *godbus.Call {
	s.method = method
	return s.call
}

func TestSendTriggerWithObjectDecodesResponse(t *testing.T) {
	t.Parallel()

	obj := &stubTriggerObject{
		call: &godbus.Call{Body: []interface{}{true, "trigger active", true}},
	}

	resp, err := sendTriggerWithObject(context.Background(), obj, TriggerCommandStatus)
	if err != nil {
		t.Fatalf("sendTriggerWithObject() error = %v", err)
	}
	if obj.method != DictationInterface+".TriggerStatus" {
		t.Fatalf("method = %q, want %q", obj.method, DictationInterface+".TriggerStatus")
	}
	if !resp.OK || !resp.Active || resp.Message != "trigger active" {
		t.Fatalf("response = %#v, want ok/active/message", resp)
	}
}

func TestSendTriggerWithObjectReturnsCallError(t *testing.T) {
	t.Parallel()

	obj := &stubTriggerObject{
		call: &godbus.Call{Err: errors.New("dbus unavailable")},
	}

	_, err := sendTriggerWithObject(context.Background(), obj, TriggerCommandToggle)
	if err == nil || err.Error() != "dbus unavailable" {
		t.Fatalf("sendTriggerWithObject() error = %v, want dbus unavailable", err)
	}
}

func TestTriggerMethodNameRejectsUnknownCommand(t *testing.T) {
	t.Parallel()

	_, err := triggerMethodName("invalid")
	if err == nil {
		t.Fatal("triggerMethodName() error = nil, want error")
	}
}
