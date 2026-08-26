package profile

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strconv"

	"github.com/Buco7854/vehinode/agent/internal/model"
	"go.yaml.in/yaml/v3"
)

var integerTypes = map[string]struct {
	length int
	signed bool
}{
	"uint8": {1, false}, "uint16": {2, false}, "uint32": {4, false},
	"int8": {1, true}, "int16": {2, true}, "int32": {4, true},
}

type Definition struct {
	ID              string           `json:"id" yaml:"id"`
	Signals         []Signal         `json:"signals" yaml:"signals"`
	ComputedMetrics []ComputedMetric `json:"computed_metrics,omitempty" yaml:"computed_metrics,omitempty"`
}

type Signal struct {
	Name    string   `json:"name" yaml:"name"`
	Source  Source   `json:"source" yaml:"source"`
	Decoder Decoder  `json:"decoder" yaml:"decoder"`
	Unit    string   `json:"unit,omitempty" yaml:"unit,omitempty"`
	Minimum *float64 `json:"minimum,omitempty" yaml:"minimum,omitempty"`
	Maximum *float64 `json:"maximum,omitempty" yaml:"maximum,omitempty"`
}

type Source struct {
	Type  string `json:"type" yaml:"type"`
	CANID int    `json:"can_id" yaml:"can_id"`
}

type Decoder struct {
	ByteOffset int            `json:"byte_offset,omitempty" yaml:"byte_offset,omitempty"`
	DataType   string         `json:"data_type" yaml:"data_type"`
	Length     int            `json:"length,omitempty" yaml:"length,omitempty"`
	Signed     bool           `json:"signed,omitempty" yaml:"signed,omitempty"`
	Endianness string         `json:"endianness,omitempty" yaml:"endianness,omitempty"`
	Bit        int            `json:"bit,omitempty" yaml:"bit,omitempty"`
	BitMask    any            `json:"bit_mask,omitempty" yaml:"bit_mask,omitempty"`
	Shift      int            `json:"shift,omitempty" yaml:"shift,omitempty"`
	Scale      *float64       `json:"scale,omitempty" yaml:"scale,omitempty"`
	Offset     *float64       `json:"offset,omitempty" yaml:"offset,omitempty"`
	Enum       map[string]any `json:"enum,omitempty" yaml:"enum,omitempty"`
}

type ComputedMetric struct {
	Name      string   `json:"name" yaml:"name"`
	Operation string   `json:"operation" yaml:"operation"`
	Inputs    []string `json:"inputs" yaml:"inputs"`
	Unit      string   `json:"unit,omitempty" yaml:"unit,omitempty"`
	// Scale converts the raw product into the declared unit, so a profile can
	// multiply volts by amps and still publish kilowatts.
	Scale *float64 `json:"scale,omitempty" yaml:"scale,omitempty"`
}

type DecodedSignal struct {
	Name  string
	Value any
	Unit  string
}

type DecoderEngine struct {
	definition Definition
	byCANID    map[int][]Signal
}

func ParseJSON(value json.RawMessage) (*DecoderEngine, error) {
	var definition Definition
	if err := json.Unmarshal(value, &definition); err != nil {
		return nil, fmt.Errorf("invalid profile JSON: %w", err)
	}
	return New(definition)
}

func FromFile(path string) (*DecoderEngine, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var definition Definition
	if err := yaml.Unmarshal(content, &definition); err != nil {
		return nil, fmt.Errorf("invalid profile: %w", err)
	}
	return New(definition)
}

func New(definition Definition) (*DecoderEngine, error) {
	if definition.ID == "" || definition.Signals == nil {
		return nil, fmt.Errorf("profile requires an id and signals")
	}
	engine := &DecoderEngine{definition: definition, byCANID: map[int][]Signal{}}
	for _, signal := range definition.Signals {
		if err := validateSignal(signal); err != nil {
			return nil, err
		}
		engine.byCANID[signal.Source.CANID] = append(engine.byCANID[signal.Source.CANID], signal)
	}
	for _, computed := range definition.ComputedMetrics {
		if computed.Name == "" || computed.Operation != "multiply" || len(computed.Inputs) != 2 {
			return nil, fmt.Errorf("invalid computed metric %q", computed.Name)
		}
	}
	return engine, nil
}

func validateSignal(signal Signal) error {
	if signal.Name == "" || signal.Source.Type != "can" || signal.Source.CANID < 0 || signal.Source.CANID > 0x1fffffff {
		return fmt.Errorf("invalid CAN signal %q", signal.Name)
	}
	if _, ok := integerTypes[signal.Decoder.DataType]; !ok && signal.Decoder.DataType != "bytes" && signal.Decoder.DataType != "boolean" {
		return fmt.Errorf("unsupported decoder type %q", signal.Decoder.DataType)
	}
	return nil
}

func (engine *DecoderEngine) ID() string { return engine.definition.ID }

func (engine *DecoderEngine) Decode(frame model.CANFrame, current map[string]any) []DecodedSignal {
	result := []DecodedSignal{}
	values := map[string]any{}
	for key, value := range current {
		values[key] = value
	}
	for _, signal := range engine.byCANID[frame.CANID] {
		value, err := decodeValue(signal, frame.Data)
		if err != nil {
			continue
		}
		values[signal.Name] = value
		result = append(result, DecodedSignal{Name: signal.Name, Value: value, Unit: signal.Unit})
	}
	for _, computed := range engine.definition.ComputedMetrics {
		left, leftOK := numeric(values[computed.Inputs[0]])
		right, rightOK := numeric(values[computed.Inputs[1]])
		if leftOK && rightOK {
			value := left * right
			if computed.Scale != nil {
				value *= *computed.Scale
			}
			values[computed.Name] = value
			result = append(result, DecodedSignal{Name: computed.Name, Value: value, Unit: computed.Unit})
		}
	}
	return result
}

func decodeValue(signal Signal, data []byte) (any, error) {
	decoder := signal.Decoder
	if decoder.ByteOffset < 0 || decoder.ByteOffset >= len(data) {
		return nil, fmt.Errorf("offset exceeds CAN payload")
	}
	if decoder.DataType == "boolean" {
		if decoder.Bit < 0 || decoder.Bit > 7 {
			return nil, fmt.Errorf("invalid bit")
		}
		return data[decoder.ByteOffset]&(1<<decoder.Bit) != 0, nil
	}
	typeInfo, knownInteger := integerTypes[decoder.DataType]
	length, signed := typeInfo.length, typeInfo.signed
	if decoder.DataType == "bytes" {
		length, signed = decoder.Length, decoder.Signed
	}
	if !knownInteger && decoder.DataType != "bytes" || length <= 0 || decoder.ByteOffset+length > len(data) || length > 8 {
		return nil, fmt.Errorf("decoder slice exceeds CAN payload")
	}
	endianness := decoder.Endianness
	if endianness == "" {
		endianness = "big"
	}
	var raw uint64
	for index := 0; index < length; index++ {
		position := index
		if endianness == "little" {
			position = length - index - 1
		} else if endianness != "big" {
			return nil, fmt.Errorf("invalid endianness")
		}
		raw = (raw << 8) | uint64(data[decoder.ByteOffset+position])
	}
	if decoder.BitMask != nil {
		mask, err := integer(decoder.BitMask)
		if err != nil {
			return nil, err
		}
		raw &= mask
	}
	if decoder.Shift < 0 {
		return nil, fmt.Errorf("invalid shift")
	}
	raw >>= decoder.Shift
	var number float64
	if signed {
		bits := uint(length * 8)
		if raw&(uint64(1)<<(bits-1)) != 0 {
			number = float64(int64(raw | (^uint64(0) << bits)))
		} else {
			number = float64(raw)
		}
	} else {
		number = float64(raw)
	}
	if decoder.Enum != nil {
		if value, ok := decoder.Enum[strconv.FormatInt(int64(number), 10)]; ok {
			return value, nil
		}
		return fmt.Sprintf("unknown:%d", int64(number)), nil
	}
	scale, offset := 1.0, 0.0
	if decoder.Scale != nil {
		scale = *decoder.Scale
	}
	if decoder.Offset != nil {
		offset = *decoder.Offset
	}
	value := number*scale + offset
	if math.IsNaN(value) || math.IsInf(value, 0) || signal.Minimum != nil && value < *signal.Minimum || signal.Maximum != nil && value > *signal.Maximum {
		return nil, fmt.Errorf("decoded value outside safe bounds")
	}
	return value, nil
}

func integer(value any) (uint64, error) {
	switch typed := value.(type) {
	case int:
		return uint64(typed), nil
	case uint64:
		return typed, nil
	case float64:
		return uint64(typed), nil
	case string:
		return strconv.ParseUint(typed, 0, 64)
	default:
		return 0, fmt.Errorf("invalid integer %v", value)
	}
}

func numeric(value any) (float64, bool) {
	switch typed := value.(type) {
	case float64:
		return typed, true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	default:
		return 0, false
	}
}
