package asr

import (
	"fmt"
	"os"
	"strings"
)

func resolveRequiredAPIKey(providerLabel, explicit, envName, defaultEnv string) (string, string, error) {
	if value := strings.TrimSpace(explicit); value != "" {
		return value, "config", nil
	}

	keyEnv := strings.TrimSpace(envName)
	if keyEnv == "" {
		keyEnv = defaultEnv
	}

	apiKey := strings.TrimSpace(os.Getenv(keyEnv))
	if apiKey == "" {
		return "", keyEnv, fmt.Errorf("missing %s API key in %s", providerLabel, keyEnv)
	}

	return apiKey, keyEnv, nil
}

func resolveOptionalAPIKey(explicit, envName, defaultEnv string) string {
	if value := strings.TrimSpace(explicit); value != "" {
		return value
	}

	keyEnv := strings.TrimSpace(envName)
	if keyEnv == "" {
		keyEnv = defaultEnv
	}

	return strings.TrimSpace(os.Getenv(keyEnv))
}
