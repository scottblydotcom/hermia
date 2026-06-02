package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestBearerAuth(t *testing.T) {
	const validToken = "correct-token"

	// newBearerAuth uses crypto/subtle.ConstantTimeCompare internally.
	// These are functional correctness tests; timing properties are not verified here.
	authMiddleware := newBearerAuth(validToken)

	tests := []struct {
		name          string
		authHeader    string
		expectStatus  int
		expectBody    string
		handlerCalled bool
	}{
		{
			name:          "Valid token passes",
			authHeader:    "Bearer correct-token",
			expectStatus:  http.StatusOK,
			handlerCalled: true,
		},
		{
			name:          "Wrong token",
			authHeader:    "Bearer wrong-token",
			expectStatus:  http.StatusUnauthorized,
			expectBody:    `"status":"error"`,
			handlerCalled: false,
		},
		{
			name:          "Missing Authorization header",
			authHeader:    "",
			expectStatus:  http.StatusUnauthorized,
			expectBody:    `"error":"unauthorized"`,
			handlerCalled: false,
		},
		{
			name:          "Malformed header no Bearer prefix",
			authHeader:    "sometoken",
			expectStatus:  http.StatusUnauthorized,
			expectBody:    `"error":"unauthorized"`,
			handlerCalled: false,
		},
		{
			name:          "Empty token after Bearer",
			authHeader:    "Bearer ",
			expectStatus:  http.StatusUnauthorized,
			expectBody:    `"error":"unauthorized"`,
			handlerCalled: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var handlerCalled bool
			inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				handlerCalled = true
				w.WriteHeader(http.StatusOK)
			})

			req := httptest.NewRequest(http.MethodGet, "/gpu", nil)
			if tt.authHeader != "" {
				req.Header.Set("Authorization", tt.authHeader)
			}
			rec := httptest.NewRecorder()

			authMiddleware(inner).ServeHTTP(rec, req)

			if rec.Code != tt.expectStatus {
				t.Errorf("status = %d, want %d", rec.Code, tt.expectStatus)
			}
			if handlerCalled != tt.handlerCalled {
				t.Errorf("handlerCalled = %v, want %v", handlerCalled, tt.handlerCalled)
			}
			if tt.expectBody != "" && !strings.Contains(rec.Body.String(), tt.expectBody) {
				t.Errorf("body = %q, want it to contain %q", rec.Body.String(), tt.expectBody)
			}
		})
	}
}
