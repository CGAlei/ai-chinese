package portal

import "github.com/godbus/dbus/v5"

const (
	GlobalShortcutsCreateSessionMethod   = GlobalShortcutsInterface + ".CreateSession"
	GlobalShortcutsBindShortcutsMethod   = GlobalShortcutsInterface + ".BindShortcuts"
	GlobalShortcutsListShortcutsMethod   = GlobalShortcutsInterface + ".ListShortcuts"
	GlobalShortcutsConfigureMethod       = GlobalShortcutsInterface + ".ConfigureShortcuts"
	GlobalShortcutsActivatedSignalName   = GlobalShortcutsInterface + ".Activated"
	GlobalShortcutsDeactivatedSignalName = GlobalShortcutsInterface + ".Deactivated"
)

type GlobalShortcut struct {
	ID               string
	Description      string
	PreferredTrigger string
}

type GlobalShortcutsEventType string

const (
	GlobalShortcutsActivated   GlobalShortcutsEventType = "activated"
	GlobalShortcutsDeactivated GlobalShortcutsEventType = "deactivated"
)

type GlobalShortcutsEvent struct {
	Type          GlobalShortcutsEventType
	SessionHandle dbus.ObjectPath
	ShortcutID    string
	Timestamp     uint64
	Options       map[string]dbus.Variant
}
