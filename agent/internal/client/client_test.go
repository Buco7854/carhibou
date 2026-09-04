package client

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Buco7854/carhibou/agent/internal/model"
)

func TestExplicitHTTPEnrollmentAndBatchTransport(t *testing.T) {
	var authorization string
	var enrollment enrollmentRequest
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/api/v1/agent/enroll":
			json.NewDecoder(request.Body).Decode(&enrollment)
			json.NewEncoder(response).Encode(map[string]any{"agent_id": "agent-1", "vehicle_id": "vehicle-1", "credential": "secret", "config": map[string]any{"version": 1, "sampling": map[string]any{"default_seconds": 5}, "upload": map[string]any{"default_seconds": 30}, "vehicle_profile": nil}})
		case "/api/v1/agent/telemetry/batch":
			authorization = request.Header.Get("Authorization")
			var body struct {
				Samples []model.Sample `json:"samples"`
			}
			json.NewDecoder(request.Body).Decode(&body)
			json.NewEncoder(response).Encode(map[string]any{"accepted": []string{body.Samples[0].ID}, "duplicates": []string{}})
		}
	}))
	defer server.Close()
	enrolled, err := Enroll(server.URL, "one-time-token-value", "agent", "test", nil, true)
	if err != nil {
		t.Fatal(err)
	}
	api, err := New(server.URL, enrolled.Credential, "test", true)
	if err != nil {
		t.Fatal(err)
	}
	sample := model.NewSample(1, nil, nil, nil)
	accepted, err := api.Upload(model.NewUUID(), []model.Sample{sample})
	if err != nil {
		t.Fatal(err)
	}
	if len(accepted) != 1 || accepted[0] != sample.ID || authorization != "Agent secret" {
		t.Fatalf("unexpected upload: %#v %q", accepted, authorization)
	}
	if enrollment.ImplementationID != "carhibou.go" || enrollment.ProtocolVersion != ProtocolVersion || enrollment.AgentVersion != "test" {
		t.Fatalf("unexpected enrollment identity: %#v", enrollment)
	}
}

func TestServerURLValidation(t *testing.T) {
	for _, value := range []string{"http://192.168.1.151:8000", "http://localhost.evil.example", "https://user:password@example.com", "https://example.com/path", "ftp://example.com"} {
		if _, err := NormalizeServerURL(value, false); err == nil {
			t.Errorf("accepted %s", value)
		}
	}
	if normalized, err := NormalizeServerURL("http://192.168.1.151:8000", true); err != nil || normalized != "http://192.168.1.151:8000" {
		t.Fatalf("explicit LAN HTTP was rejected: %q %v", normalized, err)
	}
	for _, value := range []string{"https://cars.example/", "http://localhost:8000", "http://[::1]:8000"} {
		if _, err := NormalizeServerURL(value, false); err != nil {
			t.Errorf("rejected %s: %v", value, err)
		}
	}
}

func TestUploadRejectsAnOversizedBatch(t *testing.T) {
	api, err := New("http://localhost:8000", "secret", "test", false)
	if err != nil {
		t.Fatal(err)
	}
	samples := make([]model.Sample, MaxTelemetryBatchSize+1)
	if _, err := api.Upload(model.NewUUID(), samples); err == nil {
		t.Fatal("oversized telemetry batch was accepted")
	}
}

func TestMalformedResponseNamesTheRoutePeerAndBoundedPreviewOnce(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		response.Header().Set("Content-Type", "text/html; charset=utf-8")
		response.Write([]byte("  <!doctype html>\n<html lang=en>   <head>" + strings.Repeat("x", 300)))
	}))
	defer server.Close()

	api, err := New(server.URL, "secret", "test", true)
	if err != nil {
		t.Fatal(err)
	}
	_, first := api.FetchConfiguration()
	if first == nil {
		t.Fatal("HTML response was accepted as configuration")
	}
	message := first.Error()
	for _, want := range []string{"200 OK", "text/html; charset=utf-8", server.URL + "/api/v1/agent/config", "<!doctype html> <html lang=en> <head>"} {
		if !strings.Contains(message, want) {
			t.Fatalf("error=%q, want %q", message, want)
		}
	}
	if strings.Count(message, "x") > 200 {
		t.Fatalf("response preview was not bounded: %q", message)
	}
	if !api.ShouldReport(first) {
		t.Fatal("first response signature was suppressed")
	}
	_, repeated := api.FetchConfiguration()
	if api.ShouldReport(repeated) {
		t.Fatal("repeated response signature was reported twice")
	}
}
