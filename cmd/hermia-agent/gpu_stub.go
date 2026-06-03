//go:build !windows

package main

import (
	"context"
	"errors"
)

func queryGPU(_ context.Context, _ float64) gpuResult {
	return gpuResult{Err: errors.New("PDH not supported on this platform")}
}
