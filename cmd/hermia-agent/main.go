package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"
)

type gpuResponse struct {
	Status           string             `json:"status"`
	NodeID           string             `json:"node_id"`
	Gaming           bool               `json:"gaming"`
	GateThresholdPct float64            `json:"gate_threshold_pct"`
	Engines          map[string]float64 `json:"engines"`
	SampledAt        string             `json:"sampled_at"`
	Error            string             `json:"error,omitempty"`
	ErrorDetail      string             `json:"error_detail,omitempty"`
}

type gpuErrResponse struct {
	Status      string `json:"status"`
	NodeID      string `json:"node_id"`
	Error       string `json:"error"`
	ErrorDetail string `json:"error_detail,omitempty"`
	SampledAt   string `json:"sampled_at"`
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func main() {
	// Env vars set flag defaults; explicit CLI flags override them.
	port := flag.String("port", envOr("HERMIA_AGENT_PORT", "11435"), "port to listen on")
	bind := flag.String("bind", envOr("HERMIA_AGENT_BIND", "0.0.0.0"), "address to bind")
	tokenEnv := flag.String("token-env", envOr("HERMIA_AGENT_TOKEN_ENV", "HERMIA_AGENT_TOKEN"), "env var holding the bearer token")
	nodeID := flag.String("node-id", envOr("HERMIA_AGENT_NODE_ID", ""), "node identifier (default: hostname)")
	errorMode := flag.String("error-mode", envOr("HERMIA_AGENT_ERROR_MODE", "fail-closed"), "fail-closed or fail-open")

	defaultThreshold := 10.0
	if v := os.Getenv("HERMIA_AGENT_THRESHOLD"); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			defaultThreshold = f
		} else {
			log.Printf("WARNING: HERMIA_AGENT_THRESHOLD=%q is not a valid float, using default %.1f", v, defaultThreshold)
		}
	}
	threshold := flag.Float64("threshold", defaultThreshold, "3D engine % above which owner is gaming")

	flag.Parse()

	if *errorMode != "fail-closed" && *errorMode != "fail-open" {
		log.Fatalf("invalid --error-mode %q: must be fail-closed or fail-open", *errorMode)
	}
	if *threshold < 0.0 || *threshold > 100.0 {
		log.Fatalf("invalid --threshold %.2f: must be in [0.0, 100.0]", *threshold)
	}

	token := os.Getenv(*tokenEnv)
	if token == "" {
		log.Fatalf("token env var %q is not set; refusing to start unauthenticated", *tokenEnv)
	}

	if *nodeID == "" {
		hostname, err := os.Hostname()
		if err != nil {
			log.Fatalf("os.Hostname: %v", err)
		}
		*nodeID = hostname
	}

	log.Printf("WARNING: serving without TLS on %s:%s — isolated VLAN only, not for untrusted networks", *bind, *port)

	handler := func(w http.ResponseWriter, r *http.Request) {
		result := queryGPU(r.Context(), *threshold)
		sampledAt := time.Now().UTC().Format(time.RFC3339)
		w.Header().Set("Content-Type", "application/json")

		if result.Err != nil {
			log.Printf("ERROR: pdh query: %v", result.Err)
			if *errorMode == "fail-closed" {
				w.WriteHeader(http.StatusOK)
				json.NewEncoder(w).Encode(gpuResponse{ //nolint:errcheck
					Status:           "ok",
					NodeID:           *nodeID,
					Gaming:           true,
					GateThresholdPct: *threshold,
					Engines:          map[string]float64{},
					SampledAt:        sampledAt,
					Error:            "pdh_query_failed",
					ErrorDetail:      result.Err.Error(),
				})
			} else {
				w.WriteHeader(http.StatusServiceUnavailable)
				json.NewEncoder(w).Encode(gpuErrResponse{ //nolint:errcheck
					Status:      "error",
					NodeID:      *nodeID,
					Error:       "pdh_query_failed",
					ErrorDetail: result.Err.Error(),
					SampledAt:   sampledAt,
				})
			}
			return
		}

		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(gpuResponse{ //nolint:errcheck
			Status:           "ok",
			NodeID:           *nodeID,
			Gaming:           result.Gaming,
			GateThresholdPct: *threshold,
			Engines:          result.Engines,
			SampledAt:        sampledAt,
		})
	}

	mux := http.NewServeMux()
	mux.Handle("/gpu", newBearerAuth(token)(http.HandlerFunc(handler)))

	srv := &http.Server{
		Addr:              net.JoinHostPort(*bind, *port),
		Handler:           mux,
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      10 * time.Second,
	}

	go func() {
		log.Printf("hermia-agent listening on %s:%s", *bind, *port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("ListenAndServe: %v", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("Shutdown: %v", err)
	}
	log.Println("stopped")
}
