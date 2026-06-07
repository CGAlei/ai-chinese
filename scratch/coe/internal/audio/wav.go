package audio

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"strings"
)

func EncodeWAV(result Result) ([]byte, error) {
	if result.SampleRate <= 0 {
		return nil, fmt.Errorf("invalid sample rate %d", result.SampleRate)
	}
	if result.Channels <= 0 {
		return nil, fmt.Errorf("invalid channel count %d", result.Channels)
	}

	format := strings.ToLower(result.Format)
	if format != "s16" && format != "s16le" {
		return nil, fmt.Errorf("unsupported PCM format %q", result.Format)
	}

	const bitsPerSample = 16
	const pcmFormat = 1

	dataSize := uint32(len(result.Data))
	byteRate := uint32(result.SampleRate * result.Channels * bitsPerSample / 8)
	blockAlign := uint16(result.Channels * bitsPerSample / 8)
	riffSize := 36 + dataSize

	buf := bytes.NewBuffer(make([]byte, 0, 44+len(result.Data)))
	buf.WriteString("RIFF")
	_ = binary.Write(buf, binary.LittleEndian, riffSize)
	buf.WriteString("WAVE")
	buf.WriteString("fmt ")
	_ = binary.Write(buf, binary.LittleEndian, uint32(16))
	_ = binary.Write(buf, binary.LittleEndian, uint16(pcmFormat))
	_ = binary.Write(buf, binary.LittleEndian, uint16(result.Channels))
	_ = binary.Write(buf, binary.LittleEndian, uint32(result.SampleRate))
	_ = binary.Write(buf, binary.LittleEndian, byteRate)
	_ = binary.Write(buf, binary.LittleEndian, blockAlign)
	_ = binary.Write(buf, binary.LittleEndian, uint16(bitsPerSample))
	buf.WriteString("data")
	_ = binary.Write(buf, binary.LittleEndian, dataSize)
	buf.Write(result.Data)
	return buf.Bytes(), nil
}
