package asr

import (
	"encoding/binary"
	"fmt"

	"coe/internal/audio"
)

func pcmS16MonoToFloat32(capture audio.Result) ([]float32, error) {
	if capture.SampleRate != 16000 {
		return nil, fmt.Errorf("whisper.cpp expects 16 kHz audio, got %d Hz", capture.SampleRate)
	}
	if capture.Channels != 1 {
		return nil, fmt.Errorf("whisper.cpp expects mono audio, got %d channels", capture.Channels)
	}
	if capture.Format != "s16" && capture.Format != "s16le" {
		return nil, fmt.Errorf("whisper.cpp expects s16 PCM, got %q", capture.Format)
	}
	if len(capture.Data)%2 != 0 {
		return nil, fmt.Errorf("PCM payload has odd byte length %d", len(capture.Data))
	}

	samples := make([]float32, len(capture.Data)/2)
	for i := range samples {
		raw := int16(binary.LittleEndian.Uint16(capture.Data[i*2 : i*2+2]))
		samples[i] = float32(raw) / 32768.0
	}
	return samples, nil
}
