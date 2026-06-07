package llm

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"coe/internal/config"
)

type SelectionEditInput struct {
	SelectedText string `json:"selected_text"`
	Instruction  string `json:"instruction"`
}

type SelectionEditor interface {
	Edit(context.Context, SelectionEditInput) (Result, error)
	Name() string
}

type StubSelectionEditor struct{}

func (StubSelectionEditor) Edit(_ context.Context, input SelectionEditInput) (Result, error) {
	return Result{Text: input.SelectedText}, nil
}

func (StubSelectionEditor) Name() string {
	return "stub-selection-editor"
}

type PromptSelectionEditor struct {
	Corrector Corrector
}

func (e PromptSelectionEditor) Edit(ctx context.Context, input SelectionEditInput) (Result, error) {
	if e.Corrector == nil {
		return Result{}, fmt.Errorf("selection editor is not configured")
	}

	payload, err := json.Marshal(struct {
		SelectedText string `json:"selected_text"`
		Instruction  string `json:"instruction"`
	}{
		SelectedText: input.SelectedText,
		Instruction:  input.Instruction,
	})
	if err != nil {
		return Result{}, err
	}

	return e.Corrector.Correct(ctx, string(payload))
}

func (e PromptSelectionEditor) Name() string {
	if e.Corrector == nil {
		return "prompt-selection-editor"
	}
	return e.Corrector.Name()
}

func NewSelectionEditorWithResolvedPrompt(provider config.LLMConfig, resolvedPrompt string) (SelectionEditor, error) {
	switch strings.ToLower(provider.Provider) {
	case "", "stub":
		return StubSelectionEditor{}, nil
	default:
		corrector, err := NewCorrectorWithResolvedPrompt(provider, resolvedPrompt)
		if err != nil {
			return nil, err
		}
		return PromptSelectionEditor{Corrector: corrector}, nil
	}
}
