package agent

import (
	"reflect"
	"testing"

	"github.com/iew-org/iew/internal/config"
)

func TestProcessFeedback(t *testing.T) {
	a := NewAgent(config.DefaultConfig())

	rawOutput := `Here is my review:
12: First issue with code.
This is a continuation line for issue 12.
* 24: Second issue.
- 30: Third issue with extra bullet.
40: Fourth issue.
`

	got := a.ProcessFeedback(rawOutput)
	want := []string{
		"12: First issue with code.\nThis is a continuation line for issue 12.",
		"24: Second issue.",
		"30: Third issue with extra bullet.",
		"40: Fourth issue.",
	}

	if !reflect.DeepEqual(got, want) {
		t.Errorf("ProcessFeedback mismatch:\nGot:  %#v\nWant: %#v", got, want)
	}
}
