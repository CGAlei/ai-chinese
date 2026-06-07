package pipeline

import (
	"context"
	"testing"

	"coe/internal/asr"
	"coe/internal/audio"
	"coe/internal/llm"
	"coe/internal/output"
)

func TestProcessCaptureSkipsCorrectionWhenTranscriptIsEmpty(t *testing.T) {
	corrector := &fakeCorrector{}
	coordinator := &output.Coordinator{}

	orchestrator := Orchestrator{
		Recorder:  fakeRecorder{},
		ASR:       fakeASR{text: ""},
		Corrector: corrector,
		Output:    coordinator,
	}

	result, err := orchestrator.ProcessCapture(context.Background(), audio.Result{
		Data:       []byte{1, 2, 3, 4},
		ByteCount:  4,
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err != nil {
		t.Fatalf("ProcessCapture() error = %v", err)
	}
	if result.TranscriptWarning == "" {
		t.Fatal("expected transcript warning")
	}
	if corrector.calls != 0 {
		t.Fatalf("corrector calls = %d, want 0", corrector.calls)
	}
	if result.Output.ClipboardWritten {
		t.Fatal("expected output stage to be skipped")
	}
}

func TestProcessCaptureSkipsASRForNearSilentAudio(t *testing.T) {
	t.Parallel()

	corrector := &fakeCorrector{}
	asrClient := &countingASR{text: "unused"}
	orchestrator := Orchestrator{
		Recorder:  fakeRecorder{},
		ASR:       asrClient,
		Corrector: corrector,
		Output:    &output.Coordinator{},
	}

	result, err := orchestrator.ProcessCapture(context.Background(), audio.Result{
		Data:       make([]byte, 1600),
		ByteCount:  1600,
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err != nil {
		t.Fatalf("ProcessCapture() error = %v", err)
	}
	if result.TranscriptWarning != "captured audio is near-silent; skipped transcription" {
		t.Fatalf("unexpected transcript warning %q", result.TranscriptWarning)
	}
	if asrClient.calls != 0 {
		t.Fatalf("ASR calls = %d, want 0", asrClient.calls)
	}
	if corrector.calls != 0 {
		t.Fatalf("corrector calls = %d, want 0", corrector.calls)
	}
}

func TestProcessCaptureSkipsASRForCorruptAudio(t *testing.T) {
	t.Parallel()

	corrector := &fakeCorrector{}
	asrClient := &countingASR{text: "unused"}
	orchestrator := Orchestrator{
		Recorder:  fakeRecorder{},
		ASR:       asrClient,
		Corrector: corrector,
		Output:    &output.Coordinator{},
	}

	data := make([]byte, 0, 4000)
	for i := 0; i < 2000; i++ {
		if i%2 == 0 {
			data = append(data, 0xff, 0x7f)
		} else {
			data = append(data, 0x00, 0x80)
		}
	}

	result, err := orchestrator.ProcessCapture(context.Background(), audio.Result{
		Data:       data,
		ByteCount:  len(data),
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err != nil {
		t.Fatalf("ProcessCapture() error = %v", err)
	}
	if result.TranscriptWarning != "captured audio appears saturated or corrupted; skipped transcription" {
		t.Fatalf("unexpected transcript warning %q", result.TranscriptWarning)
	}
	if asrClient.calls != 0 {
		t.Fatalf("ASR calls = %d, want 0", asrClient.calls)
	}
	if corrector.calls != 0 {
		t.Fatalf("corrector calls = %d, want 0", corrector.calls)
	}
}

type fakeRecorder struct{}

func (fakeRecorder) Start(context.Context) (audio.CaptureSession, error) {
	panic("unexpected call")
}

func (fakeRecorder) Summary() string {
	return "fake-recorder"
}

type fakeASR struct {
	text string
}

func (f fakeASR) Transcribe(context.Context, audio.Result) (asr.Result, error) {
	return asr.Result{Text: f.text}, nil
}

func (f fakeASR) Name() string {
	return "fake-asr"
}

type countingASR struct {
	text  string
	calls int
}

func (f *countingASR) Transcribe(context.Context, audio.Result) (asr.Result, error) {
	f.calls++
	return asr.Result{Text: f.text}, nil
}

func (f *countingASR) Name() string {
	return "counting-asr"
}

type fakeCorrector struct {
	calls int
}

func (f *fakeCorrector) Correct(context.Context, string) (llm.Result, error) {
	f.calls++
	return llm.Result{Text: "unused"}, nil
}

func (f *fakeCorrector) Name() string {
	return "fake-llm"
}
