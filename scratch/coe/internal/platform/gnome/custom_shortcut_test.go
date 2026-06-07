package gnome

import (
	"context"
	"fmt"
	"strings"
	"testing"
)

func TestEnsureTriggerShortcutCreatesNewBinding(t *testing.T) {
	t.Parallel()

	runner := &fakeRunner{
		values: map[string]string{
			joinKey("gsettings", "get", mediaKeysSchema, "custom-keybindings"): "[]",
		},
	}
	manager := ShortcutManager{runner: runner}

	if err := manager.ensure(context.Background(), Shortcut{
		Name:    "coe-trigger",
		Command: "/home/test/.local/bin/coe trigger toggle",
		Binding: "<Shift><Super>d",
	}); err != nil {
		t.Fatalf("ensure() error = %v", err)
	}

	expectedPath := customBindingBase + "custom0/"
	if got := runner.values[joinKey("gsettings", "set", mediaKeysSchema, "custom-keybindings", "['"+expectedPath+"']")]; got != "ok" {
		t.Fatalf("expected custom shortcut list write, got %q", got)
	}
	if got := runner.values[joinKey("gsettings", "set", schemaForPath(expectedPath), "command", "'/home/test/.local/bin/coe trigger toggle'")]; got != "ok" {
		t.Fatalf("expected command write, got %q", got)
	}
}

func TestEnsureTriggerShortcutUpdatesExistingBindingWithoutAppending(t *testing.T) {
	t.Parallel()

	path := customBindingBase + "custom2/"
	runner := &fakeRunner{
		values: map[string]string{
			joinKey("gsettings", "get", mediaKeysSchema, "custom-keybindings"): fmt.Sprintf("['%s']", path),
			joinKey("gsettings", "get", schemaForPath(path), "name"):           "'coe-trigger'",
			joinKey("gsettings", "get", schemaForPath(path), "command"):        "'/old/path/coe trigger toggle'",
			joinKey("gsettings", "get", schemaForPath(path), "binding"):        "'<Shift><Super>d'",
		},
	}
	manager := ShortcutManager{runner: runner}

	if err := manager.ensure(context.Background(), Shortcut{
		Name:    "coe-trigger",
		Command: "/home/test/.local/bin/coe trigger toggle",
		Binding: "<Shift><Super>d",
	}); err != nil {
		t.Fatalf("ensure() error = %v", err)
	}

	for _, call := range runner.calls {
		if strings.Contains(strings.Join(call, " "), "custom-keybindings ['") {
			t.Fatalf("did not expect list append, got call %v", call)
		}
	}
	if got := runner.values[joinKey("gsettings", "set", schemaForPath(path), "binding", "'<Shift><Super>d'")]; got != "ok" {
		t.Fatalf("expected binding update, got %q", got)
	}
}

func TestNextShortcutPathUsesFirstGap(t *testing.T) {
	t.Parallel()

	paths := []string{
		customBindingBase + "custom0/",
		customBindingBase + "custom2/",
	}
	if got := nextShortcutPath(paths); got != customBindingBase+"custom1/" {
		t.Fatalf("nextShortcutPath() = %q", got)
	}
}

func TestRemoveTriggerShortcutRemovesManagedBindingOnly(t *testing.T) {
	t.Parallel()

	coePath := customBindingBase + "custom0/"
	otherPath := customBindingBase + "custom1/"
	runner := &fakeRunner{
		values: map[string]string{
			joinKey("gsettings", "get", mediaKeysSchema, "custom-keybindings"): fmt.Sprintf("['%s', '%s']", coePath, otherPath),
			joinKey("gsettings", "get", schemaForPath(coePath), "name"):        "'coe-trigger'",
			joinKey("gsettings", "get", schemaForPath(coePath), "command"):     "'/home/test/.local/bin/coe trigger toggle'",
			joinKey("gsettings", "get", schemaForPath(coePath), "binding"):     "'<Shift><Super>d'",
			joinKey("gsettings", "get", schemaForPath(otherPath), "name"):      "'other-shortcut'",
			joinKey("gsettings", "get", schemaForPath(otherPath), "command"):   "'/usr/bin/echo hello'",
			joinKey("gsettings", "get", schemaForPath(otherPath), "binding"):   "'<Ctrl><Alt>t'",
		},
	}
	manager := ShortcutManager{runner: runner}

	if err := manager.RemoveTriggerShortcut(context.Background(), "coe-trigger"); err != nil {
		t.Fatalf("RemoveTriggerShortcut() error = %v", err)
	}

	if got := runner.values[joinKey("gsettings", "set", mediaKeysSchema, "custom-keybindings", "['"+otherPath+"']")]; got != "ok" {
		t.Fatalf("expected updated custom shortcut list, got %q", got)
	}
}

type fakeRunner struct {
	values map[string]string
	calls  [][]string
}

func (r *fakeRunner) Run(_ context.Context, name string, args ...string) ([]byte, error) {
	call := append([]string{name}, args...)
	r.calls = append(r.calls, call)

	key := joinKey(name, args...)
	if name == "gsettings" && len(args) > 0 && args[0] == "set" {
		if r.values == nil {
			r.values = map[string]string{}
		}
		r.values[key] = "ok"
		return []byte(""), nil
	}

	value, ok := r.values[key]
	if !ok {
		return nil, fmt.Errorf("unexpected command: %s", key)
	}
	return []byte(value), nil
}

func joinKey(name string, args ...string) string {
	parts := append([]string{name}, args...)
	return strings.Join(parts, "\x00")
}
