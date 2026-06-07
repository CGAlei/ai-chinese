package audio

import (
	"errors"
	"os/exec"
	"testing"
)

func TestNormalizeStopErrorSuppressesExpectedPWRecordExitOne(t *testing.T) {
	err := exitError(t, 1)

	got := normalizeSessionEndError(err, Result{
		ByteCount: 1024,
		Stderr:    "",
	}, false)

	if got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
}

func TestNormalizeStopErrorKeepsRealExitOneWithoutAudio(t *testing.T) {
	err := exitError(t, 1)

	got := normalizeSessionEndError(err, Result{
		ByteCount: 0,
		Stderr:    "",
	}, false)

	if got == nil {
		t.Fatal("expected exit error to be preserved")
	}
}

func TestNormalizeStopErrorKeepsExitOneWithStderr(t *testing.T) {
	err := exitError(t, 1)

	got := normalizeSessionEndError(err, Result{
		ByteCount: 1024,
		Stderr:    "error: pw_context_connect() failed: Operation not permitted",
	}, false)

	if got == nil {
		t.Fatal("expected exit error to be preserved")
	}
}

func TestNormalizeCancelErrorSuppressesExpectedPWRecordExitOneWithoutAudio(t *testing.T) {
	err := exitError(t, 1)

	got := normalizeSessionEndError(err, Result{
		ByteCount: 0,
		Stderr:    "",
	}, true)

	if got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
}

func TestNormalizeCancelErrorKeepsExitOneWithStderr(t *testing.T) {
	err := exitError(t, 1)

	got := normalizeSessionEndError(err, Result{
		ByteCount: 0,
		Stderr:    "error: something real happened",
	}, true)

	if got == nil {
		t.Fatal("expected exit error to be preserved")
	}
}

func exitError(t *testing.T, code int) error {
	t.Helper()

	cmd := exec.Command("sh", "-c", "exit 1")
	err := cmd.Run()
	if err == nil {
		t.Fatal("expected exit error")
	}

	var exitErr *exec.ExitError
	if !errors.As(err, &exitErr) {
		t.Fatalf("expected *exec.ExitError, got %T", err)
	}
	if exitErr.ExitCode() != code {
		t.Fatalf("expected exit code %d, got %d", code, exitErr.ExitCode())
	}
	return err
}
