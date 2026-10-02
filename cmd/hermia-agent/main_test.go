package main

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"runtime"
	"testing"
	"time"
)

// The handler tests inject the GPU query instead of relying on gpu_stub.go. The stub
// only builds off Windows; on the Windows runner the real PDH query runs and succeeded
// in every sampled CI run, so the error-path tests never saw an error (hermia-4m7).
// A fake query makes every path deterministic on every platform.

const fakePDHError = "simulated PDH failure"

func failingQuery(_ context.Context, _ float64) gpuResult {
	return gpuResult{Err: errors.New(fakePDHError)}
}

func succeedingQuery(engines map[string]float64, gaming bool) gpuQuery {
	return func(_ context.Context, _ float64) gpuResult {
		return gpuResult{Engines: engines, Gaming: gaming}
	}
}

func makeRequest(t *testing.T, handler http.Handler, token string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/gpu", nil)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec
}

func decodeResponse(t *testing.T, rec *httptest.ResponseRecorder) gpuResponse {
	t.Helper()
	var resp gpuResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	return resp
}

func TestGPUHandler_FailClosed(t *testing.T) {
	// A query error under fail-closed must return 200 + gaming:true, so the fleet
	// treats an unreadable GPU as busy and does not dispatch.
	h := newGPUHandlerWithQuery("test-node", "fail-closed", 10.0, failingQuery)
	rec := makeRequest(t, h, "")

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	resp := decodeResponse(t, rec)
	if !resp.Gaming {
		t.Error("gaming = false, want true (fail-closed on PDH error)")
	}
	if resp.NodeID != "test-node" {
		t.Errorf("node_id = %q, want %q", resp.NodeID, "test-node")
	}
	if resp.SampledAt == "" {
		t.Error("sampled_at is empty")
	}
	if resp.Error != "pdh_query_failed" {
		t.Errorf("error = %q, want %q", resp.Error, "pdh_query_failed")
	}
	if resp.ErrorDetail != fakePDHError {
		t.Errorf("error_detail = %q, want %q", resp.ErrorDetail, fakePDHError)
	}
}

func TestGPUHandler_FailOpen(t *testing.T) {
	// A query error under fail-open must return 503 + gaming:false.
	h := newGPUHandlerWithQuery("test-node", "fail-open", 10.0, failingQuery)
	rec := makeRequest(t, h, "")

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503", rec.Code)
	}
	resp := decodeResponse(t, rec)
	if resp.Gaming {
		t.Error("gaming = true, want false (fail-open allows dispatch on PDH error)")
	}
	if resp.NodeID != "test-node" {
		t.Errorf("node_id = %q, want %q", resp.NodeID, "test-node")
	}
	if resp.SampledAt == "" {
		t.Error("sampled_at is empty")
	}
	if resp.Error != "pdh_query_failed" {
		t.Errorf("error = %q, want %q", resp.Error, "pdh_query_failed")
	}
	if resp.ErrorDetail != fakePDHError {
		t.Errorf("error_detail = %q, want %q", resp.ErrorDetail, fakePDHError)
	}
	if resp.Status != "error" {
		t.Errorf("status = %q, want %q", resp.Status, "error")
	}
	if resp.GateThresholdPct != 10.0 {
		t.Errorf("gate_threshold_pct = %v, want 10.0", resp.GateThresholdPct)
	}
}

func TestGPUHandler_AuthGateFiresFirst(t *testing.T) {
	// Auth middleware must reject before the handler runs, even on fail-closed.
	const token = "secret"
	h := newBearerAuth(token)(newGPUHandlerWithQuery("test-node", "fail-closed", 10.0, failingQuery))

	t.Run("no token returns 401", func(t *testing.T) {
		rec := makeRequest(t, h, "")
		if rec.Code != http.StatusUnauthorized {
			t.Errorf("status = %d, want 401", rec.Code)
		}
	})

	t.Run("wrong token returns 401", func(t *testing.T) {
		rec := makeRequest(t, h, "wrong")
		if rec.Code != http.StatusUnauthorized {
			t.Errorf("status = %d, want 401", rec.Code)
		}
	})

	t.Run("correct token reaches handler", func(t *testing.T) {
		rec := makeRequest(t, h, token)
		if rec.Code != http.StatusOK {
			t.Fatalf("status = %d, want 200", rec.Code)
		}
		// Prove the handler body ran: only the fail-closed error path sets this.
		if resp := decodeResponse(t, rec); resp.Error != "pdh_query_failed" {
			t.Errorf("error = %q, want %q (handler did not run)", resp.Error, "pdh_query_failed")
		}
	})
}

func TestGPUHandler_FailClosedResponseShape(t *testing.T) {
	// Verify all expected fields are present in a fail-closed response.
	h := newGPUHandlerWithQuery("shape-node", "fail-closed", 15.0, failingQuery)
	rec := makeRequest(t, h, "")

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	resp := decodeResponse(t, rec)

	if resp.Engines == nil {
		t.Error("engines field is nil, want empty map")
	}
	if resp.GateThresholdPct != 15.0 {
		t.Errorf("gate_threshold_pct = %v, want 15.0", resp.GateThresholdPct)
	}
	if resp.Status != "ok" {
		t.Errorf("status = %q, want %q", resp.Status, "ok")
	}
	if resp.Error != "pdh_query_failed" {
		t.Errorf("error = %q, want %q", resp.Error, "pdh_query_failed")
	}
}

func TestGPUHandler_SuccessPassesQueryResultThrough(t *testing.T) {
	// The success path was never asserted before: off Windows the stub always errors,
	// and on Windows the old tests expected an error.
	for _, errorMode := range []string{"fail-closed", "fail-open"} {
		for _, gaming := range []bool{true, false} {
			engines := map[string]float64{"3D": 42.5, "Copy": 1.25}
			h := newGPUHandlerWithQuery("ok-node", errorMode, 10.0, succeedingQuery(engines, gaming))
			rec := makeRequest(t, h, "")

			if rec.Code != http.StatusOK {
				t.Fatalf("%s gaming=%v: status = %d, want 200", errorMode, gaming, rec.Code)
			}
			resp := decodeResponse(t, rec)
			if resp.Status != "ok" {
				t.Errorf("%s gaming=%v: status = %q, want ok", errorMode, gaming, resp.Status)
			}
			if resp.Gaming != gaming {
				t.Errorf("%s: gaming = %v, want %v (from the query)", errorMode, resp.Gaming, gaming)
			}
			if resp.Error != "" || resp.ErrorDetail != "" {
				t.Errorf("%s gaming=%v: error = %q / %q, want both empty", errorMode, gaming, resp.Error, resp.ErrorDetail)
			}
			if resp.Engines["3D"] != 42.5 || resp.Engines["Copy"] != 1.25 || len(resp.Engines) != 2 {
				t.Errorf("%s gaming=%v: engines = %v, want the query's map", errorMode, gaming, resp.Engines)
			}
			if resp.NodeID != "ok-node" || resp.GateThresholdPct != 10.0 || resp.SampledAt == "" {
				t.Errorf("%s gaming=%v: node_id=%q threshold=%v sampled_at=%q", errorMode, gaming, resp.NodeID, resp.GateThresholdPct, resp.SampledAt)
			}
		}
	}
}

func TestGPUHandler_PassesThresholdAndRequestContextToQuery(t *testing.T) {
	var gotThreshold float64
	var gotCtx context.Context
	q := func(ctx context.Context, threshold float64) gpuResult {
		gotCtx, gotThreshold = ctx, threshold
		return gpuResult{Engines: map[string]float64{}}
	}
	h := newGPUHandlerWithQuery("ctx-node", "fail-closed", 37.5, q)
	req := httptest.NewRequest(http.MethodGet, "/gpu", nil)
	ctx, cancel := context.WithCancel(req.Context())
	defer cancel()
	h.ServeHTTP(httptest.NewRecorder(), req.WithContext(ctx))

	if gotThreshold != 37.5 {
		t.Errorf("query threshold = %v, want 37.5", gotThreshold)
	}
	if gotCtx == nil {
		t.Fatal("query was not called")
	}
	cancel()
	if gotCtx.Err() == nil {
		t.Error("query context is not the request's: cancelling the request did not cancel it")
	}
}

func TestQueryGPU_RealImplementationReturnsResultOrError(t *testing.T) {
	// Smoke test of the production query on whatever platform runs the suite. On
	// Windows this and ProductionWiring are the two tests that run the real PDH query.
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	res := queryGPU(ctx, 10.0)

	if runtime.GOOS != "windows" {
		if res.Err == nil {
			t.Fatal("non-Windows stub returned no error; ProductionWiring relies on it to pin the wiring")
		}
		return
	}
	if res.Err != nil {
		// The real query succeeded on the Windows CI runner in every sampled run, so in CI
		// an error means the PDH path broke. Off CI (a dev box without GPU counters) it is
		// only reported.
		if os.Getenv("CI") != "" {
			t.Fatalf("real PDH query failed on the CI runner: %v", res.Err)
		}
		t.Logf("PDH query error on this machine (not CI): %v", res.Err)
		return
	}
	t.Logf("real PDH reading: engines=%v gaming=%v", res.Engines, res.Gaming)
	if res.Engines == nil {
		t.Error("PDH success with nil engines map, want non-nil")
	}
	for eng, v := range res.Engines {
		if math.IsNaN(v) || math.IsInf(v, 0) || v < 0 {
			t.Errorf("engines[%q] = %v, want a finite, non-negative utilisation", eng, v)
		}
	}
}

func TestGPUHandler_ProductionWiringIsSelfConsistent(t *testing.T) {
	// newGPUHandler must wire the real queryGPU. On Windows the real query may succeed
	// or fail, so only the non-Windows job can pin the wiring exactly (by the stub's
	// error text); every platform checks that the response is one of the valid shapes.
	rec := makeRequest(t, newGPUHandler("wired-node", "fail-closed", 10.0), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200 (fail-closed answers 200 on success and on error)", rec.Code)
	}
	resp := decodeResponse(t, rec)
	if resp.Engines == nil {
		t.Error("engines field is nil, want a map")
	}
	if resp.Error != "" && !resp.Gaming {
		t.Errorf("error = %q with gaming=false: fail-closed must report gaming on error", resp.Error)
	}
	if runtime.GOOS != "windows" {
		if resp.Error != "pdh_query_failed" {
			t.Errorf("error = %q, want pdh_query_failed from the non-Windows stub", resp.Error)
		}
		want := queryGPU(context.Background(), 10.0).Err.Error()
		if resp.ErrorDetail != want {
			t.Errorf("error_detail = %q, want %q: newGPUHandler is not wired to queryGPU", resp.ErrorDetail, want)
		}
	}
}
