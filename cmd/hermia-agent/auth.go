package main

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"net/http"
	"strings"
)

type errResponse struct {
	Status string `json:"status"`
	Error  string `json:"error"`
}

func newBearerAuth(token string) func(http.Handler) http.Handler {
	wantHash := sha256.Sum256([]byte(token))
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			var gotToken string
			// RFC 7235 §2.1: scheme tokens are case-insensitive.
			if scheme, rest, found := strings.Cut(authHeader, " "); found && strings.EqualFold(scheme, "Bearer") {
				gotToken = rest
			}
			gotHash := sha256.Sum256([]byte(gotToken))
			if subtle.ConstantTimeCompare(gotHash[:], wantHash[:]) != 1 {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				json.NewEncoder(w).Encode(errResponse{Status: "error", Error: "unauthorized"}) //nolint:errcheck
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
