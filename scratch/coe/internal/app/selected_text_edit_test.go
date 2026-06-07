package app

import (
	"context"
	"errors"
	"testing"

	"coe/internal/dictionary"
	"coe/internal/i18n"
	"coe/internal/llm"
	"coe/internal/scene"
)

type stubSelectionEditor struct {
	text string
	err  error
}

func (s stubSelectionEditor) Edit(context.Context, llm.SelectionEditInput) (llm.Result, error) {
	return llm.Result{Text: s.text}, s.err
}

func (s stubSelectionEditor) Name() string {
	return "stub-selection-editor"
}

func TestApplySelectedTextEditUsesSceneEditor(t *testing.T) {
	t.Parallel()

	instance := &App{
		SceneEditors: map[string]llm.SelectionEditor{
			scene.IDGeneral: stubSelectionEditor{text: "rewritten"},
		},
	}

	got, err := instance.applySelectedTextEdit(context.Background(), scene.IDGeneral, "hello", "make it formal")
	if err != nil {
		t.Fatalf("applySelectedTextEdit() error = %v", err)
	}
	if got != "rewritten" {
		t.Fatalf("applySelectedTextEdit() = %q, want %q", got, "rewritten")
	}
}

func TestApplySelectedTextEditNormalizesByScene(t *testing.T) {
	t.Parallel()

	dict, err := dictionary.Parse([]byte(`
entries:
  - canonical: "systemctl"
    aliases: ["system control"]
    scenes: ["terminal"]
`))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}

	instance := &App{
		Localizer:  i18n.NewForLocale("en_US.UTF-8"),
		Dictionary: dict,
		SceneEditors: map[string]llm.SelectionEditor{
			scene.IDTerminal: stubSelectionEditor{text: "please run system control now"},
		},
	}

	got, err := instance.applySelectedTextEdit(context.Background(), scene.IDTerminal, "old", "rewrite")
	if err != nil {
		t.Fatalf("applySelectedTextEdit() error = %v", err)
	}
	if got != "please run systemctl now" {
		t.Fatalf("applySelectedTextEdit() = %q", got)
	}
}

func TestApplySelectedTextEditRejectsEmptyResult(t *testing.T) {
	t.Parallel()

	instance := &App{
		SceneEditors: map[string]llm.SelectionEditor{
			scene.IDGeneral: stubSelectionEditor{text: ""},
		},
	}

	if _, err := instance.applySelectedTextEdit(context.Background(), scene.IDGeneral, "hello", "rewrite"); err == nil {
		t.Fatal("applySelectedTextEdit() error = nil, want error")
	}
}

func TestApplySelectedTextEditReturnsEditorError(t *testing.T) {
	t.Parallel()

	instance := &App{
		SceneEditors: map[string]llm.SelectionEditor{
			scene.IDGeneral: stubSelectionEditor{err: errors.New("boom")},
		},
	}

	if _, err := instance.applySelectedTextEdit(context.Background(), scene.IDGeneral, "hello", "rewrite"); err == nil {
		t.Fatal("applySelectedTextEdit() error = nil, want error")
	}
}
