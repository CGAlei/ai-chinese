package main

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"strings"
	"testing"

	dbusipc "coe/internal/ipc/dbus"
)

func TestRunTrigger(t *testing.T) {
	tests := []struct {
		name    string
		args    []string
		resp    dbusipc.TriggerResponse
		sendErr error
		wantErr string
		wantOut string
		wantCmd dbusipc.TriggerCommand
	}{
		{
			name:    "successful trigger command",
			args:    []string{"status"},
			resp:    dbusipc.TriggerResponse{OK: true, Message: "trigger inactive", Active: false},
			wantOut: "trigger inactive (active=false)\n",
			wantCmd: dbusipc.TriggerCommandStatus,
		},
		{
			name:    "transport error surfaces",
			args:    []string{"toggle"},
			sendErr: errors.New("name has no owner"),
			wantErr: "send trigger command over D-Bus: name has no owner",
			wantCmd: dbusipc.TriggerCommandToggle,
		},
		{
			name:    "daemon rejects command",
			args:    []string{"start"},
			resp:    dbusipc.TriggerResponse{OK: false, Message: "dictation runtime loop is not ready", Active: false},
			wantErr: "dictation runtime loop is not ready",
			wantOut: "dictation runtime loop is not ready (active=false)\n",
			wantCmd: dbusipc.TriggerCommandStart,
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			original := sendTrigger
			defer func() { sendTrigger = original }()

			var gotCmd dbusipc.TriggerCommand
			sendTrigger = func(_ context.Context, command dbusipc.TriggerCommand) (dbusipc.TriggerResponse, error) {
				gotCmd = command
				return tt.resp, tt.sendErr
			}

			output := captureStdout(t, func() error {
				return runTrigger(context.Background(), tt.args)
			})

			if gotCmd != tt.wantCmd {
				t.Fatalf("command = %q, want %q", gotCmd, tt.wantCmd)
			}
			if output.out != tt.wantOut {
				t.Fatalf("stdout = %q, want %q", output.out, tt.wantOut)
			}
			if tt.wantErr == "" {
				if output.err != nil {
					t.Fatalf("runTrigger() error = %v", output.err)
				}
				return
			}
			if output.err == nil || output.err.Error() != tt.wantErr {
				t.Fatalf("runTrigger() error = %v, want %q", output.err, tt.wantErr)
			}
		})
	}
}

func TestParseTriggerCommandRejectsUnknownCommand(t *testing.T) {
	t.Parallel()

	_, err := parseTriggerCommand("resume")
	if err == nil || !strings.Contains(err.Error(), "unknown trigger command") {
		t.Fatalf("parseTriggerCommand() error = %v, want unknown command error", err)
	}
}

func captureStdout(t *testing.T, fn func() error) struct {
	out string
	err error
} {
	t.Helper()

	original := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("os.Pipe() error = %v", err)
	}
	defer r.Close()

	os.Stdout = w
	runErr := fn()
	_ = w.Close()
	os.Stdout = original

	var buf bytes.Buffer
	if _, err := io.Copy(&buf, r); err != nil {
		t.Fatalf("io.Copy() error = %v", err)
	}

	return struct {
		out string
		err error
	}{
		out: buf.String(),
		err: runErr,
	}
}
