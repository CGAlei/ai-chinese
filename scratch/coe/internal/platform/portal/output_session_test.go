package portal

import "testing"

func TestPasteShortcutEvents(t *testing.T) {
	t.Parallel()

	tests := []struct {
		shortcut string
		want     int
	}{
		{shortcut: "ctrl+v", want: 4},
		{shortcut: "ctrl+shift+v", want: 6},
		{shortcut: "shift+insert", want: 4},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.shortcut, func(t *testing.T) {
			t.Parallel()

			events, err := pasteShortcutEvents(tt.shortcut)
			if err != nil {
				t.Fatalf("pasteShortcutEvents() error = %v", err)
			}
			if len(events) != tt.want {
				t.Fatalf("len(events) = %d, want %d", len(events), tt.want)
			}
		})
	}
}

func TestPasteShortcutEventsRejectsUnknownShortcut(t *testing.T) {
	t.Parallel()

	if _, err := pasteShortcutEvents("meta+v"); err == nil {
		t.Fatal("pasteShortcutEvents() error = nil, want error")
	}
}
