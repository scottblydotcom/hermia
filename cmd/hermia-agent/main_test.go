package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// On Linux/macOS the gpu_stub.go build tag makes queryGPU always return a PDH
// error, which exercises the fail-closed and fail-open paths without any mock.

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
	// gpu_stub always returns a PDH error; fail-closed must return 200 + gaming:true.
	h := newGPUHandler("test-node", "fail-closed", 10.0)
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
}

func TestGPUHandler_FailOpen(t *testing.T) {
	// gpu_stub always returns a PDH error; fail-open must return 503 + gaming:false.
	h := newGPUHandler("test-node", "fail-open", 10.0)
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
	if resp.Status != "error" {
		t.Errorf("status = %q, want %q", resp.Status, "error")
	}
}

func TestGPUHandler_AuthGateFiresFirst(t *testing.T) {
	// Auth middleware must reject before the handler runs, even on fail-closed.
	const token = "secret"
	h := newBearerAuth(token)(newGPUHandler("test-node", "fail-closed", 10.0))

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
		// Handler runs (fail-closed with PDH stub error returns 200).
		if rec.Code != http.StatusOK {
			t.Errorf("status = %d, want 200", rec.Code)
		}
	})
}

func TestGPUHandler_FailClosedResponseShape(t *testing.T) {
	// Verify all expected fields are present in a fail-closed response.
	h := newGPUHandler("shape-node", "fail-closed", 15.0)
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
}
