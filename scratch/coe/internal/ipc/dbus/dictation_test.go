package dbus

import (
	"context"
	"errors"
	"testing"
)

type stubHandler struct {
	toggleCalls              int
	toggleWithSelectionCalls []string
	startCalls               int
	startWithSelectionCalls  []string
	cancelCalls              int
	stopCalls                int
	triggerResp              TriggerResponse
	status                   Status
	runtimeMode              string
	triggerKey               string
	triggerMode              string
	sceneID                  string
	sceneName                string
	scenesJSON               string
	switchScene              string
	err                      error
}

func (h *stubHandler) Toggle(context.Context) error {
	h.toggleCalls++
	return h.err
}

func (h *stubHandler) ToggleWithSelectionEdit(_ context.Context, selectedText string) error {
	h.toggleWithSelectionCalls = append(h.toggleWithSelectionCalls, selectedText)
	return h.err
}

func (h *stubHandler) Start(context.Context) error {
	h.startCalls++
	return h.err
}

func (h *stubHandler) StartWithSelectionEdit(_ context.Context, selectedText string) error {
	h.startWithSelectionCalls = append(h.startWithSelectionCalls, selectedText)
	return h.err
}

func (h *stubHandler) Cancel(context.Context) error {
	h.cancelCalls++
	return h.err
}

func (h *stubHandler) Stop(context.Context) error {
	h.stopCalls++
	return h.err
}

func (h *stubHandler) TriggerToggle(context.Context) TriggerResponse {
	return h.triggerResp
}

func (h *stubHandler) TriggerStart(context.Context) TriggerResponse {
	return h.triggerResp
}

func (h *stubHandler) TriggerStop(context.Context) TriggerResponse {
	return h.triggerResp
}

func (h *stubHandler) TriggerStatus(context.Context) TriggerResponse {
	return h.triggerResp
}

func (h *stubHandler) Status(context.Context) Status {
	return h.status
}

func (h *stubHandler) RuntimeMode(context.Context) string {
	return h.runtimeMode
}

func (h *stubHandler) TriggerKey(context.Context) string {
	return h.triggerKey
}

func (h *stubHandler) TriggerMode(context.Context) string {
	return h.triggerMode
}

func (h *stubHandler) CurrentScene(context.Context) (string, string) {
	return h.sceneID, h.sceneName
}

func (h *stubHandler) ListScenes(context.Context) string {
	return h.scenesJSON
}

func (h *stubHandler) SwitchScene(_ context.Context, sceneID string) error {
	h.switchScene = sceneID
	return h.err
}

func TestDictationObjectToggleDelegatesToHandler(t *testing.T) {
	handler := &stubHandler{}
	object := &dictationObject{handler: handler}

	if err := object.Toggle(); err != nil {
		t.Fatalf("Toggle() error = %v, want nil", err)
	}
	if handler.toggleCalls != 1 {
		t.Fatalf("toggleCalls = %d, want 1", handler.toggleCalls)
	}
}

func TestDictationObjectToggleReturnsDBusError(t *testing.T) {
	handler := &stubHandler{err: errors.New("boom")}
	object := &dictationObject{handler: handler}

	if err := object.Toggle(); err == nil {
		t.Fatal("Toggle() error = nil, want D-Bus error")
	}
}

func TestDictationObjectToggleWithSelectionEditDelegatesToHandler(t *testing.T) {
	handler := &stubHandler{}
	object := &dictationObject{handler: handler}

	if err := object.ToggleWithSelectionEdit("hello"); err != nil {
		t.Fatalf("ToggleWithSelectionEdit() error = %v, want nil", err)
	}
	if len(handler.toggleWithSelectionCalls) != 1 || handler.toggleWithSelectionCalls[0] != "hello" {
		t.Fatalf("toggleWithSelectionCalls = %#v, want [hello]", handler.toggleWithSelectionCalls)
	}
}

func TestDictationObjectStartWithSelectionEditDelegatesToHandler(t *testing.T) {
	handler := &stubHandler{}
	object := &dictationObject{handler: handler}

	if err := object.StartWithSelectionEdit("hello"); err != nil {
		t.Fatalf("StartWithSelectionEdit() error = %v, want nil", err)
	}
	if len(handler.startWithSelectionCalls) != 1 || handler.startWithSelectionCalls[0] != "hello" {
		t.Fatalf("startWithSelectionCalls = %#v, want [hello]", handler.startWithSelectionCalls)
	}
}

func TestDictationObjectStatusReturnsSnapshot(t *testing.T) {
	handler := &stubHandler{
		status: Status{
			State:     "recording",
			SessionID: "session-1",
			Detail:    "capturing",
		},
	}
	object := &dictationObject{handler: handler}

	state, sessionID, detail, err := object.Status()
	if err != nil {
		t.Fatalf("Status() error = %v, want nil", err)
	}
	if state != handler.status.State || sessionID != handler.status.SessionID || detail != handler.status.Detail {
		t.Fatalf("Status() = (%q, %q, %q), want (%q, %q, %q)", state, sessionID, detail, handler.status.State, handler.status.SessionID, handler.status.Detail)
	}
}

func TestDictationObjectTriggerToggleReturnsResponse(t *testing.T) {
	handler := &stubHandler{
		triggerResp: TriggerResponse{
			OK:      true,
			Message: "trigger toggled on",
			Active:  true,
		},
	}
	object := &dictationObject{handler: handler}

	ok, message, active, err := object.TriggerToggle()
	if err != nil {
		t.Fatalf("TriggerToggle() error = %v, want nil", err)
	}
	if !ok || !active || message != "trigger toggled on" {
		t.Fatalf("TriggerToggle() = (%t, %q, %t), want (true, %q, true)", ok, message, active, "trigger toggled on")
	}
}

func TestDictationObjectCancelDelegatesToHandler(t *testing.T) {
	handler := &stubHandler{}
	object := &dictationObject{handler: handler}

	if err := object.Cancel(); err != nil {
		t.Fatalf("Cancel() error = %v, want nil", err)
	}
	if handler.cancelCalls != 1 {
		t.Fatalf("cancelCalls = %d, want 1", handler.cancelCalls)
	}
}

func TestDictationObjectTriggerKeyReturnsHandlerValue(t *testing.T) {
	handler := &stubHandler{triggerKey: "<Shift><Super>d"}
	object := &dictationObject{handler: handler}

	triggerKey, err := object.TriggerKey()
	if err != nil {
		t.Fatalf("TriggerKey() error = %v, want nil", err)
	}
	if triggerKey != handler.triggerKey {
		t.Fatalf("TriggerKey() = %q, want %q", triggerKey, handler.triggerKey)
	}
}

func TestDictationObjectRuntimeModeReturnsHandlerValue(t *testing.T) {
	handler := &stubHandler{runtimeMode: "fcitx"}
	object := &dictationObject{handler: handler}

	runtimeMode, err := object.RuntimeMode()
	if err != nil {
		t.Fatalf("RuntimeMode() error = %v, want nil", err)
	}
	if runtimeMode != handler.runtimeMode {
		t.Fatalf("RuntimeMode() = %q, want %q", runtimeMode, handler.runtimeMode)
	}
}

func TestDictationObjectCurrentSceneReturnsHandlerValue(t *testing.T) {
	handler := &stubHandler{sceneID: "terminal", sceneName: "Terminal"}
	object := &dictationObject{handler: handler}

	sceneID, sceneName, err := object.CurrentScene()
	if err != nil {
		t.Fatalf("CurrentScene() error = %v, want nil", err)
	}
	if sceneID != handler.sceneID || sceneName != handler.sceneName {
		t.Fatalf("CurrentScene() = (%q, %q), want (%q, %q)", sceneID, sceneName, handler.sceneID, handler.sceneName)
	}
}

func TestDictationObjectTriggerModeReturnsHandlerValue(t *testing.T) {
	handler := &stubHandler{triggerMode: "hold"}
	object := &dictationObject{handler: handler}

	triggerMode, err := object.TriggerMode()
	if err != nil {
		t.Fatalf("TriggerMode() error = %v, want nil", err)
	}
	if triggerMode != handler.triggerMode {
		t.Fatalf("TriggerMode() = %q, want %q", triggerMode, handler.triggerMode)
	}
}

func TestDictationObjectListScenesReturnsHandlerValue(t *testing.T) {
	handler := &stubHandler{scenesJSON: `[{"id":"general"}]`}
	object := &dictationObject{handler: handler}

	scenesJSON, err := object.ListScenes()
	if err != nil {
		t.Fatalf("ListScenes() error = %v, want nil", err)
	}
	if scenesJSON != handler.scenesJSON {
		t.Fatalf("ListScenes() = %q, want %q", scenesJSON, handler.scenesJSON)
	}
}

func TestDictationObjectSwitchSceneDelegatesToHandler(t *testing.T) {
	handler := &stubHandler{}
	object := &dictationObject{handler: handler}

	if err := object.SwitchScene("terminal"); err != nil {
		t.Fatalf("SwitchScene() error = %v, want nil", err)
	}
	if handler.switchScene != "terminal" {
		t.Fatalf("switchScene = %q, want %q", handler.switchScene, "terminal")
	}
}
