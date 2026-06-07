package llm

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"coe/internal/config"
)

func TestPromptSelectionEditorEdit(t *testing.T) {
	t.Setenv("OPENAI_API_KEY", "test-key")

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		rawInput, _ := payload["input"].(string)
		if !strings.Contains(rawInput, `"selected_text":"hello"`) {
			t.Fatalf("input = %q", rawInput)
		}
		if !strings.Contains(rawInput, `"instruction":"make it formal"`) {
			t.Fatalf("input = %q", rawInput)
		}

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"output_text":"Greetings."}`))
	}))
	defer server.Close()

	editor, err := NewSelectionEditorWithResolvedPrompt(config.LLMConfig{
		Provider:     "openai",
		Endpoint:     server.URL,
		EndpointType: "responses",
		Model:        "gpt-4o-mini",
		APIKey:       "test-key",
	}, "rewrite text")
	if err != nil {
		t.Fatalf("NewSelectionEditorWithResolvedPrompt() error = %v", err)
	}

	promptEditor, ok := editor.(PromptSelectionEditor)
	if !ok {
		t.Fatalf("editor type = %T", editor)
	}
	openaiCorrector, ok := promptEditor.Corrector.(OpenAICorrector)
	if !ok {
		t.Fatalf("corrector type = %T", promptEditor.Corrector)
	}
	openaiCorrector.HTTPClient = server.Client()
	promptEditor.Corrector = openaiCorrector

	result, err := promptEditor.Edit(context.Background(), SelectionEditInput{
		SelectedText: "hello",
		Instruction:  "make it formal",
	})
	if err != nil {
		t.Fatalf("Edit() error = %v", err)
	}
	if result.Text != "Greetings." {
		t.Fatalf("result.Text = %q", result.Text)
	}
}

func TestStubSelectionEditorReturnsOriginalSelection(t *testing.T) {
	editor, err := NewSelectionEditorWithResolvedPrompt(config.LLMConfig{
		Provider: "stub",
	}, "")
	if err != nil {
		t.Fatalf("NewSelectionEditorWithResolvedPrompt() error = %v", err)
	}

	result, err := editor.Edit(context.Background(), SelectionEditInput{
		SelectedText: "hello",
		Instruction:  "make it formal",
	})
	if err != nil {
		t.Fatalf("Edit() error = %v", err)
	}
	if result.Text != "hello" {
		t.Fatalf("result.Text = %q, want hello", result.Text)
	}
}
