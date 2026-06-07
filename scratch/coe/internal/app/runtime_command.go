package app

type runtimeCommandType string

const (
	runtimeCommandToggle runtimeCommandType = "toggle"
	runtimeCommandStart  runtimeCommandType = "start"
	runtimeCommandStop   runtimeCommandType = "stop"
	runtimeCommandCancel runtimeCommandType = "cancel"
)

type runtimeCommand struct {
	Type   runtimeCommandType
	Source string
	Edit   *selectedTextEditRequest
	Reply  chan runtimeCommandResponse
}

type runtimeCommandResponse struct {
	Active  bool
	Changed bool
	Err     error
}

type selectedTextEditRequest struct {
	SelectedText string
}

type selectedTextEditSession struct {
	SessionID    string
	SelectedText string
}
