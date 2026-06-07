package app

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"

	"coe/internal/config"
	dbusipc "coe/internal/ipc/dbus"
	"coe/internal/scene"
)

func (a *App) Toggle(context.Context) error {
	_, err := a.triggerToggleFrom("fcitx-module")
	return err
}

func (a *App) ToggleWithSelectionEdit(_ context.Context, selectedText string) error {
	_, err := a.triggerToggleWithSelectionEditFrom("fcitx-module", selectedText)
	return err
}

func (a *App) Start(context.Context) error {
	_, err := a.triggerStartFrom("fcitx-module")
	return err
}

func (a *App) StartWithSelectionEdit(_ context.Context, selectedText string) error {
	_, err := a.triggerStartWithSelectionEditFrom("fcitx-module", selectedText)
	return err
}

func (a *App) Cancel(context.Context) error {
	_, err := a.triggerCancelFrom("fcitx-module")
	return err
}

func (a *App) Stop(context.Context) error {
	_, err := a.triggerStopFrom("fcitx-module")
	return err
}

func (a *App) TriggerToggle(context.Context) dbusipc.TriggerResponse {
	active, err := a.triggerToggleFrom("trigger-command")
	if err != nil {
		return dbusipc.TriggerResponse{OK: false, Message: err.Error(), Active: a.triggerActive()}
	}
	return dbusipc.TriggerResponse{
		OK:      true,
		Message: pickMessage(active, "trigger toggled on", "trigger toggled off"),
		Active:  active,
	}
}

func (a *App) TriggerStart(context.Context) dbusipc.TriggerResponse {
	changed, err := a.triggerStartFrom("trigger-command")
	if err != nil {
		return dbusipc.TriggerResponse{OK: false, Message: err.Error(), Active: a.triggerActive()}
	}
	return dbusipc.TriggerResponse{
		OK:      true,
		Message: pickMessage(changed, "trigger started", "trigger already active"),
		Active:  a.triggerActive(),
	}
}

func (a *App) TriggerStop(context.Context) dbusipc.TriggerResponse {
	changed, err := a.triggerStopFrom("trigger-command")
	if err != nil {
		return dbusipc.TriggerResponse{OK: false, Message: err.Error(), Active: a.triggerActive()}
	}
	return dbusipc.TriggerResponse{
		OK:      true,
		Message: pickMessage(changed, "trigger stopped", "trigger already inactive"),
		Active:  a.triggerActive(),
	}
}

func (a *App) TriggerStatus(context.Context) dbusipc.TriggerResponse {
	active := a.triggerActive()
	return dbusipc.TriggerResponse{
		OK:      true,
		Message: pickMessage(active, "trigger active", "trigger inactive"),
		Active:  active,
	}
}

func (a *App) Status(context.Context) dbusipc.Status {
	if a.dictationState == nil {
		return a.withSceneDetail(dbusipc.Status{State: "idle"})
	}
	return a.withSceneDetail(a.dictationState.Snapshot())
}

func (a *App) RuntimeMode(context.Context) string {
	mode := config.NormalizeRuntimeMode(a.Config.Runtime.Mode)
	if mode == "" {
		return config.Default().Runtime.Mode
	}
	return mode
}

func (a *App) TriggerKey(context.Context) string {
	if value := strings.TrimSpace(a.Config.Hotkey.PreferredAccelerator); value != "" {
		return value
	}
	return config.Default().Hotkey.PreferredAccelerator
}

func (a *App) TriggerMode(context.Context) string {
	if config.NormalizeRuntimeMode(a.Config.Runtime.Mode) != config.RuntimeModeFcitx {
		return config.FcitxTriggerModeToggle
	}
	if value := strings.TrimSpace(a.Config.Hotkey.TriggerMode); value != "" {
		return config.NormalizeFcitxTriggerMode(value)
	}
	return config.Default().Hotkey.TriggerMode
}

func (a *App) CurrentScene(context.Context) (string, string) {
	current := a.currentScene()
	return current.ID, a.sceneDisplayName(current)
}

func (a *App) ListScenes(context.Context) string {
	payload, err := json.Marshal(scene.ListDisplayScenes(a.SceneState, a.Localizer))
	if err != nil {
		return "[]"
	}
	return string(payload)
}

func (a *App) SwitchScene(_ context.Context, sceneID string) error {
	_, _, err := a.switchSceneByID(sceneID)
	return err
}

func (a *App) triggerToggle() (bool, error) {
	return a.triggerToggleFrom("ipc")
}

func (a *App) triggerToggleFrom(source string) (bool, error) {
	response, err := a.executeRuntimeCommand(context.Background(), runtimeCommandToggle, source, nil)
	if err != nil {
		return false, err
	}
	return response.Active, nil
}

func (a *App) triggerToggleWithSelectionEditFrom(source, selectedText string) (bool, error) {
	response, err := a.executeRuntimeCommand(context.Background(), runtimeCommandToggle, source, &selectedTextEditRequest{
		SelectedText: selectedText,
	})
	if err != nil {
		return false, err
	}
	return response.Active, nil
}

func (a *App) triggerStart() (bool, error) {
	return a.triggerStartFrom("ipc")
}

func (a *App) triggerStartFrom(source string) (bool, error) {
	response, err := a.executeRuntimeCommand(context.Background(), runtimeCommandStart, source, nil)
	if err != nil {
		return false, err
	}
	return response.Changed, nil
}

func (a *App) triggerStartWithSelectionEditFrom(source, selectedText string) (bool, error) {
	response, err := a.executeRuntimeCommand(context.Background(), runtimeCommandStart, source, &selectedTextEditRequest{
		SelectedText: selectedText,
	})
	if err != nil {
		return false, err
	}
	return response.Changed, nil
}

func (a *App) triggerStop() (bool, error) {
	return a.triggerStopFrom("ipc")
}

func (a *App) triggerCancel() (bool, error) {
	return a.triggerCancelFrom("ipc")
}

func (a *App) triggerCancelFrom(source string) (bool, error) {
	response, err := a.executeRuntimeCommand(context.Background(), runtimeCommandCancel, source, nil)
	if err != nil {
		return false, err
	}
	return response.Changed, nil
}

func (a *App) triggerStopFrom(source string) (bool, error) {
	response, err := a.executeRuntimeCommand(context.Background(), runtimeCommandStop, source, nil)
	if err != nil {
		return false, err
	}
	return response.Changed, nil
}

func (a *App) triggerActive() bool {
	status := a.Status(context.Background())
	return status.State == "recording"
}

func (a *App) emitStateChanged(logger *slog.Logger, status dbusipc.Status) {
	status = a.withSceneDetail(status)
	if a.DictationBus == nil {
		return
	}
	if err := a.DictationBus.EmitStateChanged(status); err != nil {
		logger.Warn("dictation D-Bus state emit failed", "error", err)
	}
}

func (a *App) emitResultReady(logger *slog.Logger, sessionID, text string) {
	if a.DictationBus == nil {
		return
	}
	if err := a.DictationBus.EmitResultReady(sessionID, text); err != nil {
		logger.Warn("dictation D-Bus result emit failed", "error", err)
	}
}

func (a *App) emitDictationError(logger *slog.Logger, sessionID, message string) {
	if a.DictationBus == nil {
		return
	}
	if err := a.DictationBus.EmitError(sessionID, message); err != nil {
		logger.Warn("dictation D-Bus error emit failed", "error", err)
	}
}

func (a *App) emitSceneChanged(logger *slog.Logger, currentScene scene.Scene) {
	if a.DictationBus == nil {
		return
	}
	if err := a.DictationBus.EmitSceneChanged(currentScene.ID, a.sceneDisplayName(currentScene)); err != nil {
		logger.Warn("dictation D-Bus scene emit failed", "error", err)
	}
}

func (a *App) withSceneDetail(status dbusipc.Status) dbusipc.Status {
	current := a.currentScene()
	if current.ID == "" {
		return status
	}

	detail := strings.TrimSpace(status.Detail)
	sceneDetail := "scene=" + current.ID
	switch {
	case detail == "":
		status.Detail = sceneDetail
	case strings.Contains(detail, sceneDetail):
		status.Detail = detail
	default:
		status.Detail = detail + "; " + sceneDetail
	}
	return status
}

func pickMessage(condition bool, yes, no string) string {
	if condition {
		return yes
	}
	return no
}

func (a *App) executeRuntimeCommand(ctx context.Context, kind runtimeCommandType, source string, edit *selectedTextEditRequest) (runtimeCommandResponse, error) {
	if !a.runtimeRunning.Load() {
		return runtimeCommandResponse{}, errors.New("dictation runtime loop is not ready")
	}

	command := runtimeCommand{
		Type:   kind,
		Source: source,
		Edit:   edit,
		Reply:  make(chan runtimeCommandResponse, 1),
	}

	select {
	case a.runtimeCommands <- command:
	case <-ctx.Done():
		return runtimeCommandResponse{}, ctx.Err()
	}

	select {
	case response := <-command.Reply:
		if response.Err != nil {
			return response, response.Err
		}
		return response, nil
	case <-ctx.Done():
		return runtimeCommandResponse{}, ctx.Err()
	}
}
