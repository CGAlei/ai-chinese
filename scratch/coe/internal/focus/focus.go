package focus

import (
	"context"
	"fmt"

	"github.com/godbus/dbus/v5"
)

const (
	GNOMEShellFocusService   = "org.gnome.Shell"
	GNOMEShellFocusPath      = "/org/gnome/Shell/Extensions/FocusWmClass"
	GNOMEShellFocusInterface = "org.gnome.Shell.Extensions.FocusWmClass"
	getFocusedWindowMethod   = GNOMEShellFocusInterface + ".Get"
)

type Target struct {
	AppID   string
	WMClass string
	Title   string
}

func (t Target) Summary() string {
	switch {
	case t.AppID != "":
		return t.AppID
	case t.WMClass != "":
		return t.WMClass
	case t.Title != "":
		return t.Title
	default:
		return "unknown"
	}
}

type Provider interface {
	Focused(context.Context) (Target, error)
	Summary() string
	Close() error
}

type Disabled struct{}

func (Disabled) Focused(context.Context) (Target, error) {
	return Target{}, fmt.Errorf("focus provider is disabled")
}

func (Disabled) Summary() string {
	return "disabled"
}

func (Disabled) Close() error {
	return nil
}

type GNOMEShellProvider struct {
	conn *dbus.Conn
	obj  dbus.BusObject
}

func ConnectGNOMESession() (*GNOMEShellProvider, error) {
	conn, err := dbus.ConnectSessionBus()
	if err != nil {
		return nil, err
	}

	return &GNOMEShellProvider{
		conn: conn,
		obj:  conn.Object(GNOMEShellFocusService, dbus.ObjectPath(GNOMEShellFocusPath)),
	}, nil
}

func (p *GNOMEShellProvider) Focused(ctx context.Context) (Target, error) {
	if p == nil || p.obj == nil {
		return Target{}, fmt.Errorf("focus provider is unavailable")
	}

	var target Target
	if err := p.obj.CallWithContext(ctx, getFocusedWindowMethod, 0).Store(&target.WMClass); err != nil {
		return Target{}, err
	}
	return target, nil
}

func (p *GNOMEShellProvider) Summary() string {
	return "gnome-shell-dbus"
}

func (p *GNOMEShellProvider) Close() error {
	if p == nil || p.conn == nil {
		return nil
	}
	return p.conn.Close()
}
