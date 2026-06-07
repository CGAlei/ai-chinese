package portal

import (
	"testing"

	"github.com/godbus/dbus/v5/introspect"
)

func TestClassifyNode(t *testing.T) {
	t.Parallel()

	node := &introspect.Node{
		Name: DesktopObjectPath,
		Interfaces: []introspect.Interface{
			{Name: GlobalShortcutsInterface},
			{Name: RemoteDesktopInterface},
		},
	}

	parsed := ClassifyNode(node)
	if !parsed.GlobalShortcuts.Available {
		t.Fatal("expected GlobalShortcuts interface")
	}
	if !parsed.RemoteDesktop.Available {
		t.Fatal("expected RemoteDesktop interface")
	}
	if parsed.Clipboard.Available {
		t.Fatal("did not expect Clipboard interface")
	}
}
