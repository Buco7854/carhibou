package client

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/Buco7854/carhibou/agent/internal/model"
	"github.com/Buco7854/carhibou/agent/internal/store"
)

type Client struct {
	serverURL         string
	credential        string
	version           string
	http              *http.Client
	reportMutex       sync.Mutex
	reportedResponses map[string]struct{}
}

type responseFormatError struct {
	message   string
	signature string
}

func (err *responseFormatError) Error() string { return err.message }

type EnrollmentResponse struct {
	AgentID    string              `json:"agent_id"`
	VehicleID  string              `json:"vehicle_id"`
	Credential string              `json:"credential"`
	Config     store.Configuration `json:"config"`
}

type enrollmentRequest struct {
	Token            string         `json:"token"`
	ImplementationID string         `json:"implementation_id"`
	ProtocolVersion  int            `json:"protocol_version"`
	AgentVersion     string         `json:"agent_version"`
	Hostname         string         `json:"hostname"`
	Hardware         map[string]any `json:"hardware"`
}

const (
	ProtocolVersion               = 2
	maxReportedResponseSignatures = 64
	// MaxTelemetryBatchSize keeps one request, one ingest transaction, and the
	// hook trigger produced from it small enough for a Pi and the server to hold
	// comfortably. Two hundred samples still amortize HTTP overhead while a
	// catch-up upload makes steady progress over unreliable links.
	MaxTelemetryBatchSize = 200
)

func NormalizeServerURL(value string, allowInsecureHTTP bool) (string, error) {
	parsed, err := url.Parse(value)
	if err != nil || parsed.Hostname() == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || parsed.Path != "" && parsed.Path != "/" {
		return "", fmt.Errorf("agent server URL must be an origin without credentials or a path")
	}
	if parsed.Scheme == "https" {
		return strings.TrimSuffix(value, "/"), nil
	}
	host := parsed.Hostname()
	loopback := host == "localhost"
	if address := net.ParseIP(host); address != nil {
		loopback = address.IsLoopback()
	}
	if parsed.Scheme == "http" && (loopback || allowInsecureHTTP) {
		return strings.TrimSuffix(value, "/"), nil
	}
	return "", fmt.Errorf("agent server URL must use HTTPS except when insecure HTTP was explicitly allowed")
}

func New(serverURL, credential, version string, allowInsecureHTTP bool) (*Client, error) {
	normalized, err := NormalizeServerURL(serverURL, allowInsecureHTTP)
	if err != nil {
		return nil, err
	}
	return &Client{
		serverURL: normalized, credential: credential, version: version,
		http: &http.Client{Timeout: 30 * time.Second},
	}, nil
}

func Enroll(serverURL, token, hostname, version string, hardware map[string]any, allowInsecureHTTP bool) (EnrollmentResponse, error) {
	api, err := New(serverURL, "", version, allowInsecureHTTP)
	if err != nil {
		return EnrollmentResponse{}, err
	}
	var response EnrollmentResponse
	err = api.request(http.MethodPost, "/api/v1/agent/enroll", enrollmentRequest{
		Token: token, ImplementationID: "carhibou.go", ProtocolVersion: ProtocolVersion,
		AgentVersion: version, Hostname: hostname, Hardware: hardware,
	}, &response, false)
	if err != nil {
		return response, fmt.Errorf("agent enrollment failed: %w", err)
	}
	if response.AgentID == "" || response.VehicleID == "" || response.Credential == "" {
		return response, fmt.Errorf("agent enrollment response is incomplete")
	}
	if err := response.Config.Validate(); err != nil {
		return response, fmt.Errorf("agent enrollment configuration is invalid: %w", err)
	}
	return response, nil
}

func (client *Client) FetchConfiguration() (store.Configuration, error) {
	var configuration store.Configuration
	if err := client.request(http.MethodGet, "/api/v1/agent/config", nil, &configuration, true); err != nil {
		return configuration, fmt.Errorf("configuration sync failed: %w", err)
	}
	return configuration, nil
}

func (client *Client) Upload(bootID string, samples []model.Sample) ([]string, error) {
	if len(samples) > MaxTelemetryBatchSize {
		return nil, fmt.Errorf("telemetry batch has %d samples; maximum is %d", len(samples), MaxTelemetryBatchSize)
	}
	payload := struct {
		BootID  string         `json:"boot_id"`
		Samples []model.Sample `json:"samples"`
	}{BootID: bootID, Samples: samples}
	var response struct {
		Accepted   []string `json:"accepted"`
		Duplicates []string `json:"duplicates"`
	}
	if err := client.request(http.MethodPost, "/api/v1/agent/telemetry/batch", payload, &response, true); err != nil {
		return nil, fmt.Errorf("telemetry upload failed: %w", err)
	}
	return append(response.Accepted, response.Duplicates...), nil
}

func (client *Client) Download(path string, authenticated bool) ([]byte, error) {
	request, err := http.NewRequest(http.MethodGet, client.serverURL+path, nil)
	if err != nil {
		return nil, err
	}
	client.headers(request, authenticated)
	response, err := client.http.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, responseError(response)
	}
	return io.ReadAll(io.LimitReader(response.Body, 100*1024*1024))
}

func (client *Client) request(method, path string, body, destination any, authenticated bool) error {
	var source io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		source = bytes.NewReader(encoded)
	}
	request, err := http.NewRequest(method, client.serverURL+path, source)
	if err != nil {
		return err
	}
	client.headers(request, authenticated)
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	remoteAddress := "unknown remote address"
	trace := &httptrace.ClientTrace{GotConn: func(info httptrace.GotConnInfo) {
		remoteAddress = info.Conn.RemoteAddr().String()
	}}
	request = request.WithContext(httptrace.WithClientTrace(request.Context(), trace))
	response, err := client.http.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return responseError(response)
	}
	if destination == nil {
		return nil
	}
	content, err := io.ReadAll(io.LimitReader(response.Body, 4*1024*1024))
	if err != nil {
		return err
	}
	if err := json.Unmarshal(content, destination); err != nil {
		collapsed := "response body omitted"
		if path != "/api/v1/agent/enroll" {
			preview := content
			if len(preview) > 200 {
				preview = preview[:200]
			}
			collapsed = strings.Join(strings.Fields(string(preview)), " ")
		}
		finalURL := response.Request.URL
		message := fmt.Sprintf(
			"server answered %s %s from %s for %s: %q",
			response.Status, response.Header.Get("Content-Type"), remoteAddress, finalURL.String(), collapsed,
		)
		signature := fmt.Sprintf("%d|%s|%s%s", response.StatusCode,
			response.Header.Get("Content-Type"), finalURL.Host, finalURL.EscapedPath())
		return &responseFormatError{message: message, signature: signature}
	}
	return nil
}

// ShouldReport suppresses a repeated malformed-response diagnosis while still
// returning the error to callers, so retries and durable outbox semantics stay
// unchanged. Signatures deliberately exclude body content and peers so a proxy
// cannot grow this set with arbitrary responses.
func (client *Client) ShouldReport(err error) bool {
	var formatErr *responseFormatError
	if !errors.As(err, &formatErr) {
		return true
	}
	client.reportMutex.Lock()
	defer client.reportMutex.Unlock()
	if client.reportedResponses == nil {
		client.reportedResponses = make(map[string]struct{})
	}
	if _, reported := client.reportedResponses[formatErr.signature]; reported {
		return false
	}
	if len(client.reportedResponses) >= maxReportedResponseSignatures {
		clear(client.reportedResponses)
	}
	client.reportedResponses[formatErr.signature] = struct{}{}
	return true
}

func (client *Client) headers(request *http.Request, authenticated bool) {
	request.Header.Set("User-Agent", fmt.Sprintf("Carhibou-Agent/%s (%s/%s)", client.version, runtime.GOOS, runtime.GOARCH))
	if authenticated {
		request.Header.Set("Authorization", "Agent "+client.credential)
	}
}

func responseError(response *http.Response) error {
	content, _ := io.ReadAll(io.LimitReader(response.Body, 16*1024))
	var payload struct {
		Detail any `json:"detail"`
	}
	if json.Unmarshal(content, &payload) == nil && payload.Detail != nil {
		return fmt.Errorf("server returned %s: %v", response.Status, payload.Detail)
	}
	return fmt.Errorf("server returned %s", response.Status)
}
