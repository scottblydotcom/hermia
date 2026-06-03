//go:build !windows

package main

import (
	"context"
	"errors"
)

// gpuResult is redeclared here for non-Windows builds (tests + Linux CI).
type gpuResult struct {
	Engines map[string]float64
	Gaming  bool
	Err     error
}

func queryGPU(_ context.Context, _ float64) gpuResult {
	return gpuResult{Err: errors.New("PDH not supported on this platform")}
}
