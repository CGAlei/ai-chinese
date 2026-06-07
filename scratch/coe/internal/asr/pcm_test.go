package asr

import (
	"testing"

	"coe/internal/audio"
)

func TestPCMS16MonoToFloat32(t *testing.T) {
	t.Parallel()

	capture := audio.Result{
		Data:       []byte{0x00, 0x80, 0x00, 0x00, 0xff, 0x7f},
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	}

	samples, err := pcmS16MonoToFloat32(capture)
	if err != nil {
		t.Fatalf("pcmS16MonoToFloat32() error = %v", err)
	}
	if len(samples) != 3 {
		t.Fatalf("len(samples) = %d, want 3", len(samples))
	}
	if samples[0] != -1.0 {
		t.Fatalf("samples[0] = %v, want -1.0", samples[0])
	}
	if samples[1] != 0 {
		t.Fatalf("samples[1] = %v, want 0", samples[1])
	}
	if samples[2] < 0.9999 || samples[2] > 1.0 {
		t.Fatalf("samples[2] = %v, want near 1.0", samples[2])
	}
}

func TestPCMS16MonoToFloat32RejectsInvalidFormat(t *testing.T) {
	t.Parallel()

	_, err := pcmS16MonoToFloat32(audio.Result{
		Data:       []byte{0x00, 0x00},
		SampleRate: 48000,
		Channels:   2,
		Format:     "f32",
	})
	if err == nil {
		t.Fatal("pcmS16MonoToFloat32() error = nil, want error")
	}
}
