//go:build windows

package main

import (
	"context"
	"fmt"
	"runtime"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

const (
	pdhFmtDouble        = 0x00000200
	pdhMoreData         = 0x800007D2
	errorSuccess        = 0
	pdhCStatusValidData = 0x00000000 // counter value is valid
	pdhCStatusNewData   = 0x00000001 // counter value is valid and new
)

var (
	modPdh                           = windows.NewLazySystemDLL("pdh.dll")
	procPdhOpenQuery                 = modPdh.NewProc("PdhOpenQuery")
	procPdhCloseQuery                = modPdh.NewProc("PdhCloseQuery")
	procPdhAddEnglishCounterW        = modPdh.NewProc("PdhAddEnglishCounterW")
	procPdhCollectQueryData          = modPdh.NewProc("PdhCollectQueryData")
	procPdhGetFormattedCounterArrayW = modPdh.NewProc("PdhGetFormattedCounterArrayW")
)

// matches PDH_FMT_COUNTERVALUE on 64-bit Windows: DWORD CStatus + 4-byte pad + 8-byte double union
type pdhFmtCounterValue struct {
	CStatus uint32
	_       [4]byte
	Double  float64
}

// matches PDH_FMT_COUNTERVALUE_ITEM_W: LPWSTR + PDH_FMT_COUNTERVALUE
type pdhFmtCounterValueItemW struct {
	SzName   *uint16
	FmtValue pdhFmtCounterValue
}

func queryGPU(ctx context.Context, threshold float64) gpuResult {
	// Each request opens its own independent PDH query handle — no shared
	// mutable state, so no mutex is needed for concurrent requests.
	var hQuery uintptr
	ret, _, _ := procPdhOpenQuery.Call(0, 0, uintptr(unsafe.Pointer(&hQuery)))
	if ret != errorSuccess {
		return gpuResult{Err: fmt.Errorf("PdhOpenQuery: 0x%08X", ret)}
	}
	defer procPdhCloseQuery.Call(hQuery)

	counterPath, err := windows.UTF16PtrFromString(`\GPU Engine(*)\Utilization Percentage`)
	if err != nil {
		return gpuResult{Err: fmt.Errorf("UTF16PtrFromString: %w", err)}
	}

	var hCounter uintptr
	ret, _, _ = procPdhAddEnglishCounterW.Call(
		hQuery,
		uintptr(unsafe.Pointer(counterPath)),
		0,
		uintptr(unsafe.Pointer(&hCounter)),
	)
	// Proc.Call takes ...uintptr (variadic), breaking Go's Rule 4 safe-pointer
	// guarantee. KeepAlive pins the backing []uint16 until after the DLL call.
	runtime.KeepAlive(counterPath)
	if ret != errorSuccess {
		return gpuResult{Err: fmt.Errorf("PdhAddEnglishCounterW: 0x%08X", ret)}
	}

	// baseline collect — establishes counter state; values discarded
	ret, _, _ = procPdhCollectQueryData.Call(hQuery)
	if ret != errorSuccess {
		return gpuResult{Err: fmt.Errorf("PdhCollectQueryData (baseline): 0x%08X", ret)}
	}

	timer := time.NewTimer(1 * time.Second)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return gpuResult{Err: ctx.Err()}
	case <-timer.C:
	}

	// actual collect
	ret, _, _ = procPdhCollectQueryData.Call(hQuery)
	if ret != errorSuccess {
		return gpuResult{Err: fmt.Errorf("PdhCollectQueryData: 0x%08X", ret)}
	}

	// sizing probe: PDH returns PDH_MORE_DATA when instances exist,
	// or ERROR_SUCCESS when the counter set is empty.
	var bufSize, itemCount uint32
	ret, _, _ = procPdhGetFormattedCounterArrayW.Call(
		hCounter,
		pdhFmtDouble,
		uintptr(unsafe.Pointer(&bufSize)),
		uintptr(unsafe.Pointer(&itemCount)),
		0,
	)
	if ret == errorSuccess {
		// No GPU engine instances active — machine is idle.
		return gpuResult{Engines: make(map[string]float64), Gaming: false}
	}
	if ret != pdhMoreData {
		return gpuResult{Err: fmt.Errorf("PdhGetFormattedCounterArrayW (size): 0x%08X", ret)}
	}

	// fill call: cap fillCount to the allocated buffer to guard against
	// TOCTOU (new GPU instances appearing between the size probe and fill).
	buf := make([]byte, bufSize)
	var fillCount uint32
	ret, _, _ = procPdhGetFormattedCounterArrayW.Call(
		hCounter,
		pdhFmtDouble,
		uintptr(unsafe.Pointer(&bufSize)),
		uintptr(unsafe.Pointer(&fillCount)),
		uintptr(unsafe.Pointer(unsafe.SliceData(buf))),
	)
	if ret != errorSuccess {
		return gpuResult{Err: fmt.Errorf("PdhGetFormattedCounterArrayW: 0x%08X", ret)}
	}

	itemSize := unsafe.Sizeof(pdhFmtCounterValueItemW{})
	if maxItems := uint32(uintptr(len(buf)) / itemSize); fillCount > maxItems {
		fillCount = maxItems
	}
	samples := make([]pdhSample, 0, fillCount)
	for i := uint32(0); i < fillCount; i++ {
		item := (*pdhFmtCounterValueItemW)(unsafe.Pointer(&buf[uintptr(i)*itemSize]))
		// Skip entries with invalid or stale CStatus — only sum confirmed-valid values.
		if item.FmtValue.CStatus != pdhCStatusValidData && item.FmtValue.CStatus != pdhCStatusNewData {
			continue
		}
		samples = append(samples, pdhSample{
			instance: windows.UTF16PtrToString(item.SzName),
			value:    item.FmtValue.Double,
		})
	}

	engines := aggregateEngineCounters(samples)
	return gpuResult{
		Engines: engines,
		Gaming:  engines["3D"] > threshold,
	}
}
