package main

import (
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
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			var gotToken string
			if strings.HasPrefix(authHeader, "Bearer ") {
				gotToken = authHeader[7:]
			}
			if subtle.ConstantTimeCompare([]byte(gotToken), []byte(token)) != 1 {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				json.NewEncoder(w).Encode(errResponse{Status: "error", Error: "unauthorized"}) //nolint:errcheck
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
