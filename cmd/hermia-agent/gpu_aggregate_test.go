package main

import (
	"testing"
)

func TestParseInstanceName(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected parsedInstance
	}{
		{
			name:     "Standard 3D engine",
			input:    "pid_4132_luid_0x00000000000A1234_phys_0_gpu_0_engtype_3D",
			expected: parsedInstance{physIdx: 0, gpuIdx: 0, engType: "3D"},
		},
		{
			name:     "Compute engine",
			input:    "pid_880_luid_0x00000000000A1234_phys_0_gpu_0_engtype_Compute",
			expected: parsedInstance{physIdx: 0, gpuIdx: 0, engType: "Compute"},
		},
		{
			name:     "Copy engine",
			input:    "pid_1024_luid_0x00000000000A1234_phys_0_gpu_0_engtype_Copy",
			expected: parsedInstance{physIdx: 0, gpuIdx: 0, engType: "Copy"},
		},
		{
			name:     "VideoDecode engine",
			input:    "pid_512_luid_0x00000000000A1234_phys_0_gpu_1_engtype_VideoDecode",
			expected: parsedInstance{physIdx: 0, gpuIdx: 1, engType: "VideoDecode"},
		},
		{
			name:     "VideoEncode engine",
			input:    "pid_512_luid_0x00000000000A1234_phys_0_gpu_2_engtype_VideoEncode",
			expected: parsedInstance{physIdx: 0, gpuIdx: 2, engType: "VideoEncode"},
		},
		{
			name:     "Unknown engine type",
			input:    "pid_512_luid_0x00000000000A1234_phys_0_gpu_0_engtype_Scheduler",
			expected: parsedInstance{physIdx: 0, gpuIdx: 0, engType: "Other"},
		},
		{
			name:     "Multi-GPU second physical",
			input:    "pid_4132_luid_0x00000000000B5678_phys_1_gpu_0_engtype_3D",
			expected: parsedInstance{physIdx: 1, gpuIdx: 0, engType: "3D"},
		},
		{
			name:     "Malformed no engtype",
			input:    "pid_4132_luid_0x00000000000A1234_phys_0_gpu_0",
			expected: parsedInstance{physIdx: 0, gpuIdx: 0, engType: "Other"},
		},
		{
			name:     "Engtype with trailing suffix (future-proofing against e.g. engtype_3D_v2)",
			input:    "pid_4132_luid_0x00000000000A1234_phys_0_gpu_0_engtype_3D_v2",
			expected: parsedInstance{physIdx: 0, gpuIdx: 0, engType: "3D"},
		},
		{
			name:     "Empty string",
			input:    "",
			expected: parsedInstance{physIdx: 0, gpuIdx: 0, engType: "Other"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := parseInstanceName(tt.input)
			if result.physIdx != tt.expected.physIdx {
				t.Errorf("physIdx = %v, want %v", result.physIdx, tt.expected.physIdx)
			}
			if result.gpuIdx != tt.expected.gpuIdx {
				t.Errorf("gpuIdx = %v, want %v", result.gpuIdx, tt.expected.gpuIdx)
			}
			if result.engType != tt.expected.engType {
				t.Errorf("engType = %q, want %q", result.engType, tt.expected.engType)
			}
		})
	}
}

func TestAggregateEngineCounters(t *testing.T) {
	const eps = 0.001

	tests := []struct {
		name     string
		samples  []pdhSample
		expected map[string]float64
	}{
		{
			// ROCm inference leaves 3D near zero; benchmark pegs it
			name: "Gaming state",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 93.6},
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_Compute", value: 0.0},
			},
			expected: map[string]float64{
				"3D":      93.6,
				"Compute": 0.0,
			},
		},
		{
			// ROCm registers as Compute, 3D stays flat
			name: "Inference state",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 0.1},
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_Compute", value: 1847300.0},
			},
			expected: map[string]float64{
				"3D":      0.1,
				"Compute": 1847300.0,
			},
		},
		{
			name: "Idle state",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 0.05},
			},
			expected: map[string]float64{
				"3D": 0.05,
			},
		},
		{
			name: "All-zeros",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 0.0},
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_Compute", value: 0.0},
			},
			expected: map[string]float64{
				"3D":      0.0,
				"Compute": 0.0,
			},
		},
		{
			name: "Missing 3D key",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_Compute", value: 10.0},
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_Copy", value: 20.0},
			},
			expected: map[string]float64{
				"Compute": 10.0,
				"Copy":    20.0,
			},
		},
		{
			name: "Multi-instance same engine summing",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 30.0},
				{instance: "pid_1_luid_0x1_phys_0_gpu_1_engtype_3D", value: 31.5},
				{instance: "pid_1_luid_0x1_phys_0_gpu_2_engtype_3D", value: 32.1},
			},
			expected: map[string]float64{
				"3D": 93.6,
			},
		},
		{
			// v1 sums globally across physical GPUs
			name: "Multi-GPU global sum",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 85.0},
				{instance: "pid_1_luid_0x1_phys_1_gpu_0_engtype_3D", value: 8.6},
			},
			expected: map[string]float64{
				"3D": 93.6,
			},
		},
		{
			name: "Gate boundary exactly 10.0",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 10.0},
			},
			expected: map[string]float64{"3D": 10.0},
		},
		{
			name: "Just over threshold",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 10.1},
			},
			expected: map[string]float64{"3D": 10.1},
		},
		{
			name: "Just under threshold",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_3D", value: 9.9},
			},
			expected: map[string]float64{"3D": 9.9},
		},
		{
			name: "Unknown engine type bucketed as Other",
			samples: []pdhSample{
				{instance: "pid_1_luid_0x1_phys_0_gpu_0_engtype_Scheduler", value: 5.0},
			},
			expected: map[string]float64{"Other": 5.0},
		},
		{
			name:     "Empty slice",
			samples:  []pdhSample{},
			expected: map[string]float64{},
		},
		{
			name:     "Nil slice",
			samples:  nil,
			expected: map[string]float64{},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := aggregateEngineCounters(tt.samples)
			for k, want := range tt.expected {
				got, exists := result[k]
				if !exists {
					t.Errorf("missing key %q in result", k)
					continue
				}
				if got < want-eps || got > want+eps {
					t.Errorf("key %q: got %v, want %v", k, got, want)
				}
			}
			for k, v := range result {
				if _, exists := tt.expected[k]; !exists {
					t.Errorf("unexpected key %q = %v in result", k, v)
				}
			}
		})
	}
}
