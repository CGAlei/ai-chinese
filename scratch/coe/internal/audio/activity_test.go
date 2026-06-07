package audio

import "testing"

func TestAnalyzeActivityDetectsSilence(t *testing.T) {
	t.Parallel()

	data := make([]byte, 1600)
	result := AnalyzeActivity(Result{
		Data:      data,
		ByteCount: len(data),
		Channels:  1,
		Format:    "s16",
	}, DefaultActivityThresholds())

	if !result.Supported {
		t.Fatal("expected supported analysis")
	}
	if !result.ApproxSilent {
		t.Fatalf("expected silence, got %#v", result)
	}
}

func TestAnalyzeActivityDetectsSignal(t *testing.T) {
	t.Parallel()

	data := []byte{
		0x00, 0x00,
		0x20, 0x03,
		0x40, 0x06,
		0x20, 0x03,
		0x00, 0x00,
	}
	result := AnalyzeActivity(Result{
		Data:      data,
		ByteCount: len(data),
		Channels:  1,
		Format:    "s16",
	}, DefaultActivityThresholds())

	if !result.Supported {
		t.Fatal("expected supported analysis")
	}
	if result.ApproxSilent {
		t.Fatalf("expected active signal, got %#v", result)
	}
}

func TestAnalyzeActivityTreatsConstantOffsetAsSilent(t *testing.T) {
	t.Parallel()

	data := []byte{
		0x00, 0x80,
		0x00, 0x80,
		0x00, 0x80,
		0x00, 0x80,
	}
	result := AnalyzeActivity(Result{
		Data:      data,
		ByteCount: len(data),
		Channels:  1,
		Format:    "s16",
	}, DefaultActivityThresholds())

	if !result.Supported {
		t.Fatal("expected supported analysis")
	}
	if !result.ApproxSilent {
		t.Fatalf("expected constant DC offset to be silent, got %#v", result)
	}
	if result.DCOffsetNormalized > -0.99 {
		t.Fatalf("expected a strong negative DC offset, got %#v", result)
	}
}

func TestAnalyzeActivityDetectsCorruptClippedSignal(t *testing.T) {
	t.Parallel()

	data := make([]byte, 0, 2000)
	for i := 0; i < 1000; i++ {
		if i%2 == 0 {
			data = append(data, 0xff, 0x7f)
		} else {
			data = append(data, 0x00, 0x80)
		}
	}

	result := AnalyzeActivity(Result{
		Data:      data,
		ByteCount: len(data),
		Channels:  1,
		Format:    "s16",
	}, DefaultActivityThresholds())

	if !result.ApproxCorrupt {
		t.Fatalf("expected clipped signal to be marked corrupt, got %#v", result)
	}
	if result.ApproxSilent {
		t.Fatalf("expected clipped signal to be non-silent, got %#v", result)
	}
}
