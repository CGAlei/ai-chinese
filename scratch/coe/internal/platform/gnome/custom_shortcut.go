package gnome

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

const (
	mediaKeysSchema      = "org.gnome.settings-daemon.plugins.media-keys"
	customBindingBase    = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
	customBindingPrefix  = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"
	defaultShortcutName  = "coe-trigger"
	defaultShortcutLabel = "trigger toggle"
)

var pathPattern = regexp.MustCompile(`'([^']+)'`)

type Shortcut struct {
	Name    string
	Command string
	Binding string
}

type commandRunner interface {
	Run(context.Context, string, ...string) ([]byte, error)
}

type execRunner struct{}

func (execRunner) Run(ctx context.Context, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		message := strings.TrimSpace(string(out))
		if message != "" {
			return nil, fmt.Errorf("%w: %s", err, message)
		}
		return nil, err
	}
	return out, nil
}

type ShortcutManager struct {
	runner commandRunner
}

func NewShortcutManager() ShortcutManager {
	return ShortcutManager{runner: execRunner{}}
}

func (m ShortcutManager) EnsureTriggerShortcut(ctx context.Context, name, binding string) error {
	command, err := resolveTriggerCommand()
	if err != nil {
		return err
	}

	shortcut := Shortcut{
		Name:    strings.TrimSpace(name),
		Command: command,
		Binding: strings.TrimSpace(binding),
	}

	return m.ensure(ctx, shortcut)
}

func (m ShortcutManager) RemoveTriggerShortcut(ctx context.Context, name string) error {
	name = strings.TrimSpace(name)
	if name == "" {
		name = defaultShortcutName
	}

	paths, err := m.listShortcutPaths(ctx)
	if err != nil {
		return err
	}

	filtered := make([]string, 0, len(paths))
	changed := false
	for _, path := range paths {
		entry, err := m.readShortcut(ctx, path)
		if err != nil {
			return err
		}
		if matchesManagedShortcut(entry, name) {
			changed = true
			continue
		}
		filtered = append(filtered, path)
	}

	if !changed {
		return nil
	}

	return m.setShortcutPaths(ctx, filtered)
}

func (m ShortcutManager) LookupTriggerShortcut(ctx context.Context, name string) (Shortcut, bool, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		name = defaultShortcutName
	}

	paths, err := m.listShortcutPaths(ctx)
	if err != nil {
		return Shortcut{}, false, err
	}

	for _, path := range paths {
		entry, err := m.readShortcut(ctx, path)
		if err != nil {
			return Shortcut{}, false, err
		}
		if matchesManagedShortcut(entry, name) {
			return entry, true, nil
		}
	}

	return Shortcut{}, false, nil
}

func (m ShortcutManager) ensure(ctx context.Context, shortcut Shortcut) error {
	if strings.TrimSpace(shortcut.Binding) == "" {
		return fmt.Errorf("GNOME custom shortcut requires a binding")
	}
	if strings.TrimSpace(shortcut.Command) == "" {
		return fmt.Errorf("GNOME custom shortcut requires a command")
	}
	if strings.TrimSpace(shortcut.Name) == "" {
		shortcut.Name = defaultShortcutName
	}

	paths, err := m.listShortcutPaths(ctx)
	if err != nil {
		return err
	}

	targetPath, exists, err := m.findExistingShortcut(ctx, paths, shortcut)
	if err != nil {
		return err
	}
	if !exists {
		targetPath = nextShortcutPath(paths)
		paths = append(paths, targetPath)
		if err := m.setShortcutPaths(ctx, paths); err != nil {
			return err
		}
	}

	if err := m.setShortcutField(ctx, targetPath, "name", shortcut.Name); err != nil {
		return err
	}
	if err := m.setShortcutField(ctx, targetPath, "command", shortcut.Command); err != nil {
		return err
	}
	if err := m.setShortcutField(ctx, targetPath, "binding", shortcut.Binding); err != nil {
		return err
	}

	return nil
}

func (m ShortcutManager) listShortcutPaths(ctx context.Context) ([]string, error) {
	out, err := m.runner.Run(ctx, "gsettings", "get", mediaKeysSchema, "custom-keybindings")
	if err != nil {
		return nil, fmt.Errorf("read GNOME custom shortcuts: %w", err)
	}
	return parseQuotedList(string(out)), nil
}

func (m ShortcutManager) setShortcutPaths(ctx context.Context, paths []string) error {
	var quoted []string
	for _, path := range paths {
		quoted = append(quoted, quoteGVariantString(path))
	}
	value := "[" + strings.Join(quoted, ", ") + "]"
	_, err := m.runner.Run(ctx, "gsettings", "set", mediaKeysSchema, "custom-keybindings", value)
	if err != nil {
		return fmt.Errorf("write GNOME custom shortcut list: %w", err)
	}
	return nil
}

func (m ShortcutManager) findExistingShortcut(ctx context.Context, paths []string, shortcut Shortcut) (string, bool, error) {
	for _, path := range paths {
		entry, err := m.readShortcut(ctx, path)
		if err != nil {
			return "", false, err
		}
		if matchesShortcut(entry, shortcut) {
			return path, true, nil
		}
	}
	return "", false, nil
}

func (m ShortcutManager) readShortcut(ctx context.Context, path string) (Shortcut, error) {
	name, err := m.getShortcutField(ctx, path, "name")
	if err != nil {
		return Shortcut{}, err
	}
	command, err := m.getShortcutField(ctx, path, "command")
	if err != nil {
		return Shortcut{}, err
	}
	binding, err := m.getShortcutField(ctx, path, "binding")
	if err != nil {
		return Shortcut{}, err
	}
	return Shortcut{Name: name, Command: command, Binding: binding}, nil
}

func (m ShortcutManager) getShortcutField(ctx context.Context, path, field string) (string, error) {
	out, err := m.runner.Run(ctx, "gsettings", "get", schemaForPath(path), field)
	if err != nil {
		return "", fmt.Errorf("read GNOME custom shortcut %s %s: %w", path, field, err)
	}
	return parseGVariantString(string(out)), nil
}

func (m ShortcutManager) setShortcutField(ctx context.Context, path, field, value string) error {
	_, err := m.runner.Run(ctx, "gsettings", "set", schemaForPath(path), field, quoteGVariantString(value))
	if err != nil {
		return fmt.Errorf("write GNOME custom shortcut %s %s: %w", path, field, err)
	}
	return nil
}

func matchesShortcut(existing, wanted Shortcut) bool {
	if existing.Command == wanted.Command {
		return true
	}
	return matchesManagedShortcut(existing, wanted.Name)
}

func matchesManagedShortcut(existing Shortcut, name string) bool {
	if strings.TrimSpace(name) == "" {
		name = defaultShortcutName
	}
	if existing.Name == name {
		return true
	}
	if strings.Contains(existing.Command, "coe trigger toggle") {
		return true
	}
	if strings.Contains(existing.Command, defaultShortcutLabel) && strings.Contains(existing.Command, "coe") {
		return true
	}
	return false
}

func nextShortcutPath(paths []string) string {
	used := map[int]bool{}
	for _, path := range paths {
		name := strings.TrimSuffix(strings.TrimPrefix(path, customBindingBase), "/")
		if !strings.HasPrefix(name, "custom") {
			continue
		}
		index, err := strconv.Atoi(strings.TrimPrefix(name, "custom"))
		if err != nil {
			continue
		}
		used[index] = true
	}

	index := 0
	for used[index] {
		index++
	}

	return fmt.Sprintf("%scustom%d/", customBindingBase, index)
}

func parseQuotedList(value string) []string {
	matches := pathPattern.FindAllStringSubmatch(value, -1)
	paths := make([]string, 0, len(matches))
	for _, match := range matches {
		if len(match) > 1 {
			paths = append(paths, match[1])
		}
	}
	return paths
}

func parseGVariantString(value string) string {
	trimmed := strings.TrimSpace(value)
	if len(trimmed) >= 2 && strings.HasPrefix(trimmed, "'") && strings.HasSuffix(trimmed, "'") {
		return strings.Trim(trimmed, "'")
	}
	return trimmed
}

func quoteGVariantString(value string) string {
	return "'" + strings.ReplaceAll(value, "'", "\\'") + "'"
}

func schemaForPath(path string) string {
	return customBindingPrefix + path
}

func resolveTriggerCommand() (string, error) {
	exe, err := os.Executable()
	if err == nil && isStableExecutable(exe) {
		return exe + " trigger toggle", nil
	}

	path, lookErr := exec.LookPath("coe")
	if lookErr == nil && isStableExecutable(path) {
		return path + " trigger toggle", nil
	}

	if err != nil {
		return "", fmt.Errorf("resolve Coe executable for GNOME custom shortcut: %w", err)
	}
	return "", fmt.Errorf("resolve Coe executable for GNOME custom shortcut: no stable coe binary found")
}

func isStableExecutable(path string) bool {
	if strings.TrimSpace(path) == "" {
		return false
	}
	if filepath.Base(path) != "coe" {
		return false
	}
	temp := os.TempDir()
	cleanPath := filepath.Clean(path)
	cleanTemp := filepath.Clean(temp)
	if cleanTemp != "." && strings.HasPrefix(cleanPath, cleanTemp+string(os.PathSeparator)) {
		return false
	}
	if strings.Contains(cleanPath, "go-build") {
		return false
	}
	return true
}
