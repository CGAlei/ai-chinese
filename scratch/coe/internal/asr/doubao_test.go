package asr

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"coe/internal/audio"
)

func TestDoubaoClientTranscribe(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method = %s", r.Method)
		}
		if got := r.Header.Get("X-Api-Key"); got != "test-key" {
			t.Fatalf("X-Api-Key = %q", got)
		}
		if got := r.Header.Get("X-Api-Resource-Id"); got != doubaoResourceID {
			t.Fatalf("X-Api-Resource-Id = %q", got)
		}
		if got := r.Header.Get("X-Api-Sequence"); got != "-1" {
			t.Fatalf("X-Api-Sequence = %q", got)
		}
		if got := r.Header.Get("X-Api-Request-Id"); strings.TrimSpace(got) == "" {
			t.Fatal("X-Api-Request-Id is empty")
		}

		var payload doubaoRecognizeRequest
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		if payload.User.UID != "coe" {
			t.Fatalf("user.uid = %q", payload.User.UID)
		}
		if payload.Request.ModelName != defaultDoubaoModelName {
			t.Fatalf("request.model_name = %q", payload.Request.ModelName)
		}

		wav, err := base64.StdEncoding.DecodeString(payload.Audio.Data)
		if err != nil {
			t.Fatalf("DecodeString() error = %v", err)
		}
		if string(wav[:4]) != "RIFF" || string(wav[8:12]) != "WAVE" {
			t.Fatalf("expected WAV upload, got %q / %q", string(wav[:4]), string(wav[8:12]))
		}

		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Api-Status-Code", "20000000")
		w.Header().Set("X-Api-Message", "OK")
		w.Header().Set("X-Tt-Logid", "log-001")
		_, _ = w.Write([]byte(`{"result":{"text":"  你好，豆包。  "}}`))
	}))
	defer server.Close()

	client := DoubaoClient{
		Endpoint:   server.URL,
		APIKey:     "test-key",
		HTTPClient: server.Client(),
	}

	result, err := client.Transcribe(context.Background(), audio.Result{
		Data:       []byte{0x01, 0x02, 0x03, 0x04},
		ByteCount:  4,
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err != nil {
		t.Fatalf("Transcribe() error = %v", err)
	}
	if result.Text != "你好，豆包。" {
		t.Fatalf("result.Text = %q", result.Text)
	}
	if result.Warning != "" {
		t.Fatalf("result.Warning = %q, want empty", result.Warning)
	}
}

func TestDoubaoClientReturnsWarningForEmptyText(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Api-Status-Code", "20000003")
		w.Header().Set("X-Api-Message", "silent audio")
		w.Header().Set("X-Tt-Logid", "log-empty")
		_, _ = w.Write([]byte(`{"result":{"text":""}}`))
	}))
	defer server.Close()

	client := DoubaoClient{
		Endpoint:   server.URL,
		APIKey:     "test-key",
		HTTPClient: server.Client(),
	}

	result, err := client.Transcribe(context.Background(), audio.Result{
		Data:       []byte{0x01, 0x02},
		ByteCount:  2,
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err != nil {
		t.Fatalf("Transcribe() error = %v", err)
	}
	if result.Text != "" {
		t.Fatalf("result.Text = %q, want empty", result.Text)
	}
	for _, want := range []string{
		"doubao transcription returned empty text",
		"api_status_code=20000003",
		"api_message=silent audio",
		"logid=log-empty",
	} {
		if !strings.Contains(result.Warning, want) {
			t.Fatalf("result.Warning missing %q in %q", want, result.Warning)
		}
	}
}

func TestDoubaoClientFailsOnProviderErrorStatus(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Api-Status-Code", "45000001")
		w.Header().Set("X-Api-Message", "invalid request")
		w.Header().Set("X-Tt-Logid", "log-error")
		_, _ = w.Write([]byte(`{"result":{"text":""}}`))
	}))
	defer server.Close()

	client := DoubaoClient{
		Endpoint:   server.URL,
		APIKey:     "test-key",
		HTTPClient: server.Client(),
	}

	_, err := client.Transcribe(context.Background(), audio.Result{
		Data:       []byte{0x01, 0x02},
		ByteCount:  2,
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	for _, want := range []string{
		"doubao transcription failed",
		"api_status_code=45000001",
		"api_message=invalid request",
		"logid=log-error",
	} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error missing %q in %q", want, err)
		}
	}
}

func TestDoubaoClientMissingAPIKey(t *testing.T) {
	t.Parallel()

	if err := os.Unsetenv(defaultDoubaoAPIKeyEnv); err != nil {
		t.Fatalf("Unsetenv() error = %v", err)
	}

	client := DoubaoClient{}
	_, err := client.Transcribe(context.Background(), audio.Result{
		Data:       []byte{0x01, 0x02},
		ByteCount:  2,
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err == nil || !strings.Contains(err.Error(), defaultDoubaoAPIKeyEnv) {
		t.Fatalf("expected missing key error, got %v", err)
	}
}
