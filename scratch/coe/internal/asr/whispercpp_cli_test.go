package asr

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"coe/internal/audio"
)

func TestWhisperCPPCLIClientTranscribe(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	binary := filepath.Join(dir, "whisper-cli")
	script := "#!/bin/sh\nprintf '%s' \"吃葡萄不吐葡萄皮\"\n"
	if err := os.WriteFile(binary, []byte(script), 0o755); err != nil {
		t.Fatalf("WriteFile() error = %v", err)
	}

	client := WhisperCPPCLIClient{
		Binary:    binary,
		ModelPath: "/models/ggml-base.bin",
		Language:  "zh",
		Threads:   2,
	}

	result, err := client.Transcribe(context.Background(), audio.Result{
		Data:       []byte{0x00, 0x00, 0x00, 0x00},
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err != nil {
		t.Fatalf("Transcribe() error = %v", err)
	}
	if result.Text != "吃葡萄不吐葡萄皮" {
		t.Fatalf("Transcribe().Text = %q, want %q", result.Text, "吃葡萄不吐葡萄皮")
	}
}

func TestWhisperCPPCLIClientRequiresModelPath(t *testing.T) {
	t.Parallel()

	_, err := WhisperCPPCLIClient{}.Transcribe(context.Background(), audio.Result{
		Data:       []byte{0x00, 0x00},
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err == nil {
		t.Fatal("Transcribe() error = nil, want error")
	}
	if !strings.Contains(err.Error(), "model_path") {
		t.Fatalf("Transcribe() error = %q, want model_path hint", err)
	}
}
