package audio

import (
	"encoding/binary"
	"fmt"
)

type Activity struct {
	Supported           bool
	DCOffsetNormalized  float64
	PeakNormalized      float64
	RMSNormalized       float64
	ActiveSampleRatio   float64
	ClippingSampleRatio float64
	ZeroCrossingRate    float64
	ApproxCorrupt       bool
	ApproxSilent        bool
}

type ActivityThresholds struct {
	MinPeakNormalized    float64
	MinRMSNormalized     float64
	MinActiveSampleRatio float64
}

func DefaultActivityThresholds() ActivityThresholds {
	return ActivityThresholds{
		MinPeakNormalized:    0.006,
		MinRMSNormalized:     0.0012,
		MinActiveSampleRatio: 0.0025,
	}
}

func AnalyzeActivity(result Result, thresholds ActivityThresholds) Activity {
	if result.Format != "s16" || result.Channels != 1 || len(result.Data) < 2 {
		return Activity{}
	}

	sampleCount := len(result.Data) / 2
	if sampleCount == 0 {
		return Activity{}
	}

	const fullScale = 32768.0
	var maxAbs float64
	var activeCount int
	var clippingCount int
	var zeroCrossings int
	var sum float64
	var sumSquares float64

	samples := make([]int32, 0, sampleCount)
	for i := 0; i+1 < len(result.Data); i += 2 {
		sample := int32(int16(binary.LittleEndian.Uint16(result.Data[i : i+2])))
		samples = append(samples, sample)
		sum += float64(sample)
	}
	mean := sum / float64(sampleCount)

	activeThreshold := thresholds.MinPeakNormalized
	if activeThreshold <= 0 {
		activeThreshold = 1 / fullScale
	}
	clipThreshold := 0.98
	prevSign := 0

	for _, sample := range samples {
		centeredSigned := (float64(sample) - mean) / fullScale
		centered := centeredSigned
		if centered < 0 {
			centered = -centered
		}
		if centered > maxAbs {
			maxAbs = centered
		}
		if centered >= activeThreshold {
			activeCount++
		}
		if centered >= clipThreshold {
			clippingCount++
		}
		sumSquares += centered * centered

		sign := 0
		switch {
		case centeredSigned > 0:
			sign = 1
		case centeredSigned < 0:
			sign = -1
		}
		if sign != 0 {
			if prevSign != 0 && sign != prevSign {
				zeroCrossings++
			}
			prevSign = sign
		}
	}

	peak := maxAbs
	rms := 0.0
	if sampleCount > 0 {
		rms = sqrt(sumSquares / float64(sampleCount))
	}
	activeRatio := float64(activeCount) / float64(sampleCount)

	return Activity{
		Supported:           true,
		DCOffsetNormalized:  mean / fullScale,
		PeakNormalized:      peak,
		RMSNormalized:       rms,
		ActiveSampleRatio:   activeRatio,
		ClippingSampleRatio: float64(clippingCount) / float64(sampleCount),
		ZeroCrossingRate:    float64(zeroCrossings) / float64(sampleCount),
		ApproxCorrupt:       isLikelyCorrupt(peak, rms, activeRatio, float64(clippingCount)/float64(sampleCount)),
		ApproxSilent: peak < thresholds.MinPeakNormalized &&
			rms < thresholds.MinRMSNormalized &&
			activeRatio < thresholds.MinActiveSampleRatio,
	}
}

func (a Activity) Summary() string {
	if !a.Supported {
		return "unsupported"
	}

	return fmt.Sprintf(
		"dc_offset=%.5f peak=%.5f rms=%.5f active_ratio=%.5f clip_ratio=%.5f zero_cross=%.5f approx_silent=%t approx_corrupt=%t",
		a.DCOffsetNormalized,
		a.PeakNormalized,
		a.RMSNormalized,
		a.ActiveSampleRatio,
		a.ClippingSampleRatio,
		a.ZeroCrossingRate,
		a.ApproxSilent,
		a.ApproxCorrupt,
	)
}

func isLikelyCorrupt(peak, rms, activeRatio, clipRatio float64) bool {
	return peak >= 0.9 && rms >= 0.45 && activeRatio >= 0.9 && clipRatio >= 0.08
}

// sqrt keeps the analysis local to stdlib-free primitives.
func sqrt(v float64) float64 {
	if v <= 0 {
		return 0
	}
	z := v
	for i := 0; i < 8; i++ {
		z -= (z*z - v) / (2 * z)
	}
	return z
}
