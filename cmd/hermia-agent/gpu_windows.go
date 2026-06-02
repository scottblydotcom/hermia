//go:build windows

package main

import (
	"fmt"
	"sync"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

const (
	pdhFmtDouble  = 0x00000200
	pdhMoreData   = 0x800007D2
	errorSuccess  = 0
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

type gpuResult struct {
	Engines map[string]float64
	Gaming  bool
	Err     error
}

var pdhMu sync.Mutex

func queryGPU(threshold float64) gpuResult {
	// Serialize PDH handle lifetime; mutex is released before the 1s sleep so
	// concurrent requests don't queue behind the mandatory inter-sample delay.
	pdhMu.Lock()

	var hQuery uintptr
	ret, _, _ := procPdhOpenQuery.Call(0, 0, uintptr(unsafe.Pointer(&hQuery)))
	if ret != errorSuccess {
		pdhMu.Unlock()
		return gpuResult{Err: fmt.Errorf("PdhOpenQuery: 0x%08X", ret)}
	}

	counterPath, err := windows.UTF16PtrFromString(`\GPU Engine(*)\Utilization Percentage`)
	if err != nil {
		procPdhCloseQuery.Call(hQuery)
		pdhMu.Unlock()
		return gpuResult{Err: fmt.Errorf("UTF16PtrFromString: %w", err)}
	}

	var hCounter uintptr
	ret, _, _ = procPdhAddEnglishCounterW.Call(
		hQuery,
		uintptr(unsafe.Pointer(counterPath)),
		0,
		uintptr(unsafe.Pointer(&hCounter)),
	)
	if ret != errorSuccess {
		procPdhCloseQuery.Call(hQuery)
		pdhMu.Unlock()
		return gpuResult{Err: fmt.Errorf("PdhAddEnglishCounterW: 0x%08X", ret)}
	}

	// baseline collect — establishes counter state; values discarded
	ret, _, _ = procPdhCollectQueryData.Call(hQuery)
	if ret != errorSuccess {
		procPdhCloseQuery.Call(hQuery)
		pdhMu.Unlock()
		return gpuResult{Err: fmt.Errorf("PdhCollectQueryData (baseline): 0x%08X", ret)}
	}

	// Release lock before the mandatory inter-sample sleep so concurrent
	// requests are not serialized across the full 1-second measurement window.
	pdhMu.Unlock()
	time.Sleep(1 * time.Second)
	pdhMu.Lock()
	defer func() {
		procPdhCloseQuery.Call(hQuery)
		pdhMu.Unlock()
	}()

	// actual collect
	ret, _, _ = procPdhCollectQueryData.Call(hQuery)
	if ret != errorSuccess {
		return gpuResult{Err: fmt.Errorf("PdhCollectQueryData: 0x%08X", ret)}
	}

	// sizing probe: PDH returns PDH_MORE_DATA when instances exist,
	// or ERROR_SUCCESS / PDH_NO_DATA when the counter set is empty.
	var bufSize, itemCount uint32
	ret, _, _ = procPdhGetFormattedCounterArrayW.Call(
		hCounter,
		pdhFmtDouble,
		uintptr(unsafe.Pointer(&bufSize)),
		uintptr(unsafe.Pointer(&itemCount)),
		0,
	)
	if ret == errorSuccess || itemCount == 0 {
		// No GPU engine instances active — machine is idle.
		return gpuResult{Engines: make(map[string]float64), Gaming: false}
	}
	if ret != pdhMoreData {
		return gpuResult{Err: fmt.Errorf("PdhGetFormattedCounterArrayW (size): 0x%08X", ret)}
	}

	// fill call: use a fresh itemCount variable so the sizing estimate is
	// preserved for bounds checking regardless of what Windows writes here.
	buf := make([]byte, bufSize)
	var fillCount uint32
	ret, _, _ = procPdhGetFormattedCounterArrayW.Call(
		hCounter,
		pdhFmtDouble,
		uintptr(unsafe.Pointer(&bufSize)),
		uintptr(unsafe.Pointer(&fillCount)),
		uintptr(unsafe.Pointer(&buf[0])),
	)
	if ret != errorSuccess {
		return gpuResult{Err: fmt.Errorf("PdhGetFormattedCounterArrayW: 0x%08X", ret)}
	}

	itemSize := unsafe.Sizeof(pdhFmtCounterValueItemW{})
	samples := make([]pdhSample, 0, fillCount)
	for i := uint32(0); i < fillCount; i++ {
		item := (*pdhFmtCounterValueItemW)(unsafe.Pointer(&buf[uintptr(i)*itemSize]))
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
