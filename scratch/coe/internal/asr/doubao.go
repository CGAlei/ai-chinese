package asr

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"coe/internal/audio"
)

const (
	defaultDoubaoEndpoint   = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
	defaultDoubaoAPIKeyEnv  = "DOUBAO_ASR_API_KEY"
	defaultDoubaoModelName  = "bigmodel"
	doubaoResourceID        = "volc.bigasr.auc_turbo"
	doubaoSuccessCodePrefix = "200"
)

type DoubaoClient struct {
	Endpoint   string
	APIKey     string
	APIKeyEnv  string
	HTTPClient *http.Client
}

func (c DoubaoClient) Name() string {
	return "doubao-" + defaultDoubaoModelName
}

func (c DoubaoClient) Transcribe(ctx context.Context, capture audio.Result) (Result, error) {
	apiKey, _, err := resolveRequiredAPIKey("Doubao", c.APIKey, c.APIKeyEnv, defaultDoubaoAPIKeyEnv)
	if err != nil {
		return Result{}, err
	}

	wav, err := audio.EncodeWAV(capture)
	if err != nil {
		return Result{}, err
	}

	reqBody := doubaoRecognizeRequest{
		User: doubaoRecognizeUser{
			UID: "coe",
		},
		Audio: doubaoRecognizeAudio{
			Data: base64.StdEncoding.EncodeToString(wav),
		},
		Request: doubaoRecognizeOptions{
			ModelName: defaultDoubaoModelName,
		},
	}

	var body bytes.Buffer
	if err := json.NewEncoder(&body).Encode(reqBody); err != nil {
		return Result{}, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint(), &body)
	if err != nil {
		return Result{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Api-Key", apiKey)
	req.Header.Set("X-Api-Resource-Id", doubaoResourceID)
	req.Header.Set("X-Api-Request-Id", newDoubaoRequestID())
	req.Header.Set("X-Api-Sequence", "-1")

	client := c.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: 60 * time.Second}
	}

	resp, err := client.Do(req)
	if err != nil {
		return Result{}, err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return Result{}, err
	}

	headers := doubaoResponseHeaders{
		APIStatusCode: strings.TrimSpace(resp.Header.Get("X-Api-Status-Code")),
		APIMessage:    strings.TrimSpace(resp.Header.Get("X-Api-Message")),
		LogID:         strings.TrimSpace(resp.Header.Get("X-Tt-Logid")),
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return Result{}, doubaoResponseError(resp.Status, headers, data)
	}
	if headers.APIStatusCode != "" && !strings.HasPrefix(headers.APIStatusCode, doubaoSuccessCodePrefix) {
		return Result{}, doubaoResponseError(resp.Status, headers, data)
	}

	var payload doubaoRecognizeResponse
	if err := json.Unmarshal(data, &payload); err != nil {
		return Result{}, fmt.Errorf("doubao transcription failed: decode response: %w", err)
	}

	text := strings.TrimSpace(payload.Result.Text)
	if text != "" {
		return Result{Text: text}, nil
	}

	return Result{
		Warning: doubaoEmptyTextWarning(headers, data),
	}, nil
}

func (c DoubaoClient) endpoint() string {
	if value := strings.TrimSpace(c.Endpoint); value != "" {
		return value
	}
	return defaultDoubaoEndpoint
}

func newDoubaoRequestID() string {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return fmt.Sprintf("coe-%d", time.Now().UnixNano())
	}

	raw[6] = (raw[6] & 0x0f) | 0x40
	raw[8] = (raw[8] & 0x3f) | 0x80

	parts := []string{
		hex.EncodeToString(raw[0:4]),
		hex.EncodeToString(raw[4:6]),
		hex.EncodeToString(raw[6:8]),
		hex.EncodeToString(raw[8:10]),
		hex.EncodeToString(raw[10:16]),
	}
	return strings.Join(parts, "-")
}

func doubaoResponseError(httpStatus string, headers doubaoResponseHeaders, body []byte) error {
	parts := []string{"doubao transcription failed"}
	if strings.TrimSpace(httpStatus) != "" {
		parts = append(parts, "http_status="+strings.TrimSpace(httpStatus))
	}
	if headers.APIStatusCode != "" {
		parts = append(parts, "api_status_code="+headers.APIStatusCode)
	}
	if headers.APIMessage != "" {
		parts = append(parts, "api_message="+headers.APIMessage)
	}
	if headers.LogID != "" {
		parts = append(parts, "logid="+headers.LogID)
	}
	if trimmed := strings.TrimSpace(string(body)); trimmed != "" {
		parts = append(parts, "body="+truncateForWarning(trimmed, 240))
	}
	return errors.New(strings.Join(parts, "; "))
}

func doubaoEmptyTextWarning(headers doubaoResponseHeaders, body []byte) string {
	parts := []string{"doubao transcription returned empty text"}
	if headers.APIStatusCode != "" {
		parts = append(parts, "api_status_code="+headers.APIStatusCode)
	}
	if headers.APIMessage != "" {
		parts = append(parts, "api_message="+headers.APIMessage)
	}
	if headers.LogID != "" {
		parts = append(parts, "logid="+headers.LogID)
	}
	if trimmed := strings.TrimSpace(string(body)); trimmed != "" {
		parts = append(parts, "raw="+truncateForWarning(trimmed, 240))
	}
	return strings.Join(parts, "; ")
}

type doubaoRecognizeRequest struct {
	User    doubaoRecognizeUser    `json:"user"`
	Audio   doubaoRecognizeAudio   `json:"audio"`
	Request doubaoRecognizeOptions `json:"request"`
}

type doubaoRecognizeUser struct {
	UID string `json:"uid"`
}

type doubaoRecognizeAudio struct {
	Data string `json:"data"`
}

type doubaoRecognizeOptions struct {
	ModelName string `json:"model_name"`
}

type doubaoRecognizeResponse struct {
	Result doubaoRecognizeResult `json:"result"`
}

type doubaoRecognizeResult struct {
	Text string `json:"text"`
}

type doubaoResponseHeaders struct {
	APIStatusCode string
	APIMessage    string
	LogID         string
}
