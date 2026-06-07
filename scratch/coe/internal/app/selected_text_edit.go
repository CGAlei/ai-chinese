package app

import (
	"context"
	"fmt"
	"strings"

	"coe/internal/llm"
	"coe/internal/pipeline"
	"coe/internal/scene"
)

func (a *App) selectionEditorForScene(id string) llm.SelectionEditor {
	if editor, ok := a.SceneEditors[id]; ok {
		return editor
	}
	if editor, ok := a.SceneEditors[scene.IDGeneral]; ok {
		return editor
	}
	return nil
}

func (a *App) applySelectedTextEdit(ctx context.Context, sceneID, selectedText, instruction string) (string, error) {
	if selectedText == "" {
		return "", fmt.Errorf("selected text edit requires non-empty selected text")
	}

	instruction = strings.TrimSpace(instruction)
	if instruction == "" {
		return "", fmt.Errorf("selected text edit instruction produced no text")
	}

	editor := a.selectionEditorForScene(sceneID)
	if editor == nil {
		return "", fmt.Errorf("selected text edit is not configured for scene %q", sceneID)
	}

	edited, err := editor.Edit(ctx, llm.SelectionEditInput{
		SelectedText: selectedText,
		Instruction:  instruction,
	})
	if err != nil {
		return "", err
	}

	result := pipeline.Result{Corrected: strings.TrimSpace(edited.Text)}
	result = a.normalizeForScene(result, sceneID)
	if strings.TrimSpace(result.Corrected) == "" {
		return "", fmt.Errorf("selected text edit returned empty text")
	}
	return result.Corrected, nil
}
