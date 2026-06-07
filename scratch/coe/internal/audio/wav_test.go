package audio

import (
	"encoding/binary"
	"testing"
)

func TestEncodeWAV(t *testing.T) {
	t.Parallel()

	data := []byte{0x01, 0x02, 0x03, 0x04}
	wav, err := EncodeWAV(Result{
		Data:       data,
		ByteCount:  len(data),
		SampleRate: 16000,
		Channels:   1,
		Format:     "s16",
	})
	if err != nil {
		t.Fatalf("EncodeWAV() error = %v", err)
	}
	if string(wav[:4]) != "RIFF" {
		t.Fatalf("missing RIFF header: %q", string(wav[:4]))
	}
	if string(wav[8:12]) != "WAVE" {
		t.Fatalf("missing WAVE header: %q", string(wav[8:12]))
	}
	size := binary.LittleEndian.Uint32(wav[40:44])
	if size != uint32(len(data)) {
		t.Fatalf("data chunk size = %d, want %d", size, len(data))
	}
}
